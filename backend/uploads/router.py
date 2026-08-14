import logging
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, status
from backend.uploads.service import import_pipeline, upload_batches_db, upload_logs_db
from backend.core.security import RoleChecker
from backend.db.client import get_supabase
from backend.uploads.schemas import UploadBatchResponse, UploadLogResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["Excel Upload & Import Pipeline"])

admin_only = RoleChecker(["admin"])


@router.post("/", response_model=UploadBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(admin_only)
):
    """
    Asynchronous High-Throughput Excel Upload Endpoint (Admin Only).
    Instantly returns '202 Accepted' with batch_id and status='processing'.
    Executes heavy Excel parsing (100,000+ rows), column validation, master resolution,
    and bulk Supabase inserts in a non-blocking background thread.
    """
    try:
        user_id = current_user.get("user_id", "00000000-0000-0000-0000-000000000001")

        contents = await file.read()
        filename = file.filename or "uploaded_file.xlsx"

        batch_record = import_pipeline.create_initial_batch(filename, user_id)

        background_tasks.add_task(
            import_pipeline.process_file_upload_async,
            filename,
            contents,
            user_id,
            batch_record["upload_batch_id"]
        )

        return batch_record
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload initialization error: {str(e)}")


@router.get("/batches", response_model=List[UploadBatchResponse])
async def list_upload_batches():
    return list(upload_batches_db.values())

@router.get("/latest")
async def get_latest_upload_batch():
    """
    Returns details of the latest upload batch from Supabase DB or memory.
    """
    client = get_supabase()
    if client:
        try:
            res = client.table("upload_batches").select("batch_id, source_file, file_name, storage_path, load_type, covers_start, covers_end, row_count, total_rows, imported_rows, duplicate_rows, failed_rows, processing_time_seconds, status, upload_status, remarks, uploaded_by, created_at, updated_at").order("created_at", desc=True).limit(1).execute()
            if res.data:
                batch = res.data[0]
                # If imported_rows is 0, verify count from sales_fact
                if not batch.get("imported_rows") or batch.get("imported_rows") == 0:
                    fact_res = client.table("sales_fact").select("fact_id", count="exact").eq("batch_id", batch["batch_id"]).limit(1).execute()
                    if fact_res.count and fact_res.count > 0:
                        batch["imported_rows"] = fact_res.count
                        batch["status"] = "success"
                        batch["upload_status"] = "success"
                return batch
        except Exception as e:
            logger.warning(f"Failed to fetch latest batch from Supabase: {e}")
            
    batches = list(upload_batches_db.values())
    if batches:
        return sorted(batches, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        
    return {
        "status": "none",
        "message": "No upload history found."
    }

@router.get("/batches/{batch_id}", response_model=UploadBatchResponse)
async def get_upload_batch(batch_id: str):
    if batch_id in upload_batches_db:
        return upload_batches_db[batch_id]

    client = get_supabase()
    if client:
        try:
            res = client.table("upload_batches").select("batch_id, source_file, file_name, storage_path, load_type, covers_start, covers_end, row_count, total_rows, imported_rows, duplicate_rows, failed_rows, processing_time_seconds, status, upload_status, remarks, uploaded_by, created_at, updated_at").eq("batch_id", batch_id).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            logger.warning(f"Failed to fetch batch {batch_id} status from Supabase: {e}")

    return upload_batches_db.get(batch_id, {
        "batch_id": batch_id,
        "status": "not_found",
        "remarks": "Batch record not found."
    })


@router.get("/batches/{batch_id}/logs", response_model=List[UploadLogResponse])
async def get_batch_logs(batch_id: str):
    logs = [log for log in upload_logs_db if str(log.get("upload_batch_id")) == str(batch_id) or str(log.get("batch_id")) == str(batch_id)]
    client = get_supabase()
    if client:
        try:
            res = client.table("upload_validation_errors").select("error_id, batch_id, raw_id, row_number, column_name, error_message, created_at").eq("batch_id", batch_id).execute()
            if res.data:
                return res.data
        except Exception:
            pass
    return logs
