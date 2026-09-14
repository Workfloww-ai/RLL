import logging
import uuid
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, status, Header, Query
from backend.uploads.service import import_pipeline, upload_batches_db, upload_logs_db
from backend.core.security import RoleChecker
from backend.db.client import get_supabase
from backend.uploads.schemas import UploadBatchResponse, UploadLogResponse

logger = logging.getLogger(__name__)

admin_only = RoleChecker(["admin"])

router = APIRouter(
    prefix="/uploads", 
    tags=["Excel Upload & Import Pipeline"],
    dependencies=[Depends(admin_only)]
)


@router.post("/", response_model=UploadBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    tenant_id: Optional[str] = Query(None),
    current_user: dict = Depends(admin_only)
):
    """
    Asynchronous High-Throughput Excel Upload Endpoint (Admin Only).
    Instantly returns '202 Accepted' with batch_id and status='processing'.
    Executes heavy Excel parsing (100,000+ rows), column validation, master resolution,
    and bulk Supabase inserts in a non-blocking background thread.
    """
    user_id = current_user.get("user_id")
    resolved_tenant_id = x_tenant_id or tenant_id or current_user.get("tenant_id") or "a0000000-0000-0000-0000-000000000001"
    filename = file.filename or "upload.xlsx"
    logger.info(f"Excel upload request initiated by user: {user_id} for file: {filename} (tenant: {resolved_tenant_id})")

    # 0. Preflight Database Health Guard
    db_health = import_pipeline.check_db_health()
    if not db_health.get("healthy"):
        logger.error(f"Upload rejected due to unhealthy database state: {db_health.get('message')}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is currently unreachable or unhealthy ({db_health.get('message')}). Upload deferred."
        )

    # 0b. Phase 2 Single-Upload Queue & Concurrency Guard (HTTP 409 Conflict)
    active_batch = import_pipeline.is_upload_active()
    if active_batch:
        active_id = active_batch.get("batch_id") or active_batch.get("upload_batch_id")
        active_file = active_batch.get("source_file") or active_batch.get("file_name") or "unknown"
        if active_file.strip().lower() != filename.strip().lower():
            logger.warning(f"Upload rejected (HTTP 409): Active pipeline Batch #{active_id} ({active_file}) in progress.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An upload pipeline is currently active (Batch #{active_id}: '{active_file}'). Single-upload queue prevents concurrent execution."
            )

    # 1. File Extension Validation (.xlsx, .xls, .xlsb, .xlsm, .csv)
    allowed_extensions = {".xlsx", ".xls", ".xlsb", ".xlsm", ".csv"}
    file_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
    if file_ext not in allowed_extensions:
        err_msg = f"Unsupported file format '{file_ext}'. Allowed formats: {', '.join(sorted(allowed_extensions))}"
        from backend.db.supabase_client import log_upload_validation_error
        log_upload_validation_error(batch_id=None, column_name="FILE_EXTENSION", error_message=err_msg)
        raise HTTPException(
            status_code=400,
            detail=err_msg
        )

    # 2. File Size Limit Validation (250 MB Limit)
    MAX_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
    try:
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            err_msg = f"File size exceeds maximum allowed limit of 250 MB (Received: {len(contents) / (1024*1024):.2f} MB)."
            from backend.db.supabase_client import log_upload_validation_error
            log_upload_validation_error(batch_id=None, column_name="FILE_SIZE", error_message=err_msg)
            raise HTTPException(
                status_code=413,
                detail=err_msg
            )

        batch_record = import_pipeline.create_initial_batch(filename, user_id, tenant_id=resolved_tenant_id)

        # Phase 2 Idempotent Retry: If returning existing active batch, do not add duplicate background task
        if batch_record.get("is_existing_active"):
            logger.info(f"Idempotent upload endpoint call: returning active batch #{batch_record.get('batch_id')} without duplicate queue.")
            return batch_record

        background_tasks.add_task(
            import_pipeline.process_file_upload_async,
            filename,
            contents,
            user_id,
            batch_record["upload_batch_id"],
            resolved_tenant_id
        )

        logger.info(f"Excel file {filename} queued successfully for asynchronous processing (Batch ID: {batch_record['upload_batch_id']})")
        return batch_record
    except ValueError as ve:
        logger.warning(f"Excel upload failed validation for file {filename} by user {user_id}: {str(ve)}")
        from backend.db.supabase_client import log_upload_validation_error
        log_upload_validation_error(batch_id=None, column_name="FILE_VALIDATION", error_message=str(ve))
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Excel upload initialization failed for file {filename} by user {user_id}: {str(e)}")
        from backend.db.supabase_client import log_upload_validation_error
        log_upload_validation_error(batch_id=None, column_name="FILE_INIT_ERROR", error_message=str(e))
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
    batch = None
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
        except Exception as e:
            logger.warning(f"Failed to fetch latest batch from Supabase: {e}")

    if not batch:
        batches = list(upload_batches_db.values())
        if batches:
            batch = sorted(batches, key=lambda x: x.get("created_at", ""), reverse=True)[0]

    if not batch:
        return {
            "status": "none",
            "message": "No upload history found."
        }

    # Resolve uploader's name if uploaded_by is present
    uploader_id = batch.get("uploaded_by")
    uploader_name = "Admin User"
    if uploader_id and client:
        try:
            u_res = client.table("users").select("first_name, last_name, email").eq("user_id", uploader_id).limit(1).execute()
            if u_res.data and len(u_res.data) > 0:
                u_data = u_res.data[0]
                fn = u_data.get("first_name") or ""
                ln = u_data.get("last_name") or ""
                full_name = f"{fn} {ln}".strip()
                uploader_name = full_name or u_data.get("email") or "Admin User"
            elif "@" in str(uploader_id):
                uploader_name = str(uploader_id)
        except Exception as e_u:
            logger.warning(f"Could not resolve uploader_name for {uploader_id}: {e_u}")

    batch["uploader_name"] = uploader_name
    return batch

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


