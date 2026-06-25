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

def extract_questions_from_text(text: str) -> list:
    """Helper to parse and extract sample questions/query starters from a text block.
    Supports inline numbered lists (e.g. (1) ... (2) ...), vertical numbered lists,
    and questions inside quotes ending in a question mark."""
    if not text:
        return []
    questions = []
    
    # 1. Match numbered list questions (supporting both newlines and inline like "(1) ... (2) ...")
    # Matches a number marker like 1. or (1) or 1), followed by text, up to the next marker or end of string
    numbered_matches = re.findall(r'(?:\(?\d+[\.\)]\s*)\s*(.*?)(?=\s*\(?\d+[\.\)]|$)', text, re.DOTALL)
    for m in numbered_matches:
        q = m.strip()
        # Clean trailing periods, commas, or spaces
        q = q.rstrip(".,; ")
        if 15 < len(q) < 160:
            # Filter out structural schemas or descriptions containing colons, markdown stars, or BQ keys
            if any(k in q.lower() for k in ["primary key", "key column", "foreign key", "table schema"]):
                continue
            if q.count(":") > 1 or q.count("`") > 2 or "*" in q or "#" in q:
                continue
            if not q.endswith("?"):
                q += "?"
            questions.append(q)
            
    # 2. Extract questions inside quotes ending with a question mark (fallback/extra)
    quoted_matches = re.findall(r'["\']([^"\']+\?)["\']', text)
    for m in quoted_matches:
        q = m.strip()
        if 15 < len(q) < 160:
            if not any(k in q.lower() for k in ["primary key", "key column", "foreign key", "table schema"]):
                if q.count(":") > 1 or q.count("`") > 2 or "*" in q or "#" in q:
                    continue
                if not any(k in q.upper() for k in ["SELECT", "FROM", "WHERE", "WITH", "LIMIT"]):
                    q = re.sub(r'[\*\`\_]', '', q)
                    if q not in questions:
                        questions.append(q)
                    
    return questions

def get_table_specific_suggestions(table_name: str) -> list:
    """Returns premium, highly-analytical table-level suggested queries based on table names."""
    name_lower = table_name.lower()
    
    # A. order_items / sales orders
    if "order_items" in name_lower or "order" in name_lower:
        return [
            "What are our total sales and profit margins from order_items this month?",
            "Can we see the monthly order volume and return rate from order_items?",
            "What is the distribution of order status (Processing, Completed, Returned) in order_items?"
        ]
        
    # B. products catalog
    if "product" in name_lower:
        return [
            "What are the top 10 most expensive products by retail price?",
            "How many unique products do we have in each department and category?",
            "Which product brands have the highest average retail price in our catalog?"
        ]
        
    # C. users / customers profiles
    if "user" in name_lower or "customer" in name_lower:
        return [
            "What is the distribution of users by traffic source and age group?",
            "Can we see the number of new user signups by country and state?",
            "What are the most common traffic sources for our customers?"
        ]
        
    # D. events / web traffic logs
    if "event" in name_lower or "session" in name_lower:
        return [
            "What is the count of events by action type (view, cart, purchase)?",
            "Which traffic sources generate the highest number of website sessions?",
            "What is the daily trend of website events for the last 30 days?"
        ]
        
    # E. SA360 / Marketing actuals
    if "sa360" in name_lower or "actual" in name_lower or "marketing" in name_lower:
        return [
            "What is the sum of cost, impressions, and clicks grouped by account?",
            "Can we calculate the click-through rate (CTR) for each account type?",
            "Show me the daily clicks and cost trends from this marketing dataset."
        ]
        
    # F. corpusembeddings / vector database
    if "embedding" in name_lower or "corpus" in name_lower:
        return [
            "What are the columns and schema of the corpusembeddings table?",
            "Show me a sample of 5 records with their text content and embeddings.",
            "How many total text chunks and embedding vectors are stored here?"
        ]
        
    # Default fallback for custom/unknown tables
    return [
        f"Show me a detailed summary and column types of the {table_name} table.",
        f"What are the top 10 most recent records from the {table_name} table?",
        f"Can you show me the count of records grouped by the primary columns in {table_name}?"
    ]

