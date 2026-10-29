import logging
import secrets
import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status

from backend.core.config import settings
from backend.core.security import create_access_token
from backend.db.redis_client import safe_get, safe_set, safe_delete
from backend.db.client import get_supabase

logger = logging.getLogger("token_service")

REFRESH_TOKEN_PREFIX = "rll:refresh_token:"
USER_TOKENS_PREFIX = "rll:user_refresh_tokens:"
ROTATION_GRACE_PREFIX = "rll:rotated_token:"


def generate_secure_random_token() -> str:
    """Generates a high-entropy cryptographically unpredictable opaque refresh token."""
    return secrets.token_urlsafe(48)


async def create_token_pair(
    user_data: Dict[str, Any],
    client_type: str = "mobile"
) -> Dict[str, Any]:
    """
    Creates a standard dual-token pair:
    1. Short-lived Access Token (JWT, defaults to 60 minutes).
    2. Long-lived Refresh Token (Opaque token, 30-day sliding window in Redis).
    """
    user_id = str(user_data.get("user_id") or "")
    email = str(user_data.get("email") or "")
    role_name = str(user_data.get("role_name") or user_data.get("role") or "tsm")
    roles = user_data.get("roles") or [role_name]
    tenant_id = str(user_data.get("tenant_id") or "")
    company_name = str(user_data.get("company_name") or "")

    # 1. Generate short-lived Access Token
    token_claims = {
        "sub": email,
        "user_id": user_id,
        "role": role_name,
        "roles": roles,
        "tenant_id": tenant_id,
        "company_name": company_name,
        "client_type": client_type,
        "token_type": "access",
        "jti": str(uuid.uuid4()),
    }

    is_review_user = bool(user_data.get("is_review_user") or user_id == settings.APP_REVIEW_USER_ID)
    if is_review_user:
        token_claims["is_review_user"] = True
        token_claims["allowed_hqs"] = user_data.get("allowed_hqs", ["All Headquarters"])
        access_delta = timedelta(hours=settings.APP_REVIEW_TOKEN_EXPIRE_HOURS)
    else:
        access_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(data=token_claims, expires_delta=access_delta)

    # 2. Generate long-lived Refresh Token (30-day rolling window)
    refresh_token = generate_secure_random_token()
    refresh_ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400  # 30 days in seconds

    refresh_payload = {
        "refresh_token": refresh_token,
        "user_id": user_id,
        "email": email,
        "role_name": role_name,
        "roles": roles,
        "tenant_id": tenant_id,
        "company_name": company_name,
        "client_type": client_type,
        "is_review_user": is_review_user,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_refreshed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store refresh token in Redis with 30-day TTL
    await safe_set(
        f"{REFRESH_TOKEN_PREFIX}{refresh_token}",
        json.dumps(refresh_payload),
        ttl=refresh_ttl
    )

    # Maintain user's active refresh tokens index for instant bulk revocation
    if user_id:
        try:
            user_tokens_key = f"{USER_TOKENS_PREFIX}{user_id}"
            existing_tokens_raw = await safe_get(user_tokens_key)
            tokens_list: List[str] = json.loads(existing_tokens_raw) if existing_tokens_raw else []
            # Prune list to at most 10 active devices/sessions
            tokens_list = [t for t in tokens_list if t != refresh_token]
            tokens_list.append(refresh_token)
            if len(tokens_list) > 10:
                tokens_list = tokens_list[-10:]
            await safe_set(user_tokens_key, json.dumps(tokens_list), ttl=refresh_ttl)
        except Exception as e_idx:
            logger.warning(f"Error updating user tokens index: {e_idx}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(access_delta.total_seconds()),
        "refresh_expires_in": refresh_ttl,
    }


async def refresh_session_async(refresh_token: str) -> Dict[str, Any]:
    """
    Validates the refresh token and issues a renewed access token and rotated refresh token.
    Implements a 30-day rolling window on every refresh, plus a 30-second grace period
    on rotated tokens to absorb concurrent network retries.
    """
    if not refresh_token or not refresh_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required."
        )

    clean_token = refresh_token.strip()

    # 1. Check if this token was recently rotated (Grace Period Handling)
    rotated_mapping_raw = await safe_get(f"{ROTATION_GRACE_PREFIX}{clean_token}")
    if rotated_mapping_raw:
        try:
            cached_result = json.loads(rotated_mapping_raw)
            logger.info("Token refresh hit rotation grace window. Replaying previous refresh response.")
            return cached_result
        except Exception:
            pass

    # 2. Fetch active refresh token from Redis
    raw_payload = await safe_get(f"{REFRESH_TOKEN_PREFIX}{clean_token}", security_sensitive=True)
    if not raw_payload:
        logger.warning(f"Token refresh rejected: token not found or expired in Redis.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please log in again."
        )

    try:
        session_data = json.loads(raw_payload)
    except Exception as e_parse:
        logger.error(f"Failed to parse refresh token payload: {e_parse}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Corrupted session payload. Please log in again."
        )

    user_id = session_data.get("user_id")
    email = session_data.get("email")

    # 3. Check instant user revocation flag
    if user_id:
        is_revoked = await safe_get(f"rll:revoked:{user_id}")
        if is_revoked:
            await safe_delete(f"{REFRESH_TOKEN_PREFIX}{clean_token}")
            logger.warning(f"Token refresh rejected: user {user_id} was revoked by admin.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked by administrator. Please log in again."
            )

    # 4. Authoritatively verify user is still active in database (or fast cache)
    client = get_supabase()
    user_data = {
        "user_id": user_id,
        "email": email,
        "role_name": session_data.get("role_name", "tsm"),
        "role": session_data.get("role_name", "tsm"),
        "roles": session_data.get("roles", ["tsm"]),
        "tenant_id": session_data.get("tenant_id"),
        "company_name": session_data.get("company_name", ""),
        "is_review_user": session_data.get("is_review_user", False),
    }

    if client and user_id and not session_data.get("is_review_user"):
        try:
            res = client.table("users").select("user_id, email, is_active, tenant_id").eq("user_id", str(user_id)).execute()
            if not res.data or len(res.data) == 0:
                await safe_delete(f"{REFRESH_TOKEN_PREFIX}{clean_token}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account no longer exists."
                )
            db_user = res.data[0]
            if not db_user.get("is_active", True):
                await safe_delete(f"{REFRESH_TOKEN_PREFIX}{clean_token}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is deactivated. Contact your administrator."
                )
            if db_user.get("tenant_id"):
                user_data["tenant_id"] = str(db_user["tenant_id"])
        except HTTPException:
            raise
        except Exception as e_db:
            logger.warning(f"Could not verify user status against DB during refresh: {e_db}")

    # 5. Issue new token pair with rolled 30-day window (Sliding Session)
    client_type = session_data.get("client_type", "mobile")
    new_pair = await create_token_pair(user_data, client_type=client_type)

    response_payload = {
        **new_pair,
        "user": user_data
    }

    # 6. Apply Grace Window to old refresh token (30 seconds)
    # This prevents parallel in-flight requests from failing with 401 when a refresh occurs
    grace_ttl = getattr(settings, "REFRESH_TOKEN_GRACE_SECONDS", 30)
    await safe_set(
        f"{ROTATION_GRACE_PREFIX}{clean_token}",
        json.dumps(response_payload),
        ttl=grace_ttl
    )
    # Remove old active token
    await safe_delete(f"{REFRESH_TOKEN_PREFIX}{clean_token}")

    logger.info(f"Token refresh successful for user {email} (Rolled 30-day session window extended).")
    return response_payload


