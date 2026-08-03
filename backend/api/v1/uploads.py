from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from backend.services.import_pipeline import import_pipeline, upload_batches_db, upload_logs_db
from backend.core.security import RoleChecker
from backend.schemas.transactional import UploadBatchResponse, UploadLogResponse

router = APIRouter(prefix="/uploads", tags=["Excel Upload & Import Pipeline"])

admin_only = RoleChecker(["admin"])

@router.post("/", response_model=UploadBatchResponse)
async def upload_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(admin_only)
):
    """
    Excel Upload Endpoint (Admin Only).
    Stores uploaded .xlsx, .xls, or .numbers spreadsheet in Supabase Storage ('excel-uploads'),
    executes format & column validation, detects duplicate records, populates Supabase database
    tables ('upload_batches', 'upload_logs', 'sales', 'dashboard_summary_daily', 'audit_logs'),
    and returns full upload batch summary.
    """
    try:
        user_id = current_user.get("user_id", "00000000-0000-0000-0000-000000000001")
        batch_record = await import_pipeline.process_file_upload(file, user_id)
        return batch_record
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")

@router.get("/batches", response_model=List[UploadBatchResponse])
async def list_upload_batches():
    return list(upload_batches_db.values())

@router.get("/batches/{batch_id}", response_model=UploadBatchResponse)
async def get_upload_batch(batch_id: int):
    if batch_id not in upload_batches_db:
        raise HTTPException(status_code=404, detail="Upload batch not found.")
    return upload_batches_db[batch_id]

@router.get("/batches/{batch_id}/logs", response_model=List[UploadLogResponse])
async def get_batch_logs(batch_id: int):
    return [log for log in upload_logs_db if log["upload_batch_id"] == batch_id]
