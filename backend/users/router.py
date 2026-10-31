import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Header, Query
from backend.users.service import user_service
from backend.db.redis_client import safe_get, safe_set, safe_delete, safe_delete_pattern
from backend.core.security import RoleChecker, get_current_user
from backend.core.route import EncryptedRoute
from backend.core.system_lock import check_system_lock_or_raise, roster_upload_lock, check_upload_cooldown_or_raise, record_upload_completion

logger = logging.getLogger(__name__)

admin_only = RoleChecker(["admin", "super_admin", "developer"])

router = APIRouter(
    prefix="/users", 
    tags=["Users & Role Management"],
    dependencies=[Depends(admin_only)],
    route_class=EncryptedRoute
)

async def invalidate_user_and_territory_caches():
    """Purge Redis caches when users, roles, or territory assignments change."""
    await safe_delete_pattern("rll:cache:users_list*")
    await safe_delete("rll:cache:users_list:all")
    await safe_delete("rll:cache:users_list:a0000000-0000-0000-0000-000000000001")
    await safe_delete("rll:cache:depots_list")
    await safe_delete("rll:cache:headquarters_list")
    await safe_delete("rll:cache:roles_list")
    await safe_delete("rll:cache:master_lookups")
    await safe_delete_pattern("rll:mobile:sales:*")


async def refresh_users_list_cache(tenant_id: Optional[str] = None):
    """
    Write-through cache update:
    1. Immediately purges all stale users_list cache keys across all tenant variations.
    2. Queries the authoritative DB via user_service.list_users.
    3. Writes the latest refreshed user list directly into Redis.
    """
    await invalidate_user_and_territory_caches()

    tenants_to_refresh = set()
    if tenant_id:
        tenants_to_refresh.add(str(tenant_id))
    tenants_to_refresh.add("all")
    tenants_to_refresh.add("a0000000-0000-0000-0000-000000000001")

    for tid in tenants_to_refresh:
        query_tid = None if tid == "all" else tid
        try:
            fresh_users = user_service.list_users(tenant_id=query_tid)
            if fresh_users:
                cache_key = f"rll:cache:users_list:{tid}"
                await safe_set(cache_key, json.dumps(fresh_users), ttl=86400)
                logger.info(f"Write-through cache refreshed for key: {cache_key} ({len(fresh_users)} users)")
        except Exception as e_refresh:
            logger.warning(f"Notice refreshing users list cache for {tid}: {e_refresh}")


@router.get("/")
async def list_users(
    current_user: dict = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    tenant_id: Optional[str] = Query(None),
    fresh: bool = Query(False),
):
    target_tenant_id = x_tenant_id or tenant_id or (current_user.get("tenant_id") if current_user else None)
    cache_key = f"rll:cache:users_list:{target_tenant_id or 'all'}"
    if not fresh:
        cached = await safe_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning(f"Error parsing cached users_list: {e}")

    data = user_service.list_users(tenant_id=target_tenant_id)
    if data:
        await safe_set(cache_key, json.dumps(data), ttl=86400)
    return data


@router.post("/")
async def create_user(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    try:
        acting_user_id = current_user.get("user_id") if current_user else None
        acting_tenant_id = current_user.get("tenant_id") if current_user else None
        res = user_service.create_user(payload, created_by=acting_user_id)
        await refresh_users_list_cache(acting_tenant_id)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def create_role(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    try:
        acting_user_id = current_user.get("user_id") if current_user else None
        acting_tenant_id = current_user.get("tenant_id") if current_user else None
        res = user_service.create_role(payload, created_by=acting_user_id)
        await refresh_users_list_cache(acting_tenant_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    try:
        acting_user_id = current_user.get("user_id") if current_user else None
        acting_tenant_id = current_user.get("tenant_id") if current_user else None
        res = user_service.update_role(role_id, payload, updated_by=acting_user_id)
        await refresh_users_list_cache(acting_tenant_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    success = user_service.delete_role(role_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete role.")
    acting_tenant_id = current_user.get("tenant_id") if current_user else None
    await refresh_users_list_cache(acting_tenant_id)
    return {"message": "Role deleted successfully"}


@router.get("/hierarchy")
async def get_hierarchy():
    return user_service.get_hierarchy()


@router.post("/upload-roster")
async def upload_roster(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    check_upload_cooldown_or_raise()
    if not file.filename.endswith(('.xlsx', '.xls', '.csv', '.xlsb')):
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, .xlsb, or .csv files are supported.")
    
    with roster_upload_lock(file.filename):
        contents = await file.read()
        try:
            acting_user_id = current_user.get("user_id") if current_user else None
            acting_tenant_id = current_user.get("tenant_id") if current_user else None
            if not acting_tenant_id and acting_user_id:
                try:
                    from backend.db.supabase_client import get_supabase_client
                    client = get_supabase_client()
                    if client:
                        u_res = client.table("users").select("tenant_id").eq("user_id", str(acting_user_id)).limit(1).execute()
                        if u_res.data and u_res.data[0].get("tenant_id"):
                            acting_tenant_id = str(u_res.data[0]["tenant_id"])
                except Exception:
                    pass
            res = user_service.process_excel_roster(contents, file.filename, uploaded_by=acting_user_id, tenant_id=acting_tenant_id)
            await refresh_users_list_cache(acting_tenant_id)
            record_upload_completion("roster_upload", file.filename)
            return res
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}")
async def update_user(user_id: str, payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    is_active_val = payload.get("is_active", payload.get("isActive"))
    
    # Prevent self-deactivation
    if (is_active_val is False or is_active_val == "inactive") and str(current_user.get("user_id")) == str(user_id):
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    try:
        acting_user_id = current_user.get("user_id") if current_user else None
        acting_tenant_id = current_user.get("tenant_id") if current_user else None
        res = user_service.update_user(user_id, payload, updated_by=acting_user_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
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

    await refresh_users_list_cache(acting_tenant_id)
    return res


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    if str(current_user.get("user_id")) == str(user_id):
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    acting_user_id = current_user.get("user_id") if current_user else None
    acting_tenant_id = current_user.get("tenant_id") if current_user else None
    success = user_service.delete_user(user_id, deleted_by=acting_user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete user.")
    
    # Instantly revoke all active sessions for deleted user
    await safe_set(f"rll:revoked:{user_id}", "true", ttl=86400 * 30)
    logger.info(f"Instant Remote User Revocation executed for deleted user: {user_id}")
    await refresh_users_list_cache(acting_tenant_id)
    return {"message": "User deleted successfully", "user_id": user_id}


@router.get("/{user_id}/headquarters")
async def get_user_headquarters(user_id: str):
    try:
        return user_service.get_user_headquarters(user_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error fetching user headquarters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}/headquarters")
async def set_user_headquarters(user_id: str, payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    check_system_lock_or_raise()
    hq_ids = payload.get("headquarters_ids")
    if hq_ids is None and "headquarters" in payload:
        hq_ids = payload.get("headquarters")
    if not isinstance(hq_ids, list):
        raise HTTPException(status_code=400, detail="'headquarters_ids' must be a list of headquarters UUIDs.")

    admin_user_id = str(current_user.get("user_id") or "")
    acting_tenant_id = current_user.get("tenant_id") if current_user else None
    try:
        res = user_service.set_user_headquarters(user_id, hq_ids, updated_by=admin_user_id)
        await refresh_users_list_cache(acting_tenant_id)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error updating user headquarters: {e}")
        raise HTTPException(status_code=500, detail=str(e))
