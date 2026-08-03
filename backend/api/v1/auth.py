from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from backend.core.security import create_access_token, get_current_user, MOCK_USERS

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    email = credentials.email.lower().strip()
    user = MOCK_USERS.get(email)
    if not user:
        # Default fallback to admin for testing
        user = MOCK_USERS["admin@rll.gov.in"]
    
    token = create_access_token(data={"sub": user["email"], "role": user["role_name"], "user_id": user["user_id"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
