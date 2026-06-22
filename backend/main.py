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

app = FastAPI(title="Conversational Analytics Showcase")

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
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Telemetry Pydantic models & helpers
class AuditLogModel(BaseModel):
    event_type: str
    details: Optional[dict] = {}

def log_audit_to_firestore(user_email: str, event_type: str, details: dict):
    try:
        db = firestore.client()
        doc_ref = db.collection("audit_logs").document()
        doc_ref.set({
            "timestamp": datetime.now(timezone.utc),
            "user_email": user_email,
            "event_type": event_type,
            "details": details
        })
        logger.info(f"Logged audit event to Firestore: {event_type}")
    except Exception as e:
        logger.error(f"Failed to log audit event to Firestore: {e}")

def log_chat_to_bigquery(user_email: str, conversation_name: str, agent_name: str, query: str):
    try:
        bq_client = bigquery.Client()
        project_id = get_project_id()
        dataset_id = f"{project_id}.telemetry"
        table_id = f"{dataset_id}.chat_logs"
        
        # Self-healing dataset check
        try:
            bq_client.get_dataset(dataset_id)
        except Exception:
            from google.cloud.bigquery import Dataset
            dataset = Dataset(dataset_id)
            dataset.location = "us-central1"
            bq_client.create_dataset(dataset)
            logger.info(f"Created BigQuery telemetry dataset: {dataset_id}")
            
        # Self-healing table check
        try:
            bq_client.get_table(table_id)
        except Exception:
            from google.cloud.bigquery import Table, SchemaField
            schema = [
                SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                SchemaField("user_email", "STRING", mode="REQUIRED"),
                SchemaField("conversation_id", "STRING", mode="REQUIRED"),
                SchemaField("agent_name", "STRING", mode="REQUIRED"),
                SchemaField("query", "STRING", mode="REQUIRED"),
            ]
            table = Table(table_id, schema=schema)
            bq_client.create_table(table)
            logger.info(f"Created BigQuery telemetry table: {table_id}")
            
        # Stream insert row
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_email": user_email,
            "conversation_id": conversation_name,
            "agent_name": agent_name,
            "query": query,
        }
        errors = bq_client.insert_rows_json(table_id, [row])
        if errors:
            logger.error(f"BigQuery streaming insert errors: {errors}")
        else:
            logger.info(f"Logged chat event to BigQuery: {query[:50]}...")
    except Exception as e:
        logger.error(f"Failed to log chat to BigQuery: {e}")

# Helper to find GCP Project ID for Analytics Agents
def get_project_id() -> str:
    # 1. First, check if a project ID is defined inside the branding.json settings!
    if os.path.exists(BRANDING_FILE):
        try:
            with open(BRANDING_FILE, "r") as f:
                branding_data = json.load(f)
                active_brand = branding_data.get("activeBrand", "default")
                brand_settings = branding_data.get("brands", {}).get(active_brand, {})
                project_id = brand_settings.get("gcpProjectId")
                if project_id:
                    logger.info(f"Loaded GCP Project ID from branding settings: {project_id}")
                    return project_id
        except Exception as e:
            logger.warning(f"Could not load project_id from branding settings: {e}")

    # 2. Explicitly configured GCP Analytics Project in env/.env
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if project_id:
        logger.info(f"Loaded GCP Analytics Project ID: {project_id}")
        return project_id

    # 3. Resolve dynamically using google.auth.default
    try:
        import google.auth
        _, auth_project = google.auth.default()
        if auth_project:
            logger.info(f"Loaded GCP Project ID dynamically from auth context: {auth_project}")
            return auth_project
    except Exception as e:
        logger.warning(f"Could not resolve project ID via google.auth.default: {e}")

    # 4. Try loading from Streamlit secrets file of quickstarts if present
    quickstart_secrets = os.path.expanduser("~/Documents/Google/Conversational_Analytics/ca-api-quickstarts/.streamlit/secrets.toml")
    if os.path.exists(quickstart_secrets):
        try:
            import toml
            secrets = toml.load(quickstart_secrets)
            project_id = secrets.get("cloud", {}).get("project_id")
            if project_id:
                logger.info(f"Loaded Project ID from quickstart secrets: {project_id}")
                return project_id
        except Exception as e:
            logger.warning(f"Could not load project_id from quickstart secrets: {e}")

    # Fallback default (reverting to YamiArcade project where the agents are created)
    logger.warning("No project ID found, using default YamiArcade fallback.")
    return "studio-8562875242-77194"

