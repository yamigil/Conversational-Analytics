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


@router.post("/api/telemetry/audit")
def audit_log(req: AuditLogModel, user: dict = Depends(get_current_user)):
    log_audit_to_firestore(
        user_email=user.get("email", "unknown"),
        event_type=req.event_type,
        details=req.details
    )
    return {"status": "success"}
