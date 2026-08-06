import os
import shutil
import uuid as uuid_mod
from datetime import date
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, status
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, status, Request, Depends
from backend.core.config import settings
from backend.db.supabase_client import create_upload_batch, get_batch_details
from backend.uploads.importer import process_upload_batch_chunked
from backend.auth.deps import get_current_user_optional
router = APIRouter(prefix="/uploads", tags=["Excel Upload Engine"])
ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".numbers", ".csv")
def _validate_and_save_temp(file: UploadFile) -> str:
    """Validates file extension and saves it to TEMP_UPLOAD_DIR. Returns the temp path."""
    filename_lower = file.filename.lower() if file.filename else ""
    if not filename_lower.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{file.filename}'. "
                f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            ),
        )
    ext = os.path.splitext(filename_lower)[1] or ".xlsx"
    temp_name = f"pre_{uuid_mod.uuid4().hex}{ext}"
    temp_path = os.path.join(str(settings.TEMP_UPLOAD_DIR), temp_name)
    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return temp_path
def _rename_for_batch(temp_path: str, batch_id: int) -> str:
    """Renames the pre-saved temp file to include the batch_id."""
    ext = os.path.splitext(temp_path)[1]
    final_name = f"batch_{batch_id}_{uuid_mod.uuid4().hex}{ext}"
    final_path = os.path.join(str(settings.TEMP_UPLOAD_DIR), final_name)
    os.rename(temp_path, final_path)
    return final_path
def _normalize_load_type(raw: str) -> str:
    v = str(raw).lower().strip()
    return v if v in ("daily", "monthly") else "daily"
def _sanitize_uuid(val: Optional[str]) -> Optional[str]:
    """Returns None if val is blank, a placeholder, or not a valid UUID."""
    if not val or not val.strip():
        return None
    try:
        return str(uuid_mod.UUID(val.strip()))
    except (ValueError, AttributeError):
        return None
def _resolve_dates(
    temp_path: str,
    covers_start: Optional[str],
    covers_end: Optional[str],
) -> tuple[str, str]:
    """
    Returns (covers_start, covers_end) as ISO strings.
    If either is missing/blank, auto-detects from the file's date column.
    Falls back to today's date if detection fails.
    """
    if covers_start and covers_start.strip() and covers_end and covers_end.strip():
        # Both supplied — validate format
        try:
            return (
                str(date.fromisoformat(covers_start.strip())),
                str(date.fromisoformat(covers_end.strip())),
            )
        except ValueError:
            pass  # fall through to auto-detect
    # Auto-detect from the file
    try:
        from backend.uploads.parser import scan_date_range
        start, end = scan_date_range(temp_path)
        if start and end:
            return start, end
    except Exception:
        pass
    # Last resort: today
    today = str(date.today())
    return today, today
