from typing import Optional, List, Any, Dict
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, ConfigDict

# Upload Batches
class UploadBatchBase(BaseModel):
    source_file: str
    load_type: str = "daily"
    covers_start: Optional[date] = None
    covers_end: Optional[date] = None
    row_count: Optional[int] = None
    status: str = "pending"
    upload_status: Optional[str] = "pending"
    uploaded_by: Optional[UUID] = None
    is_active: bool = True
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    remarks: Optional[str] = None
    imported_rows: Optional[int] = 0
    failed_rows: Optional[int] = 0
    duplicate_rows: Optional[int] = 0
    processing_time_seconds: Optional[float] = 0.0

class UploadBatchCreate(UploadBatchBase):
    pass

class UploadBatchResponse(UploadBatchBase):
    batch_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Upload Logs
class UploadLogBase(BaseModel):
    upload_batch_id: int
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

class UploadLogCreate(UploadLogBase):
    pass

class UploadLogResponse(UploadLogBase):
    upload_log_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Sales Schema
class SaleBase(BaseModel):
    sales_date: date
    depot_id: int
    licensee_id: int
    brand_id: int
    packing_size_id: int
    total_cases: float = 0.0
    total_bottles: float = 0.0
    total_bulk_liters: float = 0.0
    sale_value: float = 0.0
    upload_batch_id: Optional[int] = None

class SaleCreate(SaleBase):
    pass

class SaleResponse(SaleBase):
    sale_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Dashboard Summary Daily Schema
class DashboardSummaryDailyBase(BaseModel):
    summary_date: date
    total_sales: float = 0.0
    total_cases: float = 0.0
    total_bottles: float = 0.0
    total_bulk_liters: float = 0.0
    total_brands: int = 0
    total_licensees: int = 0
    top_brand_id: Optional[int] = None
    top_depot_id: Optional[int] = None

class DashboardSummaryDailyResponse(DashboardSummaryDailyBase):
    dashboard_summary_id: int
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Audit Logs Schema
class AuditLogCreate(BaseModel):
    user_id: Optional[UUID] = None
    action: str
    table_name: Optional[str] = None
    record_id: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None

class AuditLogResponse(AuditLogCreate):
    audit_log_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
