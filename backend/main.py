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

# Import modular components and helpers
from config import (
    logger,
    BRANDING_FILE,
    FRONTEND_DIR,
    DELETED_CONVOS_FILE,
    get_deleted_conversations,
    add_deleted_conversation,
    get_project_id,
    get_location
)
from telemetry import (
    AuditLogModel,
    log_audit_to_firestore,
    log_chat_to_bigquery
)

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
                    # Map legacy slow "all" location to fast stable "global" location to prevent dual scanning
                    if location == "all":
                        location = "global"
                    logger.info(f"Loaded GCP Location from branding settings: {location}")
                    return location
        except Exception as e:
            logger.warning(f"Could not load location from branding settings: {e}")

    # 2. Explicitly configured in env/.env or default
    return os.getenv("GCP_LOCATION") or "global"

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
            logger.info(f"SSO Token Diagnostic: prefix={x_gcp_user_token[:15]}..., length={len(x_gcp_user_token)}")
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

def handle_route_exception(e: Exception, action_context: str):
    err_str = str(e).lower()
    if "401" in err_str or "unauthenticated" in err_str or "session expired" in err_str or "invalid authentication credentials" in err_str:
        logger.error(f"Mapped {action_context} exception to 401 Unauthenticated: {e}")
        raise HTTPException(status_code=401, detail="Google Cloud session expired. Please re-authenticate.")
    if "403" in err_str or "permission denied" in err_str or "denied" in err_str:
        logger.error(f"Mapped {action_context} exception to 403 Permission Denied: {e}")
        raise HTTPException(status_code=403, detail="Permission denied. Your account does not have the required Gemini Data Analytics User IAM role in this project.")
    
    logger.error(f"Error {action_context}: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to {action_context}: {e}")

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

# Import modular schema discovery and BigQuery components
from schema_discovery import (
    extract_questions_from_text,
    get_table_specific_suggestions,
    discover_bq_graph_schema,
    enrich_agent_metadata
)
from bq_client import get_live_table_preview

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
        
        # Write raw agents metadata to a debug JSON file for inspection
        try:
            debug_path = os.path.join(os.path.dirname(__file__), "agent_debug.json")
            with open(debug_path, "w") as f:
                import json
                json.dump(agents, f, indent=2)
            logger.info(f"Successfully wrote agent debug metadata to {debug_path}")
        except Exception as debug_err:
            logger.warning(f"Could not write agent debug file: {debug_err}")
            
        enriched = [enrich_agent_metadata(agent) for agent in agents]
        return enriched
    except Exception as e:
        handle_route_exception(e, "list data agents")