# Helper to find GCP Location/Region for Analytics Agents
def get_location() -> str:
    # 1. First, check if a location is defined inside the branding.json settings!
    if os.path.exists(BRANDING_FILE):
        try:
            with open(BRANDING_FILE, "r") as f:
                branding_data = json.load(f)
                active_brand = branding_data.get("activeBrand", "default")
                brand_settings = branding_data.get("brands", {}).get(active_brand, {})
                location = brand_settings.get("gcpLocation")
                if location:
                    logger.info(f"Loaded GCP Location from branding settings: {location}")
                    return location
        except Exception as e:
            logger.warning(f"Could not load location from branding settings: {e}")

    # 2. Explicitly configured in env/.env or default
    return os.getenv("GCP_LOCATION") or "all"

# Dynamic client injection dependency based on GCP OAuth Access Token, Project ID & Location
def get_analytics_client(
    x_gcp_user_token: Optional[str] = Header(None),
    x_gcp_project_id: Optional[str] = Header(None),
    x_gcp_location: Optional[str] = Header(None)
) -> ConversationalAnalyticsClient:
    target_project = x_gcp_project_id or get_project_id()
    target_location = x_gcp_location or get_location()
    
    if x_gcp_user_token:
        try:
            logger.info(f"Initializing ConversationalAnalyticsClient using End-User SSO Credentials for project: {target_project}, location: {target_location}")
            return ConversationalAnalyticsClient(target_project, user_token=x_gcp_user_token, location=target_location)
        except Exception as e:
            logger.error(f"Failed to initialize ConversationalAnalyticsClient with user token: {e}. Falling back to Service Account.")
    
    # If a custom project or location is requested in Service Account mode, try to instantiate it. Otherwise fallback.
    default_project = get_project_id()
    default_location = get_location()
    if target_project != default_project or target_location != default_location:
        try:
            return ConversationalAnalyticsClient(target_project, location=target_location)
        except Exception as e:
            logger.error(f"Failed to initialize Service Account client for project {target_project}, location {target_location}: {e}")
    # Always return a client for the freshly resolved default project and location
    return ConversationalAnalyticsClient(default_project, location=default_location)

# Pydantic models for request bodies
class CreateConvoRequest(BaseModel):
    agent_name: str

class GenerateBrandingRequest(BaseModel):
    prompt: str
    logo_image: Optional[str] = None
    logo_mime_type: Optional[str] = None
    logo_svg_content: Optional[str] = None
    logo_url: Optional[str] = None

class GenerateGreetingRequest(BaseModel):
    brand_name: str

class ChatRequestModel(BaseModel):
    conversation_name: str
    agent_name: str
    message_text: str
    looker_credentials: Optional[dict] = None
    chat_mode: Optional[str] = "fast"

# Resolve the branding file location (checked in priority: public -> dist -> root)
BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/public/branding.json"))
if not os.path.exists(BRANDING_FILE):
    BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist/branding.json"))
    if not os.path.exists(BRANDING_FILE):
        BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/branding.json"))

# Serve compiled files if they exist, otherwise serve raw project (for local development)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist"))
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))

# Local database for deleted conversations (simulating deletion since backend API client lacks it)
DELETED_CONVOS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "deleted_conversations.json"))

