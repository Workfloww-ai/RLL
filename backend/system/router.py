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

class ActivityTrackRequest(BaseModel):
    event: str
    client_type: str = "mobile"  # "mobile" or "web"
    properties: Optional[Dict[str, Any]] = None
    distinct_id: Optional[str] = None

@router.post("/log-error")
async def log_error(
    payload: ErrorLogRequest,
    request: Request
):
    """
    Logs frontend or system errors to the error_logs table in Supabase and PostHog.
    """
    user_id = None
    try:
        # Manually extract user_id from token if present, to avoid 401 on anonymous logs
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                import jwt
                from backend.core.config import settings
                payload_jwt = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"verify_signature": False})
                user_id = payload_jwt.get("user_id") or payload_jwt.get("sub")
            except Exception:
                pass

        # Forward to PostHog error event & log stream
        try:
            from backend.core.posthog import capture_posthog_event, posthog_logs_logger, posthog_logs_provider
            capture_posthog_event(
                "frontend_error",
                properties={
                    "source": payload.source,
                    "error_message": payload.error_message,
                    "stack_trace": payload.stack_trace,
                    "context": payload.context or {},
                },
                distinct_id=str(user_id) if user_id else "anonymous_frontend_user",
            )
            if posthog_logs_provider:
                posthog_logs_logger.error(
                    f"[{payload.source}] {payload.error_message}",
                    extra={
                        "source": payload.source,
                        "error_message": payload.error_message,
                        "user_id": str(user_id) if user_id else None,
                        "context": payload.context or {},
                    },
                )
        except Exception as e_ph:
            logger.warning(f"Failed to forward error to PostHog: {e_ph}")

        client = get_supabase()
        if client:
            insert_data = {
                "source": payload.source,
                "error_message": payload.error_message,
                "stack_trace": payload.stack_trace,
                "user_id": user_id,
                "context": payload.context or {}
            }
            client.table("error_logs").insert(insert_data).execute()
        return {"status": "success", "message": "Error logged successfully"}
    except Exception as e:
        logger.error(f"Failed to log error: {str(e)}")
        # We don't throw 500 here because the frontend doesn't need to crash if logging fails.
        return {"status": "error", "message": "Failed to log error"}


@router.post("/track-activity")
async def track_activity(payload: ActivityTrackRequest, request: Request):
    """
    Ingest user activity from Mobile and Web clients into PostHog.
    Attaches user session context, IP, client type, and forwards to PostHog.
    """
    user_id = payload.distinct_id
    user_email = None
    user_role = None
    tenant_id = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            import jwt
            from backend.core.config import settings
            decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"verify_signature": False})
            user_id = user_id or decoded.get("user_id") or decoded.get("sub")
            user_email = decoded.get("email")
            user_role = decoded.get("role") or decoded.get("role_name")
            tenant_id = decoded.get("tenant_id")
        except Exception:
            pass

    event_props = (payload.properties or {}).copy()
    event_props["client_type"] = payload.client_type
    if user_email and "email" not in event_props:
        event_props["email"] = user_email
    if user_role and "role" not in event_props:
        event_props["role"] = user_role
    if tenant_id and "tenant_id" not in event_props:
        event_props["tenant_id"] = tenant_id

    try:
        from backend.core.posthog import capture_posthog_event, log_user_activity
        capture_posthog_event(
            event=payload.event,
            properties=event_props,
            distinct_id=str(user_id) if user_id else f"anonymous_{payload.client_type}_user",
        )
    except Exception as e:
        logger.warning(f"Notice tracking activity for {payload.event}: {e}")

    return {"status": "success"}


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


@router.get("/lock-status")
def get_lock_status():
    """
    Returns live system read-only lock status during active uploads.
    """
    from backend.core.system_lock import get_system_lock_status
    return get_system_lock_status()


@router.post("/cooldown/reset")
def reset_cooldown():
    """
    Administrative reset for the 30-minute upload cooldown buffer.
    """
    from backend.core.system_lock import reset_upload_cooldown, get_upload_cooldown_status
    reset_upload_cooldown()
    return {"message": "Upload cooldown reset successfully.", "cooldown": get_upload_cooldown_status()}


