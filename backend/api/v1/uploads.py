from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, status
from backend.services.import_pipeline import import_pipeline, upload_batches_db, upload_logs_db
from backend.core.security import RoleChecker
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
    Asynchronous High-Throughput Excel Upload Endpoint (Admin Only).
    Instantly returns '202 Accepted' with batch_id and status='processing'.
    Executes heavy Excel parsing (100,000+ rows), column validation, master resolution,
    and bulk Supabase inserts in a non-blocking background thread.
    """
    try:
        user_id = current_user.get("user_id", "00000000-0000-0000-0000-000000000001")
        
        # Read contents immediately into memory
        contents = await file.read()
        filename = file.filename or "uploaded_file.xlsx"

        # Initialize batch record immediately for instant client response
        batch_record = import_pipeline.create_initial_batch(filename, user_id)
        
        # Dispatch heavy 100k row processing to background worker
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

@router.get("/batches/{batch_id}", response_model=UploadBatchResponse)
async def get_upload_batch(batch_id: int):
    if batch_id not in upload_batches_db:
        raise HTTPException(status_code=404, detail="Upload batch not found.")
    return upload_batches_db[batch_id]

@router.get("/batches/{batch_id}/logs", response_model=List[UploadLogResponse])
async def get_batch_logs(batch_id: int):
    return [log for log in upload_logs_db if log["upload_batch_id"] == batch_id]
