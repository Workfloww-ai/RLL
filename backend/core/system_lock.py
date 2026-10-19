import os
import json
import time
import copy
import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
from contextlib import contextmanager

logger = logging.getLogger(__name__)

COOLDOWN_STATE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".cooldown_state.json"))

# Short in-memory cache to prevent concurrent browser tabs/pollers from spamming Supabase
_SYSTEM_LOCK_CACHE = {
    "data": None,
    "timestamp": 0.0
}
_SYSTEM_LOCK_CACHE_TTL = 10  # 3 seconds cache buffer for near real-time state sync

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

UPLOAD_COOLDOWN_SECONDS = 1800  # 30 minutes for success
VALIDATION_ERROR_COOLDOWN_SECONDS = 600  # 10 minutes for validation error / rollback

_LAST_UPLOAD_COMPLETION = {
    "timestamp": 0.0,
    "upload_type": None,
    "filename": None,
    "cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,
    "reason": None
}

_COOLDOWN_OVERRIDE_RESET = False

def record_upload_cooldown(
    upload_type: str = "validation_error",
    filename: Optional[str] = None,
    cooldown_seconds: int = VALIDATION_ERROR_COOLDOWN_SECONDS,
    reason: Optional[str] = None
):
    """
    Enforces a cooldown buffer (10 minutes for validation errors/rollbacks, 30 minutes for successful uploads).
    During this period, any partial records are purged safely and new uploads are locked.
    """
    global _LAST_UPLOAD_COMPLETION, _COOLDOWN_OVERRIDE_RESET
    invalidate_system_lock_cache()
    _COOLDOWN_OVERRIDE_RESET = False
    now = time.time()
    rem_m = cooldown_seconds // 60
    is_success = cooldown_seconds > 600

    if is_success:
        default_msg = f"Upload completed successfully. 30-minute verification cooldown active."
        clean_reason = reason or default_msg
        if "10-minute" in clean_reason or "rollback" in clean_reason:
            clean_reason = default_msg
    else:
        default_msg = f"Validation issue detected. 10-minute rollback & purge buffer active. Next upload enabled in {rem_m} minutes."
        clean_reason = reason or default_msg
        if "30-minute" in clean_reason:
            clean_reason = default_msg

    _LAST_UPLOAD_COMPLETION = {
        "timestamp": now,
        "upload_type": upload_type,
        "filename": filename,
        "cooldown_seconds": cooldown_seconds,
        "reason": clean_reason
    }
    try:
        with open(COOLDOWN_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_LAST_UPLOAD_COMPLETION, f)
    except Exception as e_save:
        logger.warning(f"Could not save cooldown state to disk: {e_save}")

    logger.info(f"Recorded cooldown for '{filename}' ({upload_type}) for {cooldown_seconds}s at timestamp {now}.")


def record_upload_completion(upload_type: str, filename: str):
    """
    Records the timestamp when an upload (sales or roster) completes,
    initiating the 30-minute system cooldown and locking the whole system in read-only mode.
    """
    record_upload_cooldown(
        upload_type=upload_type,
        filename=filename,
        cooldown_seconds=UPLOAD_COOLDOWN_SECONDS,
        reason="Sales data ingestion successfully verified. 30-minute post-upload verification cooldown active."
    )


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
        "filename": None,
        "cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,
        "reason": None
    }
    try:
        if os.path.exists(COOLDOWN_STATE_FILE):
            os.remove(COOLDOWN_STATE_FILE)
    except Exception:
        pass
    logger.info("Upload cooldown manually reset.")


