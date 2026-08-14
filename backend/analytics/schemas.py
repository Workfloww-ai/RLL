from typing import Optional, List
from pydantic import BaseModel, Field


class TotalsSummary(BaseModel):
    total_cases: float = Field(..., description="Total Cases sold")
    total_bottles: float = Field(..., description="Total Bottles sold")
    total_bl: float = Field(..., description="Total Bulk Liters sold")


class BrandAnalyticsItem(BaseModel):
    brand_id: int
    brand_name: str
    total_cases: float
    total_bottles: float
    total_bl: float


class CompanyAnalyticsItem(BaseModel):
    company_id: int
    company_name: str
    total_cases: float
    total_bottles: float
    total_bl: float
    brands: List[BrandAnalyticsItem]


class DashboardResponse(BaseModel):
    period: str = Field(..., description="period type: daily, mtd, ytd")
    from_date: str
    to_date: str
    totals: TotalsSummary
    companies: List[CompanyAnalyticsItem] = []
    brands: List[BrandAnalyticsItem] = []
