from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Optional, Dict, Any
from pydantic import BaseModel
from db.supabase_client import get_supabase_client
from core.security import get_current_user_optional
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["System"])

class ErrorLogRequest(BaseModel):
    source: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

@router.post("/log-error")
async def log_error(
    payload: ErrorLogRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Logs frontend or system errors to the error_logs table in Supabase.
    """
    try:
        client = get_supabase_client()
        user_id = current_user.get("user_id") if current_user else None
        
        insert_data = {
            "source": payload.source,
            "error_message": payload.error_message,
            "stack_trace": payload.stack_trace,
            "user_id": user_id,
            "context": payload.context or {}
        }
        
        res = client.table("error_logs").insert(insert_data).execute()
        return {"status": "success", "message": "Error logged successfully"}
    except Exception as e:
        logger.error(f"Failed to log error to Supabase: {str(e)}")
        # We don't throw 500 here because the frontend doesn't need to crash if logging fails.
        return {"status": "error", "message": "Failed to log error"}
