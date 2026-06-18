import os
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ca-web-app-auth")

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
fb_project_id = os.getenv("FB_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "your-gcp-project-id"
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
            mock_email = "admin@google.com" if restrict_to_google else "admin@gilgtz.altostrat.com"
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