# Dictionary of known semantic node IDs and their curated premium configurations
KNOWN_NODES = {
    "customers": {
        "label": "Customers",
        "icon": "users",
        "type": "customer",
        "description": "Customer demographic details, CRM records, tier designations, and business indicators.",
        "suggestions": [
            "How many premium tier customers do we have?",
            "What is the average customer lifetime value across our dealership?",
            "Show me the distribution of customers by region and status."
        ]
    },
    "sales": {
        "label": "Sales",
        "icon": "shopping-bag",
        "type": "transaction",
        "description": "Vehicle sales transactions, deal jackets, purchase types, and financing indicators.",
        "suggestions": [
            "What is our total sales revenue and gross profit margins this quarter?",
            "Compare monthly vehicle sales volume between retail lease and finance types.",
            "Show me the average finance and insurance (F&I) amount in our deal jackets."
        ]
    },
    "service_visits": {
        "label": "Service Visits",
        "icon": "wrench",
        "type": "event",
        "description": "Vehicle maintenance logs, service tickets, diagnostic codes, and repair details.",
        "suggestions": [
            "What are the most common service diagnostic codes reported?",
            "Show the monthly trend of repair service costs over the last year.",
            "List vehicles that have had more than three service visits in 6 months."
        ]
    },
    "web_events": {
        "label": "Web Events",
        "icon": "globe",
        "type": "interaction",
        "description": "Digital footprints, vehicle detail views, dealership site visits, and application logs.",
        "suggestions": [
            "Which vehicle pages generate the highest number of online detail views?",
            "What is the daily trend of website visits and session duration?",
            "List the most common web events triggered by lease holders."
        ]
    },
    "vehicles": {
        "label": "Vehicles",
        "icon": "car",
        "type": "asset",
        "description": "Dealership vehicle inventory, make, model, trim levels, and purchase classifications.",
        "suggestions": [
            "What is the distribution of vehicle inventory by trim level and year?",
            "Compare total service costs between lease and retail purchased vehicles.",
            "Show the most popular vehicle models sold in the last 12 months."
        ]
    },
    "deal_jackets": {
        "label": "Deal Jackets",
        "icon": "folder",
        "type": "document",
        "description": "F&I deal jackets, credit scores, loan amounts, interest rates, and approval statuses.",
        "suggestions": [
            "What is the average interest rate approved for credit scores above 750?",
            "Show the monthly volume of deal jackets grouped by credit tier.",
            "List all deal jackets currently in audit status."
        ]
    },
    "users": {
        "label": "Users",
        "icon": "users",
        "type": "customer",
        "description": "Customer profiles, registrations, demographic locations, and traffic source channels.",
        "suggestions": [
            "How many new users registered last month by country?",
            "What is the distribution of users by traffic source medium and age?",
            "List the top 10 most loyal customers by order count."
        ]
    },
    "orders": {
        "label": "Orders",
        "icon": "shopping-bag",
        "type": "transaction",
        "description": "Purchase transactions, shipping statuses, order items, and revenue statistics.",
        "suggestions": [
            "What is the average order value (AOV) for this year?",
            "Compare monthly order volumes and total sales revenue across different countries.",
            "Show the status distribution of orders (e.g. processing, shipped, returned)."
        ]
    },
    "products": {
        "label": "Products",
        "icon": "package",
        "type": "inventory",
        "description": "E-commerce product catalog details, pricing history, inventory stock, and categories.",
        "suggestions": [
            "What are the top 5 best-selling product categories by total sales revenue?",
            "List all products with a retail price greater than $150 and their categories.",
            "Which product categories have the highest profit margins?"
        ]
    },
    "brands": {
        "label": "Brands",
        "icon": "award",
        "type": "vendor",
        "description": "Brand manufacturers, manufacturer profiles, and brand-specific sales performance metrics.",
        "suggestions": [
            "What are the top 5 brand names by number of items sold?",
            "Which brand has the highest average retail price in our catalog?",
            "Show me the sales trend for products belonging to the brand 'Nike'."
        ]
    },
    "stores": {
        "label": "Stores",
        "icon": "store",
        "type": "warehouse",
        "description": "Physical retail store locations, warehouses, regional stock levels, and store inventory distributions.",
        "suggestions": [
            "Which store warehouse currently holds the highest inventory value?",
            "What is the total stock quantity of items distributed across our store locations?",
            "Show me products with stock levels below 25 units in the Chicago warehouse."
        ]
    }
}

