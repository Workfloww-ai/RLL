import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response, status
from backend.analytics.service import analytics_service
from backend.analytics.schemas import DashboardResponse
from backend.core.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["Sales Analytics Engine"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_analytics(
    period: str = Query("daily", description="Period selection: daily | mtd | ytd"),
    from_date: Optional[str] = Query(None, description="Start date format: YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date format: YYYY-MM-DD"),
    brand_id: Optional[int] = Query(None, description="Filter by specific brand_id"),
    depot_id: Optional[int] = Query(None, description="Filter by specific depot_id"),
    current_user: dict = Depends(get_current_user)
):
    """
    High-Performance Mobile Dashboard Endpoint for Daily, MTD, and YTD analytics.
    Strictly queries summary pre-aggregates with RBAC depot scope validation.
    """
    return analytics_service.get_dashboard(
        period=period,
        from_date=from_date,
        to_date=to_date,
        depot_id=depot_id,
        brand_id=brand_id,
        current_user=current_user
    )


@router.get("/export")
async def export_dashboard_data(
    period: str = Query("daily", description="Period selection: daily | mtd | ytd"),
    from_date: Optional[str] = Query(None, description="Start date format: YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date format: YYYY-MM-DD"),
    brand_id: Optional[int] = Query(None, description="Filter by specific brand_id"),
    depot_id: Optional[int] = Query(None, description="Filter by specific depot_id"),
    current_user: dict = Depends(get_current_user)
):
    """
    Export CSV analytics dataset respecting date filters and RBAC scope.
    """
    data = analytics_service.get_dashboard(
        period=period,
        from_date=from_date,
        to_date=to_date,
        depot_id=depot_id,
        brand_id=brand_id,
        current_user=current_user
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Period", "From Date", "To Date", "Brand ID", "Brand Name", "Total Cases", "Total Bottles", "Total Bulk Liters (BL)"])

    for b in data.get("brands", []):
        writer.writerow([
            data.get("period"),
            data.get("from_date"),
            data.get("to_date"),
            b.get("brand_id"),
            b.get("brand_name"),
            b.get("total_cases"),
            b.get("total_bottles"),
            b.get("total_bl")
        ])

    csv_content = output.getvalue()
    filename = f"sales_analytics_{period}_{data.get('to_date')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
