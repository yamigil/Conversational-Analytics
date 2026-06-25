from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from firebase_admin import firestore
from google.cloud import bigquery

from config import logger, get_project_id

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