def discover_bq_graph_schema(project_id: str, dataset_id: str) -> Optional[dict]:
    """Queries BigQuery INFORMATION_SCHEMA.PROPERTY_GRAPHS to dynamically discover the property graph schema."""
    try:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=project_id)
        
        # 1. Fetch dataset location using API to ensure region compatibility
        dataset = bq_client.get_dataset(f"{project_id}.{dataset_id}")
        location = dataset.location
        if not location:
            return None
            
        # 2. Query regional PROPERTY_GRAPHS metadata view
        graph_query = f"""
        SELECT property_graph_name, property_graph_metadata_json
        FROM `region-{location.lower()}.INFORMATION_SCHEMA.PROPERTY_GRAPHS`
        WHERE property_graph_schema = '{dataset_id}'
        LIMIT 1
        """
        
        query_job = bq_client.query(graph_query)
        rows = list(query_job)
        if not rows:
            logger.info(f"No BigQuery property graphs found in dataset '{dataset_id}'.")
            return None
            
        row = rows[0]
        metadata = row['property_graph_metadata_json']
        
        # 3. Parse nodeTables
        nodes = []
        node_suggestions = {}
        for nt in metadata.get('nodeTables', []):
            table_id = nt['name'].split('.')[-1]
            label = table_id
            if 'labelAndProperties' in nt and nt['labelAndProperties']:
                label = nt['labelAndProperties'][0].get('label', label)
                
            known = KNOWN_NODES.get(table_id)
            if known:
                nodes.append({
                    "id": table_id,
                    "label": known["label"],
                    "icon": known["icon"],
                    "type": known["type"],
                    "description": known["description"]
                })
                node_suggestions[table_id] = known["suggestions"]
            else:
                nodes.append({
                    "id": table_id,
                    "label": label.upper() + "S" if not label.endswith('s') else label.upper(),
                    "icon": "package",
                    "type": "entity",
                    "description": f"BigQuery Graph Node: {label}"
                })
                node_suggestions[table_id] = [
                    f"Can you give me a summary of the data in the {table_id} table?",
                    f"What are the key metrics and columns available in {table_id}?",
                    f"Show me the top 10 most recent records from {table_id}."
                ]
                
        # 4. Parse edgeTables
        edges = []
        for et in metadata.get('edgeTables', []):
            label = et['name']
            if 'labelAndProperties' in et and et['labelAndProperties']:
                label = et['labelAndProperties'][0].get('label', label)
                
            source_table = et.get('sourceNodeReference', {}).get('nodeTable', '')
            dest_table = et.get('destinationNodeReference', {}).get('nodeTable', '')
            
            source_id = source_table.split('.')[-1]
            dest_id = dest_table.split('.')[-1]
            
            edges.append({
                "source": source_id,
                "target": dest_id,
                "label": label.upper()
            })
            
        logger.info(f"Dynamically discovered BigQuery property graph '{row['property_graph_name']}' in dataset '{dataset_id}'.")
        return {
            "nodes": nodes,
            "edges": edges,
            "nodeSuggestions": node_suggestions
        }
        
    except Exception as e:
        logger.error(f"Failed to dynamically discover BigQuery property graph schema: {e}")
        return None

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
                    
    # 2. Extract suggested queries from the agent's description first (where GCP console stores sample queries)
    suggestions = []
    if description:
        suggestions.extend(extract_questions_from_text(description))
        
    # 3. Extract suggested queries from system instruction if we still need more
    if len(suggestions) < 3 and system_instruction:
        suggestions.extend(extract_questions_from_text(system_instruction))
        
    # Remove duplicates while preserving order
    unique_suggestions = []
    for s in suggestions:
        if s not in unique_suggestions:
            unique_suggestions.append(s)
    suggestions = unique_suggestions[:3]
    
    # 4. Fallback: Dynamic Brand-based default presets
    name_lower = display_name.lower()
    desc_lower = description.lower()
    
    if len(suggestions) < 3:
        preset_suggestions = []
        
        # A. Marketing / Advertising
        if any(k in name_lower or k in desc_lower for k in ["marketing", "ga4", "sa360", "advertising"]):
            preset_suggestions = [
                "What are the top 10 best-selling product categories by total sales revenue?",
                "How does our monthly order volume compare across different countries?",
                "Can we see the distribution of users by traffic source and country?"
            ]
            
        # B. Penske / Automotive / Customer 360
        elif any(k in name_lower or k in desc_lower for k in ["penske", "customer 360", "customer360", "dealership"]):
            preset_suggestions = [
                "Show me the distribution of customer purchase history by vehicle brand.",
                "What is the average F&I deal jacket amount for our premium tier customers?",
                "Can we see the trends in customer service satisfaction scores over the last quarter?"
            ]
            
        # C. Graph-specific Looker agent
        elif "graph" in name_lower or "graph" in desc_lower:
            preset_suggestions = [
                "How does the graph schema prevent overcounting across order items?",
                "Show me the monthly trend of cost and revenue using graph measures.",
                "What are the top 5 brands by number of items sold according to graph aggregations?"
            ]
            
        # D. General E-commerce (The Look)
        elif any(k in name_lower or k in desc_lower for k in ["ecommerce", "the look", "thelook", "retail", "shop"]):
            preset_suggestions = [
                "Show me the monthly trend of cost and revenue for this year.",
                "What are the top 5 brands by number of items sold?",
                "What is the average order value (AOV) for each month?"
            ]
            
        # If we matched any specific category, append them!
        if preset_suggestions:
            for ps in preset_suggestions:
                if ps not in suggestions:
                    suggestions.append(ps)
            suggestions = suggestions[:3]
        
    # 5. Double Fallback: Custom table-based queries for custom agents
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
        
    # 6. Triple Fallback: Generic presets as last resort
    if len(suggestions) < 3:
        preset_suggestions = [
            "Show me the monthly trend of cost and revenue for this year.",
            "What are the top 5 brands by number of items sold?",
            "What is the average order value (AOV) for each month?"
        ]
        for ps in preset_suggestions:
            if ps not in suggestions:
                suggestions.append(ps)
        suggestions = suggestions[:3]
            
    # 7. Generate a beautiful, custom welcome subtitle based on the agent's tables or description
    welcome_subtitle = description
    if not welcome_subtitle:
        if tables:
            welcome_subtitle = f"Ask any analytical question about your connected data tables (including {', '.join(tables[:2])})."
        else:
            welcome_subtitle = "Ask any analytical question about your business data, cost trends, or performance."
            
    # 8. Detect and Inject Graph Database Schema if it is a Graph Agent
    is_graph_agent = (
        "graph" in name_lower or 
        "graph" in desc_lower or 
        any(k in name_lower or k in desc_lower for k in ["penske", "customer 360", "customer360"])
    )
    agent["isGraphAgent"] = is_graph_agent
    
    if is_graph_agent:
        # 8a. Attempt to discover the graph schema dynamically from BigQuery
        project_id = get_project_id()
        dataset_id = None
        if tables:
            first_table = tables[0]
            if "." in first_table:
                dataset_id = first_table.split(".")[0]
                
        discovered_schema = None
        if dataset_id:
            discovered_schema = discover_bq_graph_schema(project_id, dataset_id)
            
        if discovered_schema:
            agent["graphData"] = discovered_schema
            welcome_subtitle = f"Explore your connected BigQuery Property Graph '{dataset_id}'. Hover and click nodes to discover relationships and ask questions!"
        else:
            # 8b. Fallback to local curated presets if database is offline or schema not found
            if any(k in name_lower or k in desc_lower for k in ["penske", "customer 360", "customer360"]):
                # Penske Property Graph
                agent["graphData"] = {
                    "nodes": [
                        {"id": "customers", "label": "Customers", "icon": "users", "type": "customer", "description": "Customer demographic details, CRM records, tier designations, and business indicators."},
                        {"id": "sales", "label": "Sales", "icon": "shopping-bag", "type": "transaction", "description": "Vehicle sales transactions, deal jackets, purchase types, and financing indicators."},
                        {"id": "service_histories", "label": "Service Histories", "icon": "wrench", "type": "event", "description": "Vehicle maintenance logs, service tickets, diagnostic codes, and repair details."},
                        {"id": "web_events", "label": "Web Events", "icon": "globe", "type": "interaction", "description": "Digital footprints, vehicle detail views, dealership site visits, and application logs."}
                    ],
                    "edges": [
                        {"source": "customers", "target": "sales", "label": "BUYS"},
                        {"source": "customers", "target": "service_histories", "label": "SERVICED_BY"},
                        {"source": "customers", "target": "web_events", "label": "TRIGGERS"}
                    ],
                    "nodeSuggestions": {
                        "customers": [
                            "How many premium tier customers do we have?",
                            "What is the average customer lifetime value across our dealership?",
                            "Show me the distribution of customers by region and status."
                        ],
                        "sales": [
                            "What is our total sales revenue and gross profit margins this quarter?",
                            "Compare monthly vehicle sales volume between retail lease and finance types.",
                            "Show me the average finance and insurance (F&I) amount in our deal jackets."
                        ],
                        "service_histories": [
                            "What are the most common service diagnostic codes reported?",
                            "Show the monthly trend of repair service costs over the last year.",
                            "List vehicles that have had more than three service visits in 6 months."
                        ],
                        "web_events": [
                            "Which vehicle pages generate the highest number of online detail views?",
                            "What is the daily trend of website visits and session duration?",
                            "List the most common web events triggered by lease holders."
                        ]
                    }
                }
                welcome_subtitle = "Explore the Penske Customer 360 Property Graph. Unify Sales, Willow Service History, F&I, and Web Events in a single consolidated view."
            else:
                # Default E-commerce Graph
                agent["graphData"] = {
                    "nodes": [
                        {"id": "users", "label": "Users", "icon": "users", "type": "customer", "description": "Customer profiles, registrations, demographic locations, and traffic source channels."},
                        {"id": "orders", "label": "Orders", "icon": "shopping-bag", "type": "transaction", "description": "Purchase transactions, shipping statuses, order items, and revenue statistics."},
                        {"id": "products", "label": "Products", "icon": "package", "type": "inventory", "description": "E-commerce product catalog details, pricing history, inventory stock, and categories."},
                        {"id": "brands", "label": "Brands", "icon": "award", "type": "vendor", "description": "Brand manufacturers, manufacturer profiles, and brand-specific sales performance metrics."},
                        {"id": "stores", "label": "Stores", "icon": "store", "type": "warehouse", "description": "Physical retail store locations, warehouses, regional stock levels, and store inventory distributions."}
                    ],
                    "edges": [
                        {"source": "users", "target": "orders", "label": "PLACES"},
                        {"source": "orders", "target": "products", "label": "CONTAINS"},
                        {"source": "products", "target": "brands", "label": "BELONGS_TO"},
                        {"source": "products", "target": "stores", "label": "STOCKED_IN"}
                    ],
                    "nodeSuggestions": {
                        "users": [
                            "How many new users registered last month by country?",
                            "What is the distribution of users by traffic source medium and age?",
                            "List the top 10 most loyal customers by order count."
                        ],
                        "orders": [
                            "What is the average order value (AOV) for this year?",
                            "Compare monthly order volumes and total sales revenue across different countries.",
                            "Show the status distribution of orders (e.g. processing, shipped, returned)."
                        ],
                        "products": [
                            "What are the top 5 best-selling product categories by total sales revenue?",
                            "List all products with a retail price greater than $150 and their categories.",
                            "Which product categories have the highest profit margins?"
                        ],
                        "brands": [
                            "What are the top 5 brand names by number of items sold?",
                            "Which brand has the highest average retail price in our catalog?",
                            "Show me the sales trend for products belonging to the brand 'Nike'."
                        ],
                        "stores": [
                            "Which store warehouse currently holds the highest inventory value?",
                            "What is the total stock quantity of items distributed across our store locations?",
                            "Show me products with stock levels below 25 units in the Chicago warehouse."
                        ]
                    }
                }
                if not description:
                    welcome_subtitle = "Explore your connected BigQuery Graph database. Hover and click nodes to discover relationships and ask questions!"
            
    else:
        # Auto-generate Star Relational Schema for standard agents!
        table_nodes = []
        table_edges = []
        
        # Add central root node
        table_nodes.append({
            "id": "schema_root",
            "label": "Database Schema",
            "icon": "database",
            "type": "database",
            "description": f"Relational database schema containing all tables available to the {display_name} agent."
        })
        
        for t in tables:
            # Extract clean table name (e.g. from "dataset.table_name" -> "table_name")
            clean_name = t.split(".")[-1] if "." in t else t
            
            table_nodes.append({
                "id": clean_name,
                "label": clean_name,
                "icon": clean_name,
                "type": "table",
                "description": f"Connected database table: {clean_name}. Contains columns, metrics, and records for analytical queries."
            })
            
            # Draw a directed edge from database to table
            table_edges.append({
                "source": "schema_root",
                "target": clean_name,
                "label": "CONTAINS"
            })
            
        agent["graphData"] = {
            "nodes": table_nodes,
            "edges": table_edges,
            "nodeSuggestions": {
                # Dynamically generate domain-specific table-level suggestions
                clean_name: get_table_specific_suggestions(clean_name) 
                for clean_name in [t.split(".")[-1] if "." in t else t for t in tables]
            }
        }
        if not welcome_subtitle:
            welcome_subtitle = f"Explore the connected tables schema for {display_name}. Hover and click table nodes to inspect columns and preview data!"

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
        
        enriched = [enrich_agent_metadata(agent) for agent in agents]
        return enriched
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


