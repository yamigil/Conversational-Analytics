import os
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv
import json
from typing import Optional
from fastapi import Header
from config import get_project_id, BRANDING_FILE
from ca_client import ConversationalAnalyticsClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ca-web-app-auth")

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
fb_project_id = os.getenv("FB_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")

if not fb_project_id:
    try:
        import google.auth
        _, auth_project = google.auth.default()
        if auth_project:
            fb_project_id = auth_project
            logger.info(f"Dynamically resolved Firebase Project ID via ADC: {fb_project_id}")
    except Exception as e:
        logger.warning(f"Failed to resolve project ID via ADC: {e}")

if not fb_project_id:
    fb_project_id = "your-gcp-project-id"

fb_client_email = os.getenv("FB_CLIENT_EMAIL")
fb_private_key = os.getenv("FB_PRIVATE_KEY")

if fb_project_id:
    try:
        if not firebase_admin._apps:
            if fb_client_email and fb_private_key:
                # Resolve private key format (newlines & quotes)
                private_key = fb_private_key
                if private_key.startswith('"') and private_key.endswith('"'):
                    private_key = private_key[1:-1]
                private_key = private_key.replace("\\n", "\n")
                
                cred_dict = {
                    "type": "service_account",
                    "project_id": fb_project_id,
                    "private_key": private_key,
                    "client_email": fb_client_email,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK successfully initialized via Service Account credentials.")
            else:
                # Initialize with Project ID only (for token verification via Google public certs)
                firebase_admin.initialize_app(options={"projectId": fb_project_id})
                logger.info(f"Firebase Admin SDK successfully initialized for project: {fb_project_id} (no-key verification mode).")
    except Exception as e:
        logger.error(f"Error initializing Firebase Admin SDK: {e}")
        raise e
else:
    logger.warning("Firebase Admin credentials or Project ID not configured in environment. Auth will fail.")

# HTTPBearer security scheme
security = HTTPBearer()

def get_current_user(authorization: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency to verify Firebase ID Token from Authorization header.
    Raises 401 Unauthorized if verification fails or 403 Forbidden if restricted and not in the allowed list.
    """
    restrict_to_google = os.getenv("RESTRICT_TO_GOOGLE", "true") != "false"
    allowed_domains_env = os.getenv("ALLOWED_DOMAINS")
    allowed_emails_env = os.getenv("ALLOWED_EMAILS")
    
    if os.getenv("MOCK_AUTH") == "true":
        if os.getenv("ENVIRONMENT") == "production":
            logger.warning("Security Warning: MOCK_AUTH is enabled in environment but bypassed because ENVIRONMENT is set to 'production'!")
        else:
            mock_email = "admin@google.com" if restrict_to_google else "admin@corporate.altostrat.com"
            return {"email": mock_email, "uid": "mock-user-123"}

    token = authorization.credentials
    try:
        # Verify the ID token using Firebase Admin SDK
        decoded_token = auth.verify_id_token(token)
        email = decoded_token.get("email", "").lower()
        
        # 1. If ALLOWED_EMAILS is configured, check if the email is explicitly in the list
        if allowed_emails_env:
            allowed_emails = [e.strip().lower() for e in allowed_emails_env.split(",") if e.strip()]
            if email not in allowed_emails:
                logger.warning(f"Access denied: email {email} is not in the allowed emails list.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Your email is not authorized to access this portal.",
                )
        # 2. Else if ALLOWED_DOMAINS is configured, check if the email ends with any of the allowed domains
        elif allowed_domains_env:
            allowed_domains = [d.strip().lower() for d in allowed_domains_env.split(",") if d.strip()]
            if not any(email.endswith(f"@{domain}") or email == domain for domain in allowed_domains):
                logger.warning(f"Access denied: email {email} domain is not in the allowed domains list.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access restricted to authorized domains: {allowed_domains_env}",
                )
        # 3. Else, fall back to the legacy RESTRICT_TO_GOOGLE behavior
        elif restrict_to_google:
            if not (email.endswith("@google.com") or email.endswith("altostrat.com")):
                logger.warning(f"Access denied for email under restriction mode: {email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access restricted to @google.com and Argolis accounts only.",
                )
                
        return decoded_token
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify ID Token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    return os.getenv("GCP_LOCATION") or "global"

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
    
    default_project = get_project_id()
    default_location = get_location()
    if target_project != default_project or target_location != default_location:
        try:
            return ConversationalAnalyticsClient(target_project, location=target_location)
        except Exception as e:
            logger.error(f"Failed to initialize Service Account client for project {target_project}, location {target_location}: {e}")
    # Always return a client for the freshly resolved default project and location
    return ConversationalAnalyticsClient(default_project, location=default_location)
