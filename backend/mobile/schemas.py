from typing import Optional, List
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class MobileLoginRequest(BaseModel):
    email: str
    password: str


class MobileLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
