from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from backend.services.user_service import user_service

router = APIRouter(prefix="/users", tags=["Users & Role Management"])

@router.get("/")
async def list_users():
    return user_service.list_users()

@router.post("/")
async def create_user(payload: Dict[str, Any]):
    return user_service.create_user(payload)

@router.put("/{user_id}")
async def update_user(user_id: str, payload: Dict[str, Any]):
    return user_service.update_user(user_id, payload)

@router.delete("/{user_id}")
async def delete_user(user_id: str):
    success = user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete user.")
    return {"message": "User deleted successfully", "user_id": user_id}

@router.post("/upload-roster")
async def upload_roster(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, or .csv files are supported.")
    
    contents = await file.read()
    try:
        res = user_service.process_excel_roster(contents, file.filename)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/roles")
async def list_roles():
    return [
        {"role_id": 1, "role_name": "Area Sales Executive", "description": "Circle / Area Sales Manager (TSM)"},
        {"role_id": 2, "role_name": "Territory Sales Manager", "description": "Depot Field Sales Executive (ASE)"},
        {"role_id": 3, "role_name": "Leadership", "description": "Regional Supervisor"},
        {"role_id": 4, "role_name": "Admin", "description": "System Administrator with full access"}
    ]

