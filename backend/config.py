import os
import json
import logging
from typing import Optional

# Automatically locate and set Google Application Credentials if the key file is present in the project root
key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../gilbertos-project-340619-2ed76d85322c.json"))
if os.path.exists(key_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
    try:
        with open(key_path, "r") as f:
            key_data = json.load(f)
            project_id = key_data.get("project_id")
            if project_id:
                os.environ["GCP_PROJECT_ID"] = project_id
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                print(f"Auto-configured GCP credentials using key: {key_path}")
    except Exception as e:
        print(f"Warning: Could not load project_id from key file: {e}")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ca-web-app")

# Resolve path locations relative to this config file
BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/public/branding.json"))
if not os.path.exists(BRANDING_FILE):
    BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist/branding.json"))
    if not os.path.exists(BRANDING_FILE):
        BRANDING_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/branding.json"))

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist"))
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))

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

# Helper to find GCP Project ID for Analytics Agents (no hardcoding fallbacks!)
def get_project_id() -> str:
    # 1. Check if a project ID is defined inside the branding.json settings
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

    # 2. Explicitly configured GCP Analytics Project in env
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

    # Fallback exception (raising an error if no project ID can be resolved)
    logger.error("No project ID could be resolved from environment or configuration.")
    raise RuntimeError("GCP Project ID not configured. Please set the GCP_PROJECT_ID environment variable or specify it in branding.json.")

# Helper to find GCP Location/Region for Analytics Agents
def get_location() -> str:
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

    location = os.getenv("GCP_LOCATION") or os.getenv("GCP_REGION")
    if location:
        logger.info(f"Loaded GCP Location: {location}")
        return location

    return "us-central1"
