from typing import List, Optional
from datetime import date
from pydantic import BaseModel

class KPICards(BaseModel):
    total_sales_value: float
    total_cases_sold: float
    total_bottles_sold: float
    total_bulk_liters: float
    active_licensees_count: int
    active_brands_count: int
    growth_percentage: Optional[float] = 0.0

class SalesTrendItem(BaseModel):
    sales_date: date
    total_sales: float
    total_cases: float
    total_bottles: float

class TopBrandItem(BaseModel):
    brand_id: int
    brand_name: str
    brand_code: str
    total_cases: float
    total_sales_value: float
    market_share_percentage: float

class TopDepotItem(BaseModel):
    depot_id: int
    depot_name: str
    depot_code: str
    circle_name: Optional[str] = None
    total_cases: float
    total_sales_value: float

class DashboardOverview(BaseModel):
    kpis: KPICards
    trends: List[SalesTrendItem]
    top_brands: List[TopBrandItem]
    top_depots: List[TopDepotItem]