def get_upload_cooldown_status() -> Dict[str, Any]:
    """
    Determines if the system is within the 30-minute post-upload buffer.
    Checks memory state and queries Supabase DB for the most recent completed batch.
    """
    global _LAST_UPLOAD_COMPLETION
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
    cooldown_target = _LAST_UPLOAD_COMPLETION.get("cooldown_seconds") or UPLOAD_COOLDOWN_SECONDS

    # If memory is uninitialized, check persistent file on disk
    if latest_ts <= 0:
        try:
            if os.path.exists(COOLDOWN_STATE_FILE):
                with open(COOLDOWN_STATE_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    saved_ts = float(saved.get("timestamp", 0.0))
                    saved_cd = int(saved.get("cooldown_seconds", UPLOAD_COOLDOWN_SECONDS))
                    if 0 <= (now - saved_ts) < saved_cd:
                        latest_ts = saved_ts
                        latest_type = saved.get("upload_type")
                        latest_file = saved.get("filename")
                        cooldown_target = saved_cd
                        _LAST_UPLOAD_COMPLETION = saved
                    else:
                        try:
                            os.remove(COOLDOWN_STATE_FILE)
                        except Exception:
                            pass
        except Exception as e_file:
            logger.debug(f"Notice reading cooldown file: {e_file}")

    # Check database for latest batch if DB timestamp is newer or memory is uninitialized
    try:
        from backend.db.client import get_supabase
        from datetime import datetime, timezone
        client = get_supabase()
        if client:
            res = client.table("upload_batches").select(
                "batch_id, source_file, created_at, updated_at, status, processing_time_seconds"
            ).order("created_at", desc=True).limit(5).execute()

            if res.data:
                for b in res.data:
                    b_status = str(b.get("status") or "").lower()
                    if b_status in ("loaded", "completed", "success"):
                        b_cd_target = UPLOAD_COOLDOWN_SECONDS  # 1800s (30m)
                        b_type = "sales_upload"
                    elif b_status in ("failed", "error", "interrupted"):
                        b_cd_target = 600  # 600s (10m)
                        b_type = "validation_error"
                    else:
                        continue

                    created_str = b.get("created_at")
                    updated_str = b.get("updated_at")
                    proc_sec = float(b.get("processing_time_seconds") or 0.0)

                    c_ts = 0.0
                    if created_str:
                        try:
                            clean_c = created_str.replace("Z", "+00:00")
                            c_dt = datetime.fromisoformat(clean_c)
                            if c_dt.tzinfo is None:
                                c_dt = c_dt.replace(tzinfo=timezone.utc)
                            c_ts = c_dt.timestamp()
                        except Exception:
                            pass

                    u_ts = 0.0
                    if updated_str:
                        try:
                            clean_u = updated_str.replace("Z", "+00:00")
                            u_dt = datetime.fromisoformat(clean_u)
                            if u_dt.tzinfo is None:
                                u_dt = u_dt.replace(tzinfo=timezone.utc)
                            u_ts = u_dt.timestamp()
                        except Exception:
                            pass

                    # True completion timestamp: If processing took X seconds, completion is c_ts + proc_sec
                    if c_ts > 0 and proc_sec > 0:
                        completion_ts = c_ts + proc_sec
                    elif u_ts > c_ts:
                        completion_ts = u_ts
                    elif u_ts > 0:
                        completion_ts = u_ts
                    elif c_ts > 0:
                        completion_ts = c_ts
                    else:
                        completion_ts = 0.0

                    if completion_ts > latest_ts:
                        latest_ts = completion_ts
                        latest_type = b_type
                        latest_file = b.get("source_file") or b.get("file_name")
                        cooldown_target = b_cd_target
                        _LAST_UPLOAD_COMPLETION = {
                            "timestamp": latest_ts,
                            "upload_type": latest_type,
                            "filename": latest_file,
                            "cooldown_seconds": cooldown_target,
                            "reason": (
                                "Upload completed successfully. 30-minute verification cooldown active."
                                if cooldown_target > 600
                                else "Validation issue detected. 10-minute rollback & purge buffer active."
                            )
                        }
                        break
    except Exception as e_db:
        logger.debug(f"Notice querying latest upload batch for cooldown: {e_db}")

    if latest_ts > 0:
        elapsed = now - latest_ts
        if -60 < elapsed < 0:
            elapsed = 0.0
        if 0 <= elapsed < cooldown_target:
            remaining = int(cooldown_target - elapsed)
            rem_m = remaining // 60
            rem_s = remaining % 60
            is_val_err = (latest_type == "validation_error" or cooldown_target <= 600)

            if is_val_err:
                default_msg = f"Validation issue detected: 10-minute rollback & purge buffer active. Next upload enabled in {rem_m}m {rem_s:02d}s."
                raw_msg = _LAST_UPLOAD_COMPLETION.get("reason") or default_msg
                msg = default_msg if ("30-minute" in raw_msg or not raw_msg) else raw_msg
            else:
                default_msg = f"Upload completed successfully. 30-minute verification cooldown active. Next upload enabled in {rem_m}m {rem_s:02d}s."
                raw_msg = _LAST_UPLOAD_COMPLETION.get("reason") or default_msg
                msg = default_msg if ("10-minute" in raw_msg or "rollback" in raw_msg or not raw_msg) else raw_msg

            return {
                "is_active": True,
                "remaining_seconds": remaining,
                "cooldown_seconds": cooldown_target,
                "last_upload_time": latest_ts,
                "last_upload_type": latest_type,
                "last_upload_file": latest_file,
                "message": msg
            }

    return {
        "is_active": False,
        "remaining_seconds": 0,
        "cooldown_seconds": cooldown_target,
        "last_upload_time": latest_ts if latest_ts > 0 else None,
        "last_upload_type": latest_type,
        "last_upload_file": latest_file,
        "message": "Upload is enabled."
    }


def check_upload_cooldown_or_raise():
    """
    Raises HTTP 429 Too Many Requests if an upload is attempted during an active cooldown.
    """
    cooldown = get_upload_cooldown_status()
    if cooldown.get("is_active"):
        rem_m = cooldown["remaining_seconds"] // 60
        rem_s = cooldown["remaining_seconds"] % 60
        total_m = (cooldown.get("cooldown_seconds") or 1800) // 60
        custom_msg = cooldown.get("message")
        detail_msg = custom_msg or f"Upload rate limit: A {total_m}-minute interval is enforced between uploads. Next upload will be enabled in {rem_m}m {rem_s:02d}s."
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail_msg
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
            cd_target = cd.get("cooldown_seconds") or UPLOAD_COOLDOWN_SECONDS
            rem = max(0, int(cd_target - elapsed))
            cd["remaining_seconds"] = rem
            rem_m = rem // 60
            rem_s = rem % 60
            cd_target_m = cd_target // 60
            is_clean = (cd_target <= 600 or cd_target_m <= 10 or cd.get("last_upload_type") == "validation_error")
            desc_label = "10-minute rollback & purge buffer" if is_clean else "30-minute post-upload verification cooldown buffer"
            cd["message"] = (
                f"Validation issue detected: 10-minute rollback & purge buffer active. Next upload enabled in {rem_m}m {rem_s:02d}s."
                if is_clean else
                f"Upload completed successfully. 30-minute verification cooldown active. Next upload enabled in {rem_m}m {rem_s:02d}s."
            )
            if rem == 0:
                cd["is_active"] = False
                # Cooldown expired: system unlocked
                if cached.get("lock_type") == "cooldown":
                    cached["is_locked"] = False
                    cached["lock_type"] = None
                    cached["lock_reason"] = None
            else:
                if cached.get("lock_type") == "cooldown":
                    cached["is_locked"] = True
                    cached["lock_reason"] = f"System is in {desc_label}. Next upload enabled in {rem_m}m {rem_s:02d}s. All updates, personnel edits, and uploads are locked in Read-Only mode."
        return cached

    cooldown_info = get_upload_cooldown_status()

    # 1. Check sales upload pipeline (active row ingestion)
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

    # 3. If no active upload is running, but 30-minute cooldown is active:
    # Lock the ENTIRE system in Read-Only mode!
    if cooldown_info.get("is_active"):
        rem = cooldown_info.get("remaining_seconds", 0)
        rem_m = rem // 60
        rem_s = rem % 60
        lf = cooldown_info.get("last_upload_file")
        file_desc = f" ({lf})" if lf else ""
        cd_target = cooldown_info.get("cooldown_seconds") or 1800
        cd_target_m = cd_target // 60
        is_clean = (cd_target <= 600 or cd_target_m <= 10 or cooldown_info.get("last_upload_type") == "validation_error")
        desc_label = "10-minute rollback & purge buffer" if is_clean else "30-minute post-upload verification cooldown buffer"
        locked_res = {
            "is_locked": True,
            "lock_type": "cooldown",
            "lock_reason": f"System is in {desc_label}{file_desc}. Next upload enabled in {rem_m}m {rem_s:02d}s. All updates, personnel edits, and uploads are locked in Read-Only mode.",
            "active_batch": None,
            "cooldown": cooldown_info
        }
        _SYSTEM_LOCK_CACHE["data"] = locked_res
        _SYSTEM_LOCK_CACHE["timestamp"] = now
        return locked_res

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
    Enforces read-only mode during active uploads and 30-minute cooldown by raising HTTP 423 Locked.
    """
    status_info = get_system_lock_status()
    if status_info.get("is_locked"):
        reason = status_info.get("lock_reason") or "A file upload or 30-minute cooldown buffer is currently active."
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"System is temporarily in Read-Only mode: {reason}. Personnel changes, manager reassignments, and additional uploads are locked to prevent data corruption."
        )
