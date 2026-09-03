from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import settings
from backend.db.client import get_supabase

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

import json
from fastapi import Depends, HTTPException, status, Request
from backend.db.redis_client import safe_get

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    session_token = request.cookies.get("rll_session")
    email = None
    user_id = None
    role_name = None

    if session_token:
        redis_session_raw = await safe_get(f"rll:session:{session_token}")
        if redis_session_raw:
            try:
                session_data = json.loads(redis_session_raw)
                email = session_data.get("email")
                user_id = session_data.get("user_id")
                role_name = session_data.get("role")
            except Exception:
                pass

    if not email and credentials and credentials.credentials:
        token = credentials.credentials
        if not (token.startswith("demo-token-") or token.startswith("google-token-")):
            payload = decode_access_token(token)
            if payload:
                email = payload.get("sub")
                user_id = payload.get("user_id")
                role_name = payload.get("role", "admin")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client = get_supabase()
    user_info = None

    if client:
        try:
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
            if res.data and len(res.data) > 0:
                db_user = res.data[0]
                if not db_user.get("is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is deactivated",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                
                if not role_name:
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

                user_info = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email"),
                    "first_name": db_user.get("first_name", ""),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone", ""),
                    "role_name": role_name,
                    "role": role_name,
                    "is_active": True
                }
        except HTTPException:
            raise
        except Exception as e_db:
            if email and user_id:
                user_info = {
                    "user_id": str(user_id),
                    "email": email,
                    "first_name": email.split("@")[0].capitalize(),
                    "last_name": "",
                    "phone": "",
                    "role_name": role_name or "admin",
                    "role": role_name or "admin",
                    "is_active": True
                }

    if not user_info:
        if email and user_id:
            user_info = {
                "user_id": str(user_id),
                "email": email,
                "first_name": email.split("@")[0].capitalize(),
                "last_name": "",
                "phone": "",
                "role_name": role_name or "admin",
                "role": role_name or "admin",
                "is_active": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user_info

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("role_name") or current_user.get("role") or "").lower()
        allowed = {r.lower() for r in self.allowed_roles}
        if "admin" in allowed or "super_admin" in allowed or user_role in allowed or user_role in {"admin", "super_admin"}:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: user role '{user_role}' is not authorized for this operation"
        )

