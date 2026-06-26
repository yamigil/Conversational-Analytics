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
            
        from schema_discovery import enrich_agent_metadata
        enriched = enrich_agent_metadata(agent, skip_db_scan=False)
        return enriched
    except Exception as e:
        handle_route_exception(e, "load agent schema details")



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
        
    # 3. Call our clean, modular live BigQuery preview function (timeout-enforced, 100% live!)
    return get_live_table_preview(project_id, dataset_id, clean_name, user_token=x_gcp_user_token)

