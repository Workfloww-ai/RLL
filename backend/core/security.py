import logging
import json
import time
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.config import settings
from backend.db.client import get_supabase
from backend.db.redis_client import safe_get

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

def validate_password_complexity(password: str) -> None:
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter (A-Z)."
        )
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number (0-9)."
        )
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one special character (!@#$%^&* etc.)."
        )

_LOCAL_USER_PROFILES: Dict[str, Any] = {}
_LOCAL_USER_PROFILE_TTL = 300.0  # 5 minutes

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Authoritative authentication dependency.
    Extracts user identity from session cookie or Bearer JWT, then validates the user
    and their active roles against the authoritative database.
    Fails closed on database errors or missing users. Never constructs synthetic fallback users.
    """
    session_token = request.cookies.get("rll_session")
    email = None
    user_id = None
    payload: Optional[dict] = None

    if session_token:
        redis_session_raw = await safe_get(f"rll:session:{session_token}")
        if redis_session_raw:
            try:
                session_data = json.loads(redis_session_raw)
                email = session_data.get("email")
                user_id = session_data.get("user_id")
            except Exception:
                pass

    if not email and credentials and credentials.credentials:
        token = credentials.credentials
        if not (token.startswith("demo-token-") or token.startswith("google-token-")):
            payload = decode_access_token(token)
            if payload:
                email = payload.get("sub")
                user_id = payload.get("user_id")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Instant revocation check in Redis (must run before returning cached profile)
    if user_id:
        is_revoked = await safe_get(f"rll:revoked:{user_id}")
        if is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked by administrator. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    email_key = email.lower()
    now_t = time.time()

    # 2. Fast RAM Profile Cache HIT (< 0.01ms)
    if email_key in _LOCAL_USER_PROFILES:
        ts, prof = _LOCAL_USER_PROFILES[email_key]
        if now_t - ts < _LOCAL_USER_PROFILE_TTL:
            if prof and prof.get("is_active"):
                return prof

    # 3. Fast Redis Profile Cache HIT (< 1ms)
    user_cache_key = f"rll:user_profile:{email_key}"
    cached_profile = await safe_get(user_cache_key)
    if cached_profile:
        try:
            user_info = json.loads(cached_profile)
            if user_info and isinstance(user_info, dict) and user_info.get("is_active"):
                if payload and isinstance(payload, dict) and payload.get("allowed_hqs"):
                    user_info["allowed_hqs"] = payload["allowed_hqs"]
                _LOCAL_USER_PROFILES[email_key] = (now_t, user_info)
                return user_info
        except Exception:
            pass

    # 4. Authoritative Database Lookup (Strict Fail-Closed with Stable Identity)
    client = get_supabase()
    if not client:
        logger.error("Authentication failed: Supabase client unavailable during lookup")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable: database connection could not be established"
        )

    try:
        # Prefer immutable user_id for lookup if present in token/session claims
        if user_id:
            res = client.table("users").select(
                "user_id, email, first_name, last_name, phone, is_active, tenant_id"
            ).eq("user_id", str(user_id)).execute()
        else:
            res = client.table("users").select(
                "user_id, email, first_name, last_name, phone, is_active, tenant_id"
            ).ilike("email", email.strip()).execute()
    except Exception as e_db:
        logger.error("Authentication failed: Database query exception: %s", type(e_db).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable: database lookup failed"
        )

    if not res.data or len(res.data) == 0:
        logger.warning("Authentication rejected: User not found in database")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not authorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Detect ambiguous identity when querying by email
    if len(res.data) > 1:
        logger.error("Authentication rejected: Multiple user records match identity")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ambiguous user identity: multiple user accounts matched",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_user = res.data[0]

    # Verify claim consistency: if email was in token/session, it must match db_user email
    if email and db_user.get("email") and db_user["email"].strip().lower() != email.strip().lower():
        logger.warning("Authentication rejected: Identity claim mismatch between token and database record")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity claim mismatch",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate explicit, valid active status (reject missing, None, False, or malformed non-True)
    if db_user.get("is_active") is not True:
        logger.warning("Authentication rejected: Account is inactive or invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 5. Authoritative Role Resolution from public.user_roles (Fail Closed on Error)
    active_roles: List[str] = []
    authoritative_role = "unassigned"
    try:
        ur_res = client.table("user_roles").select(
            "user_id, role_id, is_active, roles(role_id, role_name)"
        ).eq("user_id", db_user["user_id"]).execute()
    except Exception as e_role:
        logger.error("Authentication failed: Exception during user_roles query: %s", type(e_role).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable: role verification failed"
        )

    if ur_res.data:
        for ur in ur_res.data:
            if ur.get("is_active") is True:
                role_obj = ur.get("roles") or {}
                rname = role_obj.get("role_name")
                if rname and isinstance(rname, str) and rname.strip():
                    active_roles.append(rname.strip())

        # Priority resolution among the user's verified database roles
        role_priority = [
            "super_admin", "superadmin", "super admin",
            "admin", "developer", "leader", "team_leader", "team leader",
            "tsm", "ase", "territory executive", "viewer"
        ]
        for prio in role_priority:
            matched = next((r for r in active_roles if r.lower() == prio), None)
            if matched:
                authoritative_role = matched
                break
        if authoritative_role == "unassigned" and active_roles:
            authoritative_role = active_roles[0]

    user_info = {
        "user_id": str(db_user.get("user_id")),
        "email": db_user.get("email"),
        "first_name": db_user.get("first_name", ""),
        "last_name": db_user.get("last_name", ""),
        "phone": db_user.get("phone", ""),
        "role_name": authoritative_role,
        "role": authoritative_role,
        "roles": active_roles if active_roles else ([authoritative_role] if authoritative_role != "unassigned" else []),
        "tenant_id": str(db_user.get("tenant_id")) if db_user.get("tenant_id") else None,
        "is_active": True
    }

    if payload and isinstance(payload, dict) and payload.get("allowed_hqs"):
        user_info["allowed_hqs"] = payload["allowed_hqs"]

    # 6. Cache verified profile in Redis & RAM
    try:
        from backend.db.redis_client import safe_set
        await safe_set(user_cache_key, json.dumps(user_info), ttl=300)
    except Exception:
        pass
    _LOCAL_USER_PROFILES[email_key] = (now_t, user_info)

    return user_info


class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = [r.lower() for r in allowed_roles]

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("role_name") or current_user.get("role") or "").strip().lower()
        user_roles = {r.strip().lower() for r in current_user.get("roles", []) if isinstance(r, str)}
        if user_role:
            user_roles.add(user_role)

        allowed = set(self.allowed_roles)
        admin_roles = {"admin", "super_admin", "superadmin", "super admin"}

        # User is authorized if any assigned role matches an allowed role,
        # or if user holds an administrator role.
        # "unassigned", unknown roles, or missing roles NEVER match admin_roles or allowed.
        has_permission = bool(user_roles.intersection(allowed)) or bool(user_roles.intersection(admin_roles))
        if has_permission:
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: user role '{user_role}' is not authorized for this operation"
        )


class StrictRoleChecker:
    """Role checker that requires an EXACT match with allowed_roles without automatic admin fallback."""
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = [r.lower() for r in allowed_roles]

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("role_name") or current_user.get("role") or "").strip().lower()
        if user_role in self.allowed_roles:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: operation restricted to roles {self.allowed_roles}. Current role '{user_role}' is not authorized."
        )


developer_only = StrictRoleChecker(["developer"])


