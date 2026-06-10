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
fb_project_id = os.getenv("FB_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "gilbertos-project-340619"
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
    Raises 401 Unauthorized if verification fails.
    """
    if os.getenv("MOCK_AUTH") == "true":
        return {"email": "admin@gilgtz.altostrat.com", "uid": "mock-user-123"}

    token = authorization.credentials
    try:
        # Verify the ID token using Firebase Admin SDK
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.warning(f"Failed to verify ID Token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
