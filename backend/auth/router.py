import json
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status, Response, Request
from backend.core.security import create_access_token, get_current_user
from backend.db.client import get_supabase
from backend.db.redis_client import safe_set, safe_delete
from backend.core.config import settings
from backend.auth.schemas import LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from supabase import create_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


import secrets
import hashlib
from backend.core.security import create_access_token, get_current_user, validate_password_complexity, RoleChecker


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    redis_key = f"rll:ratelimit:login:{client_ip}"
    
    attempts = await safe_get(redis_key)
    if attempts:
        attempts_count = int(attempts)
        if attempts_count >= 5:
            logger.warning(f"Rate limit exceeded for IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later."
            )
        await safe_set(redis_key, str(attempts_count + 1), ttl=3600)
    else:
        await safe_set(redis_key, "1", ttl=3600)

    email = credentials.email.lower().strip()
    password = credentials.password
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
        logger.warning(f"Web login failed for user {email} (invalid credentials)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # 2. Fetch user profile from public.users
    res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
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

    # Clear any previous revocation flag upon fresh successful login
    await safe_delete(f"rll:revoked:{user_id_str}")

    # 3. Fetch user roles dynamically from public.user_roles
    active_roles = []
    role_name = "admin"
    try:
        ur_res = client.table("user_roles").select("user_id, role_id, is_active, roles(role_id, role_name)").eq("user_id", db_user["user_id"]).execute()
        if ur_res.data:
            for ur in ur_res.data:
                if ur.get("is_active", True):
                    role_obj = ur.get("roles") or {}
                    rname = role_obj.get("role_name")
                    if rname:
                        active_roles.append(rname)
            
            preferred_role = next((r for r in active_roles if r.lower() in ["admin", "super_admin", "super admin", "leader"]), None)
            if preferred_role:
                role_name = preferred_role
            elif active_roles:
                role_name = active_roles[0]
    except Exception as r_err:
        logger.warning(f"Error resolving roles for user {email}: {r_err}")

    # Guardrail: Enforce Web-only roles
    if role_name.lower() not in ["admin", "super_admin", "super admin", "leader"]:
        logger.warning(f"Web login access denied for user {email} (role '{role_name}' lacks Web permissions)")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Web Dashboard is restricted to Administrators only."
        )

    user_data = {
        "user_id": user_id_str,
        "email": db_user.get("email"),
        "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
        "last_name": db_user.get("last_name", ""),
        "phone": db_user.get("phone", ""),
        "role_name": role_name,
        "role": role_name,
        "roles": active_roles if active_roles else [role_name],
        "is_active": True
    }
    logger.info(f"Web login successful for user: {email} with role: {role_name}")

    token = create_access_token(data={"sub": user_data["email"], "role": user_data.get("role_name", "admin"), "user_id": user_data["user_id"]})

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
    """
    email = req.email.lower().strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address is required")

    client = get_supabase()
    if client:
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
    """
    email = req.email.lower().strip()
    otp = req.otp.strip()
    new_password = req.new_password.strip()

    if not email or not otp or not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email, OTP, and new password are required")

    # Validate password complexity (6+ chars, uppercase, number, special char)
    validate_password_complexity(new_password)

    from backend.db.redis_client import safe_get
    stored_otp_raw = await safe_get(f"rll:otp:{email}")
    if not stored_otp_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code. Please request a new password reset code."
        )

    try:
        stored_data = json.loads(stored_otp_raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP state.")

    if stored_data.get("attempts", 0) >= 3:
        await safe_delete(f"rll:otp:{email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum OTP verification attempts exceeded. Please request a new code."
        )

    provided_hash = hashlib.sha256(otp.encode()).hexdigest()
    if provided_hash != stored_data.get("hash"):
        stored_data["attempts"] = stored_data.get("attempts", 0) + 1
        await safe_set(f"rll:otp:{email}", json.dumps(stored_data), ttl=600)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect OTP code. {3 - stored_data['attempts']} attempt(s) remaining."
        )

    client = get_supabase()
    db_user = None
    if client:
        try:
            res = client.table("users").select("user_id, email, is_active").ilike("email", email).execute()
            if res.data:
                db_user = res.data[0]
        except Exception as e:
            logger.warning(f"User lookup error in reset_password: {e}")

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is not registered in the system."
        )

    user_id = str(db_user["user_id"])
    try:
        client.auth.admin.update_user_by_id(user_id, {"password": new_password})
        # Clear consumed OTP from Redis
        await safe_delete(f"rll:otp:{email}")
        logger.info(f"Password updated successfully in Supabase Auth for {email}")
    except Exception as e:
        logger.error(f"Error updating user password in Supabase Auth: {e}")
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
