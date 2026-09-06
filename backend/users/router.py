import json
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from backend.users.service import user_service
from backend.db.redis_client import safe_get, safe_set, safe_delete
from backend.core.security import RoleChecker, get_current_user

logger = logging.getLogger(__name__)

admin_only = RoleChecker(["admin", "super_admin"])

router = APIRouter(
    prefix="/users", 
    tags=["Users & Role Management"],
    dependencies=[Depends(admin_only)]
)

async def invalidate_user_and_territory_caches():
    """Purge Redis caches when users, roles, or territory assignments change."""
    await safe_delete("rll:cache:users_list")
    await safe_delete("rll:cache:depots_list")
    await safe_delete("rll:cache:headquarters_list")
    await safe_delete("rll:cache:roles_list")


@router.get("/")
async def list_users():
    cached = await safe_get("rll:cache:users_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached users_list: {e}")

    data = user_service.list_users()
    if data:
        await safe_set("rll:cache:users_list", json.dumps(data), ttl=86400)
    return data


@router.post("/")
async def create_user(payload: Dict[str, Any]):
    res = user_service.create_user(payload)
    await invalidate_user_and_territory_caches()
    return res


@router.get("/roles")
async def list_roles():
    cached = await safe_get("rll:cache:roles_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached roles_list: {e}")

    data = user_service.list_roles()
    if data:
        await safe_set("rll:cache:roles_list", json.dumps(data), ttl=86400)
    return data


@router.post("/roles")
async def create_role(payload: Dict[str, Any]):
    try:
        res = user_service.create_role(payload)
        await invalidate_user_and_territory_caches()
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: Dict[str, Any]):
    try:
        res = user_service.update_role(role_id, payload)
        await invalidate_user_and_territory_caches()
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str):
    success = user_service.delete_role(role_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete role.")
    await invalidate_user_and_territory_caches()
    return {"message": "Role deleted successfully"}


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
        await invalidate_user_and_territory_caches()
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}")
async def update_user(user_id: str, payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    is_active_val = payload.get("is_active", payload.get("isActive"))
    
    # Prevent self-deactivation
    if (is_active_val is False or is_active_val == "inactive") and str(current_user.get("user_id")) == str(user_id):
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    res = user_service.update_user(user_id, payload)
    
    # Instant Remote User Revocation integration:
    # If user account is set to inactive/deactivated, revoke all active sessions in Redis immediately.
    # If user account is re-activated, clear any revocation flag.
    is_active_val = payload.get("is_active", payload.get("isActive"))
    if is_active_val is False or is_active_val == "inactive":
        await safe_set(f"rll:revoked:{user_id}", "true", ttl=86400 * 30)
        logger.info(f"Instant Remote User Revocation executed for deactivated user: {user_id}")
    elif is_active_val is True or is_active_val == "active":
        await safe_delete(f"rll:revoked:{user_id}")
        logger.info(f"Revocation flag cleared for reactivated user: {user_id}")

    await invalidate_user_and_territory_caches()
    return res


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if str(current_user.get("user_id")) == str(user_id):
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    success = user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete user.")
    
    # Instantly revoke all active sessions for deleted user
    await safe_set(f"rll:revoked:{user_id}", "true", ttl=86400 * 30)
    logger.info(f"Instant Remote User Revocation executed for deleted user: {user_id}")
    await invalidate_user_and_territory_caches()
    return {"message": "User deleted successfully", "user_id": user_id}



