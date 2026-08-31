import json
import logging
from typing import List
from fastapi import APIRouter, HTTPException
from backend.master_data.service import master_service
from backend.master_data.schemas import (
    OfficeResponse, CircleResponse, DepotResponse, DepotUpdate, LicenseeResponse,
    BrandResponse, PackingSizeResponse, PackagingCategoryResponse, HeadquartersResponse
)
from backend.db.redis_client import safe_get, safe_set, safe_delete

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/master-data", tags=["Master Data"])


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
async def update_depot(depot_id: str, payload: DepotUpdate):
    result = master_service.update_depot(depot_id, payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Depot not found")
    await invalidate_master_and_user_caches()
    return result


@router.delete("/depots/{depot_id}")
async def delete_depot(depot_id: str):
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
