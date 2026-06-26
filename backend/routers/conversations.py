import os
import json
import logging
import requests
import re
from fastapi import APIRouter, HTTPException, Body, Depends, Header, Response, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from firebase_admin import firestore
from google.cloud import bigquery
from ca_client import ConversationalAnalyticsClient
from auth import get_current_user, get_analytics_client
from google.api_core import exceptions as google_exceptions
from schema_discovery import get_schema_summary
from bq_client import get_live_table_preview
from config import logger, get_project_id, DELETED_CONVOS_FILE, get_deleted_conversations, add_deleted_conversation, BRANDING_FILE
import time

router = APIRouter()


@router.post("/api/conversations")
def create_conversation(req: CreateConvoRequest, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        return client.create_conversation(req.agent_name)
    except Exception as e:
        handle_route_exception(e, "create conversation session")


@router.get("/api/conversations/{agent_name:path}")
def get_conversations(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        convos = client.list_conversations(agent_name)
        deleted = get_deleted_conversations()
        return [c for c in convos if c.get("name") not in deleted]
    except Exception as e:
        handle_route_exception(e, "list active conversations")


@router.get("/api/insights/{agent_name:path}")
def get_insights(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:

        convos = client.list_conversations(agent_name)
        deleted = get_deleted_conversations()
        active_convos = [c for c in convos if c.get("name") not in deleted]
        
        if not active_convos:
            return {
                "summary": "No recent interactions found for this agent.",
                "insights": []
            }
            
        most_recent_convo = active_convos[0]
        msgs = client.list_messages(most_recent_convo["name"])
        
        insights = []
        for msg in reversed(msgs):
            if "systemMessage" in msg:
                sys_msg = msg["systemMessage"]
                if "text" in sys_msg and "parts" in sys_msg["text"]:
                    text = "".join(sys_msg["text"]["parts"])
                    lines = text.split("\n")
                    for line in lines:
                        cleaned = line.strip()
                        if cleaned.startswith("- ") or cleaned.startswith("* ") or cleaned.startswith("• "):
                            insight_text = cleaned.lstrip("-*• ").replace("**", "")
                            if len(insight_text) > 10 and insight_text not in insights:
                                insights.append(insight_text)
                                if len(insights) >= 4:
                                    break
                if len(insights) >= 4:
                    break
                    
        if len(insights) < 2:
            for msg in reversed(msgs):
                if "systemMessage" in msg:
                    sys_msg = msg["systemMessage"]
                    if "data" in sys_msg and "result" in sys_msg["data"]:
                        res = sys_msg["data"]["result"]
                        name = res.get("name", "Query Result")
                        data_list = res.get("data", [])
                        if data_list:
                            first_row = data_list[0]
                            kv_pairs = [f"{k}: {v}" for k, v in first_row.items()]
                            insights.append(f"Retrieved {name} details - First record: {', '.join(kv_pairs)}")
                            if len(insights) >= 4:
                                break

        if not insights:
            return {
                "summary": "Active session initialized. Awaiting database analytical queries to summarize findings.",
                "insights": [
                    "Select an agent and ask a question to generate automatic insights.",
                    "Conversational analytics can summarize total revenue, sales metrics, and product metrics dynamically.",
                    "Try launching the Chat Workspace and query: 'Show me total sales for May 2026.'"
                ]
            }
            
        return {
            "summary": f"Executive summary compiled from latest conversation session ({most_recent_convo['name'].split('/')[-1][:8]}...):",
            "insights": insights[:4]
        }
    except Exception as e:
        logger.error(f"Error compiling insights: {e}")
        return {
            "summary": "Error generating insights.",
            "insights": ["Failed to load recent analytics history."]
        }


@router.delete("/api/conversations/{convo_name:path}")
def delete_conversation(convo_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        # 1. Real deletion from Conversational Analytics server
        client.delete_conversation(convo_name)
        # 2. Local cache soft-deletion marker
        add_deleted_conversation(convo_name)
        return {"status": "success", "message": f"Conversation {convo_name} deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting conversation {convo_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation.")



@router.get("/api/messages/{convo_name:path}")
def get_messages(convo_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:

        if convo_name in get_deleted_conversations():
            raise HTTPException(status_code=404, detail="Conversation has been deleted")
        return client.list_messages(convo_name)
    except HTTPException:
        raise
    except Exception as e:
        handle_route_exception(e, "retrieve conversation history")

