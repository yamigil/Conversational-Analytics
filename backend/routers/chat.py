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
from telemetry import log_chat_to_bigquery
import time

router = APIRouter()


@router.post("/api/chat")
def chat(req: ChatRequestModel, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        # Log query telemetry to BigQuery for all agents
        log_chat_to_bigquery(
            user_email=user.get("email", "unknown"),
            conversation_name=req.conversation_name,
            agent_name=req.agent_name,
            query=req.message_text
        )

        # Guide the model's reasoning behavior by appending instructions directly in the prompt
        guided_message = req.message_text
        if req.chat_mode == "thinking":
            guided_message += (
                "\n\n[System Instruction: Please think step-by-step. Write down your detailed reasoning, "
                "chain-of-thought, and analysis before generating the final SQL query or answer. Show your thinking process.]"
            )
        else:
            guided_message += (
                "\n\n[System Instruction: Please provide a fast, direct, and concise answer. Avoid long chain-of-thought "
                "explanations unless necessary.]"
            )

        def event_generator():
            try:
                generator = client.chat_stream(
                    conversation_name=req.conversation_name,
                    agent_name=req.agent_name,
                    message_text=guided_message,
                    looker_credentials=req.looker_credentials
                )
                for chunk in generator:
                    # Extract the inner message if wrapped in the API envelope (camelCase or snake_case)
                    if isinstance(chunk, dict):
                        if "message" in chunk:
                            chunk = chunk["message"]
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                logger.error(f"Error in chat stream generator: {e}")
                err_msg = str(e)
                if "ResourceExhausted" in err_msg or "429" in err_msg:
                    err_msg = "Google Cloud Gemini Quota exhausted. Please wait a moment and try again."
                else:
                    err_msg = f"API Error during response streaming: {err_msg}"
                yield f"data: {json.dumps({'systemMessage': {'error': {'message': err_msg}}})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        handle_route_exception(e, "stream chat responses")