def get_deleted_conversations() -> set:
    if os.path.exists(DELETED_CONVOS_FILE):
        try:
            with open(DELETED_CONVOS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logger.error(f"Error reading deleted conversations file: {e}")
    return set()

def add_deleted_conversation(convo_name: str):
    deleted = get_deleted_conversations()
    deleted.add(convo_name)
    try:
        with open(DELETED_CONVOS_FILE, "w") as f:
            json.dump(list(deleted), f, indent=2)
    except Exception as e:
        logger.error(f"Error writing deleted conversations file: {e}")

def enrich_agent_metadata(agent: dict) -> dict:
    """Enriches a data agent with dynamically generated suggested questions and welcome subtitles."""
    display_name = agent.get("displayName", "Data Agent")
    description = agent.get("description", "")
    
    # 1. Safely locate system instructions and table references
    system_instruction = ""
    tables = []
    da_agent = agent.get("dataAnalyticsAgent", {})
    
    # Scan through staging, published, or lastPublished contexts to extract information
    for context_key in ["publishedContext", "lastPublishedContext", "stagingContext"]:
        context = da_agent.get(context_key, {})
        if not system_instruction and context.get("systemInstruction"):
            system_instruction = context["systemInstruction"]
        
        # Discover connected tables
        ds_refs = context.get("datasourceReferences", {})
        bq_ref = ds_refs.get("bq", {})
        table_refs = bq_ref.get("tableReferences", [])
        for t in table_refs:
            dataset = t.get("datasetId", "")
            table = t.get("tableId", "")
            if dataset and table:
                table_str = f"{dataset}.{table}"
                if table_str not in tables:
                    tables.append(table_str)
                    
    # 2. Extract suggested queries directly from the agent's system prompt (instructions)
    suggestions = []
    if system_instruction:
        # Match questions ending in ? inside quotes (single or double)
        matches = re.findall(r'["\']([^"\']+\?)["\']', system_instruction)
        for m in matches:
            m_clean = m.strip()
            # Basic validation: reasonable length, not SQL fragments, ends with ?
            if 15 < len(m_clean) < 120 and "?" in m_clean:
                if not any(k in m_clean.upper() for k in ["SELECT", "FROM", "WHERE", "WITH", "LIMIT"]):
                    # Clean up markdown formatting if any
                    m_clean = re.sub(r'[\*\`\_]', '', m_clean)
                    suggestions.append(m_clean)
                    
    # Remove duplicates while preserving order
    unique_suggestions = []
    for s in suggestions:
        if s not in unique_suggestions:
            unique_suggestions.append(s)
    suggestions = unique_suggestions[:3]
    
    # 3. Fallback: Generate custom queries based on discovered BigQuery tables
    if len(suggestions) < 3 and tables:
        primary_table = tables[0]
        table_suggestions = [
            f"Can you give me a summary of the data in the {primary_table} table?",
            f"What are the key metrics and columns available in {primary_table}?",
            f"Show me the top 10 most recent records from {primary_table}."
        ]
        for ts in table_suggestions:
            if ts not in suggestions:
                suggestions.append(ts)
        suggestions = suggestions[:3]
        
    # 4. Double Fallback: Brand-based default presets
    if not suggestions:
        name_lower = display_name.lower()
        if "marketing" in name_lower or "ga4" in name_lower:
            suggestions = [
                "What are the top 10 best-selling product categories by total sales revenue?",
                "How does our monthly order volume compare across different countries?",
                "Can we see the distribution of users by traffic source and country?"
            ]
        else:
            suggestions = [
                "Show me the monthly trend of cost and revenue for this year.",
                "What are the top 5 brands by number of items sold?",
                "What is the average order value (AOV) for each month?"
            ]
            
    # 5. Generate a beautiful, custom welcome subtitle based on the agent's tables or description
    welcome_subtitle = description
    if not welcome_subtitle:
        if tables:
            welcome_subtitle = f"Ask any analytical question about your connected data tables (including {', '.join(tables[:2])})."
        else:
            welcome_subtitle = "Ask any analytical question about your business data, cost trends, or performance."
            
    # Inject metadata properties into the agent dict returned to the UI
    agent["suggestions"] = suggestions
    agent["welcomeSubtitle"] = welcome_subtitle
    return agent

# API Routes
@app.get("/api/gcp/projects")
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

@app.get("/api/agents")
def get_agents(user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        agents = client.list_agents()
        return [enrich_agent_metadata(agent) for agent in agents]
    except google_exceptions.Unauthenticated as e:
        logger.error(f"GCP Unauthenticated: {e}")
        raise HTTPException(status_code=401, detail="Google Cloud session expired. Please re-authenticate.")
    except google_exceptions.PermissionDenied as e:
        logger.error(f"GCP Permission Denied: {e}")
        raise HTTPException(status_code=403, detail="Permission denied. Your account does not have the required Discovery Engine Viewer or Gemini Data Analytics User IAM roles in this project.")
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list data agents. Please verify your connection settings.")

@app.post("/api/conversations")
def create_conversation(req: CreateConvoRequest, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        return client.create_conversation(req.agent_name)
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation session.")

@app.get("/api/conversations/{agent_name:path}")
def get_conversations(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        convos = client.list_conversations(agent_name)
        deleted = get_deleted_conversations()
        return [c for c in convos if c.get("name") not in deleted]
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list active conversations.")

@app.get("/api/insights/{agent_name:path}")
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

@app.delete("/api/conversations/{convo_name:path}")
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


@app.get("/api/messages/{convo_name:path}")
def get_messages(convo_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        if convo_name in get_deleted_conversations():
            raise HTTPException(status_code=404, detail="Conversation has been deleted")
        return client.list_messages(convo_name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation history.")

@app.post("/api/chat")
def chat(req: ChatRequestModel, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        # Log query telemetry to BigQuery
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
            generator = client.chat_stream(
                conversation_name=req.conversation_name,
                agent_name=req.agent_name,
                message_text=guided_message,
                looker_credentials=req.looker_credentials
            )
            for chunk in generator:
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error streaming chat: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while streaming chat responses.")


@app.post("/api/branding/generate")
def generate_branding(req: GenerateBrandingRequest, user: dict = Depends(get_current_user)):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    import re

    system_instruction = (
        "You are a branding assistant. Generate a beautiful, professional, and matching dark-mode "
        "visual theme configuration for a company data portal based on the user's prompt and any uploaded logo icon. "
        "If a logo icon is uploaded (as a base64 image or SVG text): "
        "1. Identify its style and brand colors. "
        "2. If it is an SVG logo, analyze the SVG structure and modify/change the color values inside the SVG path/shape elements to match the new brand color theme (e.g., use the generated primary/secondary brand colors, or 'currentColor' for paths). Return this modified SVG as the 'logoSvg' field. "
        "3. If it is a raster image, suggest brand colors that beautifully match the logo's theme, and generate a clean, modern, minimalist SVG vector representation of the logo/concept and return it in 'logoSvg'. "
        "4. Generate a warm, customized data analytics greetings message (welcomeMessage) based on the brand/company name. "
        "\nReturn the result ONLY as a raw JSON object containing these exact fields:\n"
        "- name: The clear display name of the company\n"
        "- primaryColor: A beautiful HSL color matching the company's brand identity, formatted as 'H, S%, L%'\n"
        "- secondaryColor: A matching secondary/accent HSL color, formatted as 'H, S%, L%'\n"
        "- backgroundColorStart: A dark-theme background gradient start color hex code (e.g. #0a0b12)\n"
        "- backgroundColorEnd: A dark-theme background gradient end color hex code (e.g. #121522)\n"
        "- logoText: Logo text in upper case (e.g. COCA-COLA)\n"
        "- welcomeMessage: A warm, customized data analytics greetings message (e.g. Welcome to Coca-Cola Analytics. Ask me about sales volume...)\n"
        "- logoSvg: The SVG code representing the logo. If the user uploaded an SVG, this must be the modified/changed-color SVG. Otherwise, it should be a generated vector logo matching the brand concept, styled with fill/stroke to match the primary/secondary colors."
    )

    try:
        if req.logo_url and not req.logo_image:
            if not is_safe_url(req.logo_url):
                logger.warning(f"SSRF Prevention: Blocked unsafe logo URL download request: {req.logo_url}")
            else:
                try:
                    import requests
                    import base64
                    img_resp = requests.get(req.logo_url, timeout=5)
                    if img_resp.status_code == 200:
                        req.logo_image = base64.b64encode(img_resp.content).decode("utf-8")
                        content_type = img_resp.headers.get("Content-Type")
                        if content_type:
                            req.logo_mime_type = content_type.split(";")[0]
                except Exception as ex:
                    logger.warning(f"Failed to fetch logo from URL {req.logo_url} for theme generation: {ex}")


        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/gemini-1.5-flash:generateContent"
        
        prompt_text = f"Generate a theme configuration for: {req.prompt}"
        if req.logo_svg_content:
            prompt_text += f"\n\nHere is the XML content of the logo SVG uploaded by the user. Modify its color attributes (such as fill, stroke, class, or styles) to match the new color palette, or use 'currentColor' for paths so it integrates cleanly:\n{req.logo_svg_content}"
        
        parts = [{"text": prompt_text}]
        
        if req.logo_image and not req.logo_svg_content:
            base64_data = req.logo_image
            if "," in base64_data:
                base64_data = base64_data.split(",")[1]
            parts.append({
                "inlineData": {
                    "mimeType": req.logo_mime_type or "image/png",
                    "data": base64_data
                }
            })
            
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if candidates:
                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_content:
                    parsed = json.loads(text_content.strip())
                    logger.info(f"Successfully generated branding with Gemini: {parsed['name']}")
                    return parsed

        logger.warning(f"Vertex AI API returned status {resp.status_code}. Falling back to rules-based generator.")
        raise Exception(f"API status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error calling Vertex AI API: {e}. Executing rules-based fallback generator.")
        
        clean_prompt = req.prompt.lower()
        
        # Extract brand name
        brand_name = req.prompt
        for prefix in ["create a theme for", "branding for", "theme for", "a theme for", "for", "generate a theme for", "generate theme for"]:
            if clean_prompt.startswith(prefix):
                brand_name = req.prompt[len(prefix):].strip()
                break
                
        brand_name = re.sub(r'^[^\w]+|[^\w]+$', '', brand_name).strip()
        if not brand_name:
            brand_name = "Custom Brand"
        else:
            brand_name = brand_name.title()
            
        # Match keywords
        if any(k in clean_prompt for k in ["coca-cola", "coca cola", "coke", "red"]):
            primary = "358, 100%, 47%"
            secondary = "0, 0%, 100%"
            bg_start = "#1a0002"
            bg_end = "#0d0001"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Ask me about retail volume, advertising conversion, or carbonation levels!"
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-red-600 fill-current'>"
                "<path d='M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z'/>"
                "<path d='M12 2v20'/>"
                "<path d='M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["john deere", "deere", "green", "farm", "tractor", "rustic"]):
            primary = "120, 100%, 25%"
            secondary = "48, 100%, 50%"
            bg_start = "#051205"
            bg_end = "#020802"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Let's analyze crop yields, equipment status, and parts distribution."
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-emerald-500'>"
                "<path d='M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z'/>"
                "<path d='M12 6v6l4 2'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["coffee", "starbucks", "cafe", "brew"]):
            primary = "155, 100%, 19%"
            secondary = "36, 44%, 60%"
            bg_start = "#030f0a"
            bg_end = "#010503"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. How can I help you query bean inventory and store metrics?"
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-emerald-700'>"
                "<path d='M18 8h1a4 4 0 0 1 0 8h-1'/>"
                "<path d='M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z'/>"
                "<line x1='6' y1='1' x2='6' y2='4'/>"
                "<line x1='10' y1='1' x2='10' y2='4'/>"
                "<line x1='14' y1='1' x2='14' y2='4'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["home depot", "depot", "orange", "construction", "builder"]):
            primary = "23, 100%, 50%"
            secondary = "0, 0%, 100%"
            bg_start = "#1c0d02"
            bg_end = "#0d0601"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Let's analyze tool rentals, lumber prices, and regional warehouse stock."
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-orange-500 fill-current'>"
                "<rect x='2' y='2' width='20' height='20' rx='3' />"
                "<text x='12' y='15' fill='white' font-size='9' font-weight='bold' font-family='sans-serif' text-anchor='middle'>HD</text>"
                "</svg>"
            )
        else:
            brand_hash = sum(ord(c) for c in brand_name)
            hue = brand_hash % 360
            primary = f"{hue}, 85%, 60%"
            secondary = f"{(hue + 180) % 360}, 85%, 55%"
            bg_start = "#0e0c14" if hue > 180 else "#0b0f13"
            bg_end = "#07060a" if hue > 180 else "#05080a"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics Workspace. Ask me anything about your analytics and data queries."
            if req.logo_url:
                logo_svg = f'<img src="{req.logo_url}" alt="{brand_name}" class="w-full h-full object-contain" />'
            else:
                logo_svg = (
                    "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-indigo-400'>"
                    "<polygon points='12 2 2 7 12 12 22 7 12 2'/>"
                    "<polyline points='2 17 12 22 22 17'/>"
                    "<polyline points='2 12 12 17 22 12'/>"
                    "</svg>"
                )
            
        if req.logo_url:
            logo_svg = f'<img src="{req.logo_url}" alt="{brand_name}" class="w-full h-full object-contain" />'
            
        return {
            "name": brand_name,
            "primaryColor": primary,
            "secondaryColor": secondary,
            "backgroundColorStart": bg_start,
            "backgroundColorEnd": bg_end,
            "logoText": logo_text,
            "welcomeMessage": welcome,
            "logoSvg": logo_svg
        }

@app.post("/api/branding/generate-greeting")
def generate_greeting(req: GenerateGreetingRequest, user: dict = Depends(get_current_user)):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    
    system_instruction = (
        "You are a branding assistant. Write a single, warm, professional, and customized data analytics greeting/welcome message "
        "for a company data portal of the brand provided. The message should greet users and suggest typical metrics/questions they "
        "can ask about (e.g. sales, inventory, store performance, etc.). Keep the message concise, under 25 words."
    )
    
    try:
        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/gemini-1.5-flash:generateContent"
        
        payload = {
            "contents": [{"parts": [{"text": f"Write a greeting for the brand: {req.brand_name}"}]}],
            "generationConfig": {
                "temperature": 0.5
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if candidates:
                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_content:
                    return {"welcomeMessage": text_content.strip()}
                    
        raise Exception(f"API status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error calling Gemini for greeting generation: {e}")
        return {
            "welcomeMessage": f"Welcome to {req.brand_name} Analytics. Ask me about sales volume, inventory, or performance metrics."
        }

@app.get("/api/branding/search-logo")
def search_logo(query: str, user: dict = Depends(get_current_user)):
    results = []
    clean_query = query.strip()
    if not clean_query:
        return results

    # 1. Speculative Domain Matching (helps find logos of custom/niche brands)
    if "." in clean_query:
        domain = clean_query.lower()
        results.append({
            "title": f"Domain: {domain}",
            "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={domain}&sz=128&default=404",
            "source": "Website Match"
        })
    else:
        spaced_removed = clean_query.replace(" ", "").lower()
        results.append({
            "title": f"Speculative: {spaced_removed}.com",
            "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={spaced_removed}.com&sz=128&default=404",
            "source": "Website Match"
        })
        if " " in clean_query:
            hyphenated = clean_query.replace(" ", "-").lower()
            results.append({
                "title": f"Speculative: {hyphenated}.com",
                "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={hyphenated}.com&sz=128&default=404",
                "source": "Website Match"
            })

    # 2. Try Clearbit Autocomplete API (clean SVG/PNG company logos)
    try:
        response = requests.get(
            f"https://autocomplete.clearbit.com/v1/companies/suggest?query={requests.utils.quote(clean_query)}",
            timeout=5
        )
        if response.ok:
            data = response.json()
            for item in data:
                if item.get("domain"):
                    logo_url = f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={item['domain']}&sz=128&default=404"
                    if not any(r["url"] == logo_url for r in results):
                        results.append({
                            "title": item.get("name", clean_query),
                            "url": logo_url,
                            "source": "Verified Company"
                        })
    except Exception as e:
        logger.warning(f"Clearbit autocomplete failed: {e}")
    # 3. Try Wikipedia/Wikidata official logo query (works reliably on GCP/Cloud Run without blocking)
    try:
        import hashlib
        headers = {
            "User-Agent": "ConversationalAnalyticsPortal/1.0 (https://your-custom-domain.com; contact: support@your-custom-domain.com)"
        }
        # Strip TLD if it's a domain query to improve Wikipedia search matching (e.g. wonder.com -> wonder)
        wiki_query = clean_query
        if "." in wiki_query:
            parts = wiki_query.split(".")
            if len(parts) > 1 and parts[-1].lower() in ["com", "org", "net", "edu", "gov", "co", "io", "mil", "info", "biz", "app", "dev", "ai"]:
                wiki_query = " ".join(parts[:-1])

        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={requests.utils.quote(wiki_query)}&limit=3&namespace=0&format=json"
        wr = requests.get(search_url, headers=headers, timeout=5)
        if wr.ok:
            data = wr.json()
            titles = data[1]
            for title in titles:
                wiki_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&sites=enwiki&titles={requests.utils.quote(title)}&props=claims&format=json"
                w_resp = requests.get(wiki_url, headers=headers, timeout=5)
                found_logo = False
                if w_resp.ok:
                    wdata = w_resp.json()
                    entities = wdata.get("entities", {})
                    for entity_id, entity_info in entities.items():
                        claims = entity_info.get("claims", {})
                        logo_claims = claims.get("P154", [])
                        if logo_claims:
                            filename = logo_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                            if filename:
                                spaced_name = filename.replace(" ", "_")
                                md5_hash = hashlib.md5(spaced_name.encode('utf-8')).hexdigest()
                                logo_url = f"https://upload.wikimedia.org/wikipedia/commons/{md5_hash[0]}/{md5_hash[0:2]}/{spaced_name}"
                                results.append({
                                    "title": f"{title} Official Logo",
                                    "url": logo_url,
                                    "source": "Web Search"
                                })
                                found_logo = True
                                break
                
                # Fallback: Parse all images on the Wikipedia page looking for a matching logo
                if not found_logo:
                    img_list_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(title)}&prop=images&imlimit=100&format=json"
                    ir = requests.get(img_list_url, headers=headers, timeout=5)
                    if ir.ok:
                        idata = ir.json()
                        pages = idata.get("query", {}).get("pages", {})
                        for page_id, page_info in pages.items():
                            images = page_info.get("images", [])
                            exclude_patterns = [
                                "commons-logo", "wiktionary-logo", "wikimedia-logo", "wikipedia-logo",
                                "wikiquote-logo", "wikidata-logo", "wikisource-logo", "wikibooks-logo",
                                "wikinews-logo", "wikiversity-logo", "wikivoyage-logo", "mediawiki-logo",
                                "disambig", "stub", "edit-clear", "question_book", "lock", "padlock",
                                "icon", "search-logo", "external_link", "decrease", "increase", "symbol"
                            ]
                            candidates = []
                            for img in images:
                                img_title = img.get("title", "")
                                img_lower = img_title.lower()
                                if "logo" in img_lower:
                                    excluded = False
                                    for pattern in exclude_patterns:
                                        if pattern in img_lower:
                                            excluded = True
                                            break
                                    if not excluded:
                                        candidates.append(img_title)
                            
                            if candidates:
                                # Score candidates
                                best_candidate = None
                                best_score = -100.0
                                import re
                                query_words = [w for w in re.split(r'\W+', clean_query.lower()) if len(w) > 2]
                                
                                for cand in candidates:
                                    cand_lower = cand.lower()
                                    score = 0
                                    for qw in query_words:
                                        if qw in cand_lower:
                                            score += 1
                                    
                                    title_clean = title.lower().replace("corporation", "").replace("group", "").replace("inc", "").strip()
                                    title_words = [w for w in re.split(r'\W+', title_clean) if len(w) > 2]
                                    for tw in title_words:
                                        if tw in cand_lower:
                                            score += 2
                                    
                                    if cand_lower.endswith(".svg"):
                                        score += 1.5
                                        
                                    year_match = re.search(r'(18|19|20)\d{2}', cand_lower)
                                    if year_match:
                                        year = int(year_match.group(0))
                                        score -= (2026 - year) * 0.5 + 2.0
                                        
                                    for keyword in ["historical", "old", "history"]:
                                        if keyword in cand_lower:
                                            score -= 5.0
                                            
                                    score -= len(cand) * 0.005
                                    
                                    if score > best_score:
                                        best_score = score
                                        best_candidate = cand
                                
                                if not best_candidate:
                                    best_candidate = candidates[0]
                                    
                                # Resolve URL of selected candidate
                                info_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(best_candidate)}&prop=imageinfo&iiprop=url&format=json"
                                infor = requests.get(info_url, headers=headers, timeout=5)
                                if infor.ok:
                                    infodata = infor.json()
                                    infopages = infodata.get("query", {}).get("pages", {})
                                    for ipage_id, ipage_info in infopages.items():
                                        info_list = ipage_info.get("imageinfo", [])
                                        if info_list:
                                            resolved_logo_url = info_list[0].get("url")
                                            results.append({
                                                "title": f"{title} Official Logo",
                                                "url": resolved_logo_url,
                                                "source": "Web Search"
                                            })
                                            found_logo = True
                                            break
                            if found_logo:
                                break
                if found_logo:
                    break
    except Exception as e:
        logger.warning(f"Wikipedia logo retrieval failed: {e}")

    # 4. Try Google Image Search (public scrape) as fallback or secondary results
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}+logo&tbm=isch&safe=active"
        res = requests.get(search_url, headers=headers, timeout=5)
        if res.ok:
            import re
            matches = re.findall(r'src="(https://encrypted-tbn0\.gstatic\.com/images\?q=[^"]+)"', res.text)
            for idx, img_url in enumerate(matches[:15]):
                if not any(r["url"] == img_url for r in results):
                    results.append({
                        "title": query.title(),
                        "url": img_url,
                        "source": "Web Search"
                    })
    except Exception as e:
        logger.warning(f"Google Image scrape failed: {e}")
        
    return results

@app.get("/api/branding/logo-proxy")
def logo_proxy(url: str = Query(...)):
    allowed_prefixes = (
        "https://www.google.com/s2/favicons",
        "https://t0.gstatic.com/",
        "https://t1.gstatic.com/",
        "https://t2.gstatic.com/",
        "https://t3.gstatic.com/",
        "https://logo.clearbit.com/"
    )
    if not url.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="Invalid proxy target")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if not res.ok:
            return Response(status_code=404)
            
        import hashlib
        md5_hash = hashlib.md5(res.content).hexdigest()
        FALLBACK_GLOBE_MD5S = {
            "b8a0bf372c762e966cc99ede8682bc71",  # 726-byte blue globe
            "bd292eb2e8187dd045a7d1ddf15b7f5a"   # 413-byte blue globe
        }
        if md5_hash in FALLBACK_GLOBE_MD5S:
            return Response(status_code=404)
            
        return Response(content=res.content, media_type=res.headers.get("Content-Type", "image/png"))
    except Exception as e:
        logger.warning(f"Failed to proxy logo URL {url}: {e}")
        return Response(status_code=404)

@app.get("/api/branding")
def get_branding(user: dict = Depends(get_current_user)):
    try:
        # 1. Try to load from Firestore first
        try:
            db = firestore.client()
            doc_ref = db.collection("settings").document("branding")
            doc = doc_ref.get()
            if doc.exists:
                branding_data = doc.to_dict()
                # Also save locally as a fallback
                try:
                    os.makedirs(FRONTEND_DIR, exist_ok=True)
                    with open(BRANDING_FILE, "w") as f:
                        json.dump(branding_data, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to write branding fallback file: {e}")
                return branding_data
        except Exception as fe:
            logger.warning(f"Could not load branding from Firestore: {fe}. Falling back to local file.")

        # 2. Fallback to local file
        if os.path.exists(BRANDING_FILE):
            with open(BRANDING_FILE, "r") as f:
                return json.load(f)
        else:
            # Return default branding configuration
            return {
                "activeBrand": "default",
                "brands": {
                    "default": {
                        "name": "Google Cloud",
                        "primaryColor": "217, 89%, 61%",
                        "secondaryColor": "142, 70%, 45%",
                        "backgroundColorStart": "#0b0f19",
                        "backgroundColorEnd": "#1a2333",
                        "welcomeMessage": "Welcome to your data assistant. How can I help you analyze your databases today?",
                        "logoUrl": "",
                        "logoText": "Google Cloud Analytics",
                        "logoSvg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 35 32' class='w-full h-full'><path fill='#ea4335' d='M21.85,7.41l1,0,2.85-2.85.14-1.21A12.81,12.81,0,0,0,5,9.6a1.55,1.55,0,0,1,1-.06l5.7-.94s.29-.48.44-.45a7.11,7.11,0,0,1,9.73-.74Z'/><path fill='#4285f4' d='M29.76,9.6a12.84,12.84,0,0,0-3.87-6.24l-4,4A7.11,7.11,0,0,1,24.5,13v.71a3.56,3.56,0,1,1,0,7.12H17.38l-.71.72v4.27l.71.71H24.5A9.26,9.26,0,0,0,29.76,9.6Z'/><path fill='#34a853' d='M10.25,26.49h7.12v-5.7H10.25a3.54,3.54,0,0,1-1.47-.32l-1,.31L4.91,23.63l-.25,1A9.21,9.21,0,0,0,10.25,26.49Z'/><path fill='#fbbc05' d='M10.25,8A9.26,9.26,0,0,0,4.66,24.6l4.13-4.13a3.56,3.56,0,1,1,4.71-4.71l4.13-4.13A9.25,9.25,0,0,0,10.25,8Z'/></svg>"
                    }
                }
            }
    except Exception as e:
        logger.error(f"Error fetching branding: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve branding settings.")

@app.post("/api/telemetry/audit")
def audit_log(req: AuditLogModel, user: dict = Depends(get_current_user)):
    log_audit_to_firestore(
        user_email=user.get("email", "unknown"),
        event_type=req.event_type,
        details=req.details
    )
    return {"status": "success"}

@app.post("/api/branding")
def save_branding(data: dict = Body(...), user: dict = Depends(get_current_user)):
    try:
        # 1. Try to save in Firestore first
        firestore_saved = False
        try:
            db = firestore.client()
            doc_ref = db.collection("settings").document("branding")
            doc_ref.set(data)
            logger.info("Successfully saved branding settings in Firestore.")
            firestore_saved = True
        except Exception as fe:
            logger.warning(f"Could not save branding to Firestore: {fe}. Saving only to local file.")

        # 2. Save to local file
        os.makedirs(FRONTEND_DIR, exist_ok=True)
        with open(BRANDING_FILE, "w") as f:
            json.dump(data, f, indent=2)
            
        # Log to Firestore audit log
        log_audit_to_firestore(
            user_email=user.get("email", "unknown"),
            event_type="BRANDING_UPDATE",
            details={"activeBrand": data.get("activeBrand"), "firestore_sync": firestore_saved}
        )
        
        return {"status": "success", "message": "Branding updated successfully"}
    except Exception as e:
        logger.error(f"Error saving branding: {e}")
        raise HTTPException(status_code=500, detail="Failed to save branding configurations.")

# Mount Static Files (placed at the bottom so it doesn't mask API routes)
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning(f"Static directory not found: {FRONTEND_DIR}. Create it to serve the frontend.")