def humanize_upload_error(column_name: Optional[str], raw_message: str) -> Dict[str, Any]:
    """
    Translates raw backend/database error strings into clear, friendly, and actionable UI diagnostics.
    """
    msg = (raw_message or "").strip()
    col = (column_name or "").strip()
    
    # 1. Network / Socket / Timeout errors
    if "[Errno 35]" in msg or "Resource temporarily unavailable" in msg:
        return {
            "category": "System & Network",
            "category_key": "network",
            "severity": "warning",
            "friendly_title": "Connection Buffer Stall",
            "friendly_explanation": "Network socket buffer was momentarily saturated during high-throughput bulk insertion.",
            "suggested_action": "System automatically recovered or chunk can be re-synchronized. No manual schema change required.",
            "entity": "Socket Buffer",
            "group_key": "socket_buffer_stall"
        }
    elif "timeout" in msg.lower() or "deadline" in msg.lower():
        return {
            "category": "System & Network",
            "category_key": "network",
            "severity": "warning",
            "friendly_title": "Database Query Timeout",
            "friendly_explanation": "The database took longer than standard latency limits to confirm batch write.",
            "suggested_action": "Check database health and network latency.",
            "entity": "Database Request",
            "group_key": "db_timeout"
        }
        
    # 2. Master Data Mapping Errors
    if "Unmapped Headquarters" in msg or col.lower() in ("hq_raw", "headquarters", "hq"):
        match = re.search(r"'(.*?)'", msg) or re.search(r':\s*(.*)', msg)
        hq_name = match.group(1).strip() if match else "Unknown"
        return {
            "category": "Master Data Mapping",
            "category_key": "master_mapping",
            "severity": "warning",
            "friendly_title": f"Unmapped Headquarters: '{hq_name}'",
            "friendly_explanation": f"The headquarters '{hq_name}' in the Excel file is not recognized in the system master catalog.",
            "suggested_action": f"Register '{hq_name}' under Territory Management or check Excel spelling.",
            "entity": f"Headquarters: {hq_name}",
            "group_key": f"unmapped_hq_{hq_name}"
        }
    elif "Unmapped Depot" in msg or col.lower() in ("depot_raw", "depot_name", "depot"):
        match = re.search(r"'(.*?)'", msg) or re.search(r':\s*(.*)', msg)
        depot_name = match.group(1).strip() if match else "Unknown"
        return {
            "category": "Master Data Mapping",
            "category_key": "master_mapping",
            "severity": "warning",
            "friendly_title": f"Unmapped Depot: '{depot_name}'",
            "friendly_explanation": f"Depot '{depot_name}' does not match any registered depot in the database.",
            "suggested_action": f"Add '{depot_name}' in Depot Masters or update alias.",
            "entity": f"Depot: {depot_name}",
            "group_key": f"unmapped_depot_{depot_name}"
        }
    elif "Unmapped Licensee" in msg or col.lower() in ("licensee_raw", "licensee_name", "licensee"):
        match = re.search(r"'(.*?)'", msg) or re.search(r':\s*(.*)', msg)
        lic_name = match.group(1).strip() if match else "Unknown"
        return {
            "category": "Master Data Mapping",
            "category_key": "master_mapping",
            "severity": "warning",
            "friendly_title": f"Unmapped Licensee: '{lic_name}'",
            "friendly_explanation": f"Licensee '{lic_name}' is not recognized in the licensee registry.",
            "suggested_action": f"Ensure '{lic_name}' is configured in Licensee Master records.",
            "entity": f"Licensee: {lic_name}",
            "group_key": f"unmapped_licensee_{lic_name}"
        }
    elif "Unmapped Brand" in msg or col.lower() in ("brand_raw", "brand_name", "brand"):
        match = re.search(r"'(.*?)'", msg) or re.search(r':\s*(.*)', msg)
        brand_name = match.group(1).strip() if match else "Unknown"
        return {
            "category": "Master Data Mapping",
            "category_key": "master_mapping",
            "severity": "warning",
            "friendly_title": f"Unmapped Brand: '{brand_name}'",
            "friendly_explanation": f"Brand '{brand_name}' was not found in the liquor brand master.",
            "suggested_action": f"Register '{brand_name}' under Brand Master catalog.",
            "entity": f"Brand: {brand_name}",
            "group_key": f"unmapped_brand_{brand_name}"
        }
        
    # 3. Database Insertion & Table Errors
    if "failed insertion in table" in msg or col in ("user_sales_fact", "sales_fact", "raw_sales_upload"):
        table_name = col or "sales_fact"
        return {
            "category": "Database Insertion",
            "category_key": "database",
            "severity": "critical",
            "friendly_title": f"Row Write Failure on '{table_name}'",
            "friendly_explanation": f"Could not write record into table '{table_name}'.",
            "suggested_action": "Check database table schema constraints or trigger rules.",
            "entity": f"Table: {table_name}",
            "group_key": f"insertion_failure_{table_name}"
        }

    # 4. File Structure & Header Validation
    if col in ("FILE_VALIDATION", "FILE_INIT_ERROR") or "column" in msg.lower() or "header" in msg.lower():
        return {
            "category": "File Validation",
            "category_key": "validation",
            "severity": "critical",
            "friendly_title": "File Format or Column Mismatch",
            "friendly_explanation": msg,
            "suggested_action": "Ensure Excel columns match the template exactly and contain valid data.",
            "entity": "File Header",
            "group_key": "header_validation_error"
        }

    # Default fallback
    return {
        "category": "Data Validation",
        "category_key": "validation",
        "severity": "warning",
        "friendly_title": f"Data Issue on {col or 'Record'}",
        "friendly_explanation": msg,
        "suggested_action": "Review the relevant row in the uploaded Excel workbook.",
        "entity": col or "General",
        "group_key": f"general_{col}_{msg[:30]}"
    }


