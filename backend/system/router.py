import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from backend.db.client import get_supabase
from backend.core.route import EncryptedRoute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System"], route_class=EncryptedRoute)

class ErrorLogRequest(BaseModel):
    source: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

@router.post("/log-error")
async def log_error(
    payload: ErrorLogRequest,
    request: Request
):
    """
    Logs frontend or system errors to the error_logs table in Supabase.
    """
    try:
        client = get_supabase_client()
        user_id = None
        
        # Manually extract user_id from token if present, to avoid 401 on anonymous logs
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                import jwt
                from core.config import settings
                payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"verify_signature": False})
                user_id = payload.get("user_id") or payload.get("sub")
            except Exception:
                pass
        
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


from fastapi import Header, Query

@router.get("/tenant/config")
def get_tenant_config_endpoint(
    tenant_slug: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_tenant_slug: Optional[str] = Header(None, alias="X-Tenant-Slug"),
):
    """
    Returns dynamic white-label tenant configuration (Tenant ID, App Name, Logo URL, Favicon, Splash Screen, Pinned Company).
    """
    from backend.services.tenant_service import get_tenant_config_service
    effective_id = tenant_id or x_tenant_id
    effective_slug = tenant_slug or x_tenant_slug or "rll"
    return get_tenant_config_service(tenant_slug=effective_slug, tenant_id=effective_id)

