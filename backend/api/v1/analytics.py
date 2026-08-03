from typing import Optional
from fastapi import APIRouter, Depends, Query
from backend.services.analytics_service import analytics_service
from backend.core.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics Engine"])

@router.get("/trends")
async def get_sales_trends(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    data = analytics_service.get_dashboard_overview(start_date=start_date, end_date=end_date)
    return {"trends": data["trends"]}

@router.get("/brand-rankings")
async def get_brand_rankings():
    data = analytics_service.get_dashboard_overview()
    return {"brands": data["top_brands"]}

@router.get("/depot-performance")
async def get_depot_performance():
    data = analytics_service.get_dashboard_overview()
    return {"depots": data["top_depots"]}
