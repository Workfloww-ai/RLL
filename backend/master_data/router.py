import json
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from backend.master_data.service import master_service
from backend.master_data.schemas import (
    OfficeResponse, CircleResponse, DepotResponse, DepotUpdate, LicenseeResponse,
    BrandResponse, PackingSizeResponse, PackagingCategoryResponse, HeadquartersResponse
)
from backend.db.redis_client import safe_get, safe_set, safe_delete
from backend.core.security import get_current_user, RoleChecker, developer_only
from backend.core.route import EncryptedRoute
from backend.services.cache_service import invalidate_others_toggle_cache
from backend.services.tenant_service import get_include_others_setting_async, clear_tenant_cache

logger = logging.getLogger(__name__)

admin_only = RoleChecker(["admin", "super_admin"])
authenticated = Depends(get_current_user)

router = APIRouter(prefix="/master-data", tags=["Master Data"], dependencies=[authenticated], route_class=EncryptedRoute)



async def invalidate_master_and_user_caches():
    """Purge Redis caches when master data changes."""
    await safe_delete("rll:cache:depots_list")
    await safe_delete("rll:cache:headquarters_list")
    await safe_delete("rll:cache:offices_list")
    await safe_delete("rll:cache:circles_list")
    await safe_delete("rll:cache:licensees_list")
    await safe_delete("rll:cache:brands_list")
    await safe_delete("rll:cache:packing_sizes_list")
    await safe_delete("rll:cache:system_settings_dict")
    await safe_delete("rll:cache:users_list")


@router.get("/offices", response_model=List[OfficeResponse])
async def get_offices():
    cached = await safe_get("rll:cache:offices_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached offices_list: {e}")

    data = master_service.get_offices()
    if data:
        await safe_set("rll:cache:offices_list", json.dumps(data), ttl=86400)
    return data


@router.get("/circles", response_model=List[CircleResponse])
async def get_circles():
    cached = await safe_get("rll:cache:circles_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached circles_list: {e}")

    data = master_service.get_circles()
    if data:
        await safe_set("rll:cache:circles_list", json.dumps(data), ttl=86400)
    return data


@router.get("/headquarters", response_model=List[HeadquartersResponse])
async def get_headquarters():
    cached = await safe_get("rll:cache:headquarters_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached headquarters_list: {e}")

    data = master_service.get_headquarters()
    if data:
        await safe_set("rll:cache:headquarters_list", json.dumps(data), ttl=86400)
    return data


@router.get("/depots", response_model=List[DepotResponse])
async def get_depots():
    cached = await safe_get("rll:cache:depots_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached depots_list: {e}")

    data = master_service.get_depots_with_hq()
    if data:
        await safe_set("rll:cache:depots_list", json.dumps(data), ttl=86400)
    return data