# ── POST /uploads/  ─  background async (recommended for large files) ─────
@router.post("/", status_code=status.HTTP_202_ACCEPTED, summary="Upload Excel (async, background)")
async def upload_excel_async(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Excel / Numbers / CSV file"),
    load_type: str = Form("daily", description="'daily' or 'monthly'"),
    covers_start: Optional[str] = Form(None, description="Start date YYYY-MM-DD (auto-detected if omitted)"),
    covers_end: Optional[str] = Form(None, description="End date YYYY-MM-DD (auto-detected if omitted)"),
    uploaded_by: Optional[str] = Form(None, description="UUID of the uploading user"),
    uploaded_by: Optional[str] = Form(None, description="UUID of the uploading user (optional if Bearer token present)"),
    chunk_size: int = Form(2500, description="Rows per insert chunk (default 2500)"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Accepts the Excel file, creates an upload_batches record, saves the file
    to disk, and immediately returns a batch_id while ETL runs in the background.
    `covers_start` and `covers_end` are **optional** — if omitted, the system
    automatically detects the date range from the file's date column.
    Poll `GET /uploads/batch/{batch_id}` to check progress.
    Accepts the Excel file, creates an upload_batches record with user FK and browser/IP metadata,
    and immediately returns a batch_id while ETL runs in the background.
    """
    from backend.auth.deps import extract_client_metadata
    meta = extract_client_metadata(request)
    load_type = _normalize_load_type(load_type)
    # Save file first so we can scan its dates
    temp_path = _validate_and_save_temp(file)
    # Determine acting user UUID (from Bearer token or form parameter)
    user_uuid = _sanitize_uuid(uploaded_by)
    if not user_uuid and current_user:
        user_uuid = current_user.get("user_id")
    # Resolve date coverage (auto-detect if not supplied)
    temp_path = _validate_and_save_temp(file)
    covers_start, covers_end = _resolve_dates(temp_path, covers_start, covers_end)
    batch_id = create_upload_batch(
        source_file=file.filename or "upload",
        load_type=load_type,
        covers_start=covers_start,
        covers_end=covers_end,
        uploaded_by=_sanitize_uuid(uploaded_by),
        uploaded_by=user_uuid,
        created_by=user_uuid,
        browser_info=meta["browser_info"],
        client_ip=meta["client_ip"],
    )
    if not batch_id:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail="Failed to create upload batch record in DB.")
    final_path = _rename_for_batch(temp_path, batch_id)
    background_tasks.add_task(
        process_upload_batch_chunked,
        batch_id=batch_id,
        file_path=final_path,
        load_type=load_type,
        covers_start=covers_start,
        covers_end=covers_end,
        chunk_size=chunk_size,
    )
    return {
        "batch_id":    batch_id,
        "status":      "processing",
        "filename":    file.filename,
        "load_type":   load_type,
        "covers":      f"{covers_start} → {covers_end}",
        "chunk_size":  chunk_size,
        "message":     f"Upload accepted. Poll GET /uploads/batch/{batch_id} for progress.",
    }
# ── POST /uploads/sync  ─  synchronous, waits for completion ──────────────
@router.post("/sync", summary="Upload Excel (sync, waits for completion)")
async def upload_excel_sync(
    file: UploadFile = File(...),
    load_type: str = Form("daily", description="'daily' or 'monthly'"),
    covers_start: Optional[str] = Form(None, description="Start date YYYY-MM-DD (auto-detected if omitted)"),
    covers_end: Optional[str] = Form(None, description="End date YYYY-MM-DD (auto-detected if omitted)"),
    chunk_size: int = Form(2500, description="Rows per insert chunk (default 2500)"),
):
    """
    Same ETL pipeline as the async endpoint but waits for completion before
    responding. Use only for small files or debugging.
    `covers_start` and `covers_end` are **optional** — auto-detected from the file.
    """
    load_type = _normalize_load_type(load_type)
    temp_path = _validate_and_save_temp(file)
    covers_start, covers_end = _resolve_dates(temp_path, covers_start, covers_end)
    batch_id = create_upload_batch(
        source_file=file.filename or "upload",
        load_type=load_type,
        covers_start=covers_start,
        covers_end=covers_end,
    )
    if not batch_id:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail="Failed to create upload batch record in DB.")
    final_path = _rename_for_batch(temp_path, batch_id)
    await process_upload_batch_chunked(
        batch_id=batch_id,
        file_path=final_path,
        load_type=load_type,
        covers_start=covers_start,
        covers_end=covers_end,
        chunk_size=chunk_size,
    )
    return get_batch_details(batch_id)
# ── GET /uploads/batch/{batch_id}  ─  progress & status ──────────────────
@router.get("/batch/{batch_id}", summary="Check upload batch status")
async def get_batch_status(batch_id: int):
    """
    Returns real-time status, pipeline logs, and error count for an upload batch.
    """
    details = get_batch_details(batch_id)
    if not details or "error" in details:
        raise HTTPException(
            status_code=404,
            detail=details.get("error", "Batch not found.") if details else "Batch not found.",
        )
    return details