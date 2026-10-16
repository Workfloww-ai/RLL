import time
import copy
import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Short in-memory cache to prevent concurrent browser tabs/pollers from spamming Supabase
_SYSTEM_LOCK_CACHE = {
    "data": None,
    "timestamp": 0.0
}
_SYSTEM_LOCK_CACHE_TTL = 4.0  # 4 seconds

def invalidate_system_lock_cache():
    global _SYSTEM_LOCK_CACHE
    _SYSTEM_LOCK_CACHE["timestamp"] = 0.0
    _SYSTEM_LOCK_CACHE["data"] = None

# In-memory tracking for roster upload state
_ROSTER_UPLOAD_LOCK = {
    "active": False,
    "filename": None,
    "started_at": 0.0
}

def set_roster_upload_active(filename: str):
    global _ROSTER_UPLOAD_LOCK
    invalidate_system_lock_cache()
    _ROSTER_UPLOAD_LOCK = {
        "active": True,
        "filename": filename,
        "started_at": time.time()
    }

def clear_roster_upload_active():
    global _ROSTER_UPLOAD_LOCK
    invalidate_system_lock_cache()
    _ROSTER_UPLOAD_LOCK = {
        "active": False,
        "filename": None,
        "started_at": 0.0
    }

@contextmanager
def roster_upload_lock(filename: str):
    set_roster_upload_active(filename)
    try:
        yield
    finally:
        clear_roster_upload_active()

UPLOAD_COOLDOWN_SECONDS = 1800  # 30 minutes

_LAST_UPLOAD_COMPLETION = {
    "timestamp": 0.0,
    "upload_type": None,
    "filename": None
}

_COOLDOWN_OVERRIDE_RESET = False

def record_upload_completion(upload_type: str, filename: str):
    """
    Records the timestamp when an upload (sales or roster) completes,
    initiating the 30-minute system cooldown.
    """
    global _LAST_UPLOAD_COMPLETION, _COOLDOWN_OVERRIDE_RESET
    invalidate_system_lock_cache()
    _COOLDOWN_OVERRIDE_RESET = False
    now = time.time()
    _LAST_UPLOAD_COMPLETION = {
        "timestamp": now,
        "upload_type": upload_type,
        "filename": filename
    }
    logger.info(f"Recorded upload completion for '{filename}' ({upload_type}) at timestamp {now}. 30-minute cooldown active.")


def reset_upload_cooldown():
    """
    Resets post-upload cooldown (for testing and administrative purposes).
    """
    global _LAST_UPLOAD_COMPLETION, _COOLDOWN_OVERRIDE_RESET
    invalidate_system_lock_cache()
    _COOLDOWN_OVERRIDE_RESET = True
    _LAST_UPLOAD_COMPLETION = {
        "timestamp": 0.0,
        "upload_type": None,
        "filename": None
    }
    logger.info("Upload cooldown manually reset.")


def get_upload_cooldown_status() -> Dict[str, Any]:
    """
    Determines if the system is within the 30-minute post-upload buffer.
    Checks memory state and queries Supabase DB for the most recent completed batch.
    """
    if _COOLDOWN_OVERRIDE_RESET:
        return {
            "is_active": False,
            "remaining_seconds": 0,
            "cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,
            "last_upload_time": None,
            "last_upload_type": None,
            "last_upload_file": None,
            "message": "Upload is enabled (cooldown reset)."
        }

    now = time.time()
    latest_ts = _LAST_UPLOAD_COMPLETION.get("timestamp", 0.0)
    latest_type = _LAST_UPLOAD_COMPLETION.get("upload_type")
    latest_file = _LAST_UPLOAD_COMPLETION.get("filename")

    # Check database for latest batch if DB timestamp is newer or memory is uninitialized
    try:
        from backend.db.client import get_supabase
        from datetime import datetime, timezone
        client = get_supabase()
        if client:
            res = client.table("upload_batches").select(
                "batch_id, source_file, file_name, created_at, updated_at, status, upload_status"
            ).in_("status", ["loaded", "completed", "success"]).order("created_at", desc=True).limit(1).execute()

            if res.data and len(res.data) > 0:
                b = res.data[0]
                ts_str = b.get("updated_at") or b.get("created_at")
                if ts_str:
                    clean_dt_str = ts_str.replace("Z", "+00:00")
                    c_dt = datetime.fromisoformat(clean_dt_str)
                    if c_dt.tzinfo is None:
                        c_dt = c_dt.replace(tzinfo=timezone.utc)
                    db_ts = c_dt.timestamp()
                    if db_ts > latest_ts:
                        latest_ts = db_ts
                        latest_type = "sales_upload"
                        latest_file = b.get("source_file") or b.get("file_name")
    except Exception as e_db:
        logger.debug(f"Notice querying latest upload batch for cooldown: {e_db}")

    if latest_ts > 0:
        elapsed = now - latest_ts
        if -60 < elapsed < 0:
            elapsed = 0.0
        if 0 <= elapsed < UPLOAD_COOLDOWN_SECONDS:
            remaining = int(UPLOAD_COOLDOWN_SECONDS - elapsed)
            rem_m = remaining // 60
            rem_s = remaining % 60
            return {
                "is_active": True,
                "remaining_seconds": remaining,
                "cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,
                "last_upload_time": latest_ts,
                "last_upload_type": latest_type,
                "last_upload_file": latest_file,
                "message": f"Upload cooldown active. Next upload enabled in {rem_m}m {rem_s:02d}s."
            }

    return {
        "is_active": False,
        "remaining_seconds": 0,
        "cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,
        "last_upload_time": latest_ts if latest_ts > 0 else None,
        "last_upload_type": latest_type,
        "last_upload_file": latest_file,
        "message": "Upload is enabled."
    }


