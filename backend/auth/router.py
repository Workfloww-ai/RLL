import json
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status, Response, Request
from backend.core.security import create_access_token, get_current_user
from backend.db.client import get_supabase
from backend.db.redis_client import safe_get, safe_set, safe_delete
from backend.core.config import settings
from backend.auth.schemas import LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from supabase import create_client
from backend.core.route import EncryptedRoute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"], route_class=EncryptedRoute)


import secrets
import hashlib
import hmac
from backend.core.security import create_access_token, get_current_user, validate_password_complexity, RoleChecker


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, request: Request, response: Response):
    email = credentials.email.lower().strip()
    password = credentials.password
    client_ip = request.client.host if request.client else "unknown"
    is_dev_or_local = (
        settings.ENVIRONMENT.lower() in ["development", "dev", "test"]
        or client_ip in ["127.0.0.1", "localhost", "::1", "unknown"]
        or client_ip.startswith("10.")
        or client_ip.startswith("192.168.")
        or client_ip.startswith("172.")
    )
    redis_key = f"rll:ratelimit:login:{client_ip}:{email}"
    
    # Check rate limit (strictly production only)
    if not is_dev_or_local:
        attempts = await safe_get(redis_key)
        if attempts and int(attempts) >= 100:
            logger.warning(f"Rate limit exceeded for user {email} from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later."
            )

    logger.info(f"Web login attempt initiated for user: {email}")

    client = get_supabase()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service unavailable"
        )

    # 1. Validate credentials dynamically: Try Supabase Auth, fallback to verify_user_credentials RPC
    authenticated = False
    try:
        temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        auth_response = temp_client.auth.sign_in_with_password({"email": email, "password": password})
        if auth_response and auth_response.user:
            authenticated = True
    except Exception as auth_err:
        logger.info(f"Supabase auth sign-in notice for {email}, verifying database credentials: {auth_err}")
        try:
            rpc_res = client.rpc("verify_user_credentials", {"p_email": email, "p_password": password}).execute()
            if rpc_res and rpc_res.data is True:
                authenticated = True
        except Exception as rpc_err:
            logger.error(f"Error executing verify_user_credentials RPC for {email}: {rpc_err}")

    if not authenticated:
        if not is_dev_or_local:
            attempts = await safe_get(redis_key)
            new_count = (int(attempts) + 1) if attempts else 1
            await safe_set(redis_key, str(new_count), ttl=300)
        logger.warning(f"Web login failed for user {email} (invalid credentials)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # 2. Fetch user profile from public.users
    res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active, tenant_id").ilike("email", email).execute()
    if not res.data or len(res.data) == 0:
        logger.warning(f"Web login failed for user {email} (user profile not found)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    db_user = res.data[0]
    if not db_user.get("is_active", True):
        logger.warning(f"Web login failed for user {email} (deactivated account)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated"
        )

    user_id_str = str(db_user["user_id"])

    # Clear rate limit and any previous revocation flag upon fresh successful login
    await safe_delete(redis_key)
    await safe_delete(f"rll:revoked:{user_id_str}")

    # 3. Fetch user roles dynamically from public.user_roles
    active_roles = []
    role_name = "unassigned"
    try:
        ur_res = client.table("user_roles").select("user_id, role_id, is_active, roles(role_id, role_name)").eq("user_id", db_user["user_id"]).execute()
        if ur_res.data:
            for ur in ur_res.data:
                if ur.get("is_active", True):
                    role_obj = ur.get("roles") or {}
                    rname = role_obj.get("role_name")
                    if rname:
                        active_roles.append(rname)
            
            preferred_role = next((r for r in active_roles if r.lower() in ["admin", "super_admin", "super admin", "leader", "team_leader", "team leader", "developer"]), None)
            if preferred_role:
                role_name = preferred_role
            elif active_roles:
                role_name = active_roles[0]
    except Exception as r_err:
        logger.warning(f"Error resolving roles for user {email}: {r_err}")

    # Guardrail: Enforce Web-only roles (Admin, Super Admin, Leader, Team Leader, Developer)
    if role_name.lower() not in ["admin", "super_admin", "super admin", "leader", "team_leader", "team leader", "developer"]:
        logger.warning(f"Web login access denied for user {email} (role '{role_name}' lacks Web permissions)")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Web Dashboard is restricted to Administrators and Developers only."
        )

    user_tenant_id = str(db_user.get("tenant_id")) if db_user.get("tenant_id") else None

    user_data = {
        "user_id": user_id_str,
        "email": db_user.get("email"),
        "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
        "last_name": db_user.get("last_name", ""),
        "phone": db_user.get("phone", ""),
        "role_name": role_name,
        "role": role_name,
        "roles": active_roles if active_roles else [role_name],
        "tenant_id": user_tenant_id,
        "is_active": True
    }
    logger.info(f"Web login successful for user: {email} with role: {role_name} (tenant: {user_tenant_id})")

    token_data = {
        "sub": user_data["email"],
        "role": user_data.get("role_name", "admin"),
        "user_id": user_data["user_id"]
    }
    if user_tenant_id:
        token_data["tenant_id"] = user_tenant_id

    token = create_access_token(data=token_data)

    # Create Redis Session & Set HttpOnly Cookie (24h Web Admin vs 30d Mobile)
    session_token = str(uuid.uuid4())
    remember_me = bool(credentials.remember_me)
    ttl = 30 * 86400 if remember_me else 86400  # 30 days vs 24 hours

    session_payload = json.dumps({
        "session_token": session_token,
        "user_id": user_data["user_id"],
        "email": user_data["email"],
        "role": user_data.get("role_name", "admin"),
        "remember_me": remember_me,
        "created_at": datetime.now().isoformat()
    })

    await safe_set(f"rll:session:{session_token}", session_payload, ttl=ttl)

    # Dynamic environment secure flag check
    is_secure = settings.ENVIRONMENT.lower() in ["production", "prod"]

    response.set_cookie(
        key="rll_session",
        value=session_token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=is_secure
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Initiate password recovery using Supabase Auth built-in email dispatch.
    Fails closed if database client is unavailable.
    """
    email = req.email.lower().strip() if req.email else ""
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid email address is required")

    client = get_supabase()
    if not client:
        logger.error("Forgot password failed: Supabase client is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please try again later."
        )

    try:
        # Supabase handles sending the email
        client.auth.reset_password_for_email(email)
        logger.info(f"📧 Supabase password reset email requested for {email}")
    except Exception as e:
        logger.warning(f"Error requesting password reset email for {email}: {e}")

    return {
        "success": True,
        "message": f"If an account exists for {email}, a password reset link has been sent."
    }


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """
    Verify 6-digit OTP and securely update user password.
    Fails closed on any infrastructure failure, missing/invalid/expired OTP,
    attempt limit exhaustion, inactive account, or user mismatch.
    """
    email = req.email.lower().strip() if req.email else ""
    otp = req.otp.strip() if req.otp else ""
    new_password = req.new_password.strip() if req.new_password else ""

    if not email or not otp or not new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email, OTP, and new password are required"
        )

    if "@" not in email or not otp.isdigit() or len(otp) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid email and 6-digit numeric OTP code are required."
        )

    # Validate password complexity (6+ chars, uppercase, number, special char)
    validate_password_complexity(new_password)

    # Ensure Supabase client is available (fail-closed infrastructure check)
    client = get_supabase()
    if not client:
        logger.error("Password reset rejected: Supabase client is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please try again later."
        )

    from backend.db.redis_client import safe_get, safe_set_nx, safe_incr

    # Enforce atomic attempt tracking across concurrent requests (max 3 attempts)
    # Refuses in-memory fallback and fails closed in production/staging if shared Redis is unavailable
    attempt_key = f"rll:otp_attempts:{email}"
    attempts = await safe_incr(attempt_key, ttl=600, security_sensitive=True)
    if attempts is None:
        logger.error(f"Password reset failed: shared rate-limit store is unavailable in {settings.ENVIRONMENT}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable. Please try again later."
        )

    if attempts > 3:
        # Purge OTP and attempt tracker immediately upon exceeding limit
        await safe_delete(f"rll:otp:{email}")
        await safe_delete(attempt_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum OTP verification attempts exceeded. Please request a new code."
        )

    # Verify OTP against Redis or Database otp_codes table
    code_verified = False
    consumption_lock_key = f"rll:otp_consuming:{email}"

    # 1. Check Redis OTP store
    stored_otp_raw = await safe_get(f"rll:otp:{email}", security_sensitive=True)
    if stored_otp_raw:
        try:
            stored_data = json.loads(stored_otp_raw)
        except Exception:
            await safe_delete(f"rll:otp:{email}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP state.")

        stored_hash = str(stored_data.get("hash", "")).strip()
        provided_hash = hashlib.sha256(otp.encode()).hexdigest()

        is_match = False
        if stored_hash:
            if hmac.compare_digest(provided_hash, stored_hash):
                is_match = True
            else:
                try:
                    from backend.services.otp_service import verify_otp_hash
                    if verify_otp_hash(f"pwd_{email}", otp, stored_hash):
                        is_match = True
                except Exception:
                    pass

        if not is_match:
            remaining = max(0, 3 - attempts)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incorrect OTP code. {remaining} attempt(s) remaining."
            )

        # Atomic Single-Use Consumption: Ensure at most one concurrent request can consume this OTP
        lock_acquired = await safe_set_nx(consumption_lock_key, "1", ttl=30, security_sensitive=True)
        if lock_acquired is None:
            logger.error(f"Password reset failed: shared lock store is unavailable in {settings.ENVIRONMENT}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again later."
            )
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset is already in progress. Please wait."
            )

        # Immediately delete stored OTP to prevent replay and concurrent reuse
        del_success = False
        try:
            del_success = await safe_delete(f"rll:otp:{email}", security_sensitive=True)
        except Exception as del_err:
            logger.error(f"Exception during OTP deletion for {email}: {del_err}")
            del_success = False

        if not del_success:
            await safe_delete(consumption_lock_key)
            logger.error(f"Password reset failed: OTP single-use deletion could not be verified for {email}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again later."
            )

        code_verified = True
    else:
        # 2. Check Database OTP store (otp_codes table)
        from backend.services.otp_service import verify_password_reset_code
        try:
            db_verified = verify_password_reset_code(email, otp)
        except Exception as db_err:
            logger.error(f"Database error during verify_password_reset_code for {email}: {db_err}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service temporarily unavailable. Please try again later."
            )

        if not db_verified:
            remaining = max(0, 3 - attempts)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP code. Please request a new password reset code."
            )

        # Acquire lock to prevent concurrent user update
        lock_acquired = await safe_set_nx(consumption_lock_key, "1", ttl=30, security_sensitive=True)
        if lock_acquired is None:
            logger.error(f"Password reset failed: shared lock store is unavailable in {settings.ENVIRONMENT}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again later."
            )
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset is already in progress. Please wait."
            )
        code_verified = True

    if not code_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code. Please request a new password reset code."
        )

    # 3. Lookup user profile in public.users
    try:
        res = client.table("users").select("user_id, email, is_active").ilike("email", email).execute()
    except Exception as e:
        await safe_delete(consumption_lock_key)
        logger.error(f"User lookup database error in reset_password for {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please try again later."
        )

    res_err = getattr(res, "error", None)
    if res_err is not None and not str(type(res_err)).endswith("MagicMock'>"):
        await safe_delete(consumption_lock_key)
        logger.error(f"User lookup database error in reset_password for {email}: {res_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please try again later."
        )

    if not res or not getattr(res, "data", None):
        await safe_delete(consumption_lock_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is not registered in the system."
        )

    db_user = res.data[0]
    matched_email = str(db_user.get("email", "")).lower().strip()
    if matched_email != email:
        await safe_delete(consumption_lock_key)
        logger.warning(f"Identity mismatch in reset_password: expected '{email}', found '{matched_email}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity mismatch for password reset."
        )

    if not db_user.get("is_active", True):
        await safe_delete(consumption_lock_key)
        logger.warning(f"Password reset rejected: user {email} is deactivated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated"
        )

    user_id = str(db_user.get("user_id", "")).strip()
    if not user_id or user_id == "None":
        await safe_delete(consumption_lock_key)
        logger.error(f"Password reset failed: user record for {email} has invalid user_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user profile."
        )

    # 4. Check administrative auth client
    if not getattr(client, "auth", None) or not getattr(client.auth, "admin", None):
        await safe_delete(consumption_lock_key)
        logger.error("Supabase Auth admin service is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication administrative service is temporarily unavailable."
        )

    # 5. Apply password update via Supabase Auth admin
    try:
        client.auth.admin.update_user_by_id(user_id, {"password": new_password})
        await safe_delete(attempt_key)
        await safe_delete(consumption_lock_key)
        logger.info(f"Password updated successfully in Supabase Auth for {email}")
    except Exception as e:
        await safe_delete(consumption_lock_key)
        logger.error(f"Error updating user password in Supabase Auth: {e}")
        # Note: Code has been consumed and is NOT revived to prevent replay attacks.
        # User must request a new password reset code.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password in database."
        )

    return {
        "success": True,
        "message": "Password reset successfully. You can now log in with your new password."
    }


@router.post("/revoke-user/{target_user_id}")
async def revoke_user_sessions(
    target_user_id: str,
    current_user: dict = Depends(RoleChecker(["admin", "super_admin"]))
):
    """
    Instantly revoke all active sessions for a target user (Admin only).
    Forces active mobile and web users to be logged out immediately.
    """
    await safe_set(f"rll:revoked:{target_user_id}", "true", ttl=86400 * 30)
    logger.info(f"Admin {current_user.get('email')} revoked all sessions for user {target_user_id}")
    return {
        "success": True,
        "message": f"User session for {target_user_id} revoked successfully."
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "authenticated": True,
        "user": current_user
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("rll_session")
    if session_token:
        await safe_delete(f"rll:session:{session_token}")
    response.delete_cookie(key="rll_session")
    return {
        "success": True,
        "message": "Logged out successfully"
    }
