"""
Sales Analytics Chatbot Pydantic Schemas.
Defines structured request and response models for chatbot interaction,
tool execution, KPI cards, tables, charts, and suggested prompts.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="User's sales analytics question or command")
    period: Optional[str] = Field("Daily", description="Sales period: Daily, MTD, or YTD")
    date_from: Optional[str] = Field(None, description="Optional start date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Optional end date (YYYY-MM-DD)")
    selected_hq: Optional[str] = Field("All Headquarters", description="Selected Headquarters filter")


class ChatbotKPI(BaseModel):
    title: str
    value: str
    subtext: Optional[str] = None
    change_pct: Optional[float] = None
    change_type: Optional[str] = None  # "up", "down", "neutral"


class ChatbotTableColumn(BaseModel):
    key: str
    label: str
    align: Optional[str] = "left"


class ChatbotTable(BaseModel):
    title: str
    columns: List[ChatbotTableColumn]
    rows: List[Dict[str, Any]]


class ChatbotChartDataPoint(BaseModel):
    label: str
    value: float
    secondary_value: Optional[float] = None


class ChatbotChart(BaseModel):
    title: str
    chart_type: str = "bar"  # "bar", "line", "pie"
    series_name: str = "Cases"
    data: List[ChatbotChartDataPoint]


class ChatMessageResponse(BaseModel):
    text: str
    intent: str
    period: str = "Daily"
    target_date: str
    selected_hq: str = "All Headquarters"
    kpis: Optional[List[ChatbotKPI]] = None
    table: Optional[ChatbotTable] = None
    chart: Optional[ChatbotChart] = None
    comparison: Optional[Dict[str, Any]] = None
    movers: Optional[Dict[str, Any]] = None
    suggested_questions: Optional[List[str]] = None
    clarification_needed: bool = False
    execution_time_ms: float = 0.0
    cache_hit: bool = False