def check_upload_cooldown_or_raise():
    """
    Raises HTTP 429 Too Many Requests if an upload is attempted during the 30-minute cooldown.
    """
    cooldown = get_upload_cooldown_status()
    if cooldown.get("is_active"):
        rem_m = cooldown["remaining_seconds"] // 60
        rem_s = cooldown["remaining_seconds"] % 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Upload rate limit: A 30-minute interval is enforced between uploads. Next upload will be enabled in {rem_m}m {rem_s:02d}s."
        )


def get_system_lock_status() -> Dict[str, Any]:
    """
    Returns whether the system is currently locked in read-only mode due to an active upload,
    and returns 30-minute upload cooldown state.
    1. Sales data upload pipeline (queued, running, processing, aggregating, validating)
    2. Headcount roster upload pipeline
    3. Post-upload 30-minute cooldown timer
    """
    global _SYSTEM_LOCK_CACHE
    now = time.time()
    if _SYSTEM_LOCK_CACHE["data"] is not None and (now - _SYSTEM_LOCK_CACHE["timestamp"]) < _SYSTEM_LOCK_CACHE_TTL:
        cached = copy.deepcopy(_SYSTEM_LOCK_CACHE["data"])
        cd = cached.get("cooldown", {})
        if cd.get("is_active") and cd.get("last_upload_time"):
            elapsed = now - cd["last_upload_time"]
            rem = max(0, int(UPLOAD_COOLDOWN_SECONDS - elapsed))
            cd["remaining_seconds"] = rem
            rem_m = rem // 60
            rem_s = rem % 60
            cd["message"] = f"Upload cooldown active. Next upload enabled in {rem_m}m {rem_s:02d}s."
            if rem == 0:
                cd["is_active"] = False
        return cached

    cooldown_info = get_upload_cooldown_status()

    # 1. Check sales upload pipeline
    try:
        from backend.uploads.service import import_pipeline
        active_sales = import_pipeline.is_upload_active()
        if active_sales:
            file_name = active_sales.get("source_file") or active_sales.get("file_name") or "Sales Excel File"
            batch_id = active_sales.get("batch_id") or active_sales.get("upload_batch_id")
            status_val = active_sales.get("status") or active_sales.get("upload_status") or "processing"
            progress_msg = active_sales.get("remarks") or f"Processing sales file '{file_name}'"
            locked_res = {
                "is_locked": True,
                "lock_type": "sales_upload",
                "lock_reason": f"Sales file upload in progress ({file_name})",
                "active_batch": {
                    "batch_id": str(batch_id),
                    "file_name": file_name,
                    "status": status_val,
                    "remarks": progress_msg,
                    "total_rows": active_sales.get("total_rows") or active_sales.get("row_count"),
                    "imported_rows": active_sales.get("imported_rows") or 0,
                    "created_at": active_sales.get("created_at")
                },
                "cooldown": cooldown_info
            }
            _SYSTEM_LOCK_CACHE["data"] = locked_res
            _SYSTEM_LOCK_CACHE["timestamp"] = now
            return locked_res
    except Exception as e_sales:
        logger.warning(f"Error checking active sales upload lock: {e_sales}")

    # 2. Check roster upload pipeline
    if _ROSTER_UPLOAD_LOCK["active"]:
        # Auto-timeout after 5 minutes if something crashed
        if (now - _ROSTER_UPLOAD_LOCK["started_at"]) < 300:
            fn = _ROSTER_UPLOAD_LOCK.get("filename") or "User Roster File"
            locked_res = {
                "is_locked": True,
                "lock_type": "roster_upload",
                "lock_reason": f"User headcount roster upload in progress ({fn})",
                "active_batch": {
                    "batch_id": "roster_upload",
                    "file_name": fn,
                    "status": "processing",
                    "remarks": f"Importing headcount roster '{fn}'..."
                },
                "cooldown": cooldown_info
            }
            _SYSTEM_LOCK_CACHE["data"] = locked_res
            _SYSTEM_LOCK_CACHE["timestamp"] = now
            return locked_res
        else:
            clear_roster_upload_active()

    res = {
        "is_locked": False,
        "lock_type": None,
        "lock_reason": None,
        "active_batch": None,
        "cooldown": cooldown_info
    }
    _SYSTEM_LOCK_CACHE["data"] = res
    _SYSTEM_LOCK_CACHE["timestamp"] = now
    return res


def check_system_lock_or_raise():
    """
    Enforces read-only mode during active uploads by raising HTTP 423 Locked.
    """
    status_info = get_system_lock_status()
    if status_info.get("is_locked"):
        reason = status_info.get("lock_reason") or "A file upload is currently in progress"
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"System is temporarily in Read-Only mode: {reason}. Personnel changes, manager reassignments, and additional uploads are locked to prevent data corruption."
        )
