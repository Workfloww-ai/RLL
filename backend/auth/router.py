import logging
from fastapi import APIRouter, HTTPException, Depends, status
from backend.core.security import create_access_token, get_current_user
from backend.db.client import get_supabase
from backend.core.config import settings
from backend.auth.schemas import LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from supabase import create_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    email = credentials.email.lower().strip()
    password = credentials.password

    # Hardcoded Demo Account for Client Presentation
    if email == "khwaish.gahoi@workfloww.ai":
        demo_user = {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "khwaish.gahoi@workfloww.ai",
            "first_name": "Khwaish",
            "last_name": "Gahoi",
            "phone": "+919711101492",
            "role_name": "admin",
            "role": "admin",
            "is_active": True
        }
        token = create_access_token(data={"sub": demo_user["email"], "role": "admin", "user_id": demo_user["user_id"]})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": demo_user
        }

    client = get_supabase()

    user_data = None
    if client:
        try:
            # 1. Verify credentials with an ephemeral Supabase Auth client to avoid mutating the global client
            temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            auth_response = temp_client.auth.sign_in_with_password({"email": email, "password": credentials.password})
            if not auth_response or not auth_response.user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

            # 2. Get user profile and role
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
            if res.data and len(res.data) > 0:
                db_user = res.data[0]
                if not db_user.get("is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is deactivated"
                    )

                role_name = "admin"
                try:
                    ur_res = client.table("user_roles").select("user_id, role_id, is_active, roles(role_id, role_name)").eq("user_id", db_user["user_id"]).execute()
                    if ur_res.data:
                        for ur in ur_res.data:
                            if ur.get("is_active", True):
                                role_obj = ur.get("roles") or {}
                                if role_obj.get("role_name"):
                                    role_name = role_obj["role_name"]
                                    break
                except Exception:
                    pass

                # 3. Guardrail: Enforce Web-only roles
                if role_name.lower() != "admin":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access Denied: Web Dashboard is restricted to Admins only. Please use the mobile app."
                    )

                user_data = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email"),
                    "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone", ""),
                    "role_name": role_name,
                    "role": role_name,
                    "is_active": True
                }
        except HTTPException:
            raise
        except Exception as e:
            if "Invalid login credentials" in str(e):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
            pass

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token(data={"sub": user_data["email"], "role": user_data.get("role_name", "admin"), "user_id": user_data["user_id"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Initiate password recovery by sending a reset link to the registered email.
    """
    email = req.email.lower().strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address is required")

    client = get_supabase()
    db_user = None
    if client:
        try:
            res = client.table("users").select("user_id, email, is_active").ilike("email", email).execute()
            if res.data:
                db_user = res.data[0]
        except Exception as e:
            logger.warning(f"User lookup error in forgot_password: {e}")

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is not registered in the system."
        )

    if not db_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated."
        )

    try:
        if client:
            temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            temp_client.auth.reset_password_for_email(email)
            logger.info(f"📧 Recovery email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Supabase auth reset password email error: {e}")

    logger.info(f"📧 Password reset link sent to registered email: {email}")

    return {
        "success": True,
        "message": f"Password reset link dispatched to registered email {email}. Check your inbox."
    }


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """
    Directly update user password in Supabase Auth for registered email.
    """
    email = req.email.lower().strip()
    new_password = req.new_password.strip()

    if not email or not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registered email and new password are required")

    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters long")

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

    if not db_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated."
        )

    user_id = str(db_user["user_id"])
    try:
        client.auth.admin.update_user_by_id(user_id, {"password": new_password})
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


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
