import json
import logging
import google.auth
from google.auth.transport.requests import AuthorizedSession

logger = logging.getLogger("ca-web-app-gemini")

def call_gemini(prompt: str, system_instruction: str = None, response_mime_type: str = "text/plain", temperature: float = 0.2) -> str:
    """Calls the Vertex AI Gemini 1.5 Flash API to generate content dynamically."""
    try:
        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        
        # Use gemini-2.5-flash-lite (lightning-fast low-latency foundation model)
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/gemini-2.5-flash-lite:generateContent"
        
        parts = [{"text": prompt}]
        payload = {
            # gemini-2.5-flash strictly requires the 'role' field in content objects
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature
            }
        }
        
        if response_mime_type == "application/json":
            payload["generationConfig"]["responseMimeType"] = "application/json"
            
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        logger.info(f"Calling Vertex AI Gemini API for custom suggestions...")
        resp = session.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return text.strip()
        else:
            logger.warning(f"Vertex AI Gemini API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Error calling Vertex AI Gemini API: {e}")
    return ""
