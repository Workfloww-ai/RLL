from typing import Optional
from fastapi import APIRouter, Depends, Query
from backend.services.analytics_service import analytics_service
from backend.schemas.analytics import DashboardOverview
from backend.core.security import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboards"])

@router.get("/overview", response_model=DashboardOverview)
async def get_dashboard_overview(
    start_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    depot_id: Optional[int] = None,
    circle_id: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    return analytics_service.get_dashboard_overview(
        start_date=start_date,
        end_date=end_date,
        depot_id=depot_id,
        circle_id=circle_id
    )

@router.get("/regional-manager")
async def get_regional_manager_dashboard(
    circle_id: Optional[int] = 1,
    current_user: dict = Depends(get_current_user)
):
    overview = analytics_service.get_dashboard_overview(circle_id=circle_id)
    return {
        "user_role": "regional_manager",
        "circle_id": circle_id,
        "metrics": overview
    }

@router.get("/sales-rep")
async def get_sales_rep_dashboard(
    depot_id: Optional[int] = 1,
    current_user: dict = Depends(get_current_user)
):
    overview = analytics_service.get_dashboard_overview(depot_id=depot_id)
    return {
        "user_role": "sales_representative",
        "depot_id": depot_id,
        "metrics": overview
    }
