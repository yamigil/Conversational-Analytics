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
from models import *
from google.api_core import exceptions as google_exceptions

from bq_client import get_live_table_preview
from config import logger, get_project_id, DELETED_CONVOS_FILE, get_deleted_conversations, add_deleted_conversation, BRANDING_FILE
import time
from schema_discovery import enrich_agent_metadata

router = APIRouter()


@router.get("/api/agents")
def get_agents(user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        agents = client.list_agents()
        

            
        enriched = [enrich_agent_metadata(agent, skip_db_scan=True) for agent in agents]
        return enriched
    except Exception as e:
        handle_route_exception(e, "list data agents")


@router.get("/api/agents/{agent_name:path}/schema")
def get_agent_schema(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        logger.info(f"On-Demand Schema Request received for agent: {agent_name}")
        agent = client.get_agent(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
            
        enriched = enrich_agent_metadata(agent, skip_db_scan=False)
        return enriched
    except Exception as e:
        handle_route_exception(e, "load agent schema details")



def generate_record_suggestions(table_name: str, rows: list) -> list:
    """Uses Gemini to dynamically generate 3 personalized, context-aware business questions
    for each specific record row in the preview data.
    """
    if not rows:
        return []
        
    from gemini_client import call_gemini
    
    system_instruction = (
        "You are an expert database analyst. Generate highly-personalized, context-aware, and domain-specific "
        "business query suggestions (query starters) for specific database record instances. "
        "You will be provided with a table name and a list of specific record rows. "
        "For each record row, generate exactly 3 suggested questions. "
        "CRITICAL: The questions MUST be highly personalized to the specific record. You MUST explicitly reference "
        "the actual values of the columns in the questions (e.g., use the actual name, ID, category, or status in the text) "
        "so the user feels the questions are written specifically for that record. "
        "The questions should ask about the record's connections, history, aggregations, or details. "
        "\nReturn the result ONLY as a raw JSON array of lists, where each list contains exactly 3 questions corresponding to the row index. "
        "Do not include any markdown formatting or backticks in your response. Example output format:\n"
        "[\n"
        "  [\"Question 1 for Row 0?\", \"Question 2 for Row 0?\", \"Question 3 for Row 0?\"],\n"
        "  [\"Question 1 for Row 1?\", \"Question 2 for Row 1?\", \"Question 3 for Row 1?\"]\n"
        "]"
    )
    
    prompt = (
        f"Table Name: {table_name}\n"
        f"Records (Rows):\n{json.dumps(rows, indent=2)}\n"
    )
    
    try:
        raw_json = call_gemini(prompt, system_instruction, response_mime_type="application/json", temperature=0.3)
        if raw_json:
            cleaned = raw_json.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, list) and len(parsed) == len(rows):
                logger.info(f"Successfully generated custom record suggestions via Gemini for {len(rows)} rows of table '{table_name}'")
                return parsed
    except Exception as ex:
        logger.warning(f"Gemini API fallback for record suggestions on table '{table_name}' ({ex}). Using dynamic row-aware fallbacks.")
    
    # Robust high-fidelity domain-aware fallback if Gemini rate limit (429) is encountered or cache is warming
    fallback_suggestions = []
    for r in rows:
        if not isinstance(r, dict) or not r:
            fallback_suggestions.append([
                f"What is the historical trend and distribution for records in table {table_name}?",
                f"Show me all related metrics and connected graph nodes for {table_name}.",
                f"Count the total records in {table_name} grouped by status or category."
            ])
            continue
        # Pick the most meaningful identifier column from the row (id, name, title, code, uuid, or first string)
        id_key = next((k for k in r.keys() if any(term in k.lower() for term in ["id", "name", "code", "title", "sku", "vin", "email"])), list(r.keys())[0])
        val = str(r.get(id_key, "this record"))[:30]
        fallback_suggestions.append([
            f"What is the complete historical activity and metrics for {id_key} '{val}' in {table_name}?",
            f"List all related transactions, connected graph entities, and details linked to '{val}'.",
            f"Compare {id_key} '{val}' against other top records in {table_name} by volume or spend."
        ])
    return fallback_suggestions


_TABLE_PREVIEW_CACHE = {}

@router.get("/api/preview")
def get_table_preview(
    table_name: str,
    agent_name: Optional[str] = None,
    x_gcp_user_token: Optional[str] = Header(None),
    user: dict = Depends(get_current_user),
    client: ConversationalAnalyticsClient = Depends(get_analytics_client)
):
    # 1. Resolve table and dataset names dynamically
    clean_name = table_name.split(".")[-1] if "." in table_name else table_name
    
    dataset_id = None
    project_id = None
    if agent_name:
        try:
            # Fetch agent metadata to find the connected dataset ID and project ID dynamically
            agent = client.get_agent(agent_name)
            da_agent = agent.get("dataAnalyticsAgent", {})
            for context_key in ["publishedContext", "lastPublishedContext", "stagingContext"]:
                context = da_agent.get(context_key, {})
                ds_refs = context.get("datasourceReferences", {})
                bq_ref = ds_refs.get("bq", {})
                table_refs = bq_ref.get("tableReferences", [])
                for t in table_refs:
                    ref_table = t.get("tableId", "")
                    if ref_table == clean_name or t.get("tableId", "").split(".")[-1] == clean_name:
                        dataset_id = t.get("datasetId")
                        project_id = t.get("projectId")
                        break
                if dataset_id:
                    break
            
            # If still not found, check if it is a Graph Agent using dynamic binding!
            if not dataset_id:
                from schema_discovery import enrich_agent_metadata
                enriched_agent = enrich_agent_metadata(agent)
                if enriched_agent.get("isGraphAgent") and "graphData" in enriched_agent:
                    graph_data = enriched_agent["graphData"]
                    if "datasetId" in graph_data:
                        dataset_id = graph_data["datasetId"]
                        project_id = graph_data.get("projectId")
                        logger.info(f"Resolved dataset '{dataset_id}' for graph node preview of table '{clean_name}'")
        except Exception as e:
            logger.warning(f"Could not resolve dataset_id from agent metadata: {e}")
            
    # 2. Fallback to extracting dataset ID from input table string if present
    if not dataset_id and "." in table_name:
        parts = table_name.split(".")
        if len(parts) == 3:
            project_id = parts[0]
            dataset_id = parts[1]
        elif len(parts) == 2:
            dataset_id = parts[0]
            
    if not project_id:
        project_id = get_project_id()
        
    if not dataset_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Could not resolve dataset context for table '{table_name}'. Please ensure agent_name is specified."
        )

    cache_key = (project_id, dataset_id, clean_name)
    if cache_key in _TABLE_PREVIEW_CACHE:
        logger.info(f"Returning cached preview and suggestions for {project_id}.{dataset_id}.{clean_name} (cache hit!)")
        return _TABLE_PREVIEW_CACHE[cache_key]
        
    # 3. Call our clean, modular live BigQuery preview function (timeout-enforced, 100% live!)
    preview_data = get_live_table_preview(project_id, dataset_id, clean_name, user_token=x_gcp_user_token)
    
    # 4. Generate AI-powered record suggestions in the background/inline
    if isinstance(preview_data, dict) and "rows" in preview_data:
        rows = preview_data["rows"]
        # Limit to first 3 rows (since the frontend only renders up to 3 satellites)
        target_rows = rows[:3]
        suggestions = generate_record_suggestions(clean_name, target_rows)
        # Pad with empty lists if there are more rows in the preview than target_rows
        preview_data["recordSuggestions"] = suggestions + [[] for _ in range(len(rows) - len(suggestions))]
        
    _TABLE_PREVIEW_CACHE[cache_key] = preview_data
    return preview_data

