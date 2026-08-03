from typing import List
from fastapi import APIRouter, Depends
from backend.services.master_service import master_service
from backend.schemas.master import (
    OfficeResponse, CircleResponse, DepotResponse, LicenseeResponse,
    BrandResponse, PackingSizeResponse, PackagingCategoryResponse
)

router = APIRouter(prefix="/master-data", tags=["Master Data"])

@router.get("/offices", response_model=List[OfficeResponse])
async def get_offices():
    return master_service.get_offices()

@router.get("/circles", response_model=List[CircleResponse])
async def get_circles():
    return master_service.get_circles()

@router.get("/depots", response_model=List[DepotResponse])
async def get_depots():
    return master_service.get_depots()

@router.get("/licensees", response_model=List[LicenseeResponse])
async def get_licensees():
    return master_service.get_licensees()

@router.get("/brands", response_model=List[BrandResponse])
async def get_brands():
    return master_service.get_brands()

@router.get("/packing-sizes", response_model=List[PackingSizeResponse])
async def get_packing_sizes():
    return master_service.get_packing_sizes()