@app.post("/api/conversations")
def create_conversation(req: CreateConvoRequest, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        return client.create_conversation(req.agent_name)
    except Exception as e:
        handle_route_exception(e, "create conversation session")

@app.get("/api/conversations/{agent_name:path}")
def get_conversations(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        convos = client.list_conversations(agent_name)
        deleted = get_deleted_conversations()
        return [c for c in convos if c.get("name") not in deleted]
    except Exception as e:
        handle_route_exception(e, "list active conversations")

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
        handle_route_exception(e, "retrieve conversation history")


@app.get("/api/preview")
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

import time

def penske_mock_stream_generator(query: str, chat_mode: str):
    """Generates a high-fidelity, paced mock event stream for the Penske Customer 360 Graph Agent.
    Unifies real customer names from the peer's CSV with rich, strategic business use cases.
    """
    q = query.lower()
    
    # 1. Scenario Selection based on keywords
    if "visit" in q or "loyal" in q or "most service" in q or "top customer" in q:
        scenario = "loyalty"
    elif "lease" in q or "trim" in q or "sales" in q or "volume" in q:
        scenario = "sales_volume"
    elif "audit" in q or "jacket" in q or "compliance" in q or "finance" in q:
        scenario = "audit"
    elif "campaign" in q or "marketing" in q or "segment" in q or "warranty" in q:
        scenario = "marketing"
    else:
        scenario = "generic"

    # Step A: Stream Thinking Statuses (Simulating active DB analysis)
    statuses = [
        "Analyzing context",
        "Retrieved context for customer 360 query",
        "Executing Graph MATCH query in BigQuery..."
    ]
    if scenario == "sales_volume":
        statuses.append("Generating bar chart visualization")
    else:
        statuses.append("Compiling structured tabular output")
        
    for status in statuses:
        chunk = {
            "systemMessage": {
                "text": {
                    "parts": ["Analyzing context", status] # status is recognized if first part is a status keyword
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.4)

    # Step B: Stream Collapsible Thought Process (Reasoning Log)
    if chat_mode == "thinking":
        if scenario == "loyalty":
            thought_title = "BigQuery GQL Execution Plan"
            thought_body = (
                "1. Traverse relationships: Customer vertex -(OWNS)-> Vehicle vertex -(SERVICED_AT)-> ServiceVisit vertex.\n"
                "2. Filter: Group by customer_id, name, phone, and address.\n"
                "3. Aggregate: COUNT(s.visit_id) to calculate total visits, SUM(s.service_cost) to calculate total spend.\n"
                "4. Sort: Descending by total visits to find the top 5 most loyal customers."
            )
        elif scenario == "sales_volume":
            thought_title = "BigQuery Graph Grouping Plan"
            thought_body = (
                "1. Traverse: Vehicle vertex and extract trim level (SR5, TRD Sport, etc.) and purchase_type (LEASE, RETAIL_BUY).\n"
                "2. Aggregate: Count total units per trim and split by acquisition channel.\n"
                "3. Cross-reference: Match counts against the Q4 2025 and Q1 2026 sales volume summary sheets to ensure consistency."
            )
        elif scenario == "audit":
            thought_title = "F&I Compliance Traversal Plan"
            thought_body = (
                "1. Traverse: Customer vertex -(OWNS)-> Vehicle vertex -(FINANCED_WITH)-> DealJacket vertex.\n"
                "2. Filter: Isolate DealJacket records where status = 'IN_AUDIT'.\n"
                "3. Extract: Pull customer name, phone, vehicle model, trim, finance provider, loan amount, and credit score.\n"
                "4. Goal: Audit compliance rates across different financing channels (supporting Rich's F&I project)."
            )
        elif scenario == "marketing":
            thought_title = "Omnichannel Marketing Segmentation"
            thought_body = (
                "1. Identify: Vehicles out of warranty (Service History mileage > 36,000 miles).\n"
                "2. Correlate: Match these owners against GA4 Web Events where event_type = 'ACCESSORY_SEARCH' or 'TRADE_IN_ESTIMATE'.\n"
                "3. Traverse: Customer -(OWNS)-> Vehicle -(SERVICED_AT)-> ServiceVisit and intersect with Customer -(TRIGGERED)-> WebEvent.\n"
                "4. Generate: A high-propensity target segment for Jessica's personalized rate-card campaigns."
            )
        else:
            thought_title = "Graph Schema Discovery"
            thought_body = "1. Scanning connected graph entities (Customers, Vehicles, Service History).\n2. Writing optimized Graph matching query using MATCH syntax."

        chunk = {
            "systemMessage": {
                "text": {
                    "parts": [thought_title, thought_body]
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.8)

    # Step C: Stream Answer and GQL SQL Query
    if scenario == "loyalty":
        answer_text = (
            "To find the top 5 customers with the most service visits, we write a BigQuery Graph query to traverse the relationships from the consolidated customer master records down to the service logs (representing the 'Willow' service advisor database).\n\n"
            "Here is the native BigQuery Property Graph query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  c.address,\n"
            "  COUNT(s.visit_id) AS total_visits,\n"
            "  ROUND(SUM(s.service_cost), 2) AS total_spend\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit)\n"
            "GROUP BY \n"
            "  c.name, c.phone, c.address\n"
            "ORDER BY \n"
            "  total_visits DESC\n"
            "LIMIT 5;\n"
            "```\n"
            "Based on your peer's real Toyota Tacoma service history, here are the top 5 most loyal customers who visited our service bays:"
        )
    elif scenario == "sales_volume":
        answer_text = (
            "I have queried the unified `vehicles` vertex table. By grouping the vehicles by their trim levels and splitting them by their acquisition type (Lease vs. Retail Purchase), we get a clear view of retail and lease originations.\n\n"
            "Here is the BigQuery Graph matching query:\n"
            "```sql\n"
            "SELECT \n"
            "  v.trim,\n"
            "  COUNTIF(v.purchase_type = 'LEASE') AS lease_count,\n"
            "  COUNTIF(v.purchase_type = 'RETAIL_BUY') AS retail_count,\n"
            "  COUNT(v.vin) AS total_units\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (v:Vehicle)\n"
            "GROUP BY \n"
            "  v.trim\n"
            "ORDER BY \n"
            "  total_units DESC;\n"
            "```\n"
            "Here is the distribution of Tacoma trim levels in your customer database, aligning directly with your dealership group summaries:"
        )
    elif scenario == "audit":
        answer_text = (
            "To audit Penske’s F&I (Finance & Insurance) operations, we traverse the Customer Master Record to their active Deal Jackets that are currently flagged as `IN_AUDIT`. This is the exact use case CIO Rich Hook is implementing to ensure document compliance and streamline back-office audits.\n\n"
            "Here is the BigQuery Graph query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  v.trim,\n"
            "  d.finance_provider,\n"
            "  d.loan_amount,\n"
            "  d.credit_score,\n"
            "  d.status\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:FINANCED_WITH]->(d:DealJacket)\n"
            "WHERE \n"
            "  d.status = 'IN_AUDIT';\n"
            "```\n"
            "Here are the active deal jackets currently undergoing compliance audits in your database:"
        )
    elif scenario == "marketing":
        answer_text = (
            "By querying the unified Customer 360 Property Graph, we can solve Jessica's (Director of Marketing) core business problem: operationalizing 1st-party data to run targeted campaigns.\n\n"
            "We will isolate customers whose Tacomas have **exceeded their 36,000-mile factory warranty** (siloed in the Service/Willow database) and who have recently **searched for TRD accessories or estimated trade-in values online** (siloed in GA4 web traffic).\n\n"
            "Here is the BigQuery Graph matching query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  c.email,\n"
            "  v.trim,\n"
            "  MAX(s.mileage) AS last_mileage,\n"
            "  e.details AS web_interest\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit),\n"
            "      (c)-[:TRIGGERED]->(e:WebEvent)\n"
            "WHERE \n"
            "  s.mileage > 36000\n"
            "  AND (e.event_type = 'ACCESSORY_SEARCH' OR e.event_type = 'TRADE_IN_ESTIMATE')\n"
            "GROUP BY \n"
            "  c.name, c.phone, c.email, v.trim, e.details\n"
            "ORDER BY \n"
            "  last_mileage DESC;\n"
            "```\n"
            "Here is the high-propensity, out-of-warranty customer segment ready for marketing activation:"
        )
    else:
        answer_text = (
            "Welcome to the Penske Customer 360 Graph Agent! I have queried the unified database. Here are the first few records showing consolidated customer profiles, active vehicle ownerships, and service logs:\n\n"
            "```sql\n"
            "SELECT c.name, v.model, v.trim, COUNT(s.visit_id) AS visits\n"
            "FROM `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit)\n"
            "GROUP BY c.name, v.model, v.trim LIMIT 5;\n"
            "```"
        )

    # Stream the answer character-by-character to simulate streaming response
    words = answer_text.split(" ")
    for i in range(0, len(words), 5):
        chunk_text = " ".join(words[i:i+5]) + " "
        chunk = {
            "systemMessage": {
                "text": {
                    "parts": [chunk_text]
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.05)

    # Step D: Stream structured Table Data
    if scenario == "loyalty":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Name", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Address", "type": "STRING"},
                    {"name": "Total Visits", "type": "INTEGER"},
                    {"name": "Total Spend", "type": "FLOAT"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Michael Torres"}, {"v": "(208) 134-4152"}, {"v": "9770 1st St, Blackfoot, ID 83221"}, {"v": "3"}, {"v": "269.85"}]},
                    {"f": [{"v": "Sarah Jenkins"}, {"v": "(385) 489-4843"}, {"v": "1685 1st St, Roy, UT 84067"}, {"v": "2"}, {"v": "189.00"}]},
                    {"f": [{"v": "David Chen"}, {"v": "(385) 301-1995"}, {"v": "8089 Oak Ave, Ogden, UT 84401"}, {"v": "2"}, {"v": "204.00"}]},
                    {"f": [{"v": "Emily Rodriguez"}, {"v": "(208) 801-7439"}, {"v": "7729 Main St, Idaho Falls, ID 83401"}, {"v": "2"}, {"v": "170.00"}]},
                    {"f": [{"v": "Robert Campbell"}, {"v": "(385) 316-5859"}, {"v": "7992 Oak Ave, Salt Lake City, UT 84111"}, {"v": "2"}, {"v": "231.50"}]}
                ]
            }
        }
    elif scenario == "sales_volume":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Leases", "type": "INTEGER"},
                    {"name": "Retail Sales", "type": "INTEGER"},
                    {"name": "Total Units", "type": "INTEGER"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "SR5"}, {"v": "21"}, {"v": "42"}, {"v": "63"}]},
                    {"f": [{"v": "TRD Sport"}, {"v": "15"}, {"v": "31"}, {"v": "46"}]},
                    {"f": [{"v": "TRD Off-Road"}, {"v": "10"}, {"v": "25"}, {"v": "35"}]},
                    {"f": [{"v": "SR (Base)"}, {"v": "8"}, {"v": "12"}, {"v": "20"}]},
                    {"f": [{"v": "TRD Pro"}, {"v": "3"}, {"v": "10"}, {"v": "13"}]},
                    {"f": [{"v": "Limited"}, {"v": "3"}, {"v": "5"}, {"v": "8"}]}
                ]
            }
        }
    elif scenario == "audit":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Finance Provider", "type": "STRING"},
                    {"name": "Loan Amount", "type": "FLOAT"},
                    {"name": "Credit Score", "type": "INTEGER"},
                    {"name": "Audit Status", "type": "STRING"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Emily Rodriguez"}, {"v": "(208) 801-7439"}, {"v": "TRD Off-Road"}, {"v": "Toyota Financial Services"}, {"v": "38500.00"}, {"v": "645"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Matthew O'Connor"}, {"v": "(435) 270-5636"}, {"v": "Limited"}, {"v": "Chase Auto"}, {"v": "46200.00"}, {"v": "710"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Rachel King"}, {"v": "(385) 297-8125"}, {"v": "SR5"}, {"v": "Penske Finance"}, {"v": "31800.00"}, {"v": "595"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Nicole Adams"}, {"v": "(435) 445-2986"}, {"v": "TRD Pro"}, {"v": "Toyota Financial Services"}, {"v": "44900.00"}, {"v": "680"}, {"v": "IN_AUDIT"}]}
                ]
            }
        }
    elif scenario == "marketing":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Email", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Last Mileage", "type": "INTEGER"},
                    {"name": "Web Activity", "type": "STRING"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "James Wilson"}, {"v": "(208) 228-3027"}, {"v": "james.wilson.demo@penske.com"}, {"v": "TRD Sport"}, {"v": "60334"}, {"v": "Searched TRD Off-Road suspension lift kits"}]},
                    {"f": [{"v": "Amanda Foster"}, {"v": "(385) 132-8215"}, {"v": "amanda.foster.demo@penske.com"}, {"v": "SR5"}, {"v": "52015"}, {"v": "Estimated trade-in value: $24,100 on 2021 Tacoma"}]},
                    {"f": [{"v": "Elizabeth Young"}, {"v": "(801) 502-6249"}, {"v": "elizabeth.young.demo@penske.com"}, {"v": "Limited"}, {"v": "64250"}, {"v": "Searched roof racks & towing accessories"}]},
                    {"f": [{"v": "Samantha Lewis"}, {"v": "(435) 447-6592"}, {"v": "samantha.lewis.demo@penske.com"}, {"v": "TRD Off-Road"}, {"v": "85120"}, {"v": "Estimated trade-in value: $19,500 on 2021 Tacoma"}]}
                ]
            }
        }
    else:
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer Name", "type": "STRING"},
                    {"name": "Vehicle Model", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Active Service Visits", "type": "INTEGER"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Michael Torres"}, {"v": "Toyota Tacoma"}, {"v": "SR (Base)"}, {"v": "1"}]},
                    {"f": [{"v": "Sarah Jenkins"}, {"v": "Toyota Tacoma"}, {"v": "SR5"}, {"v": "1"}]},
                    {"f": [{"v": "David Chen"}, {"v": "Toyota Tacoma"}, {"v": "TRD Sport"}, {"v": "1"}]}
                ]
            }
        }

    # Yield schema and data tables
    yield f"data: {json.dumps({'systemMessage': {'schema': table_payload['schema']}})}\n\n"
    time.sleep(0.2)
    yield f"data: {json.dumps({'systemMessage': {'data': table_payload['data']}})}\n\n"
    time.sleep(0.3)

    # Step E: Stream Vega-Lite Charts (Specifically for Sales Volume)
    if scenario == "sales_volume":
        vega_spec = {
            "spec": json.dumps({
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Tacoma Trim Level distribution by lease and retail purchases.",
                "width": "container",
                "height": 220,
                "data": {
                    "values": [
                        {"Trim": "SR5", "Channel": "Lease", "Units": 21},
                        {"Trim": "SR5", "Channel": "Retail", "Units": 42},
                        {"Trim": "TRD Sport", "Channel": "Lease", "Units": 15},
                        {"Trim": "TRD Sport", "Channel": "Retail", "Units": 31},
                        {"Trim": "TRD Off-Road", "Channel": "Lease", "Units": 10},
                        {"Trim": "TRD Off-Road", "Channel": "Retail", "Units": 25},
                        {"Trim": "SR (Base)", "Channel": "Lease", "Units": 8},
                        {"Trim": "SR (Base)", "Channel": "Retail", "Units": 12},
                        {"Trim": "TRD Pro", "Channel": "Lease", "Units": 3},
                        {"Trim": "TRD Pro", "Channel": "Retail", "Units": 10},
                        {"Trim": "Limited", "Channel": "Lease", "Units": 3},
                        {"Trim": "Limited", "Channel": "Retail", "Units": 5}
                    ]
                },
                "mark": "bar",
                "encoding": {
                    "y": {"field": "Trim", "type": "nominal", "sort": "-x", "title": "Trim Level"},
                    "x": {"field": "Units", "type": "quantitative", "title": "Units Sold"},
                    "color": {
                        "field": "Channel",
                        "type": "nominal",
                        "scale": {"range": ["#38bdf8", "#fbbf24"]},
                        "title": "Channel"
                    }
                },
                "config": {
                    "background": "transparent",
                    "view": {"stroke": "transparent"},
                    "axis": {
                        "grid": True,
                        "gridColor": "rgba(255,255,255,0.05)",
                        "labelColor": "#94a3b8",
                        "titleColor": "#cbd5e1"
                    },
                    "legend": {
                        "labelColor": "#94a3b8",
                        "titleColor": "#cbd5e1"
                    }
                }
            })
        }
        yield f"data: {json.dumps({'systemMessage': {'chart': vega_spec}})}\n\n"
        time.sleep(0.3)

    # Step F: Stream Custom Insights
    if scenario == "loyalty":
        insights_text = (
            "### Insights\n\n"
            "* **Flagship Retention**: Michael Torres is your highest value customer in this service cohort, recording 3 major service appointments with a total spending of $269.85.\n"
            "* **Regional Strength**: All top 5 loyal customers reside in the Idaho/Utah regional dealership zones, indicating excellent customer retention and loyalty in those dealer clusters."
        )
    elif scenario == "sales_volume":
        insights_text = (
            "### Insights\n\n"
            "* **Volume Powerhouse**: SR5 remains the dominant volume driver, representing over 35% of all active leases and retail purchases in the unified database.\n"
            "* **High-Margin Demand**: The high-margin TRD Off-Road and TRD Pro trims represent a growing segment (30% combined), indicating extremely strong customer demand for premium off-road packages."
        )
    elif scenario == "audit":
        insights_text = (
            "### Insights\n\n"
            "* **Auditing Credit Profile**: 3 out of 4 audited contracts belong to prime or subprime tiers (credit score <700), requiring extra doc verification by your billers.\n"
            "* **Toyota Financial Services**: TFS holds 50% of the audited contracts, making it the primary partner for compliance review."
        )
    elif scenario == "marketing":
        insights_text = (
            "### Insights\n\n"
            "* **Upgrade Candidate**: James Wilson is a prime candidate for an outbound TRD performance upgrade campaign, having 60k+ miles on his truck and actively searching for lift kits online.\n"
            "* **Trade-In Prospect**: Amanda Foster and Samantha Lewis are high-propensity trade-in prospects, having high-mileage Tacomas and actively running online valuation estimates."
        )
    else:
        insights_text = (
            "### Insights\n\n"
            "* **Unified Data**: Successfully unified customer records, vehicle registrations, and service records at a master record level."
        )

    yield f"data: {json.dumps({'systemMessage': {'text': {'parts': [insights_text]}}})}\n\n"
    time.sleep(0.2)

    # Step G: Stream Custom Suggestions
    if scenario == "loyalty":
        sugs = [
            "Show me the service history details for Michael Torres",
            "Predict service intervals for Utah-based Tacoma owners",
            "Generate a loyalty segment for customers with >2 service visits"
        ]
    elif scenario == "sales_volume":
        sugs = [
            "Which customers are approaching their end of lease?",
            "Compare average credit scores across different trim levels",
            "Generate a marketing campaign for TRD Pro prospects"
        ]
    elif scenario == "audit":
        sugs = [
            "Show me missing documents for Emily Rodriguez",
            "Generate an audit summary report by finance provider",
            "List all approved deals waiting for funding"
        ]
    elif scenario == "marketing":
        sugs = [
            "Generate a personalized service rate card email segment",
            "Show dealership capacity for trade-in inspections",
            "List average trade-in values for 2021 Tacomas"
        ]
    else:
        sugs = [
            "List the top 5 customers with the most service visits.",
            "Show total sales volume and lease originations by trim level.",
            "Audit the active deal jackets and list any that are currently IN_AUDIT."
        ]

    yield f"data: {json.dumps({'systemMessage': {'text': {'parts': sugs}}})}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/api/chat")
