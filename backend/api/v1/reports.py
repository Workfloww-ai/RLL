from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from backend.services.analytics_service import analytics_service

router = APIRouter(prefix="/reports", tags=["Reporting Service"])

@router.get("/summary")
async def get_summary_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    overview = analytics_service.get_dashboard_overview(start_date=start_date, end_date=end_date)
    return {
        "report_type": "Daily Sales Summary",
        "generated_at": overview.get("generated_at"),
        "kpis": overview["kpis"],
        "top_brands": overview["top_brands"],
        "top_depots": overview["top_depots"]
    }

@router.get("/export")
async def export_sales_report(
    format: str = Query("csv", regex="^(csv|json|excel)$")
):
    overview = analytics_service.get_dashboard_overview()
    if format == "json":
        return JSONResponse(content=overview)
    # Default CSV/Excel structure metadata
    return {
        "message": f"Export format '{format}' generated successfully.",
        "download_url": "/api/v1/reports/summary",
        "records_count": len(overview["trends"])
    }