@app.get("/api/preview")
def get_table_preview(
    table_name: str,
    agent_name: Optional[str] = None,
    user: dict = Depends(get_current_user),
    client: ConversationalAnalyticsClient = Depends(get_analytics_client)
):
    # 1. Define high-fidelity mock data dictionary
    mock_previews = {
        "customers": {
            "columns": ["customer_id", "first_name", "last_name", "email", "phone_number", "state"],
            "rows": [
                {"customer_id": 1001, "first_name": "Gilbert", "last_name": "Gomez", "email": "gilgtz@penske.com", "phone_number": "+1 (248) 555-0199", "state": "MI"},
                {"customer_id": 1002, "first_name": "Sarah", "last_name": "Connor", "email": "sconnor@resistance.net", "phone_number": "+1 (310) 555-0182", "state": "CA"},
                {"customer_id": 1003, "first_name": "John", "last_name": "Doe", "email": "jdoe@toyota.com", "phone_number": "+1 (800) 555-0155", "state": "TX"},
                {"customer_id": 1004, "first_name": "Elena", "last_name": "Rostova", "email": "elena.r@lexus.co.jp", "phone_number": "+81 3-5555-0123", "state": "Tokyo"},
                {"customer_id": 1005, "first_name": "Marcus", "last_name": "Vance", "email": "mvance@vonsarcade.com", "phone_number": "+1 (415) 555-0144", "state": "CA"}
            ]
        },
        "vehicles": {
            "columns": ["vehicle_id", "vin", "make", "model", "year", "trim", "acquisition_type"],
            "rows": [
                {"vehicle_id": "V1", "vin": "1FTFW1RG5LFA00001", "make": "Toyota", "model": "Tacoma", "year": 2021, "trim": "TRD Pro", "acquisition_type": "Lease"},
                {"vehicle_id": "V2", "vin": "5YJ3E1EB8LF000002", "make": "Toyota", "model": "Tundra", "year": 2022, "trim": "Limited", "acquisition_type": "Purchase"},
                {"vehicle_id": "V3", "vin": "1GNSKCKD2LR000003", "make": "Lexus", "model": "RX 350", "year": 2023, "trim": "F Sport", "acquisition_type": "Purchase"},
                {"vehicle_id": "V4", "vin": "4T1BF1FK1LU000004", "make": "Toyota", "model": "RAV4", "year": 2020, "trim": "XLE", "acquisition_type": "Lease"},
                {"vehicle_id": "V5", "vin": "1GCYDKED4LF000005", "make": "Toyota", "model": "Tacoma", "year": 2021, "trim": "SR5", "acquisition_type": "Purchase"}
            ]
        },
        "service_visits": {
            "columns": ["visit_id", "vehicle_id", "date", "repair_order_no", "mileage", "cost", "status"],
            "rows": [
                {"visit_id": "RO101", "vehicle_id": "V1", "date": "2026-04-15", "repair_order_no": "RO-88291", "mileage": 45120, "cost": 324.50, "status": "COMPLETED"},
                {"visit_id": "RO102", "vehicle_id": "V2", "date": "2026-05-10", "repair_order_no": "RO-88402", "mileage": 28900, "cost": 150.00, "status": "COMPLETED"},
                {"visit_id": "RO103", "vehicle_id": "V1", "date": "2026-06-01", "repair_order_no": "RO-88941", "mileage": 48200, "cost": 890.75, "status": "COMPLETED"},
                {"visit_id": "RO104", "vehicle_id": "V4", "date": "2026-06-12", "repair_order_no": "RO-89102", "mileage": 55210, "cost": 89.95, "status": "COMPLETED"},
                {"visit_id": "RO105", "vehicle_id": "V5", "date": "2026-06-20", "repair_order_no": "RO-89332", "mileage": 12400, "cost": 210.00, "status": "COMPLETED"}
            ]
        },
        "deal_jackets": {
            "columns": ["deal_id", "customer_id", "date", "finance_company", "credit_score", "loan_amount", "audit_status"],
            "rows": [
                {"deal_id": "D2001", "customer_id": 1001, "date": "2026-01-10", "finance_company": "Toyota Financial Services", "credit_score": 785, "loan_amount": 42500.00, "audit_status": "PASSED"},
                {"deal_id": "D2002", "customer_id": 1002, "date": "2026-02-14", "finance_company": "Chase Auto", "credit_score": 680, "loan_amount": 31000.00, "audit_status": "WARNING"},
                {"deal_id": "D2003", "customer_id": 1003, "date": "2026-03-22", "finance_company": "Ally Financial", "credit_score": 740, "loan_amount": 52000.00, "audit_status": "PASSED"},
                {"deal_id": "D2004", "customer_id": 1004, "date": "2026-04-05", "finance_company": "Toyota Financial Services", "credit_score": 810, "loan_amount": 38000.00, "audit_status": "PASSED"},
                {"deal_id": "D2005", "customer_id": 1005, "date": "2026-05-18", "finance_company": "Wells Fargo Auto", "credit_score": 620, "loan_amount": 24500.00, "audit_status": "IN_AUDIT"}
            ]
        },
        "web_events": {
            "columns": ["event_id", "customer_id", "timestamp", "event_name", "page_path", "source"],
            "rows": [
                {"event_id": "E901", "customer_id": 1001, "timestamp": "2026-06-24T10:12:00Z", "event_name": "trade_in_estimate", "page_path": "/vehicles/trade-in", "source": "Google"},
                {"event_id": "E902", "customer_id": 1001, "timestamp": "2026-06-24T10:15:00Z", "event_name": "build_and_price", "page_path": "/tacoma/build", "source": "Direct"},
                {"event_id": "E903", "customer_id": 1002, "timestamp": "2026-06-24T10:20:00Z", "event_name": "view_accessory", "page_path": "/tacoma/accessories", "source": "Facebook"},
                {"event_id": "E904", "customer_id": 1003, "timestamp": "2026-06-24T10:22:00Z", "event_name": "schedule_service", "page_path": "/service/book", "source": "Email"},
                {"event_id": "E905", "customer_id": 1005, "timestamp": "2026-06-24T10:25:00Z", "event_name": "finance_calculator", "page_path": "/finance/apply", "source": "Google"}
            ]
        },
        # The Look Ecommerce fallback mock data
        "users": {
            "columns": ["id", "first_name", "last_name", "email", "age", "country"],
            "rows": [
                {"id": 1, "first_name": "John", "last_name": "Smith", "email": "john.smith@gmail.com", "age": 34, "country": "United States"},
                {"id": 2, "first_name": "Marie", "last_name": "Dubois", "email": "marie.dubois@yahoo.fr", "age": 28, "country": "France"},
                {"id": 3, "first_name": "Carlos", "last_name": "Silva", "email": "csilva@outlook.com.br", "age": 42, "country": "Brazil"},
                {"id": 4, "first_name": "Yuki", "last_name": "Tanaka", "email": "yuki.t@docomo.ne.jp", "age": 31, "country": "Japan"},
                {"id": 5, "first_name": "Hans", "last_name": "Schmidt", "email": "hans.s@t-online.de", "age": 55, "country": "Germany"}
            ]
        },
        "orders": {
            "columns": ["order_id", "user_id", "status", "created_at", "num_of_item"],
            "rows": [
                {"order_id": 12501, "user_id": 1, "status": "Shipped", "created_at": "2026-06-23T14:32:00Z", "num_of_item": 2},
                {"order_id": 12502, "user_id": 2, "status": "Complete", "created_at": "2026-06-23T15:10:00Z", "num_of_item": 1},
                {"order_id": 12503, "user_id": 3, "status": "Processing", "created_at": "2026-06-24T08:45:00Z", "num_of_item": 3},
                {"order_id": 12504, "user_id": 4, "status": "Complete", "created_at": "2026-06-24T09:12:00Z", "num_of_item": 1},
                {"order_id": 12505, "user_id": 5, "status": "Cancelled", "created_at": "2026-06-24T10:05:00Z", "num_of_item": 2}
            ]
        },
        "products": {
            "columns": ["id", "name", "category", "brand", "retail_price", "department"],
            "rows": [
                {"id": 101, "name": "Men's Slim Fit Denim Jeans", "category": "Jeans", "brand": "Levi's", "retail_price": 59.50, "department": "Men"},
                {"id": 102, "name": "Women's Run Free Sneakers", "category": "Active", "brand": "Nike", "retail_price": 120.00, "department": "Women"},
                {"id": 103, "name": "Unisex Classic Leather Belt", "category": "Accessories", "brand": "Calvin Klein", "retail_price": 38.00, "department": "Unisex"},
                {"id": 104, "name": "Men's Wool Blend Winter Coat", "category": "Outerwear", "brand": "Columbia", "retail_price": 180.00, "department": "Men"},
                {"id": 105, "name": "Women's Floral Summer Dress", "category": "Dresses", "brand": "Zara", "retail_price": 49.95, "department": "Women"}
            ]
        }
    }
    
    clean_name = table_name.lower().strip()
    if "." in clean_name:
        clean_name = clean_name.split(".")[-1]
        
    try:
        project_id = get_project_id()
        if project_id and agent_name:
            bq_client = bigquery.Client(project=project_id)
            
            # Dynamically look up the agent definition to extract the real dataset and table IDs
            real_dataset_id = None
            real_table_id = None
            try:
                agents = client.list_agents()
                for a in agents:
                    if a.get("name") == agent_name:
                        da_agent = a.get("dataAnalyticsAgent", {})
                        for context_key in ["publishedContext", "lastPublishedContext", "stagingContext"]:
                            context = da_agent.get(context_key, {})
                            ds_refs = context.get("datasourceReferences", {})
                            bq_ref = ds_refs.get("bq", {})
                            table_refs = bq_ref.get("tableReferences", [])
                            for t in table_refs:
                                tid = t.get("tableId", "")
                                did = t.get("datasetId", "")
                                if tid.lower().strip() == clean_name or tid.lower().strip().replace("_", "") == clean_name.replace("_", ""):
                                    real_dataset_id = did
                                    real_table_id = tid
                                    break
                            if real_table_id:
                                break
                        break
            except Exception as lookup_err:
                logger.error(f"Error looking up agent datasource references: {lookup_err}")
                
            if real_dataset_id and real_table_id:
                full_table_id = f"{project_id}.{real_dataset_id}.{real_table_id}"
            elif "penske" in agent_name.lower() or "customer-360" in agent_name.lower():
                full_table_id = f"{project_id}.penske_customer_360.{clean_name}"
            else:
                if clean_name in ["users", "orders", "products", "distribution_centers", "events", "inventory_items", "order_items"]:
                    full_table_id = f"bigquery-public-data.thelook_ecommerce.{clean_name}"
                else:
                    raise ValueError("Unknown dataset path, falling back to mock")
                    
            query = f"SELECT * FROM `{full_table_id}` LIMIT 5"
            logger.info(f"Running live data preview query: {query}")
            query_job = bq_client.query(query)
            result = query_job.result()
            
            columns = [field.name for field in result.schema]
            rows = []
            for row in result:
                rows.append(dict(row.items()))
                
            return {"columns": columns, "rows": rows}
    except Exception as e:
        logger.warning(f"Failed to fetch live BigQuery preview (falling back to mock): {e}")
        
    if clean_name in mock_previews:
        return mock_previews[clean_name]
        
    return {
        "columns": ["id", "created_at", "status", "value"],
        "rows": [
            {"id": 1, "created_at": "2026-06-24T08:00:00Z", "status": "ACTIVE", "value": "Record A"},
            {"id": 2, "created_at": "2026-06-24T09:15:00Z", "status": "ACTIVE", "value": "Record B"},
            {"id": 3, "created_at": "2026-06-24T10:30:00Z", "status": "PENDING", "value": "Record C"},
            {"id": 4, "created_at": "2026-06-24T11:45:00Z", "status": "INACTIVE", "value": "Record D"},
            {"id": 5, "created_at": "2026-06-24T12:00:00Z", "status": "ACTIVE", "value": "Record E"}
        ]
    }

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
