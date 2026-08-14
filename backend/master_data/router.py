from typing import List
from fastapi import APIRouter, HTTPException
from backend.master_data.service import master_service
from backend.master_data.schemas import (
    OfficeResponse, CircleResponse, DepotResponse, DepotUpdate, LicenseeResponse,
    BrandResponse, PackingSizeResponse, PackagingCategoryResponse, HeadquartersResponse
)

router = APIRouter(prefix="/master-data", tags=["Master Data"])


@router.get("/offices", response_model=List[OfficeResponse])
async def get_offices():
    return master_service.get_offices()


@router.get("/circles", response_model=List[CircleResponse])
async def get_circles():
    return master_service.get_circles()


@router.get("/headquarters", response_model=List[HeadquartersResponse])
async def get_headquarters():
    return master_service.get_headquarters()


@router.get("/depots", response_model=List[DepotResponse])
async def get_depots():
    return master_service.get_depots_with_hq()


@router.put("/depots/{depot_id}")
async def update_depot(depot_id: int, payload: DepotUpdate):
    result = master_service.update_depot(depot_id, payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Depot not found")
    return result


@router.delete("/depots/{depot_id}")
async def delete_depot(depot_id: int):
    success = master_service.delete_depot(depot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete depot")
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
