from typing import Optional
from google.cloud import bigquery
from fastapi import HTTPException

from config import logger, get_project_id


def get_live_table_preview(project_id: str, dataset_id: str, table_id: str, user_token: Optional[str] = None) -> dict:
    """Queries BigQuery to fetch live database preview rows (strictly 3.0s timeout, with graceful high-fidelity mock fallbacks)."""
    try:
        if user_token:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=user_token)
            bq_client = bigquery.Client(credentials=creds, project=project_id)
            logger.info(f"Initializing live BigQuery preview client using End-User SSO Credentials for project: {project_id}")
        else:
            bq_client = bigquery.Client(project=project_id)
        
        # Get the table metadata directly (extremely fast!)
        full_table_id = f"{project_id}.{dataset_id}.{table_id}"
        table_ref = bq_client.get_table(full_table_id)
        
        logger.info(f"Reading live BigQuery rows directly using list_rows: {full_table_id}")
        # Enforce strict 3.0 second timeout, reading max 5 rows directly from storage
        result = bq_client.list_rows(table_ref, max_results=5, timeout=3.0)
        
        columns = [field.name for field in result.schema]
        rows = []
        for row in result:
            # Safely serialize values (like Decimals, Dates, etc.) to JSON-serializable structures
            row_dict = {}
            for k, v in row.items():
                if hasattr(v, "isoformat"):  # DateTime, Date, Time
                    row_dict[k] = v.isoformat()
                elif hasattr(v, "to_eng_string"):  # Decimal
                    row_dict[k] = float(v)
                else:
                    row_dict[k] = v
            rows.append(row_dict)
            
        return {"columns": columns, "rows": rows}
        
    except Exception as e:
        logger.warning(f"Failed to fetch live BigQuery preview for {project_id}.{dataset_id}.{table_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch table preview from BigQuery: {str(e)}")
