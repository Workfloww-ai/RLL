from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, status
from backend.services.import_pipeline import import_pipeline, upload_batches_db, upload_logs_db
from backend.core.security import RoleChecker
from backend.db.client import get_supabase
from backend.schemas.transactional import UploadBatchResponse, UploadLogResponse

router = APIRouter(prefix="/uploads", tags=["Excel Upload & Import Pipeline"])

admin_only = RoleChecker(["admin"])

@router.post("/", response_model=UploadBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(admin_only)
):
    """
    Async Excel Upload Endpoint (Admin Only).
    Stores uploaded file in temp disk & Supabase Storage, creates initial batch record,
    dispatches high-performance background ingestion, and immediately returns 202 Accepted.
    """
    try:
        user_id = current_user.get("user_id", "00000000-0000-0000-0000-000000000001")
        batch_record, temp_path = await import_pipeline.prepare_file_upload(file, user_id)
        
        # Enqueue heavy processing task asynchronously
        background_tasks.add_task(import_pipeline.process_file_background, batch_record, temp_path, user_id)
        
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
    if batch_id in upload_batches_db:
        return upload_batches_db[batch_id]
        
    client = get_supabase()
    if client:
        try:
            res = client.table("upload_batches").select("*").eq("batch_id", batch_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception:
            pass
            
    raise HTTPException(status_code=404, detail="Upload batch not found.")

@router.get("/batches/{batch_id}/logs", response_model=List[UploadLogResponse])
async def get_batch_logs(batch_id: int):
    logs = [log for log in upload_logs_db if log.get("upload_batch_id") == batch_id or log.get("batch_id") == batch_id]
    if not logs:
        client = get_supabase()
        if client:
            try:
                res = client.table("upload_validation_errors").select("*").eq("batch_id", batch_id).execute()
                if res.data:
                    return res.data
            except Exception:
                pass
    return logs
