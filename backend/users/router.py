from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException
from backend.users.service import user_service

router = APIRouter(prefix="/users", tags=["Users & Role Management"])


@router.get("/")
async def list_users():
    return user_service.list_users()


@router.post("/")
async def create_user(payload: Dict[str, Any]):
    return user_service.create_user(payload)

@router.get("/roles")
async def list_roles():
    return user_service.list_roles()

@router.get("/hierarchy")
async def get_hierarchy():
    return user_service.get_hierarchy()

@router.post("/upload-roster")
async def upload_roster(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv', '.xlsb')):
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, .xlsb, or .csv files are supported.")
    
    contents = await file.read()
    try:
        res = user_service.process_excel_roster(contents, file.filename)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{user_id}")
async def update_user(user_id: str, payload: Dict[str, Any]):
    return user_service.update_user(user_id, payload)


@router.delete("/{user_id}")
async def delete_user(user_id: str):
    success = user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete user.")
    return {"message": "User deleted successfully", "user_id": user_id}


