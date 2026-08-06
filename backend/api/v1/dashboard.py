from typing import Optional
from fastapi import APIRouter, Depends, Query
from backend.services.analytics_service import analytics_service
from backend.schemas.analytics import DashboardResponse
from backend.core.security import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboards"])

@router.get("/overview", response_model=DashboardResponse)
async def get_dashboard_overview(
    period: str = Query("daily", description="Period: daily | mtd | ytd"),
    start_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    depot_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    return analytics_service.get_dashboard(
        period=period,
        from_date=start_date,
        to_date=end_date,
        depot_id=depot_id,
        brand_id=brand_id,
        current_user=current_user
    )

@router.get("/regional-manager", response_model=DashboardResponse)
async def get_regional_manager_dashboard(
    period: str = Query("daily"),
    to_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return analytics_service.get_dashboard(
        period=period,
        to_date=to_date,
        current_user=current_user
    )

@router.get("/sales-rep", response_model=DashboardResponse)
async def get_sales_rep_dashboard(
    period: str = Query("daily"),
    to_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return analytics_service.get_dashboard(
        period=period,
        to_date=to_date,
        current_user=current_user
    )
