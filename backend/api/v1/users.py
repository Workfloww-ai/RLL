from typing import List
from fastapi import APIRouter, Depends
from backend.core.security import get_current_user, RoleChecker, MOCK_USERS

router = APIRouter(prefix="/users", tags=["Users & Role Management"])

admin_only = RoleChecker(["admin"])

@router.get("/", dependencies=[Depends(admin_only)])
async def list_users():
    return list(MOCK_USERS.values())

@router.get("/roles")
async def list_roles():
    return [
        {"role_id": 1, "role_name": "admin", "description": "System Administrator with full access"},
        {"role_id": 2, "role_name": "management", "description": "Executive Management Dashboard User"},
        {"role_id": 3, "role_name": "regional_manager", "description": "Circle / Regional Manager"},
        {"role_id": 4, "role_name": "sales_representative", "description": "Depot Field Sales Representative"}
    ]