@router.put("/depots/{depot_id}")
async def update_depot(depot_id: str, payload: DepotUpdate, _admin=Depends(admin_only)):
    result = master_service.update_depot(depot_id, payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Depot not found")
    await invalidate_master_and_user_caches()
    return result


@router.delete("/depots/{depot_id}")
async def delete_depot(depot_id: str, _admin=Depends(admin_only)):
    success = master_service.delete_depot(depot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete depot")
    await invalidate_master_and_user_caches()
    return {"message": f"Depot {depot_id} deleted successfully"}


@router.get("/licensees", response_model=List[LicenseeResponse])
async def get_licensees():
    cached = await safe_get("rll:cache:licensees_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached licensees_list: {e}")

    data = master_service.get_licensees()
    if data:
        await safe_set("rll:cache:licensees_list", json.dumps(data), ttl=86400)
    return data


@router.get("/brands", response_model=List[BrandResponse])
async def get_brands():
    cached = await safe_get("rll:cache:brands_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached brands_list: {e}")

    data = master_service.get_brands()
    if data:
        await safe_set("rll:cache:brands_list", json.dumps(data), ttl=86400)
    return data


@router.get("/packing-sizes", response_model=List[PackingSizeResponse])
async def get_packing_sizes():
    cached = await safe_get("rll:cache:packing_sizes_list")
    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error parsing cached packing_sizes_list: {e}")

    data = master_service.get_packing_sizes()
    if data:
        await safe_set("rll:cache:packing_sizes_list", json.dumps(data), ttl=86400)
    return data


from pydantic import BaseModel
from backend.db.client import get_supabase

class SystemSettingUpdate(BaseModel):
    setting_key: str
    setting_value: str

class IncludeOthersPayload(BaseModel):
    include_others_in_sales: bool


@router.get("/settings/include-others")
async def get_include_others_setting():
    """Fetch include_others_in_sales setting value."""
    val = await get_include_others_setting_async()
    return {"include_others_in_sales": val}


@router.put("/settings/include-others")
async def update_include_others_setting(
    payload: IncludeOthersPayload,
    current_user: dict = Depends(developer_only)
):
    """Update include_others_in_sales setting value (DEVELOPER ONLY)."""
    new_val_bool = payload.include_others_in_sales
    new_val_str = "true" if new_val_bool else "false"
    old_val_bool = await get_include_others_setting_async()
    old_val_str = "true" if old_val_bool else "false"

    user_id = current_user.get("user_id") or current_user.get("sub")
    user_email = current_user.get("email") or current_user.get("user_metadata", {}).get("email") or "developer"

    client = get_supabase()
    if client:
        try:
            client.rpc("set_system_setting", {"p_key": "include_others_in_sales", "p_val": new_val_str}).execute()
        except Exception as e:
            logger.warning(f"RPC set_system_setting notice: {e}")
            try:
                client.table("system_settings").upsert({"setting_key": "include_others_in_sales", "setting_value": new_val_str}).execute()
            except Exception as e2:
                logger.error(f"Error updating system_settings table: {e2}")

        # Audit Log Entry
        try:
            audit_entry = {
                "setting_key": "include_others_in_sales",
                "old_value": old_val_str,
                "new_value": new_val_str,
                "changed_by_user_id": str(user_id) if user_id else None,
                "changed_by_email": str(user_email),
                "source": "Admin Portal"
            }
            client.table("system_settings_audit_log").insert(audit_entry).execute()
        except Exception as e_audit:
            logger.warning(f"Failed to record audit log for include_others_in_sales toggle: {e_audit}")

    await safe_set("rll:setting:include_others_in_sales", new_val_str, ttl=86400 * 30)
    clear_tenant_cache()
    await invalidate_others_toggle_cache()

    logger.info(
        f"include_others_toggle_changed: old_value={old_val_str}, new_value={new_val_str}, "
        f"changed_by={user_email}, user_id={user_id}"
    )

    return {
        "success": True,
        "setting_key": "include_others_in_sales",
        "include_others_in_sales": new_val_bool,
        "old_value": old_val_bool,
        "new_value": new_val_bool
    }


@router.get("/settings")
async def get_system_settings():
    """Fetch global system settings (e.g. TSM/ASE Data Restriction Toggle, include_others_in_sales)."""
    client = get_supabase()
    result = {
        "tsm_ase_data_restriction_enabled": "true",
        "include_others_in_sales": "true"
    }

    if client:
        try:
            res = client.table("system_settings").select("setting_key, setting_value").execute()
            if res.data:
                for item in res.data:
                    result[item["setting_key"]] = item["setting_value"]
                return result
        except Exception as e:
            logger.debug(f"Notice fetching system settings from DB: {e}")

    include_others = await get_include_others_setting_async()
    result["include_others_in_sales"] = "true" if include_others else "false"
    return result


@router.post("/settings")
async def update_system_setting(
    payload: SystemSettingUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a global system setting."""
    key = payload.setting_key.strip()
    val = payload.setting_value.strip().lower()
    user_role = (current_user.get("role_name") or current_user.get("role") or "").strip().lower()

    # Developer-Only check for include_others_in_sales
    if key == "include_others_in_sales":
        if user_role != "developer":
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: Only Developer role can modify '{key}'. Current role is '{user_role}'."
            )

        old_val_bool = await get_include_others_setting_async()
        old_val_str = "true" if old_val_bool else "false"
        user_id = current_user.get("user_id") or current_user.get("sub")
        user_email = current_user.get("email") or "developer"

        client = get_supabase()
        if client:
            try:
                client.rpc("set_system_setting", {"p_key": key, "p_val": val}).execute()
            except Exception as e:
                logger.warning(f"RPC set_system_setting notice: {e}")
                try:
                    client.table("system_settings").upsert({"setting_key": key, "setting_value": val}).execute()
                except Exception as e2:
                    logger.error(f"Error updating system_settings table: {e2}")

            try:
                audit_entry = {
                    "setting_key": key,
                    "old_value": old_val_str,
                    "new_value": val,
                    "changed_by_user_id": str(user_id) if user_id else None,
                    "changed_by_email": str(user_email),
                    "source": "Admin Portal"
                }
                client.table("system_settings_audit_log").insert(audit_entry).execute()
            except Exception as e_audit:
                logger.warning(f"Failed to record audit log: {e_audit}")

        await safe_set(f"rll:setting:{key}", val, ttl=86400 * 30)
        clear_tenant_cache()
        await invalidate_others_toggle_cache()
        return {"success": True, "setting_key": key, "setting_value": val}

    # For other system settings (e.g. tsm_ase_data_restriction_enabled), require admin/super_admin or developer
    if user_role not in {"admin", "super_admin", "developer"}:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: user role '{user_role}' is not authorized to modify system settings"
        )

    client = get_supabase()
    if client:
        try:
            client.rpc("set_system_setting", {"p_key": key, "p_val": val}).execute()
        except Exception as e:
            logger.warning(f"RPC set_system_setting notice: {e}")
            try:
                client.table("system_settings").upsert({"setting_key": key, "setting_value": val}).execute()
            except Exception as e2:
                logger.error(f"Error updating system_settings table: {e2}")

    await safe_set(f"rll:setting:{key}", val, ttl=86400 * 30)
    await safe_delete("rll:cache:system_settings_dict")
    return {"success": True, "setting_key": key, "setting_value": val}

