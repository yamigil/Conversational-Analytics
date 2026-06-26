import os
import json
import logging
import requests
import re
from fastapi import FastAPI, HTTPException, Body, Depends, Header, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# Telemetry imports
from datetime import datetime, timezone
from firebase_admin import firestore
from google.cloud import bigquery

from ca_client import ConversationalAnalyticsClient
from auth import get_current_user
from google.api_core import exceptions as google_exceptions

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ca-web-app")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up schema discovery caches in a background thread to prevent blocking startup
    import threading
    def warmup():
        try:
            logger.info("Warming up schema discovery caches in the background...")
            from schema_discovery import discover_project_graphs, discover_bq_graph_schema
            project_id = get_project_id()
            if project_id:
                graphs = discover_project_graphs(project_id)
                for g in graphs:
                    discover_bq_graph_schema(project_id, g["dataset_id"])
                logger.info("Schema discovery caches successfully warmed up!")
            else:
                logger.warning("No default GCP project found; skipping cache warmup.")
        except Exception as e:
            logger.warning(f"Failed background cache warmup: {e}")

    threading.Thread(target=warmup, daemon=True).start()
    yield

app = FastAPI(title="Conversational Analytics Showcase", lifespan=lifespan)


# Enable CORS with security hardening
from urllib.parse import urlparse
import socket

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # Prevent accessing localhost and local metadata services
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False
            
        # Resolve hostname to verify destination IP range
        ip = socket.gethostbyname(hostname)
        ip_parts = [int(x) for x in ip.split(".")]
        
        # Check private ranges
        if ip_parts[0] == 10:  # 10.0.0.0/8
            return False
        if ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31:  # 172.16.0.0/12
            return False
        if ip_parts[0] == 192 and ip_parts[1] == 168:  # 192.168.0.0/16
            return False
        if ip_parts[0] == 127:  # Loopback
            return False
        if ip_parts[0] == 169 and ip_parts[1] == 254:  # link-local / metadata server (169.254.169.254)
            return False
            
        return True
    except Exception:
        return False

# Load allowed origins from environment
allowed_origins = ["*"]
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

is_wildcard = (len(allowed_origins) == 1 and allowed_origins[0] == "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not is_wildcard,  # Forbidden to set True with wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard security headers middleware

from routers import gcp, agents, conversations, chat, branding, telemetry

app.include_router(gcp.router)
app.include_router(agents.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(branding.router)
app.include_router(telemetry.router)

