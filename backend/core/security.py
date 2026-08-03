from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import settings

security = HTTPBearer(auto_error=False)

# Mock user database for local testing when Auth service is not yet populated
MOCK_USERS: Dict[str, Dict[str, Any]] = {
    "admin@rll.gov.in": {
        "user_id": "fb2ce618-afbf-4eb9-b4a0-732651b2d99f",
        "email": "admin@rll.gov.in",
        "first_name": "System",
        "last_name": "Admin",
        "role_id": 1,
        "role_name": "admin",
        "office_id": 1,
        "circle_id": None,
        "depot_id": None,
        "is_active": True
    },
    "manager@rll.gov.in": {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "email": "manager@rll.gov.in",
        "first_name": "Regional",
        "last_name": "Manager",
        "role_id": 2,
        "role_name": "regional_manager",
        "office_id": 1,
        "circle_id": 1,
        "depot_id": None,
        "is_active": True
    },
    "salesrep@rll.gov.in": {
        "user_id": "00000000-0000-0000-0000-000000000003",
        "email": "salesrep@rll.gov.in",
        "first_name": "Sales",
        "last_name": "Representative",
        "role_id": 3,
        "role_name": "sales_representative",
        "office_id": 1,
        "circle_id": 1,
        "depot_id": 1,
        "is_active": True
    }
}

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

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    if not credentials:
        # Default mock admin user if unauthenticated in dev environment
        return MOCK_USERS["admin@rll.gov.in"]
    
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email = payload.get("sub")
    if email in MOCK_USERS:
        return MOCK_USERS[email]
    
    return {
        "user_id": payload.get("user_id", "00000000-0000-0000-0000-000000000000"),
        "email": email,
        "role_name": payload.get("role", "admin"),
        "is_active": True
    }

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role_name", "admin")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role '{user_role}'. Required roles: {self.allowed_roles}"
            )
        return current_user