@router.get("/batches/{batch_id}/logs", response_model=List[UploadLogResponse])
async def get_batch_logs(batch_id: str):
    logs = [log for log in upload_logs_db if str(log.get("upload_batch_id")) == str(batch_id) or str(log.get("batch_id")) == str(batch_id)]
    client = get_supabase()
    if client:
        try:
            res = client.table("upload_validation_errors").select("error_id, batch_id, raw_id, column_name, error_message, created_at").eq("batch_id", batch_id).order("created_at", desc=True).limit(500).execute()
            if res.data:
                formatted = []
                for item in res.data:
                    formatted.append({
                        "upload_log_id": item.get("error_id") or str(uuid.uuid4()),
                        "upload_batch_id": item.get("batch_id") or batch_id,
                        "row_number": None,
                        "column_name": item.get("column_name"),
                        "error_message": item.get("error_message"),
                        "created_at": item.get("created_at") or datetime.utcnow(),
                    })
                return formatted
        except Exception as e:
            logger.warning(f"Failed to fetch logs from Supabase for batch {batch_id}: {e}")
    return logs


@router.get("/errors")
async def get_upload_errors(
    batch_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 250
):
    """
    Unified error endpoint returning human-friendly diagnostics, smart grouping,
    and category breakdowns for the frontend.
    """
    client = get_supabase()
    raw_errors: List[Dict[str, Any]] = []

    if client:
        try:
            query = client.table("upload_validation_errors").select("error_id, batch_id, raw_id, column_name, error_message, created_at").order("created_at", desc=True)
            if batch_id and batch_id != "all":
                query = query.eq("batch_id", batch_id)
            res = query.limit(limit).execute()
            if res.data:
                raw_errors = res.data
        except Exception as e:
            logger.warning(f"Error querying upload_validation_errors: {e}")

    # Also pull from in-memory upload_logs_db if DB yielded nothing
    if not raw_errors and upload_logs_db:
        for log in upload_logs_db:
            if not batch_id or batch_id == "all" or str(log.get("upload_batch_id")) == str(batch_id) or str(log.get("batch_id")) == str(batch_id):
                raw_errors.append({
                    "error_id": log.get("upload_log_id") or str(uuid.uuid4()),
                    "batch_id": log.get("upload_batch_id") or log.get("batch_id"),
                    "column_name": log.get("column_name"),
                    "error_message": log.get("error_message"),
                    "created_at": log.get("created_at") or datetime.utcnow().isoformat()
                })

    # Available batches for dropdown
    available_batches = []
    if client:
        try:
            b_res = client.table("upload_batches").select("batch_id, file_name, source_file, status, upload_status, created_at").order("created_at", desc=True).limit(10).execute()
            if b_res.data:
                for b in b_res.data:
                    available_batches.append({
                        "batch_id": str(b["batch_id"]),
                        "label": f"{b.get('source_file') or b.get('file_name') or 'Batch'} (#{str(b['batch_id'])[:8]})",
                        "status": b.get("upload_status") or b.get("status"),
                        "created_at": b.get("created_at")
                    })
        except Exception as eb:
            logger.warning(f"Could not load available batches: {eb}")

    # Process and humanize errors
    processed_errors = []
    grouped_map: Dict[str, Dict[str, Any]] = {}
    category_counts: Dict[str, int] = {
        "Master Data Mapping": 0,
        "System & Network": 0,
        "Database Insertion": 0,
        "File Validation": 0,
        "Data Validation": 0
    }

    for item in raw_errors:
        col = item.get("column_name")
        raw_msg = item.get("error_message") or ""
        human = humanize_upload_error(col, raw_msg)
        cat = human["category"]

        # Filter by category if requested
        if category and category.lower() != "all" and human["category_key"] != category.lower() and cat.lower() != category.lower():
            continue

        category_counts[cat] = category_counts.get(cat, 0) + 1

        error_entry = {
            "error_id": str(item.get("error_id") or uuid.uuid4()),
            "batch_id": str(item.get("batch_id") or "N/A"),
            "column_name": col or "General",
            "raw_message": raw_msg,
            "friendly_title": human["friendly_title"],
            "friendly_explanation": human["friendly_explanation"],
            "suggested_action": human["suggested_action"],
            "category": cat,
            "category_key": human["category_key"],
            "severity": human["severity"],
            "entity": human["entity"],
            "created_at": item.get("created_at")
        }
        processed_errors.append(error_entry)

        # Smart Grouping aggregation
        g_key = human["group_key"]
        if g_key not in grouped_map:
            grouped_map[g_key] = {
                "group_key": g_key,
                "category": cat,
                "category_key": human["category_key"],
                "severity": human["severity"],
                "friendly_title": human["friendly_title"],
                "friendly_explanation": human["friendly_explanation"],
                "suggested_action": human["suggested_action"],
                "entity": human["entity"],
                "affected_count": 0,
                "latest_seen": item.get("created_at"),
                "sample_raw": raw_msg,
                "batch_id": str(item.get("batch_id") or "N/A")
            }
        grouped_map[g_key]["affected_count"] += 1

    # Sort grouped issues by affected count descending
    top_issues = sorted(list(grouped_map.values()), key=lambda x: x["affected_count"], reverse=True)

    return {
        "total_errors": len(processed_errors),
        "category_counts": category_counts,
        "top_issues": top_issues,
        "errors": processed_errors,
        "available_batches": available_batches,
        "active_batch_id": batch_id or "all"
    }

