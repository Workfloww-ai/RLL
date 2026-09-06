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
from backend.core.security import get_current_user, RoleChecker

logger = logging.getLogger(__name__)

admin_only = RoleChecker(["admin", "super_admin"])
authenticated = Depends(get_current_user)

router = APIRouter(prefix="/master-data", tags=["Master Data"], dependencies=[authenticated])


async def invalidate_master_and_user_caches():
    """Purge Redis caches when depots or headquarters master data change."""
    await safe_delete("rll:cache:depots_list")
    await safe_delete("rll:cache:headquarters_list")
    await safe_delete("rll:cache:users_list")


@router.get("/offices", response_model=List[OfficeResponse])
async def get_offices():
    return master_service.get_offices()


@router.get("/circles", response_model=List[CircleResponse])
async def get_circles():
    return master_service.get_circles()


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
    return master_service.get_licensees()


@router.get("/brands", response_model=List[BrandResponse])
async def get_brands():
    return master_service.get_brands()


@router.get("/packing-sizes", response_model=List[PackingSizeResponse])
async def get_packing_sizes():
    return master_service.get_packing_sizes()


from pydantic import BaseModel
from backend.db.client import get_supabase

class SystemSettingUpdate(BaseModel):
    setting_key: str
    setting_value: str


@router.get("/settings")
async def get_system_settings():
    """Fetch global system settings (e.g. TSM/ASE Data Restriction Toggle)."""
    client = get_supabase()
    if client:
        try:
            res = client.table("system_settings").select("*").execute()
            if res.data:
                return {item["setting_key"]: item["setting_value"] for item in res.data}
        except Exception as e:
            logger.warning(f"Error fetching system settings from DB: {e}")
    
    cached_val = await safe_get("rll:setting:tsm_ase_data_restriction_enabled") or "true"
    return {"tsm_ase_data_restriction_enabled": cached_val}


@router.post("/settings")
async def update_system_setting(payload: SystemSettingUpdate, _admin=Depends(admin_only)):
    """Update a global system setting (Admin only)."""
    key = payload.setting_key.strip()
    val = payload.setting_value.strip().lower()
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
    return {"success": True, "setting_key": key, "setting_value": val}
