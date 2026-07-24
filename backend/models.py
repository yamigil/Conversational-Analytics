from pydantic import BaseModel
from typing import Optional
from fastapi import HTTPException
from config import logger
from telemetry import log_audit_to_firestore

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
    conversation_name: Optional[str] = None
    agent_name: Optional[str] = None
    message_text: str
    looker_credentials: Optional[dict] = None
    chat_mode: Optional[str] = "fast"
    inline_table_id: Optional[str] = None
    python_analysis: Optional[bool] = False

class AuditLogModel(BaseModel):
    event_type: str
    details: dict