async def revoke_refresh_token_async(refresh_token: str) -> None:
    """Revokes a single refresh token (e.g. during user logout)."""
    if refresh_token:
        clean = refresh_token.strip()
        await safe_delete(f"{REFRESH_TOKEN_PREFIX}{clean}")
        await safe_delete(f"{ROTATION_GRACE_PREFIX}{clean}")
        logger.info(f"Revoked refresh token: {clean[:8]}***")


async def revoke_all_user_tokens_async(user_id: str) -> int:
    """
    Revokes all active refresh tokens for a user (e.g. password change, admin lockout).
    Returns count of revoked tokens.
    """
    if not user_id:
        return 0

    user_tokens_key = f"{USER_TOKENS_PREFIX}{user_id}"
    raw = await safe_get(user_tokens_key)
    count = 0
    if raw:
        try:
            tokens: List[str] = json.loads(raw)
            for t in tokens:
                await safe_delete(f"{REFRESH_TOKEN_PREFIX}{t}")
                await safe_delete(f"{ROTATION_GRACE_PREFIX}{t}")
                count += 1
            await safe_delete(user_tokens_key)
        except Exception as e:
            logger.warning(f"Error purging user tokens: {e}")

    # Set instant revocation flag in Redis
    await safe_set(f"rll:revoked:{user_id}", "true", ttl=86400 * 30)
    logger.info(f"Revoked all {count} active sessions for user {user_id}.")
    return count

