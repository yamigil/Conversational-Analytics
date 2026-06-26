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


@router.get("/api/gcp/projects")
def list_gcp_projects(x_gcp_user_token: Optional[str] = Header(None)):
    default_proj = get_project_id()
    # If in Service Account mode (no user token), return only the default project
    if not x_gcp_user_token:
        return [{"projectId": default_proj, "name": f"Default Project ({default_proj})"}]

    try:
        # Fetch accessible projects from GCP Resource Manager API using the user's token
        headers = {"Authorization": f"Bearer {x_gcp_user_token}"}
        url = "https://cloudresourcemanager.googleapis.com/v1/projects"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 401:
            logger.error("GCP Resource Manager API returned 401: Token expired or invalid.")
            raise HTTPException(status_code=401, detail="Google Cloud session expired. Please re-authenticate.")
            
        if response.status_code != 200:
            logger.error(f"Failed to list GCP projects: {response.status_code} - {response.text}")
            return [{"projectId": default_proj, "name": f"Default Project ({default_proj})"}]

        data = response.json()
        projects = data.get("projects", [])
        
        # Format the result list
        results = []
        for p in projects:
            if p.get("lifecycleState") == "ACTIVE":
                results.append({
                    "projectId": p.get("projectId"),
                    "name": p.get("name") or p.get("projectId")
                })
        
        # If empty, return at least the default project
        if not results:
            return [{"projectId": default_proj, "name": f"Default Project ({default_proj})"}]
            
        return results
    except Exception as e:
        logger.error(f"Error fetching GCP projects: {e}")
        return [{"projectId": default_proj, "name": f"Default Project ({default_proj})"}]