def chat(req: ChatRequestModel, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:


        # Log query telemetry to BigQuery for standard agents
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
        handle_route_exception(e, "stream chat responses")


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
        branding_data = None
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
        except Exception as fe:
            logger.warning(f"Could not load branding from Firestore: {fe}. Falling back to local file.")

        # 2. Fallback to local file
        if not branding_data and os.path.exists(BRANDING_FILE):
            with open(BRANDING_FILE, "r") as f:
                branding_data = json.load(f)
                
        if not branding_data:
            # Return default branding configuration
            branding_data = {
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

        # 3. Dynamic Default Injection! (Ensure active brand always has resolved GCP settings)
        active_brand = branding_data.get("activeBrand", "default")
        if "brands" in branding_data and active_brand in branding_data["brands"]:
            brand_settings = branding_data["brands"][active_brand]
            modified = False
            if "gcpProjectId" not in brand_settings or not brand_settings["gcpProjectId"]:
                try:
                    brand_settings["gcpProjectId"] = get_project_id()
                    modified = True
                except Exception:
                    pass
            if "gcpLocation" not in brand_settings or not brand_settings["gcpLocation"]:
                try:
                    brand_settings["gcpLocation"] = get_location()
                    modified = True
                except Exception:
                    brand_settings["gcpLocation"] = "global"
                    modified = True

            # If we modified the branding data by injecting defaults, auto-sync and write it back to Firestore!
            if modified:
                try:
                    db = firestore.client()
                    doc_ref = db.collection("settings").document("branding")
                    doc_ref.set(branding_data)
                    logger.info("Automatically synchronized and saved resolved GCP defaults to Firestore branding document.")
                except Exception as save_err:
                    logger.warning(f"Could not auto-sync resolved GCP defaults to Firestore: {save_err}")

        return branding_data
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

@app.post("/api/debug/log")
def debug_log(data: dict = Body(...)):
    logger.info(f"FRONTEND DIAGNOSTIC LOG: {json.dumps(data)}")
    return {"status": "success"}

# Mount Static Files (placed at the bottom so it doesn't mask API routes)
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning(f"Static directory not found: {FRONTEND_DIR}. Create it to serve the frontend.")
