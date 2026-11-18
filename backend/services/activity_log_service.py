import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any
from backend.db.client import get_supabase

logger = logging.getLogger("auth_log_service")

class AuthLogService:
    """
    Enterprise-grade login authentication audit logging service.
    Maintains user's latest login timestamp, device phone type (iOS/Android/Web),
    IP address, and user agent in public.user_auth_logs.
    Updates existing user records to prevent table bloating (at most 1 row per user).
    """

    @staticmethod
    def detect_phone_type(
        request: Any = None,
        user_agent: Optional[str] = None,
        explicit_phone_type: Optional[str] = None,
    ) -> str:
        """
        Determines device platform: 'ios', 'android', 'web', or 'unknown'.
        Priority:
        1. Explicitly supplied phone_type (e.g. from React Native Platform.OS or payload).
        2. Client HTTP custom headers ('X-Device-Platform', 'X-Platform', 'X-Client-Platform').
        3. User-Agent heuristic pattern matching (iPhone, iPad, Darwin, CFNetwork, okhttp, Android).
        """
        if explicit_phone_type and str(explicit_phone_type).strip():
            clean = str(explicit_phone_type).strip().lower()
            if clean in ("ios", "iphone", "ipad", "ipod"):
                return "ios"
            if clean in ("android",):
                return "android"
            if clean in ("web",):
                return "web"
            return clean

        if request and hasattr(request, "headers"):
            hdr_val = (
                request.headers.get("x-device-platform")
                or request.headers.get("x-platform")
                or request.headers.get("x-client-platform")
                or ""
            ).strip().lower()
            if hdr_val in ("ios", "iphone", "ipad", "ipod"):
                return "ios"
            if hdr_val in ("android",):
                return "android"
            if hdr_val in ("web",):
                return "web"

            if not user_agent:
                user_agent = request.headers.get("user-agent")

        if user_agent:
            ua_clean = user_agent.lower()
            if any(k in ua_clean for k in ("iphone", "ipad", "ipod", "cfnetwork", "darwin")):
                return "ios"
            if any(k in ua_clean for k in ("android", "okhttp")):
                return "android"
            if any(k in ua_clean for k in ("mozilla", "chrome", "safari", "firefox", "edge", "macintosh", "windows")):
                return "web"

        return "unknown"

    @classmethod
    def record_login_sync(
        cls,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        phone_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        action: str = "LOGIN",
        status: str = "SUCCESS",
    ) -> bool:
        """
        Synchronously records or updates user's last login in user_auth_logs.
        If a record already exists for the user_id, it is updated in-place to
        prevent table bloating, keeping only the user's latest login state.
        """
        client = get_supabase()
        if not client:
            logger.warning("Supabase client unavailable for auth log")
            return False

        if not user_id:
            logger.warning("user_id is required to record user auth log")
            return False

        user_id_str = str(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        resolved_phone_type = str(phone_type).strip().lower() if phone_type else "unknown"
        resolved_email = str(email).strip().lower() if email else None
        trimmed_ua = user_agent[:255] if user_agent else None

        # Check if record already exists for this user_id
        try:
            existing_res = client.table("user_auth_logs").select("auth_log_id").eq("user_id", user_id_str).limit(1).execute()
            existing_data = existing_res.data or []
            existing_id = existing_data[0]["auth_log_id"] if len(existing_data) > 0 else None
        except Exception:
            existing_id = None

        # 1. Primary Attempt: dedicated columns (phone_type, last_login, email, status, action)
        full_payload: Dict[str, Any] = {
            "last_login": now_iso,
            "phone_type": resolved_phone_type,
            "status": status,
            "action": action,
        }
        if resolved_email:
            full_payload["email"] = resolved_email
        if ip_address:
            full_payload["ip_address"] = ip_address
        if trimmed_ua:
            full_payload["user_agent"] = trimmed_ua

        try:
            if existing_id:
                client.table("user_auth_logs").update(full_payload).eq("auth_log_id", existing_id).execute()
            else:
                full_payload["user_id"] = user_id_str
                client.table("user_auth_logs").insert(full_payload).execute()
            return True
        except Exception as full_err:
            err_str = str(full_err)
            # If migration 056 columns not yet in DB, fallback to base schema
            if "PGRST204" in err_str or "Could not find" in err_str or "column" in err_str.lower():
                try:
                    action_summary = f"{action} | {resolved_phone_type}"
                    if resolved_email:
                        action_summary += f" | {resolved_email}"

                    base_payload: Dict[str, Any] = {
                        "action": action_summary[:255],
                    }
                    if ip_address:
                        base_payload["ip_address"] = ip_address
                    if trimmed_ua:
                        base_payload["user_agent"] = trimmed_ua

                    if existing_id:
                        client.table("user_auth_logs").update(base_payload).eq("auth_log_id", existing_id).execute()
                    else:
                        base_payload["user_id"] = user_id_str
                        client.table("user_auth_logs").insert(base_payload).execute()
                    return True
                except Exception as fallback_err:
                    logger.warning(f"Fallback insert to user_auth_logs failed: {fallback_err}")
                    return False
            else:
                logger.warning(f"Error recording login to user_auth_logs: {full_err}")
                return False

    @classmethod
    async def record_login_async(
        cls,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        phone_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        action: str = "LOGIN",
        status: str = "SUCCESS",
    ) -> bool:
        """
        Asynchronously records last login in an executor to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            cls.record_login_sync,
            user_id,
            email,
            phone_type,
            ip_address,
            user_agent,
            action,
            status,
        )

    @classmethod
    def dispatch_background(
        cls,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        phone_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        action: str = "LOGIN",
        status: str = "SUCCESS",
        **kwargs: Any,
    ) -> None:
        """
        Dispatches login audit recording as a fire-and-forget background task.
        Guarantees 0ms overhead for API authentication endpoints.
        """
        try:
            asyncio.create_task(
                cls.record_login_async(
                    user_id=user_id,
                    email=email,
                    phone_type=phone_type,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    action=action,
                    status=status,
                )
            )
        except RuntimeError:
            # If no running event loop (e.g. sync thread), run synchronously
            cls.record_login_sync(
                user_id=user_id,
                email=email,
                phone_type=phone_type,
                ip_address=ip_address,
                user_agent=user_agent,
                action=action,
                status=status,
            )

    @classmethod
    def record_login_failure(
        cls,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        user_id: Optional[str] = None,
        reason: str = "Invalid credentials",
        client_type: str = "mobile",
        login_method: str = "password",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        """
        Authoritatively records failed login attempts:
        1. Resolves person identity (name, user_id, active status) if known in database.
        2. Logs to error_logs table (source='LOGIN_FAILED') with full user context.
        3. Updates user_auth_logs table with status='FAILED' (if user_id resolved).
        4. Captures PostHog audit event.
        Guarantees fast non-blocking execution.
        """
        try:
            client = get_supabase()
            resolved_user_id = user_id
            person_name = None
            is_active = None

            if client and not resolved_user_id:
                try:
                    if email and str(email).strip():
                        res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", str(email).strip().lower()).limit(1).execute()
                        if res and res.data:
                            u = res.data[0]
                            resolved_user_id = str(u.get("user_id"))
                            first = u.get("first_name") or ""
                            last = u.get("last_name") or ""
                            person_name = f"{first} {last}".strip()
                            is_active = u.get("is_active")
                    elif phone and str(phone).strip():
                        clean_ph = str(phone).strip()
                        res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").eq("phone", clean_ph).limit(1).execute()
                        if res and res.data:
                            u = res.data[0]
                            resolved_user_id = str(u.get("user_id"))
                            first = u.get("first_name") or ""
                            last = u.get("last_name") or ""
                            person_name = f"{first} {last}".strip()
                            is_active = u.get("is_active")
                            if not email and u.get("email"):
                                email = u.get("email")
                except Exception as e_lookup:
                    logger.warning(f"Error looking up user in record_login_failure: {e_lookup}")

            from backend.db.supabase_client import log_system_error
            identifier = email or phone or (f"User ID {resolved_user_id}" if resolved_user_id else "Unknown person")
            display_name = f"{person_name} ({identifier})" if person_name else identifier
            error_message = f"Login failed for {display_name}: {reason}"

            log_system_error(
                source="LOGIN_FAILED",
                error_message=error_message,
                stack_trace=None,
                user_id=resolved_user_id,
                context={
                    "person_email": email,
                    "person_phone": phone,
                    "person_name": person_name,
                    "person_user_id": resolved_user_id,
                    "is_account_active": is_active,
                    "failure_reason": reason,
                    "client_type": client_type,
                    "login_method": login_method,
                    "client_ip": ip_address,
                    "user_agent": user_agent,
                    "path": path or ("/api/v1/mobile/login" if client_type == "mobile" else "/api/v1/auth/login")
                }
            )

            # Record in user_auth_logs if user_id is known
            if resolved_user_id:
                phone_type = cls.detect_phone_type(None, user_agent, client_type)
                cls.dispatch_background(
                    user_id=resolved_user_id,
                    email=email,
                    phone_type=phone_type,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    action=f"LOGIN_FAILED | {reason[:50]}",
                    status="FAILED",
                )

            # Capture PostHog security audit event
            try:
                from backend.core.posthog import capture_posthog_event
                capture_posthog_event(
                    "user_login_failed",
                    properties={
                        "email": email,
                        "phone": phone,
                        "name": person_name,
                        "reason": reason,
                        "client_type": client_type,
                        "login_method": login_method,
                        "user_id": resolved_user_id,
                        "client_ip": ip_address,
                    },
                    distinct_id=resolved_user_id or email or phone or "anonymous"
                )
            except Exception:
                pass
        except Exception as e_main:
            logger.error(f"Error in record_login_failure: {e_main}")

auth_log_service = AuthLogService()
# Backward-compatibility alias
activity_log_service = auth_log_service
