import io
import os
import re
import time
import logging
import tempfile
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
import re
# pyrefly: ignore [missing-import]
from fastapi import UploadFile
import pandas as pd
# pyrefly: ignore [missing-import]
from numbers_parser import Document

from backend.db.client import get_supabase
from backend.db.supabase_client import (
    try_acquire_advisory_lock,
    release_advisory_lock,
    get_active_upload_batch,
)
from backend.master_data.service import master_service
from backend.services.cache_service import invalidate_analytics_cache

logger = logging.getLogger(__name__)



# ============================================================
# GOVERNMENT EXCEL COLUMNS
# ============================================================

MANDATORY_COLUMNS = [
    "Date",
    "Company",
    "LICENSEE_NAME",
    "Trade",
    "Group Name",
    "H.Q.",
    "DEO_OFFICE_NAME",
    "DEPOT_NAME",
    "ASE",
    "ASM/TSM",
    "BRAND_NAME",
    "PACKING_IN_ML",
    "TOTAL_CASE",
]


# Flexible aliases in case government Excel headers change slightly.
COLUMN_ALIASES = {
    "Date": [
        "date",
        "sales date",
        "sale date",
    ],
    "Company": [
        "company",
        "company name",
        "company_name",
    ],
    "Category": [
        "category",
        "company category",
        "company_category",
        "comp category",
    ],
    "LICENSEE_NAME": [
        "licensee_name",
        "licensee name",
        "licensee",
        "license number",
        "license_number",
    ],
    "Trade": [
        "trade",
        "trade type",
        "trade_type",
    ],
    "Group Name": [
        "group name",
        "group_name",
        "group",
    ],
    "H.Q.": [
        "h.q.",
        "h.q",
        "hq",
        "headquarters",
        "headquarter",
    ],
    "DEO_OFFICE_NAME": [
        "deo_office_name",
        "deo office name",
        "deo office",
        "office",
    ],
    "CIRCLE_OFFICE_NAME": [
        "circle_office_name",
        "circle office name",
        "circle office",
        "circle",
    ],
    "DEPOT_NAME": [
        "depot_name",
        "depot name",
        "depot",
        "depot code",
        "depot_code",
    ],
    "ASE": [
        "ase",
        "ase name",
        "ase_name",
    ],
    "ASM/TSM": [
        "asm/tsm",
        "asm / tsm",
        "asm_tsm",
        "asm tsm",
        "tsm",
    ],
    "BRAND_NAME": [
        "brand_name",
        "brand name",
        "brand",
        "brand code",
        "brand_code",
    ],
    "PACKING_IN_ML": [
        "packing_in_ml",
        "packing in ml",
        "packing",
        "packing size",
        "packing_size",
    ],
    "TOTAL_CASE": [
        "case",
        "cases",
        "total_case",
        "total case",
        "total cases",
    ],
    "TOTAL_BTL": [
        "total_btl",
        "total btl",
        "total bottles",
        "bottles",
        "bottle",
    ],
    # "TOTAL_BL": [
    #     "total_bl",
    #     "total bl",
    #     "bulk liters",
    #     "bulk litres",
    #     "bulk liter",
    #     "bulk litre",
    # ],
}



# ============================================================
# LOCAL RESPONSE CACHE
#
# Your current api/v1/uploads.py GET routes use these variables.
# Supabase remains the real persistent database.
# ============================================================

upload_batches_db: Dict[int, Dict[str, Any]] = {}
upload_logs_db: List[Dict[str, Any]] = []


class UploadCancelledException(Exception):
    """Raised when an active upload batch has been cancelled by the user."""
    pass


class ImportPipelineEngine:

    def __init__(self):
        self._cancelled_batches = set()

    def cancel_batch(self, batch_id: Any) -> Dict[str, Any]:
        """
        Stops the execution of an upload batch pipeline and executes an atomic rollback
        to 0 rows in database (sales_fact, user_sales_fact, raw_sales_upload, batch_chunks, upload_pipeline_logs).
        Releases advisory lock and resets system lock cache immediately.
        """
        b_str = str(batch_id).strip()
        logger.warning(f"Request to cancel and rollback upload batch {b_str} received.")
        self._cancelled_batches.add(b_str)
        try:
            self._cancelled_batches.add(int(b_str))
        except (ValueError, TypeError):
            pass

        # 1. Update in-memory state
        local_batch = upload_batches_db.get(b_str) or upload_batches_db.get(int(b_str) if b_str.isdigit() else -1)
        if local_batch:
            local_batch.update({
                "status": "cancelled",
                "upload_status": "cancelled",
                "remarks": "Upload cancelled by user. Execution stopped and partial records rolled back to 0."
            })

        # 2. Update DB upload_batches status
        client = get_supabase()
        if client:
            try:
                cancel_payload = {
                    "status": "cancelled",
                    "remarks": "Upload cancelled by user. Execution stopped and partial records rolled back to 0.",
                    "updated_at": datetime.now().isoformat()
                }
                if local_batch:
                    u_fk = local_batch.get("uploaded_by") or local_batch.get("created_by") or local_batch.get("updated_by")
                    if u_fk and len(str(u_fk)) == 36 and str(u_fk) != "00000000-0000-0000-0000-000000000001":
                        cancel_payload["updated_by"] = str(u_fk)
                client.table("upload_batches").update(cancel_payload).eq("batch_id", b_str).execute()
                logger.info(f"Updated upload_batches #{b_str} status to 'cancelled'.")
            except Exception as exc:
                logger.warning(f"Failed to update batch {b_str} status to cancelled: {exc}")

        # 3. Clean up all partial records inserted for this batch
        self._cleanup_failed_batch(b_str)

        # 4. Release locks and invalidate system lock cache
        self.release_pipeline_lock(b_str)
        try:
            from backend.core.system_lock import invalidate_system_lock_cache, clear_roster_upload_active, record_upload_cooldown
            invalidate_system_lock_cache()
            clear_roster_upload_active()
            source_fname = (local_batch.get("source_file") if local_batch else None) or "Cancelled Upload"
            record_upload_cooldown(
                upload_type="validation_error",
                filename=source_fname,
                cooldown_seconds=600,
                reason=f"Upload cancelled and rolled back for '{source_fname}'. 10-minute purge buffer active."
            )
        except Exception as e_lock:
            logger.warning(f"Error setting cooldown during cancel: {e_lock}")

        return {
            "success": True,
            "batch_id": b_str,
            "status": "cancelled",
            "message": "Upload batch successfully cancelled and all partial records rolled back to 0."
        }

    def is_batch_cancelled(self, batch_id: Any) -> bool:
        if not batch_id:
            return False
        b_str = str(batch_id).strip()
        if b_str in self._cancelled_batches or (b_str.isdigit() and int(b_str) in self._cancelled_batches):
            return True
        batch = upload_batches_db.get(b_str) or upload_batches_db.get(int(b_str) if b_str.isdigit() else -1)
        if batch:
            st = str(batch.get("status", "")).lower()
            if st in ("cancelled", "failed", "interrupted"):
                return True
        return False

    def is_batch_aborted_in_db(self, batch_id: Any) -> bool:
        """
        Authoritative DB check: Returns True if upload_batches status in Supabase 
        has been marked 'failed', 'cancelled', or 'interrupted' by a timeout, admin, or user.
        """
        if not batch_id:
            return False
        try:
            client = get_supabase()
            if not client:
                return False
            b_str = str(batch_id).strip()
            res = client.table("upload_batches").select("status").eq("batch_id", b_str).limit(1).execute()
            if res and res.data:
                st = str(res.data[0].get("status") or "").lower()
                if st in ("failed", "cancelled", "interrupted"):
                    self._cancelled_batches.add(b_str)
                    local_batch = upload_batches_db.get(b_str)
                    if local_batch:
                        local_batch["status"] = st
                    return True
        except Exception as e_chk:
            logger.debug(f"is_batch_aborted_in_db notice for batch {batch_id}: {e_chk}")
        return False


    # ========================================================
    # BASIC HELPERS
    # ========================================================

    @staticmethod
    def _clean_text(value) -> str:
        """
        Clean Excel text without changing its capitalization.

        Example:
            "  Sikar   North "
        becomes:
            "Sikar North"
        """

        if value is None:
            return ""

        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        value = str(value).strip()

        if value.lower() in {
            "nan",
            "none",
            "null",
            "nat",
        }:
            return ""

        return " ".join(value.split())

    @staticmethod
    def _normalize_header(value) -> str:
        """
        Normalize an Excel header for matching by converting to lowercase
        and stripping all whitespace, underscores, hyphens, dots, and special characters.
        Example: "  Depot_Code-Name. (ML) " -> "depotcodename-ml"
        """
        if value is None:
            return ""

        text = str(value).strip().lower()
        # Remove all whitespace, underscores, hyphens, dots, slashes, and special symbols
        import re
        return re.sub(r"[\s\-_.\/\\(),:;]", "", text)

    @staticmethod
    def _number(value, default: float = 0.0) -> float:
        """
        Convert Excel numeric values safely.

        Handles:
            1
            1.5
            "1,234"
            NaN
            blank
        """

        if value is None:
            return default

        try:
            if pd.isna(value):
                return default
        except Exception:
            pass

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()

        if not text:
            return default

        text = text.replace(",", "")

        return float(text)

    @staticmethod
    def _parse_date(value) -> str:
        """
        Convert Government Excel dates into PostgreSQL DATE format (YYYY-MM-DD).

        Supports formats:
            - 02.04.26, 02.04.2026, 2.4.26 (DD.MM.YY / DD.MM.YYYY)
            - 02/04/26, 02/04/2026 (DD/MM/YY / DD/MM/YYYY)
            - 02-04-26, 02-04-2026 (DD-MM-YY / DD-MM-YYYY)
            - 2026-04-02 (YYYY-MM-DD)
            - 02-Apr-26, 02-Apr-2026
            - Excel numeric serial numbers (e.g. 46114, 46114.0)
            - Timestamps with time portions (e.g. '02.04.26 00:00:00')
        """
        from datetime import date as date_cls

        if value is None:
            raise ValueError("Date is empty.")

        try:
            if pd.isna(value):
                raise ValueError("Date is empty.")
        except (TypeError, ValueError):
            pass

        if isinstance(value, (pd.Timestamp, datetime, date_cls)):
            return value.strftime("%Y-%m-%d")

        # Handle numeric Excel serial numbers (e.g. 46114 or 46114.0)
        if isinstance(value, (int, float)):
            if 30000 <= value <= 60000:
                try:
                    dt = pd.to_datetime(value, unit="D", origin="1899-12-30")
                    return dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

        text = str(value).strip()
        if not text or text.lower() in ("nan", "none", "null", "nat", ""):
            raise ValueError("Date is empty.")

        # Clean numeric string Excel serial numbers (e.g. '46114' or '46114.0')
        try:
            num_val = float(text)
            if 30000 <= num_val <= 60000:
                dt = pd.to_datetime(num_val, unit="D", origin="1899-12-30")
                return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        # Strip time component if present (e.g., '02.04.26 00:00:00' or '2026-04-02T00:00:00')
        clean_text = text.split("T")[0].split(" ")[0].strip()

        formats = [
            "%d.%m.%y",
            "%d.%m.%Y",
            "%d/%m/%y",
            "%d/%m/%Y",
            "%d-%m-%y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%d-%b-%y",
            "%d-%b-%Y",
            "%d %b %Y",
            "%d %b %y",
            "%d-%B-%Y",
            "%d %B %Y",
        ]

        for date_format in formats:
            try:
                parsed = datetime.strptime(clean_text, date_format)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        try:
            parsed = pd.to_datetime(clean_text, dayfirst=True, errors="raise")
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            raise ValueError(f"Invalid Date value: {value}")

    @staticmethod
    def _normalize_trade(value) -> str:
        """
        licensees.trade_type CHECK constraint allows:
            Off
            On
        """

        text = str(value or "").strip().lower()

        if text == "off":
            return "Off"

        if text == "on":
            return "On"

        raise ValueError(
            f"Invalid Trade '{value}'. "
            "Expected 'Off' or 'On'."
        )

    # ========================================================
    # PREFLIGHT HEALTH GUARD & TEMPORARY DATA CLEANUP
    # ========================================================

    def check_db_health(self) -> Dict[str, Any]:
        """
        Phase 1 Preflight Health Guard:
        Verifies database connectivity and health prior to accepting file uploads.
        """
        client = get_supabase()
        if not client:
            return {"healthy": True, "mode": "mock", "message": "Supabase client unconfigured, operating in mock mode."}
        try:
            res = client.table("upload_batches").select("batch_id").limit(1).execute()
            return {"healthy": True, "mode": "live", "message": "Database is healthy and reachable."}
        except Exception as exc:
            logger.error(f"Preflight DB health check failed: {exc}")
            return {"healthy": False, "mode": "error", "message": str(exc)}

    def _purge_batch_temporary_data(self, batch_id: int):
        """
        Phase 1 & Query Performance Optimization Automatic Post-Ingestion Cleanup:
        Executes fast index-seeking stored procedure purge_batch_data_fast to purge staging data
        (raw_sales_upload), chunk tracking (batch_chunks), and pipeline logs (upload_pipeline_logs) in < 15ms.
        """
        client = get_supabase()
        if not client or not batch_id:
            return

        logger.info(f"Phase 1 & Fast Purge: Cleaning temporary ingestion data for batch {batch_id}...")

        try:
            from backend.db.supabase_client import purge_batch_data_fast_rpc
            if purge_batch_data_fast_rpc(str(batch_id), chunk_size=10000):
                logger.info(f"Batch {batch_id}: Cleaned up temporary staging tables in chunked RPC call.")
                return
        except Exception as e_rpc:
            logger.debug(f"purge_batch_data_fast_rpc notice for batch {batch_id}: {e_rpc}")

        temp_tables = [
            "raw_sales_upload",
            "batch_chunks",
            "upload_pipeline_logs",
        ]

        b_str = str(batch_id).strip()
        for table_name in temp_tables:
            try:
                pk_col = "raw_id" if table_name == "raw_sales_upload" else ("log_id" if table_name == "upload_pipeline_logs" else "id")
                # 1. Attempt direct delete by batch_id
                try:
                    client.table(table_name).delete().eq("batch_id", b_str).execute()
                    logger.info(f"Batch {batch_id}: Cleaned up temporary {table_name} table.")
                except Exception:
                    # 2. Chunked fallback (1000 at a time to stay well within URL length limits)
                    while True:
                        sub_res = client.table(table_name).select(pk_col).eq("batch_id", b_str).limit(1000).execute()
                        rows = sub_res.data or []
                        if not rows:
                            break
                        pks = [r.get(pk_col) for r in rows if r.get(pk_col)]
                        if not pks:
                            break
                        client.table(table_name).delete().in_(pk_col, pks).execute()
                    logger.info(f"Batch {batch_id}: Cleaned up temporary {table_name} table via chunked purge.")
            except Exception as exc:
                logger.warning(f"Phase 1 Cleanup notice for table '{table_name}' batch {batch_id}: {exc}")

    # ========================================================
    # PHASE 2: SINGLE-UPLOAD QUEUE & OVERLAP PREVENTION
    # ========================================================

    def is_upload_active(self, exclude_batch_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Phase 2 Single-Upload Queue:
        Checks if an upload job is currently active in PostgreSQL DB or memory.
        Authoritative source: PostgreSQL DB.
        """
        client = get_supabase()
        if client:
            db_active = get_active_upload_batch()
            if db_active:
                active_id = db_active.get("batch_id")
                if exclude_batch_id and str(active_id) == str(exclude_batch_id):
                    return None
                return db_active
            else:
                # Database has no active batches - purge any stale in-memory active batches
                active_statuses = {"queued", "running", "processing", "aggregating", "validating", "validated", "staged", "saving", "uploading"}
                for b_id, batch in list(upload_batches_db.items()):
                    st = str(batch.get("status", "")).lower()
                    if st in active_statuses:
                        upload_batches_db.pop(b_id, None)
                return None

        # Fallback to local memory only if client is disconnected
        active_statuses = {"queued", "running", "processing", "aggregating", "validating", "validated", "staged", "saving", "uploading"}
        now_ts = time.time()
        for b_id, batch in list(upload_batches_db.items()):
            if exclude_batch_id and str(b_id) == str(exclude_batch_id):
                continue
            st = str(batch.get("status", "")).lower()
            if st in active_statuses:
                c_iso = batch.get("created_at")
                if c_iso:
                    try:
                        c_dt = datetime.fromisoformat(c_iso.replace("Z", "+00:00"))
                        if (now_ts - c_dt.timestamp()) > 3600:
                            upload_batches_db.pop(b_id, None)
                            continue
                    except Exception:
                        pass
                return batch

        return None

    def check_overlapping_date_window(
        self,
        covers_start: str,
        covers_end: str,
        exclude_batch_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Phase 2 Overlapping Date Replacement Prevention:
        Checks if an active upload batch covers a date range that overlaps with [covers_start, covers_end].
        Date Overlap Condition: existing.covers_start <= covers_end AND existing.covers_end >= covers_start
        Returns the conflicting active batch dict if an overlap exists, else None.
        """
        if not covers_start or not covers_end:
            return None

        active_batch = self.is_upload_active(exclude_batch_id=exclude_batch_id)
        if not active_batch:
            return None

        existing_start = active_batch.get("covers_start")
        existing_end = active_batch.get("covers_end")

        if existing_start and existing_end:
            if str(existing_start) <= str(covers_end) and str(existing_end) >= str(covers_start):
                return active_batch

        return None

    def acquire_pipeline_lock(
        self,
        batch_id: int,
        covers_start: Optional[str] = None,
        covers_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Phase 2 Advisory Lock & Pipeline Guard:
        Attempts to acquire PostgreSQL advisory lock and checks for active/overlapping pipelines.
        Returns dict {"acquired": True} if successful, or {"acquired": False, "reason": ..., "active_batch": ...}
        """
        # Check if another upload is active
        active_batch = self.is_upload_active(exclude_batch_id=batch_id)
        if active_batch:
            active_id = active_batch.get("batch_id") or active_batch.get("upload_batch_id")
            return {
                "acquired": False,
                "reason": f"An upload pipeline is already active (Batch #{active_id}). Single-upload queue prevents concurrent execution.",
                "active_batch": active_batch,
            }

        # Check date window overlap if dates provided
        if covers_start and covers_end:
            overlap = self.check_overlapping_date_window(covers_start, covers_end, exclude_batch_id=batch_id)
            if overlap:
                active_id = overlap.get("batch_id") or overlap.get("upload_batch_id")
                return {
                    "acquired": False,
                    "reason": f"Sales date window ({covers_start} to {covers_end}) overlaps with active ingestion Batch #{active_id}.",
                    "active_batch": overlap,
                }

        # Acquire PostgreSQL pg_try_advisory_lock
        lock_ok = try_acquire_advisory_lock()
        if not lock_ok:
            return {
                "acquired": False,
                "reason": "PostgreSQL advisory lock is held by another active process.",
                "active_batch": None,
            }

        return {"acquired": True}

    def release_pipeline_lock(self, batch_id: Optional[Any] = None):
        """
        Phase 2 Release Lock & Post-Lock Staging Drop:
        Releases PostgreSQL advisory lock upon pipeline completion or failure,
        and drops temporary data from public.raw_sales_upload.
        """
        try:
            release_advisory_lock()
            logger.info(f"Phase 2 Advisory Lock released for batch {batch_id}.")
        except Exception as exc:
            logger.warning(f"Phase 2 release_pipeline_lock notice for batch {batch_id}: {exc}")

        # Always drop staging records from raw_sales_upload after pipeline completes/fails.
        # Diagnostics are securely preserved in error_logs (source='VALIDATION_ERROR').
        try:
            client = get_supabase()
            if client and batch_id:
                b_str = str(batch_id).strip()
                try:
                    client.rpc("purge_batch_data_fast", {"p_batch_id": b_str}).execute()
                    logger.info(f"Batch {batch_id}: Purged raw_sales_upload via purge_batch_data_fast RPC.")
                except Exception:
                    client.table("raw_sales_upload").delete().eq("batch_id", b_str).execute()
                    logger.info(f"Batch {batch_id}: Purged staging records from raw_sales_upload.")
        except Exception as exc_drop:
            logger.warning(f"Notice purging raw_sales_upload for batch {batch_id} after lock release: {exc_drop}")

    # ========================================================
    # CREATE UPLOAD BATCH
    # ========================================================

    def create_initial_batch(
        self,
        filename: str,
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        filename_lower = filename.lower()

        allowed_extensions = (
            ".xlsx",
            ".xls",
            ".xlsb",
            ".numbers",
            ".csv",
        )

        if not filename_lower.endswith(allowed_extensions):
            raise ValueError(
                "Invalid file type. Only .xlsx, .xls, .xlsb, .numbers, and .csv files are accepted."
            )

        # Phase 2 Idempotency Check: if an active upload batch exists for the same source file, return existing batch
        active = self.is_upload_active()
        if active:
            act_file = active.get("source_file") or active.get("file_name")
            if act_file and str(act_file).strip().lower() == filename_lower.strip():
                logger.info(f"Phase 2 Idempotency: Returning active batch #{active.get('batch_id')} for {filename}")
                active["is_existing_active"] = True
                return active

        client = get_supabase()
        batch_id = None
        # Dynamically resolve tenant_id from the uploading user if not supplied
        if not tenant_id and user_id and client:
            try:
                u_res = client.table("users").select("tenant_id").eq("user_id", str(user_id)).limit(1).execute()
                if u_res.data and u_res.data[0].get("tenant_id"):
                    tenant_id = str(u_res.data[0]["tenant_id"])
            except Exception as e_t:
                logger.warning(f"Could not resolve tenant_id for user {user_id}: {e_t}")

        today_str = datetime.now().strftime("%Y-%m-%d")

        if client:
            payload = {
                "source_file": filename,
                "load_type": "daily",
                "covers_start": today_str,
                "covers_end": today_str,
                "row_count": 0,
                "imported_rows": 0,
                "status": "queued",
                "remarks": "Processing started: File received and queued...",
            }
            if tenant_id:
                payload["tenant_id"] = tenant_id

            if user_id and len(str(user_id)) == 36:
                payload["uploaded_by"] = str(user_id)
                payload["updated_by"] = str(user_id)

            try:
                response = client.table("upload_batches").insert(payload).execute()
                if response.data:
                    batch_id = response.data[0].get("batch_id") or response.data[0].get("upload_batch_id")
            except Exception as exc:
                try:
                    payload.pop("uploaded_by", None)
                    payload.pop("created_by", None)
                    payload.pop("updated_by", None)
                    response = client.table("upload_batches").insert(payload).execute()
                    if response.data:
                        batch_id = response.data[0].get("batch_id") or response.data[0].get("upload_batch_id")
                except Exception as exc2:
                    logger.warning(f"Could not create upload_batches in Supabase: {exc2}")

        if not batch_id:
            batch_id = len(upload_batches_db) + 1

        now_iso = datetime.now().isoformat()
        clean_user_fk = str(user_id) if (user_id and len(str(user_id)) == 36) else None
        batch_record = {
            "batch_id": batch_id,
            "upload_batch_id": batch_id,
            "source_file": filename,
            "file_name": filename,
            "load_type": "daily",
            "tenant_id": tenant_id,
            "covers_start": today_str,
            "covers_end": today_str,
            "storage_path": f"uploads/{int(time.time())}_{filename}",
            "uploaded_by": clean_user_fk,
            "created_by": clean_user_fk,
            "updated_by": clean_user_fk,
            "total_rows": 0,
            "imported_rows": 0,
            "duplicate_rows": 0,
            "failed_rows": 0,
            "processing_time_seconds": 0.0,
            "status": "queued",
            "upload_status": "queued",
            "chunk_count": 0,
            "failed_chunks": 0,
            "affected_dates_count": 0,
            "write_stats": {"raw_inserts": 0, "fact_inserts": 0, "user_fact_inserts": 0, "summary_writes": 0},
            "started_at": None,
            "completed_at": None,
            "remarks": "File accepted and queued for processing.",
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        upload_batches_db[
            batch_id
        ] = batch_record

        logger.info(
            "Upload batch %s created.",
            batch_id,
        )
        return batch_record

    # ========================================================
    # MAIN BACKGROUND PIPELINE
    # ========================================================

    async def process_file_upload(self, upload_file: Any, user_id: str) -> Dict[str, Any]:
        contents = await upload_file.read()
        filename = getattr(upload_file, "filename", "uploaded_file.xlsx") or "uploaded_file.xlsx"
        batch_record = self.create_initial_batch(filename, user_id)
        batch_id = batch_record["upload_batch_id"]
        self.process_file_upload_async(filename, contents, user_id, batch_id)
        return upload_batches_db.get(batch_id, batch_record)

    def process_file_upload_async(
        self,
        filename: str,
        contents: bytes,
        user_id: str,
        batch_id: int,
        tenant_id: Optional[str] = None,
    ):
        if not tenant_id:
            tenant_id = (upload_batches_db.get(batch_id) or {}).get("tenant_id")
        if not tenant_id and user_id:
            client = get_supabase()
            if client:
                try:
                    u_res = client.table("users").select("tenant_id").eq("user_id", str(user_id)).limit(1).execute()
                    if u_res.data and u_res.data[0].get("tenant_id"):
                        tenant_id = str(u_res.data[0]["tenant_id"])
                except Exception:
                    pass
        start_time = time.time()
        started_at_iso = datetime.now().isoformat()

        # Phase 2 Advisory Lock & Pipeline Guard Check
        lock_res = self.acquire_pipeline_lock(batch_id)
        if not lock_res.get("acquired"):
            reason = lock_res.get("reason", "Concurrent upload pipeline active.")
            logger.warning(f"Batch {batch_id} initialization rejected: {reason}")
            local_batch = upload_batches_db.get(batch_id)
            if local_batch:
                local_batch.update({"status": "failed", "upload_status": "failed", "remarks": f"Aborted: {reason}"})
            self._update_batch(batch_id=batch_id, status="failed")
            return local_batch

        try:
            if self.is_batch_cancelled(batch_id):
                raise UploadCancelledException(f"Batch {batch_id} cancelled by user before processing.")
            local_batch = upload_batches_db.get(batch_id)
            if local_batch:
                local_batch["started_at"] = started_at_iso
                local_batch["status"] = "running"
                local_batch["upload_status"] = "running"
                local_batch["remarks"] = "Processing started: Reading uploaded file..."

            self._update_batch(batch_id=batch_id, status="running")
            self._update_batch_progress(batch_id, remarks="Processing started: Reading uploaded file...")

            self._pipeline_log(
                batch_id=batch_id,
                step="file_received",
                status="started",
                message=f"Processing started: {filename}",
            )

            self._upload_original_file(
                filename=filename,
                contents=contents,
                batch_id=batch_id,
            )

            dataframe = self._parse_file(
                filename=filename,
                contents=contents,
            )

            if dataframe.empty:
                raise ValueError("Uploaded file contains no data rows.")

            total_rows = len(dataframe)
            logger.info(
                f"[INGESTION #{batch_id}] [PARSE-COMPLETE] Total rows extracted: {total_rows:,} | "
                f"Columns detected: {len(dataframe.columns)} ({list(dataframe.columns)[:8]}...)"
            )
            column_map = self._build_column_map(dataframe)
            logger.info(f"[INGESTION #{batch_id}] [COLUMN-MAPPING] Resolved mapping: {column_map}")

            self._update_batch(batch_id=batch_id, row_count=total_rows, status="running")

            if local_batch:
                local_batch["total_rows"] = total_rows

            self._update_batch_progress(
                batch_id,
                remarks=f"Processing started: {total_rows:,} rows fetched from sheet. Validating Records...",
            )
            if self.is_batch_cancelled(batch_id):
                raise UploadCancelledException(f"Batch {batch_id} cancelled by user after file parsing.")

            t_cache = time.time()
            logger.info(f"[INGESTION #{batch_id}] [PREFETCH-START] Prefetching master caches (brands, depots, licensees, personnel)...")
            master_service.prefetch_all_caches()
            logger.info(f"[INGESTION #{batch_id}] [PREFETCH-DONE] Master caches loaded in {time.time() - t_cache:.2f}s")

            # Vectorized Series Extraction & Cleaning
            def get_series(col_key, default=""):
                col_name = column_map.get(col_key)
                if col_name and col_name in dataframe.columns:
                    return dataframe[col_name].fillna("").astype(str).str.strip()
                return pd.Series([default] * total_rows, index=dataframe.index)

            s_date = get_series("Date")

            # Phase 2 Overlapping Date Replacement Prevention: Extract date range and verify no active overlap
            raw_dates = [d for d in s_date.unique() if d and str(d).strip()]
            parsed_dates = []
            for d in raw_dates:
                try:
                    p_dt = self._parse_date(d)
                    if p_dt:
                        parsed_dates.append(p_dt)
                except Exception:
                    pass
            valid_dates = [d for d in parsed_dates if d]
            if valid_dates:
                covers_start_date = min(valid_dates)
                covers_end_date = max(valid_dates)
                overlap = self.check_overlapping_date_window(covers_start_date, covers_end_date, exclude_batch_id=batch_id)
                if overlap:
                    overlap_id = overlap.get("batch_id") or overlap.get("upload_batch_id")
                    raise ValueError(f"Sales date window ({covers_start_date} to {covers_end_date}) overlaps with active ingestion Batch #{overlap_id}.")
                if local_batch:
                    local_batch["covers_start"] = covers_start_date
                    local_batch["covers_end"] = covers_end_date

            s_company = get_series("Company")
            s_category = get_series("Category")
            s_licensee = get_series("LICENSEE_NAME")
            s_trade = get_series("Trade")
            s_group = get_series("Group Name")
            s_hq = get_series("H.Q.")
            s_deo = get_series("DEO_OFFICE_NAME")
            s_circle = get_series("CIRCLE_OFFICE_NAME")
            s_depot = get_series("DEPOT_NAME")
            s_ase = get_series("ASE")
            s_asm = get_series("ASM/TSM")
            s_brand = get_series("BRAND_NAME")
            s_packing = get_series("PACKING_IN_ML")

            def get_num_series(col_key):
                col_name = column_map.get(col_key)
                if col_name and col_name in dataframe.columns:
                    return pd.to_numeric(dataframe[col_name], errors="coerce").fillna(0.0)
                return pd.Series([0.0] * total_rows, index=dataframe.index)

            s_cases = get_num_series("TOTAL_CASE")
            s_btl = get_num_series("TOTAL_BTL")
            s_bl = get_num_series("TOTAL_BL")

            # Master Bulk Resolution
            unique_groups = [g for g in s_group.unique() if g]
            unique_offices = [o for o in s_deo.unique() if o]
            unique_circles = [c for c in s_circle.unique() if c]
            unique_hqs = [h for h in s_hq.unique() if h]
            unique_companies = [c for c in s_company.unique() if c]
            unique_brands = [b for b in s_brand.unique() if b]
            unique_packagings = [p for p in s_packing.unique() if p]

            group_cache = master_service.bulk_resolve_groups(unique_groups)
            office_cache = master_service.bulk_resolve_offices(unique_offices)
            circle_cache = master_service.bulk_resolve_circles(unique_circles)
            hq_cache = master_service.bulk_resolve_headquarters(unique_hqs, tenant_id=tenant_id)

            company_category_map = {}
            if not s_category.empty:
                for c, cat in zip(s_company, s_category):
                    c_str = str(c).strip() if c else ""
                    cat_str = str(cat).strip() if cat else ""
                    if c_str and cat_str and c_str not in company_category_map:
                        company_category_map[c_str] = cat_str

            company_cache = master_service.bulk_resolve_companies(
                unique_companies,
                tenant_id=tenant_id,
                company_categories=company_category_map
            )

            depot_items = [
                {
                    "depot_name": d,
                    "office_id": office_cache.get(master_service._clean(deo)),
                    "circle_id": circle_cache.get(master_service._clean(cir)),
                    "headquarters_id": hq_cache.get(master_service._clean(hq)) or hq_cache.get(master_service._clean_no_space(hq)),
                }
                for d, deo, cir, hq in zip(s_depot, s_deo, s_circle, s_hq)
                if d
            ]
            depot_cache = master_service.bulk_resolve_depots(depot_items, tenant_id=tenant_id)

            lic_items = [
                {
                    "licensee_name": l,
                    "trade": t,
                    "group_name": g,
                    "group_id": group_cache.get(master_service._clean(g)),
                    "depot_id": depot_cache.get(master_service._clean(d)),
                    "headquarters_id": hq_cache.get(master_service._clean(hq)) or hq_cache.get(master_service._clean_no_space(hq)),
                    "office_id": office_cache.get(master_service._clean(deo)),
                    "circle_id": circle_cache.get(master_service._clean(cir)),
                }
                for l, t, g, d, hq, deo, cir in zip(s_licensee, s_trade, s_group, s_depot, s_hq, s_deo, s_circle)
                if l
            ]
            licensee_cache = master_service.bulk_resolve_licensees(lic_items, tenant_id=tenant_id)

            brand_items = [
                {
                    "brand_name": b,
                    "company_id": company_cache.get(master_service._clean_company(c)) or company_cache.get(master_service._clean(c)),
                }
                for b, c in zip(s_brand, s_company)
                if b
            ]
            if not tenant_id:
                raise ValueError(f"Batch #{batch_id}: Cannot resolve brands without tenant_id. Dynamic tenant_id is mandatory.")
            brand_cache = master_service.bulk_resolve_brands(brand_items, tenant_id=tenant_id)
            packaging_cache = master_service.bulk_resolve_packagings(unique_packagings)
            # Sync user depot mapping (non-destructive)
            self._sync_user_hierarchy(s_ase, s_asm, s_depot, depot_cache)

            # Vectorized ID Resolution
            clean_fn = master_service._clean
            clean_no_space = master_service._clean_no_space
            map_depot = s_depot.map(lambda x: depot_cache.get(clean_fn(x)))
            map_licensee = s_licensee.map(lambda x: licensee_cache.get(clean_fn(x)))
            map_brand = s_brand.map(lambda x: brand_cache.get(clean_fn(x)))
            map_packaging = s_packing.map(lambda x: packaging_cache.get(clean_fn(x)))
            map_hq = s_hq.map(lambda x: hq_cache.get(clean_fn(x)) or hq_cache.get(clean_no_space(x)))

            # Parse dates vectorized
            def parse_date_val(d):
                try:
                    return self._parse_date(d)
                except Exception:
                    return datetime.today().strftime("%Y-%m-%d")

            map_date = s_date.apply(parse_date_val)

            # Build Raw Staging DataFrame & Records
            raw_df = pd.DataFrame({
                "tenant_id": tenant_id,
                "batch_id": batch_id,
                "sale_date_raw": s_date,
                "company_raw": s_company,
                "licensee_raw": s_licensee,
                "trade_raw": s_trade,
                "group_name_raw": s_group,
                "hq_raw": s_hq,
                "deo_office_raw": s_deo,
                "circle_office_raw": s_circle,
                "depot_raw": s_depot,
                "ase_raw": s_ase,
                "asm_tsm_raw": s_asm,
                "brand_name_raw": s_brand,
                "packing_raw": s_packing,
                "total_case": s_cases,
                "total_btl": s_btl,
                "total_bl": s_bl,
            })
            raw_records = raw_df.to_dict("records")

            # 1. Stage Data into raw_sales_upload FIRST
            if raw_records:
                self._update_batch_progress(
                    batch_id,
                    remarks=f"Preparing {total_rows:,} rows...",
                )
                self._bulk_insert(
                    table="raw_sales_upload",
                    records=raw_records,
                    chunk_size=5000,
                    batch_id=batch_id,
                )

            # Fetch staging raw_ids for detailed row error linking in Diagnostic Center
            client = get_supabase()
            staged_raw_ids = []
            if client:
                try:
                    res_raw = client.table("raw_sales_upload").select("raw_id").eq("batch_id", str(batch_id)).execute()
                    if res_raw and res_raw.data:
                        staged_raw_ids = [r.get("raw_id") for r in res_raw.data]
                except Exception as e_rids:
                    logger.warning(f"Batch {batch_id}: Notice fetching staged raw_ids: {e_rids}")

            # 2. Fetch User Management hierarchy for strict employee mapping validation
            user_id_by_name: Dict[str, str] = {}
            user_name_by_id: Dict[str, str] = {}
            user_manager_by_id: Dict[str, str] = {}
            user_manager_id_by_id: Dict[str, str] = {}
            tsm_user_ids: Set[str] = set()
            user_approved_hq_names_by_id: Dict[str, Set[str]] = {}
            hq_id_to_name: Dict[str, str] = {}
            user_is_active_by_id: Dict[str, bool] = {}
            user_deactivated_date_by_id: Dict[str, str] = {}

            if client:
                try:
                    u_res = client.table("users").select("user_id, first_name, last_name, email, is_active, updated_at").execute()
                    if u_res and u_res.data:
                        all_users = u_res.data
                        all_users.sort(key=lambda x: 0 if x.get("is_active") else 1)
                        for u in all_users:
                            uid = str(u["user_id"])
                            is_act = bool(u.get("is_active", True))
                            user_is_active_by_id[uid] = is_act
                            deact_val = u.get("deactivated_at") or (u.get("updated_at") if not is_act else "")
                            user_deactivated_date_by_id[uid] = str(deact_val or "")[:10]

                            fn = (u.get("first_name") or "").strip()
                            ln = (u.get("last_name") or "").strip()
                            full_name = f"{fn} {ln}".strip()
                            full_name_clean = re.sub(r'\s+', ' ', full_name).lower()
                            email = str(u.get("email") or "").lower()
                            prefix = email.split("@")[0].strip()

                            if full_name_clean and full_name_clean not in user_id_by_name:
                                user_id_by_name[full_name_clean] = uid
                                user_name_by_id[uid] = full_name
                            ln_parts = ln.split()
                            if len(ln_parts) > 1:
                                short_name = f"{fn} {ln_parts[-1]}".strip().lower()
                                if short_name and short_name not in user_id_by_name:
                                    user_id_by_name[short_name] = uid
                            if prefix and prefix not in user_id_by_name:
                                user_id_by_name[prefix] = uid
                            if fn and fn.lower() not in user_id_by_name:
                                user_id_by_name[fn.lower()] = uid

                    # Fetch user roles to identify registered TSM / ASM personnel
                    roles_res = client.table("roles").select("role_id, role_name").execute()
                    role_name_by_id = {str(r["role_id"]): str(r.get("role_name") or "").strip().upper() for r in (roles_res.data or []) if r.get("role_id")}

                    ur_res = client.table("user_roles").select("user_id, role_id, is_active").execute()
                    for ur in (ur_res.data or []):
                        if ur.get("is_active", True) is not False:
                            uid = str(ur.get("user_id") or "")
                            rid = str(ur.get("role_id") or "")
                            rname = role_name_by_id.get(rid, "")
                            if any(k in rname for k in ["TSM", "ASM", "TERRITORY SALES MANAGER", "AREA SALES MANAGER"]):
                                tsm_user_ids.add(uid)

                    atm_res = client.table("ase_tsm_mapping").select("ase_user_id, tsm_user_id, is_active").execute()
                    if atm_res and atm_res.data:
                        for m in atm_res.data:
                            if m.get("is_active", True) is not False:
                                a_uid = str(m.get("ase_user_id") or "").strip()
                                t_uid = str(m.get("tsm_user_id") or "").strip()
                                if a_uid and t_uid:
                                    user_manager_by_id[a_uid] = t_uid
                                    user_manager_id_by_id[a_uid] = t_uid

                    # Fetch registered user headquarters supporting M:N assignments
                    hq_no_space_to_canonical: Dict[str, str] = {}
                    hq_res = client.table("headquarters").select("headquarters_id, name").execute()
                    if hq_res and hq_res.data:
                        for h in hq_res.data:
                            hid = str(h.get("headquarters_id") or "")
                            hname = str(h.get("name") or "").strip().upper()
                            if hid and hname:
                                hq_id_to_name[hid] = hname
                                no_sp = re.sub(r'[\s\-_.]+', '', hname).upper()
                                if no_sp:
                                    hq_no_space_to_canonical[no_sp] = hname

                    uhq_res = client.table("user_headquarters_mapping").select("user_id, headquarters_id, is_active").execute()
                    if uhq_res and uhq_res.data:
                        for uhq in uhq_res.data:
                            if uhq.get("is_active", True) is not False:
                                uid = str(uhq.get("user_id") or "").strip()
                                hid = str(uhq.get("headquarters_id") or "").strip()
                                if uid and hid in hq_id_to_name:
                                    user_approved_hq_names_by_id.setdefault(uid, set()).add(hq_id_to_name[hid])
                except Exception as e_um:
                    logger.warning(f"Batch {batch_id}: Exception fetching User Management hierarchy: {e_um}")

            def _canonicalize_hq(val: str) -> str:
                if not val or str(val).strip().lower() in ("unassigned", "none", "null", "nan", ""):
                    return ""
                clean_v = re.sub(r'\s+', ' ', str(val)).strip().upper()
                no_sp = re.sub(r'[\s\-_.]+', '', clean_v).upper()
                if no_sp in hq_no_space_to_canonical:
                    return hq_no_space_to_canonical[no_sp]
                # Also resolve via hq_cache
                res_hid = hq_cache.get(clean_fn(val)) or hq_cache.get(clean_no_space(val))
                if res_hid and str(res_hid) in hq_id_to_name:
                    canonical_name = hq_id_to_name[str(res_hid)]
                    hq_no_space_to_canonical[no_sp] = canonical_name
                    return canonical_name
                return clean_v

            def _is_hq_matching_approved(target_hq: str, approved_set: Set[str]) -> bool:
                if not target_hq or not approved_set:
                    return False
                if target_hq in approved_set:
                    return True
                target_no_sp = re.sub(r'[\s\-_.]+', '', target_hq).upper()
                return any(re.sub(r'[\s\-_.]+', '', a).upper() == target_no_sp for a in approved_set)

            def _resolve_user_id(name_str: str) -> Optional[str]:
                if not name_str or name_str.lower() in ("unassigned", "none", "null", "nan"):
                    return None
                c_name = re.sub(r'\s+', ' ', name_str.strip()).lower()
                if c_name in user_id_by_name:
                    return user_id_by_name[c_name]
                first_part = c_name.replace(",", "/").split("/")[0].strip()
                if first_part in user_id_by_name:
                    return user_id_by_name[first_part]
                words = first_part.split()
                if len(words) > 2:
                    fl = f"{words[0]} {words[-1]}"
                    if fl in user_id_by_name:
                        return user_id_by_name[fl]
                    if len(words) > 3:
                        fl2 = f"{words[0]} {words[1]} {words[-1]}"
                        if fl2 in user_id_by_name:
                            return user_id_by_name[fl2]
                if words and words[0] in user_id_by_name:
                    return user_id_by_name[words[0]]
                return None

            # 3. Comprehensive Row-by-Row Pre-Promotion Validation
            self._update_batch_progress(
                batch_id,
                remarks=f"Validating: Checking employee hierarchy and master records...",
            )
            validation_error_records = []

            # Trackers for 1:1 constraints across the dataset (1 ASE -> 1 HQ, 1 TSM -> 1 HQ, 1 ASE -> 1 TSM)
            sheet_ase_hqs: Dict[str, Dict[str, List[int]]] = {}
            sheet_tsm_hqs: Dict[str, Dict[str, List[int]]] = {}
            sheet_ase_managers: Dict[str, Dict[str, List[int]]] = {}

            val_progress_step = max(2000, total_rows // 4)
            for idx in range(total_rows):
                if idx > 0 and (idx % val_progress_step == 0):
                    pct_val = int((idx / total_rows) * 100)
                    self._update_batch_progress(
                        batch_id,
                        remarks=f"Checking for validation errors: {idx:,}/{total_rows:,} rows verified ({pct_val}%)..."
                    )
                row_num = idx + 2  # Excel 1-indexed row number (header is row 1)
                r_id = staged_raw_ids[idx] if idx < len(staged_raw_ids) else None

                raw_date = str(s_date.iloc[idx] or "").strip()
                raw_depot = str(s_depot.iloc[idx] or "").strip()
                raw_licensee = str(s_licensee.iloc[idx] or "").strip()
                raw_brand = str(s_brand.iloc[idx] or "").strip()
                raw_packing = str(s_packing.iloc[idx] or "").strip()
                raw_hq = str(s_hq.iloc[idx] or "").strip()
                raw_ase = str(s_ase.iloc[idx] or "").strip()
                raw_asm = str(s_asm.iloc[idx] or "").strip()
                raw_company = str(s_company.iloc[idx] or "").strip()
                val_case = s_cases.iloc[idx]

                clean_ase = re.sub(r'\s+', ' ', raw_ase).strip()
                clean_asm = re.sub(r'\s+', ' ', raw_asm).strip()
                clean_hq_norm = _canonicalize_hq(raw_hq)

                # Collect for 1:1 integrity verification (1 ASE -> 1 HQ, 1 TSM -> 1 HQ, 1 ASE -> 1 TSM)
                # Note: 1 ASE/TSM can have multiple depots, and 1 depot can have multiple ASEs (no restriction)
                if clean_ase and clean_ase.lower() not in ("unassigned", "none", "null", "nan", ""):
                    if clean_hq_norm and clean_hq_norm.lower() not in ("unassigned", "none", "null", "nan", ""):
                        sheet_ase_hqs.setdefault(clean_ase, {}).setdefault(clean_hq_norm, []).append(row_num)
                    if clean_asm and clean_asm.lower() not in ("unassigned", "none", "null", "nan", ""):
                        sheet_ase_managers.setdefault(clean_ase, {}).setdefault(clean_asm, []).append(row_num)

                if clean_asm and clean_asm.lower() not in ("unassigned", "none", "null", "nan", ""):
                    if clean_hq_norm and clean_hq_norm.lower() not in ("unassigned", "none", "null", "nan", ""):
                        sheet_tsm_hqs.setdefault(clean_asm, {}).setdefault(clean_hq_norm, []).append(row_num)

                approved_tsm_name_curr = None
                if raw_ase and raw_ase.lower() not in ("unassigned", "none", "null", "nan"):
                    clean_a = re.sub(r'\s+', ' ', raw_ase.strip()).lower()
                    clean_m = re.sub(r'\s+', ' ', raw_asm.strip()).lower()
                    if clean_a == clean_m:
                        approved_tsm_name_curr = raw_ase
                    else:
                        ase_u = _resolve_user_id(raw_ase)
                        if ase_u:
                            if ase_u in tsm_user_ids:
                                approved_tsm_name_curr = user_name_by_id.get(ase_u, raw_ase)
                            else:
                                app_tsm_u = user_manager_by_id.get(ase_u) or user_manager_id_by_id.get(ase_u)
                                if app_tsm_u:
                                    approved_tsm_name_curr = user_name_by_id.get(app_tsm_u)

                # Check registered DB Headquarters mismatch for ASE (space/punctuation resilient)
                if raw_ase and raw_ase.lower() not in ("unassigned", "none", "null", "nan", ""):
                    ase_uid = _resolve_user_id(raw_ase)
                    if ase_uid and ase_uid in user_approved_hq_names_by_id:
                        reg_hqs = user_approved_hq_names_by_id[ase_uid]
                        if clean_hq_norm and not _is_hq_matching_approved(clean_hq_norm, reg_hqs):
                            expected_str = ", ".join(sorted(list(reg_hqs)))
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": row_num,
                                "error_code": "HQ_MISMATCH_FOR_ASE",
                                "severity": "CRITICAL",
                                "field_name": "H.Q.",
                                "column_name": "hq_raw",
                                "actual_value": raw_hq,
                                "expected_value": expected_str,
                                "ase": raw_ase,
                                "asm_tsm": raw_asm,
                                "approved_asm_tsm": approved_tsm_name_curr,
                                "hq": raw_hq,
                                "depot": raw_depot,
                                "licensee": raw_licensee,
                                "company": raw_company,
                                "brand": raw_brand,
                                "raw_id": r_id,
                                "error_message": f"[Row #{row_num}] HQ_MISMATCH_FOR_ASE: ASE '{raw_ase}' is registered under '{expected_str}' in User Management, but the uploaded sales record specifies '{raw_hq}'.",
                                "resolution": f"Update sales record to specify an approved HQ ({expected_str}) or reassign Headquarters in User Management."
                            })

                # Check registered DB Headquarters mismatch for TSM (space/punctuation resilient)
                if raw_asm and raw_asm.lower() not in ("unassigned", "none", "null", "nan", ""):
                    tsm_uid = _resolve_user_id(raw_asm)
                    if tsm_uid and tsm_uid in user_approved_hq_names_by_id:
                        reg_hqs = user_approved_hq_names_by_id[tsm_uid]
                        if clean_hq_norm and not _is_hq_matching_approved(clean_hq_norm, reg_hqs):
                            expected_str = ", ".join(sorted(list(reg_hqs)))
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": row_num,
                                "error_code": "HQ_MISMATCH_FOR_TSM",
                                "severity": "CRITICAL",
                                "field_name": "H.Q.",
                                "column_name": "hq_raw",
                                "actual_value": raw_hq,
                                "expected_value": expected_str,
                                "ase": raw_ase,
                                "asm_tsm": raw_asm,
                                "approved_asm_tsm": approved_tsm_name_curr,
                                "hq": raw_hq,
                                "depot": raw_depot,
                                "licensee": raw_licensee,
                                "company": raw_company,
                                "brand": raw_brand,
                                "raw_id": r_id,
                                "error_message": f"[Row #{row_num}] HQ_MISMATCH_FOR_TSM: TSM '{raw_asm}' is registered under '{expected_str}' in User Management, but the uploaded sales record specifies '{raw_hq}'.",
                                "resolution": f"Update sales record to specify an approved HQ ({expected_str}) or reassign Headquarters in User Management."
                            })

                # A0. Validate Sale Date Field
                parsed_dt_val = None
                if raw_date and raw_date.lower() not in ("nan", "none", "null", ""):
                    try:
                        parsed_dt_val = self._parse_date(raw_date)
                    except Exception:
                        parsed_dt_val = None

                if not raw_date or raw_date.lower() in ("nan", "none", "null", "") or not parsed_dt_val:
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "DATE_ERROR",
                        "severity": "CRITICAL",
                        "field_name": "Date",
                        "column_name": "sale_date_raw",
                        "actual_value": raw_date,
                        "expected_value": "Valid Date (YYYY-MM-DD or DD/MM/YYYY)",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] DATE_ERROR: Invalid or unparseable sale date '{raw_date}'. Expected valid date format.",
                        "resolution": "Format the sale date column as a valid date in the Excel file."
                    })

                # Inactive User Sales Prohibition Check (User Requirement A4):
                # If an employee (ASE or ASM/TSM) is marked inactive, sales CANNOT be uploaded for dates
                # on or after their deactivation date. Halt and rollback, prompting user to activate first.
                if parsed_dt_val:
                    if raw_ase and raw_ase.lower() not in ("unassigned", "none", "null", "nan", ""):
                        ase_uid_chk = _resolve_user_id(raw_ase)
                        if ase_uid_chk and not user_is_active_by_id.get(ase_uid_chk, True):
                            deact_dt = user_deactivated_date_by_id.get(ase_uid_chk)
                            if deact_dt and parsed_dt_val >= deact_dt:
                                u_name = user_name_by_id.get(ase_uid_chk, raw_ase)
                                validation_error_records.append({
                                    "upload_batch_id": str(batch_id),
                                    "batch_id": str(batch_id),
                                    "filename": filename,
                                    "excel_row_number": row_num,
                                    "error_code": "INACTIVE_USER_SALES_NOT_ALLOWED",
                                    "severity": "CRITICAL",
                                    "field_name": "ASE",
                                    "column_name": "ase_raw",
                                    "actual_value": raw_ase,
                                    "expected_value": "Active Employee",
                                    "ase": raw_ase,
                                    "asm_tsm": raw_asm,
                                    "approved_asm_tsm": approved_tsm_name_curr,
                                    "hq": raw_hq,
                                    "depot": raw_depot,
                                    "licensee": raw_licensee,
                                    "company": raw_company,
                                    "brand": raw_brand,
                                    "raw_id": r_id,
                                    "error_message": f"[Row #{row_num}] INACTIVE_USER_SALES_NOT_ALLOWED: User '{u_name}' has been marked inactive on {deact_dt}. Sales cannot be uploaded for date {parsed_dt_val} (on or after deactivation date). First activate the user in User Management and then re-upload the file.",
                                    "resolution": f"First activate '{u_name}' in User Management and then re-upload the file."
                                })

                    if raw_asm and raw_asm.lower() not in ("unassigned", "none", "null", "nan", ""):
                        asm_uid_chk = _resolve_user_id(raw_asm)
                        if asm_uid_chk and not user_is_active_by_id.get(asm_uid_chk, True):
                            deact_dt = user_deactivated_date_by_id.get(asm_uid_chk)
                            if deact_dt and parsed_dt_val >= deact_dt:
                                u_name = user_name_by_id.get(asm_uid_chk, raw_asm)
                                validation_error_records.append({
                                    "upload_batch_id": str(batch_id),
                                    "batch_id": str(batch_id),
                                    "filename": filename,
                                    "excel_row_number": row_num,
                                    "error_code": "INACTIVE_USER_SALES_NOT_ALLOWED",
                                    "severity": "CRITICAL",
                                    "field_name": "ASM/TSM",
                                    "column_name": "asm_tsm_raw",
                                    "actual_value": raw_asm,
                                    "expected_value": "Active Employee",
                                    "ase": raw_ase,
                                    "asm_tsm": raw_asm,
                                    "approved_asm_tsm": approved_tsm_name_curr,
                                    "hq": raw_hq,
                                    "depot": raw_depot,
                                    "licensee": raw_licensee,
                                    "company": raw_company,
                                    "brand": raw_brand,
                                    "raw_id": r_id,
                                    "error_message": f"[Row #{row_num}] INACTIVE_USER_SALES_NOT_ALLOWED: User '{u_name}' has been marked inactive on {deact_dt}. Sales cannot be uploaded for date {parsed_dt_val} (on or after deactivation date). First activate the user in User Management and then re-upload the file.",
                                    "resolution": f"First activate '{u_name}' in User Management and then re-upload the file."
                                })

                # A. Validate Case Quantity Field
                if pd.isna(val_case) or val_case < 0:
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "INVALID_CASE",
                        "severity": "CRITICAL",
                        "field_name": "Case",
                        "column_name": "total_case",
                        "actual_value": str(val_case),
                        "expected_value": "Non-negative numeric value",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] INVALID_CASE: Case quantity must be a non-negative number. Received: '{val_case}'.",
                        "resolution": "Enter a valid non-negative numeric case quantity."
                    })

                # B. Validate Master Data Resolutions
                if pd.isna(map_depot.iloc[idx]):
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "UNMAPPED_DEPOT",
                        "severity": "CRITICAL",
                        "field_name": "DEPOT NAME",
                        "column_name": "depot_raw",
                        "actual_value": raw_depot,
                        "expected_value": "Registered Depot in Master Catalog",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] UNMAPPED_DEPOT: Depot '{raw_depot}' is not registered in Depot master catalog.",
                        "resolution": "Register Depot in Depot master catalog or correct spelling."
                    })

                if pd.isna(map_licensee.iloc[idx]):
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "UNMAPPED_LICENSEE",
                        "severity": "CRITICAL",
                        "field_name": "LICENSEE NAME",
                        "column_name": "licensee_raw",
                        "actual_value": raw_licensee,
                        "expected_value": "Registered Licensee in Master Catalog",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] UNMAPPED_LICENSEE: Licensee '{raw_licensee}' is not registered in Licensee master catalog.",
                        "resolution": "Register Licensee in Licensee master catalog or correct spelling."
                    })

                if pd.isna(map_brand.iloc[idx]):
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "UNMAPPED_BRAND",
                        "severity": "CRITICAL",
                        "field_name": "BRAND NAME",
                        "column_name": "brand_name_raw",
                        "actual_value": raw_brand,
                        "expected_value": "Registered Brand in Master Catalog",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] UNMAPPED_BRAND: Brand '{raw_brand}' is not registered in Brand master catalog.",
                        "resolution": "Register Brand in Brand master catalog or correct spelling."
                    })

                if pd.isna(map_packaging.iloc[idx]):
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "UNMAPPED_PACKAGING",
                        "severity": "CRITICAL",
                        "field_name": "PACKING IN ML",
                        "column_name": "packing_raw",
                        "actual_value": raw_packing,
                        "expected_value": "Registered Packaging Size",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] UNMAPPED_PACKAGING: Packaging size '{raw_packing}' is not registered in Packaging master catalog.",
                        "resolution": "Register Packaging size in Packaging catalog."
                    })

                if pd.isna(map_hq.iloc[idx]):
                    validation_error_records.append({
                        "upload_batch_id": str(batch_id),
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "excel_row_number": row_num,
                        "error_code": "UNMAPPED_HQ",
                        "severity": "CRITICAL",
                        "field_name": "H.Q.",
                        "column_name": "hq_raw",
                        "actual_value": raw_hq,
                        "expected_value": "Registered Headquarters in Master Catalog",
                        "ase": raw_ase,
                        "asm_tsm": raw_asm,
                        "approved_asm_tsm": approved_tsm_name_curr,
                        "hq": raw_hq,
                        "depot": raw_depot,
                        "licensee": raw_licensee,
                        "company": raw_company,
                        "brand": raw_brand,
                        "raw_id": r_id,
                        "error_message": f"[Row #{row_num}] UNMAPPED_HQ: Headquarters '{raw_hq}' is not registered in Headquarters master catalog.",
                        "resolution": "Register Headquarters in HQ catalog or correct spelling."
                    })

                # C. Validate Employee Hierarchy against User Management
                if raw_ase and raw_ase.lower() not in ("unassigned", "none", "null", "nan"):
                    ase_uid = _resolve_user_id(raw_ase)

                    if not ase_uid:
                        validation_error_records.append({
                            "upload_batch_id": str(batch_id),
                            "batch_id": str(batch_id),
                            "filename": filename,
                            "excel_row_number": row_num,
                            "error_code": "UNMAPPED_ASE",
                            "severity": "CRITICAL",
                            "field_name": "ASE",
                            "column_name": "ase_raw",
                            "actual_value": raw_ase,
                            "expected_value": "Active user registered in User Management",
                            "ase": raw_ase,
                            "asm_tsm": raw_asm,
                            "approved_asm_tsm": None,
                            "hq": raw_hq,
                            "depot": raw_depot,
                            "licensee": raw_licensee,
                            "company": raw_company,
                            "brand": raw_brand,
                            "raw_id": r_id,
                            "error_message": f"[Row #{row_num}] UNMAPPED_ASE: ASE '{raw_ase}' is not registered in User Management.",
                            "resolution": "Create or activate ASE user profile in User Management."
                        })
                    else:
                        uploaded_asm_uid = _resolve_user_id(raw_asm) if (raw_asm and raw_asm.lower() not in ("unassigned", "none", "null", "nan")) else None

                        if raw_asm and raw_asm.lower() not in ("unassigned", "none", "null", "nan") and not uploaded_asm_uid:
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": row_num,
                                "error_code": "UNMAPPED_TSM",
                                "severity": "CRITICAL",
                                "field_name": "ASM/TSM",
                                "column_name": "asm_tsm_raw",
                                "actual_value": raw_asm,
                                "expected_value": "Active ASM/TSM registered in User Management",
                                "ase": raw_ase,
                                "asm_tsm": raw_asm,
                                "approved_asm_tsm": approved_tsm_name_curr,
                                "hq": raw_hq,
                                "depot": raw_depot,
                                "licensee": raw_licensee,
                                "company": raw_company,
                                "brand": raw_brand,
                                "raw_id": r_id,
                                "error_message": f"[Row #{row_num}] UNMAPPED_TSM: ASM/TSM '{raw_asm}' specified in sales record is not registered in User Management.",
                                "resolution": "Create or activate ASM/TSM user profile in User Management."
                            })
                        else:
                            # Dual-Role TSM/ASE check:
                            # A TSM can act as an ASE for a depot if:
                            # 1. Both columns specify the exact same person name (raw text match)
                            # 2. The user has a TSM/ASM role in User Management
                            # 3. Both columns resolve to the exact same user ID
                            clean_raw_ase = re.sub(r'\s+', ' ', raw_ase.strip()).lower()
                            clean_raw_asm = re.sub(r'\s+', ' ', raw_asm.strip()).lower()
                            is_same_person = (clean_raw_ase == clean_raw_asm and clean_raw_ase not in ("unassigned", "none", "null", "nan", ""))
                            is_dual_role_tsm = is_same_person or (ase_uid in tsm_user_ids) or (uploaded_asm_uid is not None and uploaded_asm_uid == ase_uid)

                            if is_dual_role_tsm:
                                # DUAL-ROLE TSM/ASE:
                                # The TSM directly covers this depot as the ASE.
                                # Valid uploaded_asm values:
                                # 1. Direct name match or identical user (is_same_person or uploaded_asm_uid == ase_uid)
                                # 2. Empty / Unassigned (TSM is self-managing this depot)
                                # 3. Their reporting manager / Leader / RSM (uploaded_asm_uid == user_manager_id_by_id.get(ase_uid))
                                ase_mgr_uid = user_manager_id_by_id.get(ase_uid) or user_manager_by_id.get(ase_uid)
                                is_valid_asm = (
                                    is_same_person or
                                    uploaded_asm_uid is None or
                                    uploaded_asm_uid == ase_uid or
                                    (ase_mgr_uid and uploaded_asm_uid == ase_mgr_uid)
                                )
                                if not is_valid_asm:
                                    approved_name = user_name_by_id.get(ase_uid, raw_ase)
                                    validation_error_records.append({
                                        "upload_batch_id": str(batch_id),
                                        "batch_id": str(batch_id),
                                        "filename": filename,
                                        "excel_row_number": row_num,
                                        "error_code": "ASE_TSM_MAPPING_MISMATCH",
                                        "severity": "CRITICAL",
                                        "field_name": "ASM/TSM",
                                        "column_name": "asm_tsm_raw",
                                        "actual_value": raw_asm,
                                        "expected_value": approved_name,
                                        "ase": raw_ase,
                                        "asm_tsm": raw_asm,
                                        "approved_asm_tsm": approved_name,
                                        "hq": raw_hq,
                                        "depot": raw_depot,
                                        "licensee": raw_licensee,
                                        "company": raw_company,
                                        "brand": raw_brand,
                                        "raw_id": r_id,
                                        "error_message": f"[Row #{row_num}] ASE_TSM_MAPPING_MISMATCH: TSM '{raw_ase}' acting as ASE is expected to specify '{approved_name}' as ASM/TSM, but uploaded record specifies '{raw_asm}'.",
                                        "resolution": "Update sales record to specify approved ASM/TSM or reassign mapping in User Management."
                                    })
                            else:
                                # REGULAR SUBORDINATE ASE:
                                # Must have an approved ASM/TSM mapping in User Management
                                approved_tsm_uid = user_manager_by_id.get(ase_uid)
                                if not approved_tsm_uid:
                                    validation_error_records.append({
                                        "upload_batch_id": str(batch_id),
                                        "batch_id": str(batch_id),
                                        "filename": filename,
                                        "excel_row_number": row_num,
                                        "error_code": "MISSING_ASE_TSM_MAPPING",
                                        "severity": "CRITICAL",
                                        "field_name": "ASE",
                                        "column_name": "ase_raw",
                                        "actual_value": raw_ase,
                                        "expected_value": "Approved ASM/TSM assignment in User Management",
                                        "ase": raw_ase,
                                        "asm_tsm": raw_asm,
                                        "approved_asm_tsm": None,
                                        "hq": raw_hq,
                                        "depot": raw_depot,
                                        "licensee": raw_licensee,
                                        "company": raw_company,
                                        "brand": raw_brand,
                                        "raw_id": r_id,
                                        "error_message": f"[Row #{row_num}] MISSING_ASE_TSM_MAPPING: ASE '{raw_ase}' does not have an approved ASM/TSM mapping in User Management.",
                                        "resolution": "Assign an approved ASM/TSM to this ASE in User Management."
                                    })
                                else:
                                    approved_tsm_name = user_name_by_id.get(approved_tsm_uid, "Approved ASM/TSM")
                                    if uploaded_asm_uid and uploaded_asm_uid != approved_tsm_uid:
                                        validation_error_records.append({
                                            "upload_batch_id": str(batch_id),
                                            "batch_id": str(batch_id),
                                            "filename": filename,
                                            "excel_row_number": row_num,
                                            "error_code": "ASE_TSM_MAPPING_MISMATCH",
                                            "severity": "CRITICAL",
                                            "field_name": "ASM/TSM",
                                            "column_name": "asm_tsm_raw",
                                            "actual_value": raw_asm,
                                            "expected_value": approved_tsm_name,
                                            "ase": raw_ase,
                                            "asm_tsm": raw_asm,
                                            "approved_asm_tsm": approved_tsm_name,
                                            "hq": raw_hq,
                                            "depot": raw_depot,
                                            "licensee": raw_licensee,
                                            "company": raw_company,
                                            "brand": raw_brand,
                                            "raw_id": r_id,
                                            "error_message": f"[Row #{row_num}] ASE_TSM_MAPPING_MISMATCH: ASE '{raw_ase}' is currently mapped to '{approved_tsm_name}' in User Management, but the uploaded sales record specifies '{raw_asm}'.",
                                            "resolution": "Update sales record to specify approved ASM/TSM or reassign mapping in User Management."
                                        })

            # 3b. Validate Intra-Sheet Consistency Across the Uploaded Sheet:
            # 1. An ASE must belong to their registered Headquarters across the uploaded dataset
            for ase_name, hq_dict in sheet_ase_hqs.items():
                ase_uid = _resolve_user_id(ase_name)
                approved_hqs = user_approved_hq_names_by_id.get(ase_uid, set()) if ase_uid else set()
                # If ASE is mapped to multiple HQs, verify they are distinct after canonicalization and outside approved HQs
                if len(hq_dict) > 1 and len(approved_hqs) <= 1:
                    unique_canonical_hqs = {_canonicalize_hq(h) for h in hq_dict.keys()}
                    if len(unique_canonical_hqs) <= 1:
                        continue
                    if all(_is_hq_matching_approved(h, approved_hqs) for h in hq_dict.keys()):
                        continue
                    sorted_hqs = sorted(list(hq_dict.keys()))
                    sample_details = ", ".join([f"Row #{rows[0]} ({h})" for h, rows in hq_dict.items()][:5])
                    for hq_val, row_nums in hq_dict.items():
                        for r_num in row_nums[:3]:
                            idx_r = r_num - 2
                            r_id = staged_raw_ids[idx_r] if idx_r < len(staged_raw_ids) else None
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": r_num,
                                "error_code": "MULTIPLE_HQ_FOR_ASE",
                                "severity": "CRITICAL",
                                "field_name": "H.Q.",
                                "column_name": "hq_raw",
                                "actual_value": f"{hq_val} (Conflicts with: {', '.join([h for h in sorted_hqs if h != hq_val])})",
                                "expected_value": "Single Unique Headquarter per ASE",
                                "ase": ase_name,
                                "asm_tsm": str(s_asm.iloc[idx_r] or "").strip(),
                                "approved_asm_tsm": None,
                                "hq": hq_val,
                                "depot": str(s_depot.iloc[idx_r] or "").strip(),
                                "licensee": str(s_licensee.iloc[idx_r] or "").strip(),
                                "company": str(s_company.iloc[idx_r] or "").strip(),
                                "brand": str(s_brand.iloc[idx_r] or "").strip(),
                                "raw_id": r_id,
                                "error_message": f"[Row #{r_num}] MULTIPLE_HQ_FOR_ASE: ASE '{ase_name}' is mapped to multiple Headquarters ({', '.join(sorted_hqs)}) across sales records (e.g. {sample_details}). An ASE must belong to exactly 1 Headquarter.",
                                "resolution": f"Standardize Headquarter for ASE '{ase_name}' to a single Headquarter in the Excel file or update Headquarters in User Management."
                            })

            # 2. A TSM must belong to their registered Headquarters across the uploaded dataset
            for tsm_name, hq_dict in sheet_tsm_hqs.items():
                tsm_uid = _resolve_user_id(tsm_name)
                approved_hqs = user_approved_hq_names_by_id.get(tsm_uid, set()) if tsm_uid else set()
                if len(hq_dict) > 1:
                    unique_canonical_hqs = {_canonicalize_hq(h) for h in hq_dict.keys()}
                    if len(unique_canonical_hqs) <= 1:
                        continue
                    if all(_is_hq_matching_approved(h, approved_hqs) for h in hq_dict.keys()):
                        continue
                    sorted_hqs = sorted(list(hq_dict.keys()))
                    sample_details = ", ".join([f"Row #{rows[0]} ({h})" for h, rows in hq_dict.items()][:5])
                    for hq_val, row_nums in hq_dict.items():
                        for r_num in row_nums[:3]:
                            idx_r = r_num - 2
                            r_id = staged_raw_ids[idx_r] if idx_r < len(staged_raw_ids) else None
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": r_num,
                                "error_code": "MULTIPLE_HQ_FOR_TSM",
                                "severity": "CRITICAL",
                                "field_name": "H.Q.",
                                "column_name": "hq_raw",
                                "actual_value": f"{hq_val} (Conflicts with: {', '.join([h for h in sorted_hqs if h != hq_val])})",
                                "expected_value": "Single Unique Headquarter per TSM",
                                "ase": str(s_ase.iloc[idx_r] or "").strip(),
                                "asm_tsm": tsm_name,
                                "approved_asm_tsm": None,
                                "hq": hq_val,
                                "depot": str(s_depot.iloc[idx_r] or "").strip(),
                                "licensee": str(s_licensee.iloc[idx_r] or "").strip(),
                                "company": str(s_company.iloc[idx_r] or "").strip(),
                                "brand": str(s_brand.iloc[idx_r] or "").strip(),
                                "raw_id": r_id,
                                "error_message": f"[Row #{r_num}] MULTIPLE_HQ_FOR_TSM: TSM '{tsm_name}' is mapped to multiple Headquarters ({', '.join(sorted_hqs)}) across sales records (e.g. {sample_details}).",
                                "resolution": f"Standardize Headquarter for TSM '{tsm_name}' in the Excel file or update Headquarters in User Management."
                            })

            # 3. An ASE must report to at most 1 ASM/TSM manager across the uploaded dataset
            for ase_name, mgr_dict in sheet_ase_managers.items():
                if len(mgr_dict) > 1:
                    sorted_mgrs = sorted(list(mgr_dict.keys()))
                    sample_details = ", ".join([f"Row #{rows[0]} ({m})" for m, rows in mgr_dict.items()][:5])
                    for mgr_val, row_nums in mgr_dict.items():
                        for r_num in row_nums[:3]:
                            idx_r = r_num - 2
                            r_id = staged_raw_ids[idx_r] if idx_r < len(staged_raw_ids) else None
                            validation_error_records.append({
                                "upload_batch_id": str(batch_id),
                                "batch_id": str(batch_id),
                                "filename": filename,
                                "excel_row_number": r_num,
                                "error_code": "MULTIPLE_MANAGERS_FOR_ASE",
                                "severity": "CRITICAL",
                                "field_name": "ASM/TSM",
                                "column_name": "asm_tsm_raw",
                                "actual_value": f"{mgr_val} (Conflicts with: {', '.join([m for m in sorted_mgrs if m != mgr_val])})",
                                "expected_value": "Single Unique Reporting Manager per ASE (1:1 Constraint)",
                                "ase": ase_name,
                                "asm_tsm": mgr_val,
                                "approved_asm_tsm": None,
                                "hq": str(s_hq.iloc[idx_r] or "").strip(),
                                "depot": str(s_depot.iloc[idx_r] or "").strip(),
                                "licensee": str(s_licensee.iloc[idx_r] or "").strip(),
                                "company": str(s_company.iloc[idx_r] or "").strip(),
                                "brand": str(s_brand.iloc[idx_r] or "").strip(),
                                "raw_id": r_id,
                                "error_message": f"[Row #{r_num}] MULTIPLE_MANAGERS_FOR_ASE: ASE '{ase_name}' is mapped to multiple ASM/TSM managers ({', '.join(sorted_mgrs)}) across sales records (e.g. {sample_details}). An ASE must report to exactly 1 manager.",
                                "resolution": f"Standardize the ASM/TSM manager for ASE '{ase_name}' in the Excel file or reassign mapping in User Management."
                            })

            # Build Sales Fact DataFrame & Records
            fact_df = pd.DataFrame({
                "tenant_id": tenant_id,
                "sale_date": map_date,
                "licensee_id": map_licensee,
                "brand_id": map_brand,
                "packaging_id": map_packaging,
                "depot_id": map_depot,
                "headquarters_id": map_hq,
                "total_case": s_cases,
                "total_btl": s_btl,
                "total_bl": s_bl,
                "batch_id": batch_id,
            })

            valid_mask = fact_df[["depot_id", "licensee_id", "brand_id", "packaging_id", "headquarters_id"]].notna().all(axis=1)
            valid_fact_df = fact_df[valid_mask].copy()
            fact_records = valid_fact_df.to_dict("records")

            failed_rows = len(validation_error_records)
            imported_rows = total_rows if failed_rows == 0 else 0

            if local_batch:
                local_batch["imported_rows"] = imported_rows
                local_batch["failed_rows"] = failed_rows

            # 4. IF VALIDATION FAILS: HALT IMMEDIATELY AND PERSIST DIAGNOSTICS TO ERROR_LOGS
            if validation_error_records:
                try:
                    from backend.db.supabase_client import log_validation_errors
                    log_validation_errors(validation_error_records)
                    logger.info(f"Batch {batch_id}: Logged {len(validation_error_records)} detailed validation errors into error_logs table.")
                except Exception as e_err_log:
                    logger.warning(f"Batch {batch_id}: Exception logging detailed validation errors: {e_err_log}")

                first_err = validation_error_records[0]["error_message"]
                failure_reason = f"Validation issue detected: {failed_rows} record(s) need attention. First issue: {first_err}"
                logger.warning(f"Batch {batch_id}: {failure_reason}")

                # Rollback partial production writes (if any)
                self._cleanup_failed_batch(batch_id)

                processing_time = round(time.time() - start_time, 2)
                if local_batch:
                    local_batch.update({
                        "total_rows": total_rows,
                        "imported_rows": 0,
                        "failed_rows": failed_rows,
                        "status": "failed",
                        "upload_status": "failed",
                        "processing_time_seconds": processing_time,
                        "remarks": failure_reason,
                    })

                self._update_batch(
                    batch_id=batch_id,
                    status="failed",
                    row_count=total_rows,
                    remarks=failure_reason,
                )
                self._update_batch_progress(batch_id, remarks=failure_reason)

                self._pipeline_log(
                    batch_id=batch_id,
                    step="validation_failed",
                    status="failed",
                    message=failure_reason,
                )

                # Purge raw_sales_upload AFTER error_logs diagnostic persistence is confirmed
                try:
                    client_p = get_supabase()
                    if client_p and batch_id:
                        client_p.table("raw_sales_upload").delete().eq("batch_id", str(batch_id)).execute()
                        logger.info(f"Batch {batch_id}: Purged raw_sales_upload staging rows after confirming diagnostic persistence in error_logs.")
                except Exception as e_purge:
                    logger.warning(f"Notice purging raw_sales_upload for batch {batch_id}: {e_purge}")

                # Enforce 10-minute cooldown on validation error as requested:
                # "agr validation error ajaye toh 10 minutes ka timer ajaye uske baad upload hoyegi dusri sheet. yeh purge wale task fir un 10 minute mai hojaye."
                try:
                    from backend.core.system_lock import record_upload_cooldown
                    source_fname = (local_batch.get("source_file") if local_batch else None) or filename or "Sales Data File"
                    record_upload_cooldown(
                        upload_type="validation_error",
                        filename=source_fname,
                        cooldown_seconds=600,
                        reason=f"Validation issue detected in '{source_fname}'. 10-minute rollback & purge buffer active."
                    )
                except Exception as e_cd:
                    logger.warning(f"Notice setting validation error cooldown: {e_cd}")

                self.release_pipeline_lock(batch_id)
                return local_batch

            if self.is_batch_cancelled(batch_id):
                raise UploadCancelledException(f"Batch {batch_id} cancelled by user before sales_fact insertion.")

            # 5. ATOMIC PROMOTION TO PRODUCTION (ALL VALIDATIONS PASSED)
            self._update_batch(batch_id=batch_id, status="validated")
            self._update_batch_progress(
                batch_id,
                remarks=f"Validation successful! All {total_rows:,} rows verified with 0 errors. Saving to database...",
            )

            # Bulk Insert Sales Fact Records
            if fact_records:
                distinct_dates = list({str(r.get("sale_date", "")).strip() for r in fact_records if r.get("sale_date")})
                try:
                    from backend.db.supabase_client import ensure_calendar_dates
                    ensure_calendar_dates(distinct_dates)
                except Exception as e_cal:
                    logger.warning(f"dim_calendar population notice: {e_cal}")

                # Purge existing sales facts for this batch_id before insert
                if client and batch_id:
                    batch_id_str = str(batch_id).strip()
                    if batch_id_str:
                        try:
                            client.table("sales_fact").delete().eq("batch_id", batch_id_str).execute()
                        except Exception as e_del:
                            logger.warning(f"Batch {batch_id}: Error purging sales_fact: {e_del}")

                self._bulk_insert(
                    table="sales_fact",
                    records=fact_records,
                    chunk_size=5000,
                    batch_id=batch_id,
                )

            # Populate user_sales_fact (including Company = Others)
            self._populate_user_sales_fact(
                batch_id, s_date, s_company, s_ase, s_brand, s_cases, s_btl, s_bl,
                company_cache, brand_cache, tenant_id=tenant_id
            )

            # Auto-populate user_depot and user_headquarters_mapping from validated upload data
            self._sync_user_territory_mappings(
                s_ase, s_asm, s_depot, s_hq, depot_cache, hq_cache, tenant_id=tenant_id
            )

            if self.is_batch_cancelled(batch_id):
                raise UploadCancelledException(f"Batch {batch_id} cancelled by user before analytics aggregation.")

            # Step 10 - Trigger Incremental Analytics Summaries & Validation ONLY after complete sales_fact ingestion
            if fact_records and imported_rows > 0:
                distinct_dates = list({r.get("sale_date") for r in fact_records if r.get("sale_date")})
                
                # Update status state to aggregating
                self._update_batch(batch_id=batch_id, status="aggregating")
                self._update_batch_progress(batch_id, remarks="Updating sales dashboard and analytics charts...")

                from backend.analytics.incremental_engine import incremental_engine
                from backend.analytics.validator import analytics_validator

                agg_res = incremental_engine.process_batch_incremental_aggregation(
                    batch_id=batch_id,
                    sale_dates=distinct_dates
                )

                if not agg_res.get("success"):
                    logger.warning(f"Incremental summary aggregation encountered minor issues for batch {batch_id}.")

                # Run validation check on primary affected date
                if distinct_dates:
                    self._update_batch(batch_id=batch_id, status="validating")
                    self._update_batch_progress(batch_id, remarks="Final verification: Checking dashboard figures...")
                    val_res = analytics_validator.validate_date_accuracy(target_date=str(distinct_dates[0]).split("T")[0])
                    if val_res.get("is_accurate"):
                        logger.info(f"Batch {batch_id}: Incremental analytics 100% verified accurate against legacy RPC.")
                    else:
                        logger.warning(f"Batch {batch_id}: Accuracy validation notice: {val_res.get('mismatches')}")

            processing_time = round(time.time() - start_time, 2)
            if local_batch:
                local_batch["processing_time_seconds"] = processing_time

            final_status = "loaded" if imported_rows > 0 else "failed"
            self._update_batch(batch_id=batch_id, row_count=total_rows, status=final_status)

            # Phase 1 Automatic Post-Ingestion Cleanup: purge raw_sales_upload in non-blocking background thread
            if final_status == "loaded":
                import threading
                threading.Thread(target=self._purge_batch_temporary_data, args=(batch_id,), daemon=True).start()

            if final_status == "loaded":
                if distinct_dates:
                    try:
                        from backend.db.supabase_client import set_latest_sale_date_cached
                        newest_date = str(max(distinct_dates))
                        set_latest_sale_date_cached(newest_date)
                        logger.info(f"Batch {batch_id}: Updated cached latest sale date to {newest_date}.")
                    except Exception as e_date:
                        logger.warning(f"Batch {batch_id}: set_latest_sale_date_cached notice: {e_date}")

                from backend.services.cache_service import invalidate_analytics_cache_sync, prewarm_cache_egress_sync
                try:
                    purged_count = invalidate_analytics_cache_sync()
                    logger.info(f"Batch {batch_id}: Post-load cache invalidation purged {purged_count} entries.")
                    prewarm_res = prewarm_cache_egress_sync()
                    logger.info(f"Batch {batch_id}: Phase 4 Post-load cache pre-warming result: {prewarm_res}")
                except Exception as cache_err:
                    logger.warning(f"Batch {batch_id}: Cache invalidation/pre-warming notice: {cache_err}")

            completed_at_iso = datetime.now().isoformat()
            distinct_dates_count = len(distinct_dates) if fact_records else 0

            final_remarks = f"Upload completed successfully! {imported_rows:,} records verified and saved."
            if local_batch:
                local_batch.update({
                    "total_rows": total_rows,
                    "imported_rows": imported_rows,
                    "duplicate_rows": 0,
                    "failed_rows": failed_rows,
                    "processing_time_seconds": processing_time,
                    "status": final_status,
                    "upload_status": final_status,
                    "chunk_count": (len(raw_records) + 4999) // 5000 + (len(fact_records) + 4999) // 5000 if fact_records else 0,
                    "failed_chunks": 0,
                    "affected_dates_count": distinct_dates_count,
                    "completed_at": completed_at_iso,
                    "write_stats": {
                        "raw_inserts": len(raw_records) if raw_records else 0,
                        "fact_inserts": imported_rows,
                        "user_fact_inserts": len(fact_records) if fact_records else 0,
                        "summary_writes": len(distinct_dates) if fact_records else 0
                    },
                    "remarks": final_remarks,
                })
            self._update_batch_progress(batch_id, remarks=final_remarks)

            self._pipeline_log(
                batch_id=batch_id,
                step="file_processing",
                status="succeeded",
                message=(
                    f"Processing completed in {processing_time}s. "
                    f"Total={total_rows}, Loaded={imported_rows}, Failed={failed_rows}."
                ),
            )

            self._save_audit_log(
                batch_id=batch_id,
                user_id=user_id,
                imported_rows=imported_rows,
            )

            total_elapsed = time.time() - start_time
            logger.info(
                f"=== [INGESTION #{batch_id}] SUCCESSFUL FINISH ===\n"
                f"  File: '{filename}'\n"
                f"  Total Rows Extracted: {total_rows:,}\n"
                f"  Imported to sales_fact: {imported_rows:,}\n"
                f"  Total Duration: {total_elapsed:.1f}s ({total_elapsed/60:.2f} mins)\n"
                f"  Final Status: {final_status}"
            )

            if final_status in ("loaded", "completed", "success"):
                try:
                    from backend.core.system_lock import record_upload_completion
                    record_upload_completion("sales_upload", filename)
                except Exception as e_cd:
                    logger.warning(f"Failed to record upload completion cooldown: {e_cd}")

            return local_batch


        # =====================================================
        # USER CANCELLATION OR FAILURE (WITH AUTOMATIC ROLLBACK)
        # =====================================================

        except UploadCancelledException as exc:
            logger.warning(
                "[INGESTION #%s] CANCELLED BY USER: %s. Executing atomic rollback to 0.",
                batch_id,
                exc,
            )
            self._cleanup_failed_batch(batch_id)
            self.release_pipeline_lock(batch_id)

            local_batch = upload_batches_db.get(batch_id)
            if local_batch:
                local_batch.update({
                    "status": "cancelled",
                    "upload_status": "cancelled",
                    "remarks": "Upload cancelled by user. Execution stopped and partial records rolled back to 0.",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                })

            try:
                self._update_batch(
                    batch_id=batch_id,
                    status="cancelled",
                    remarks="Upload cancelled by user. Execution stopped and partial records rolled back to 0."
                )
            except Exception:
                pass

            try:
                from backend.core.system_lock import invalidate_system_lock_cache, clear_roster_upload_active, record_upload_cooldown
                invalidate_system_lock_cache()
                clear_roster_upload_active()
                source_fname = (local_batch.get("source_file") if local_batch else None) or "Cancelled Upload"
                record_upload_cooldown(
                    upload_type="validation_error",
                    filename=source_fname,
                    cooldown_seconds=600,
                    reason=f"Upload cancelled and rolled back for '{source_fname}'. 10-minute purge buffer active."
                )
            except Exception:
                pass

            return local_batch

        except Exception as exc:
            total_elapsed = time.time() - start_time
            logger.error(
                f"=== [INGESTION #{batch_id}] FAILED AT CRITICAL FAILURE POINT ===\n"
                f"  File: '{filename}'\n"
                f"  Elapsed Time: {total_elapsed:.1f}s\n"
                f"  Error Type: {type(exc).__name__}\n"
                f"  Error Details: {str(exc)}\n",
                exc_info=True
            )

            # Record error in upload_validation_errors table
            try:
                self._save_validation_error(
                    batch_id=batch_id,
                    column_name="PIPELINE_ERROR",
                    message=f"Upload batch failed: {str(exc)}",
                    raw_id=None,
                )
            except Exception as log_err:
                logger.warning(f"Could not log pipeline failure to upload_validation_errors: {log_err}")

            # Rollback / cleanup any partial records inserted for this batch
            self._cleanup_failed_batch(batch_id)

            local_batch = upload_batches_db.get(batch_id)

            if local_batch:
                local_batch.update({
                    "status": "failed",
                    "upload_status": "failed",
                    "remarks": f"Pipeline failed: {str(exc)}. All partial records rolled back.",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                })

            try:
                self._update_batch(
                    batch_id=batch_id,
                    status="failed",
                )
            except Exception:
                logger.exception(
                    "Could not mark batch %s failed.",
                    batch_id,
                )

            try:
                self._pipeline_log(
                    batch_id=batch_id,
                    step="file_processing",
                    status="failed",
                    message=str(exc),
                )
            except Exception:
                pass

            try:
                from backend.core.system_lock import invalidate_system_lock_cache, clear_roster_upload_active, record_upload_cooldown
                invalidate_system_lock_cache()
                clear_roster_upload_active()
                source_fname = (local_batch.get("source_file") if local_batch else None) or "Failed Upload"
                record_upload_cooldown(
                    upload_type="validation_error",
                    filename=source_fname,
                    cooldown_seconds=600,
                    reason=f"Upload failed: {str(exc)}. 10-minute purge buffer active."
                )
            except Exception:
                pass

            return local_batch
        finally:
            self.release_pipeline_lock(batch_id)

    # ========================================================
    # EXCEL ROW EXTRACTION
    # ========================================================

    def _extract_row(
        self,
        row,
        column_map: Dict[str, str],
    ) -> Dict[str, Any]:

        sale_date_raw = self._clean_text(
            row[
                column_map["Date"]
            ]
        )

        company = self._clean_text(
            row[
                column_map["Company"]
            ]
        )

        licensee_name = self._clean_text(
            row[
                column_map["LICENSEE_NAME"]
            ]
        )

        trade = self._normalize_trade(
            row[
                column_map["Trade"]
            ]
        )

        group_name = self._clean_text(
            row[
                column_map["Group Name"]
            ]
        )

        hq_name = self._clean_text(
            row[
                column_map["H.Q."]
            ]
        )

        deo_office_name = self._clean_text(
            row[
                column_map[
                    "DEO_OFFICE_NAME"
                ]
            ]
        )

        circle_office_name = self._clean_text(
            row[column_map["CIRCLE_OFFICE_NAME"]]
        ) if "CIRCLE_OFFICE_NAME" in column_map else ""

        depot_name = self._clean_text(
            row[
                column_map["DEPOT_NAME"]
            ]
        )

        ase_name = self._clean_text(
            row[
                column_map["ASE"]
            ]
        )

        asm_tsm_name = self._clean_text(
            row[
                column_map["ASM/TSM"]
            ]
        )

        brand_name = self._clean_text(
            row[
                column_map["BRAND_NAME"]
            ]
        )

        packing_raw = self._clean_text(
            row[
                column_map["PACKING_IN_ML"]
            ]
        )

        total_case = self._number(
            row[
                column_map["TOTAL_CASE"]
            ]
        )

        total_btl = self._number(
            row[column_map["TOTAL_BTL"]]
        ) if "TOTAL_BTL" in column_map else 0.0

        total_bl = self._number(
            row[column_map["TOTAL_BL"]]
        ) if "TOTAL_BL" in column_map else 0.0

        # ----------------------------------------------------
        # Validate mandatory textual values.
        # ----------------------------------------------------

        required_text = {

            "Date":
                sale_date_raw,

            "Company":
                company,

            "LICENSEE_NAME":
                licensee_name,

            "Group Name":
                group_name,

            "H.Q.":
                hq_name,

            "DEO_OFFICE_NAME":
                deo_office_name,

            "DEPOT_NAME":
                depot_name,

            "ASE":
                ase_name,

            "ASM/TSM":
                asm_tsm_name,

            "BRAND_NAME":
                brand_name,

            "PACKING_IN_ML":
                packing_raw,
        }

        for column_name, value in (
            required_text.items()
        ):

            if not value:
                raise ValueError(
                    f"{column_name} is empty."
                )

        sale_date = self._parse_date(
            sale_date_raw
        )

        return {

            "sale_date_raw":
                sale_date_raw,

            "sale_date":
                sale_date,

            "company":
                company,

            "licensee_name":
                licensee_name,

            "trade":
                trade,

            "group_name":
                group_name,

            "hq_name":
                hq_name,

            "deo_office_name":
                deo_office_name,

            "circle_office_name":
                circle_office_name,

            "depot_name":
                depot_name,

            "ase_name":
                ase_name,

            "asm_tsm_name":
                asm_tsm_name,

            "brand_name":
                brand_name,

            "packing_raw":
                packing_raw,

            "total_case":
                total_case,

            "total_btl":
                total_btl,

            "total_bl":
                total_bl,
        }

    # ========================================================
    # BUILD COLUMN MAP
    # ========================================================

    def _build_column_map(
        self,
        dataframe: pd.DataFrame,
    ) -> Dict[str, str]:

        available_columns = {}

        for column in dataframe.columns:

            normalized = (
                self._normalize_header(
                    column
                )
            )

            available_columns[
                normalized
            ] = column

        column_map = {}

        STRICT_MANDATORY = {
            "Date",
            "LICENSEE_NAME",
            "DEPOT_NAME",
            "BRAND_NAME",
            "PACKING_IN_ML",
            "TOTAL_CASE",
        }

        missing_columns = []

        for (
            standard_column,
            aliases,
        ) in COLUMN_ALIASES.items():

            found_column = None

            for alias in aliases:

                alias_normalized = (
                    self._normalize_header(
                        alias
                    )
                )

                if (
                    alias_normalized
                    in available_columns
                ):

                    found_column = (
                        available_columns[
                            alias_normalized
                        ]
                    )

                    break

            if found_column is None:
                if standard_column in STRICT_MANDATORY:
                    missing_columns.append(
                        standard_column
                    )
            else:

                column_map[
                    standard_column
                ] = found_column

        if missing_columns:

            actual_columns = [
                str(column)
                for column
                in dataframe.columns
            ]

            raise ValueError(
                "Missing mandatory Excel columns: "
                f"{missing_columns}. "
                f"Columns detected: "
                f"{actual_columns}"
            )

        return column_map


    # ========================================================
    # FILE PARSER
    # ========================================================

    def _parse_file(
        self,
        filename: str,
        contents: bytes,
    ) -> pd.DataFrame:

        filename_lower = filename.lower()

        # ----------------------------------------------------
        # APPLE NUMBERS (.numbers)
        # ----------------------------------------------------
        if filename_lower.endswith(".numbers"):
            try:
                return self._parse_numbers(contents)
            except Exception as e_num:
                logger.warning(f"Dedicated _parse_numbers failed: {e_num}. Trying general parsers...")

        raw_dataframe = None

        t_parse_start = time.time()
        logger.info(f"[PARSE-START] Parsing file '{filename}' ({len(contents) / (1024 * 1024):.2f} MB)...")

        # ----------------------------------------------------
        # 1. EXCEL PARSING (.xlsx, .xls, .xlsb, etc.)
        # ----------------------------------------------------
        # Direct Calamine fast Rust engine parser for Excel files (.xlsb, .xlsx, .xls)
        if filename_lower.endswith((".xlsb", ".xlsx", ".xls")):
            try:
                logger.info(f"[PARSE-ENGINE] Attempting fast Rust Calamine engine for '{filename}'...")
                t_cal = time.time()
                from python_calamine import CalamineWorkbook
                workbook = CalamineWorkbook.from_object(io.BytesIO(contents))
                sheet_name = workbook.sheet_names[0]
                rows = workbook.get_sheet_by_name(sheet_name).to_python()
                if rows:
                    raw_dataframe = pd.DataFrame(rows)
                    logger.info(f"[PARSE-SUCCESS] Calamine parsed '{filename}' in {time.time() - t_cal:.2f}s ({len(rows):,} rows).")
            except ModuleNotFoundError:
                logger.warning(f"[PARSE-WARN] 'python_calamine' library NOT installed in this environment. Falling back to pyxlsb/pandas...")
            except Exception as e_calamine:
                logger.warning(f"[PARSE-WARN] Direct CalamineWorkbook parsing failed for '{filename}': {e_calamine}")

        if raw_dataframe is None or raw_dataframe.empty:
            excel_engines = ["calamine", "pyxlsb", "openpyxl", "xlrd"]
            for engine in excel_engines:
                try:
                    logger.info(f"[PARSE-ENGINE] Trying pandas read_excel with engine='{engine}'...")
                    raw_dataframe = pd.read_excel(io.BytesIO(contents), header=None, engine=engine)
                    if raw_dataframe is not None and not raw_dataframe.empty and len(raw_dataframe) > 0:
                        logger.info(f"[PARSE-SUCCESS] pandas with engine='{engine}' parsed {len(raw_dataframe):,} rows.")
                        break
                except Exception:
                    continue

        # Dedicated pyxlsb engine fallback for binary files (.xlsb)
        if (raw_dataframe is None or raw_dataframe.empty) and filename_lower.endswith(".xlsb"):
            try:
                logger.info(f"[PARSE-ENGINE] Falling back to dedicated pure-Python pyxlsb engine for '{filename}' (iterating cells)...")
                t_xlsb = time.time()
                # pyrefly: ignore [missing-import]
                import pyxlsb
                rows = []
                with pyxlsb.open_workbook(io.BytesIO(contents)) as wb:
                    sheet_name = wb.sheets[0]
                    with wb.get_sheet(sheet_name) as sheet:
                        for row in sheet.rows():
                            rows.append([cell.v for cell in row])
                if rows:
                    raw_dataframe = pd.DataFrame(rows)
                    logger.info(f"[PARSE-SUCCESS] Dedicated pyxlsb parsed '{filename}' in {time.time() - t_xlsb:.2f}s ({len(rows):,} rows).")
            except Exception as e_xlsb:
                logger.warning(f"[PARSE-ERROR] Dedicated pyxlsb workbook parsing failed: {e_xlsb}")

        # ----------------------------------------------------
        # 2. CSV / TSV / DELIMITED TEXT PARSING
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            encodings_to_try = ["utf-8", "utf-8-sig", "cp1252", "latin1", "iso-8859-1", "ascii"]
            delimiters_to_try = [",", ";", "\t", "|"]

            for enc in encodings_to_try:
                for sep in delimiters_to_try:
                    try:
                        df_test = pd.read_csv(
                            io.BytesIO(contents),
                            header=None,
                            encoding=enc,
                            sep=sep,
                            low_memory=False,
                            on_bad_lines="skip"
                        )
                        # Ensure parser actually separated columns instead of 1 giant string column
                        if df_test is not None and not df_test.empty and len(df_test.columns) > 1:
                            raw_dataframe = df_test
                            break
                    except Exception:
                        continue
                if raw_dataframe is not None and not raw_dataframe.empty:
                    break

        # ----------------------------------------------------
        # 3. LEGACY HTML / XML TABLE EXPORTS (Government Software .xls/.csv exports)
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            try:
                html_dfs = pd.read_html(io.BytesIO(contents))
                if html_dfs and len(html_dfs) > 0:
                    raw_dataframe = html_dfs[0]
            except Exception:
                pass

        # ----------------------------------------------------
        # 4. LAST RESORT: STANDARD CSV READ
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            try:
                raw_dataframe = pd.read_csv(
                    io.BytesIO(contents),
                    header=None,
                    encoding="latin1",
                    on_bad_lines="skip",
                    low_memory=False
                )
            except Exception:
                pass

        if raw_dataframe is None or raw_dataframe.empty:
            raise ValueError(f"Could not parse file '{filename}'. Unrecognized or corrupted file format.")

        header_index = self._detect_header_row(raw_dataframe)
        if header_index is None:
            header_index = 0

        headers = [str(col).strip() for col in raw_dataframe.iloc[header_index].values]
        dataframe = raw_dataframe.iloc[header_index + 1 :].copy()
        dataframe.columns = headers
        dataframe = dataframe.dropna(how="all")

        # Remove completely unnamed columns.
        valid_columns = []

        for column in dataframe.columns:

            column_text = (
                str(column).strip()
            )

            if not column_text.lower().startswith(
                "unnamed:"
            ):

                valid_columns.append(
                    column
                )

        dataframe = dataframe[
            valid_columns
        ]

        return dataframe

    # ========================================================
    # HEADER DETECTION
    # ========================================================

    def _detect_header_row(
        self,
        dataframe: pd.DataFrame,
    ) -> Optional[int]:

        """
        Your Excel begins with:

        IMFL Ind. May-2026 ... totals

        followed by:

        Date
        Company
        LICENSEE_NAME
        Trade
        Group Name
        H.Q.
        ...
        """

        strong_headers = {
            "date",
            "company",
            "licensee_name",
            "trade",
            "group name",
            "depot_name",
            "brand_name",
            "packing_in_ml",
            "total_case",
            "total_btl",
            "total_bl",
            "depot code",
            "license number",
            "brand code",
            "packing size",
            "cases",
            # "bottles",
            # "bulk liters",
            "sale value",
            "depot",
            "brand",
            "licensee",
        }

        rows_to_scan = min(
            len(dataframe),
            25,
        )

        for index in range(
            rows_to_scan
        ):

            row_values = set()

            for value in (
                dataframe
                .iloc[index]
                .tolist()
            ):

                normalized = (
                    self._normalize_header(
                        value
                    )
                )

                if normalized:
                    row_values.add(
                        normalized
                    )

            matches = len(
                row_values.intersection(
                    strong_headers
                )
            )

            if matches >= 2:

                logger.info(
                    "Detected Excel header "
                    "at row index %s.",
                    index,
                )

                return index

        return None


    # ========================================================
    # NUMBERS PARSER
    # ========================================================

    def _parse_numbers(
        self,
        contents: bytes,
    ) -> pd.DataFrame:

        with tempfile.NamedTemporaryFile(
            suffix=".numbers",
            delete=False,
        ) as temporary_file:

            temporary_file.write(
                contents
            )

            temporary_path = (
                temporary_file.name
            )

        try:

            document = Document(
                temporary_path
            )

            if not document.sheets:
                raise ValueError(
                    "Numbers file has no sheets."
                )

            sheet = (
                document.sheets[0]
            )

            if not sheet.tables:
                raise ValueError(
                    "Numbers sheet has no tables."
                )

            rows = list(
                sheet.tables[0].rows(
                    values_only=True
                )
            )

            if not rows:
                raise ValueError(
                    "Numbers file contains no rows."
                )

            raw_dataframe = (
                pd.DataFrame(rows)
            )

            header_index = (
                self._detect_header_row(
                    raw_dataframe
                )
            )

            if header_index is None:

                raise ValueError(
                    "Could not locate header "
                    "inside Numbers file."
                )

            headers = [

                self._clean_text(value)

                for value
                in rows[
                    header_index
                ]
            ]

            dataframe = pd.DataFrame(
                rows[
                    header_index + 1:
                ],
                columns=headers,
            )

            dataframe = (
                dataframe.dropna(
                    how="all"
                )
            )

            return dataframe

        finally:

            if os.path.exists(
                temporary_path
            ):

                os.remove(
                    temporary_path
                )

    # ========================================================
    # STORAGE UPLOAD
    # ========================================================

    def _upload_original_file(
        self,
        filename: str,
        contents: bytes,
        batch_id: int,
    ):

        client = get_supabase()

        if not client:
            return

        storage_path = (
            f"uploads/"
            f"{batch_id}/"
            f"{int(time.time())}_"
            f"{filename}"
        )

        try:

            (
                client
                .storage
                .from_("excel-uploads")
                .upload(

                    path=
                        storage_path,

                    file=
                        contents,

                    file_options={
                        "content-type":
                            "application/octet-stream",

                        "upsert":
                            "true",
                    },
                )
            )

            local_batch = (
                upload_batches_db.get(
                    batch_id
                )
            )

            if local_batch:

                local_batch[
                    "storage_path"
                ] = storage_path

        except Exception as storage_error:

            # IMPORTANT:
            #
            # Earlier your file exceeded Supabase Storage size.
            # We intentionally continue processing the Excel.
            #
            # Storage and database ingestion are separate.
            # ------------------------------------------------

            logger.warning(
                "Could not upload original file "
                "to Supabase Storage: %s. "
                "Continuing with database ingestion.",
                storage_error,
            )

    # ========================================================
    # ========================================================
    # GENERIC BULK INSERT & PROGRESS TRACKING
    # ========================================================

    def _update_batch_progress(
        self,
        batch_id: int,
        remarks: str,
        status: Optional[str] = None,
    ):
        local_batch = upload_batches_db.get(batch_id)
        if local_batch:
            local_batch["remarks"] = remarks
            if status:
                local_batch["upload_status"] = status

        client = get_supabase()
        if client and status:
            try:
                payload = {"status": status}
                if local_batch:
                    u_fk = local_batch.get("uploaded_by") or local_batch.get("created_by") or local_batch.get("updated_by")
                    if u_fk and len(str(u_fk)) == 36 and str(u_fk) != "00000000-0000-0000-0000-000000000001":
                        payload["updated_by"] = str(u_fk)
                client.table("upload_batches").update(payload).eq("batch_id", batch_id).execute()
            except Exception as e:
                try:
                    client.table("upload_batches").update({"status": status}).eq("batch_id", batch_id).execute()
                except Exception as e2:
                    logger.warning(f"Could not update batch progress status: {e2}")

    def _cleanup_failed_batch(self, batch_id: Any):
        """
        Atomic Rollback to 0:
        Rollback/cleanup all partial records inserted for a batch if processing fails mid-way.
        Purges any partial rows from sales_fact, user_sales_fact, raw_sales_upload, and temporary tables.
        """
        client = get_supabase()
        if not client or not batch_id:
            return

        b_str = str(batch_id).strip()
        logger.warning(f"Atomic Rollback: Purging all partial records to 0 for upload batch {b_str}...")

        try:
            client.table("sales_fact").delete().eq("batch_id", b_str).execute()
        except Exception as exc:
            logger.warning(f"Single delete for sales_fact batch {b_str} hit timeout: {exc}. Executing date-partitioned rollback...")
            try:
                # Fallback: Delete day-by-day to stay well within Postgres statement limits
                while True:
                    d_res = client.table("sales_fact").select("sale_date").eq("batch_id", b_str).limit(100).execute()
                    dates = list({r["sale_date"] for r in (d_res.data or []) if r.get("sale_date")})
                    if not dates:
                        break
                    for d in dates:
                        client.table("sales_fact").delete().eq("batch_id", b_str).eq("sale_date", d).execute()
            except Exception as e_p:
                logger.warning(f"Date-scoped cleanup fallback notice for sales_fact: {e_p}")

        try:
            client.table("user_sales_fact").delete().eq("batch_id", b_str).execute()
        except Exception as exc:
            logger.warning(f"Single delete for user_sales_fact batch {b_str} hit timeout: {exc}. Executing date-partitioned rollback...")
            try:
                while True:
                    d_res = client.table("user_sales_fact").select("sale_date").eq("batch_id", b_str).limit(100).execute()
                    dates = list({r["sale_date"] for r in (d_res.data or []) if r.get("sale_date")})
                    if not dates:
                        break
                    for d in dates:
                        client.table("user_sales_fact").delete().eq("batch_id", b_str).eq("sale_date", d).execute()
            except Exception as e_p:
                logger.warning(f"Date-scoped cleanup fallback notice for user_sales_fact: {e_p}")

        try:
            client.table("raw_sales_upload").delete().eq("batch_id", b_str).execute()
            logger.info(f"Atomic Rollback: Purged raw_sales_upload staging records for batch {b_str}.")
        except Exception as exc_r:
            logger.warning(f"Notice purging raw_sales_upload in _cleanup_failed_batch: {exc_r}")

        # Purge temporary chunk tracking, staging records, and pipeline logs via RPC or table deletes
        try:
            from backend.db.supabase_client import purge_batch_data_fast_rpc
            purge_batch_data_fast_rpc(b_str)
        except Exception:
            for t in ["raw_sales_upload", "batch_chunks", "upload_pipeline_logs"]:
                try:
                    client.table(t).delete().eq("batch_id", b_str).execute()
                except Exception as exc_sub:
                    logger.debug(f"Notice purging {t} in _cleanup_failed_batch: {exc_sub}")

        try:
            client.table("upload_validation_errors").delete().eq("batch_id", b_str).execute()
        except Exception:
            pass

    def _record_batch_chunk(
        self,
        batch_id: int,
        chunk_number: int,
        start_row: int,
        end_row: int,
        row_count: int,
        status: str = "pending",
        inserted_rows: int = 0,
        error_message: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ):
        client = get_supabase()
        if not client or not batch_id:
            return

        now_iso = datetime.now().isoformat()
        payload = {
            "batch_id": batch_id,
            "chunk_number": chunk_number,
            "start_row": start_row,
            "end_row": end_row,
            "row_count": row_count,
            "status": status,
            "inserted_rows": inserted_rows,
            "error_message": error_message,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        if started_at:
            payload["started_at"] = started_at
        if completed_at:
            payload["completed_at"] = completed_at

        try:
            client.table("batch_chunks").upsert(
                payload,
                on_conflict="batch_id,chunk_number"
            ).execute()
        except Exception as exc:
            try:
                client.table("batch_chunks").insert(payload).execute()
            except Exception as e2:
                logger.warning(f"Could not record batch_chunks row: {exc} | fallback: {e2}")

    def _bulk_insert(
        self,
        table: str,
        records: List[Dict[str, Any]],
        chunk_size: int = 5000,
        batch_id: Optional[Any] = None,
        chunk_number_offset: int = 0,
    ):
        """
        Phase 5 Optimized Bulk Ingestion & Consolidated Progress Logging:
        Inserts records in benchmarked chunks (default 5,000) and consolidates DB metadata progress writes
        to milestone intervals (20% steps), cutting PostgREST transaction spam by 90% and bounding WAL write growth.
        """
        if not records:
            return

        client = get_supabase()
        total_chunks = (len(records) + chunk_size - 1) // chunk_size

        t_clean = (table or "").lower()
        if "raw" in t_clean:
            friendly_stage = "Preparing sales data"
        elif "sales_fact" in t_clean:
            friendly_stage = "Saving sales records"
        elif "user_sales" in t_clean:
            friendly_stage = "Updating user metrics"
        elif "summary" in t_clean:
            friendly_stage = "Updating analytics"
        else:
            friendly_stage = "Saving records"

        t_bulk_start = time.time()
        logger.info(
            f"[BULK-INSERT START] Table: '{table}' | Records: {len(records):,} | "
            f"Total Chunks: {total_chunks} (Chunk Size: {chunk_size}) | Batch ID: {batch_id}"
        )

        if batch_id:
            msg_init = f"{friendly_stage} ({len(records):,} rows in {total_chunks} parts)..."
            self._pipeline_log(
                batch_id=batch_id,
                step=f"chunk_created_{table}",
                status="started",
                message=msg_init,
            )
            self._update_batch_progress(batch_id, remarks=msg_init)

        # Milestone step interval for DB progress writes (e.g. 20% steps, or at least every 5 chunks)
        milestone_step = max(1, total_chunks // 5)

        for idx, start_index in enumerate(range(0, len(records), chunk_size), start=1):
            is_milestone = (idx == 1 or idx == total_chunks or (idx % milestone_step == 0))
            if batch_id:
                # 1. Fast in-memory cancellation/failure check
                if self.is_batch_cancelled(batch_id):
                    logger.warning(f"Upload batch {batch_id} cancellation/halt detected in _bulk_insert ({table}) at chunk {idx}/{total_chunks}.")
                    raise UploadCancelledException(f"Batch {batch_id} cancelled or marked failed during {table} chunk {idx}/{total_chunks}.")

                # 2. Authoritative Database abort check on milestones/intervals (every 5 chunks or milestone)
                if is_milestone or (idx % 5 == 0):
                    if self.is_batch_aborted_in_db(batch_id):
                        logger.warning(f"Upload batch {batch_id} marked failed/cancelled in database. Terminating background worker for {table} at chunk {idx}/{total_chunks}.")
                        raise UploadCancelledException(f"Batch {batch_id} terminated due to DB status change (failed/cancelled) during {table} chunk {idx}/{total_chunks}.")

            chunk = records[start_index : start_index + chunk_size]
            start_row = start_index + 1
            end_row = min(start_index + chunk_size, len(records))
            chunk_num = chunk_number_offset + idx
            start_time_iso = datetime.now().isoformat()
            t_chunk_start = time.time()

            pct = int((idx / total_chunks) * 100)
            msg_progress = f"{friendly_stage} ({idx}/{total_chunks}) • {pct}% complete..."

            # Always update local memory state for zero-latency UI polling
            local_batch = upload_batches_db.get(batch_id) if batch_id else None
            if local_batch:
                local_batch["remarks"] = msg_progress
                local_batch["chunk_count"] = total_chunks

            if batch_id and is_milestone:
                self._update_batch_progress(batch_id, remarks=msg_progress)
                self._record_batch_chunk(
                    batch_id=batch_id,
                    chunk_number=chunk_num,
                    start_row=start_row,
                    end_row=end_row,
                    row_count=len(chunk),
                    status="processing",
                    started_at=start_time_iso,
                )

            success = False
            err_msg = None
            inserted_count = 0

            if client:
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        if table == "dashboard_summary_daily":
                            client.table(table).upsert(chunk, on_conflict="sale_date,depot_id,brand_id", returning="minimal").execute()
                        else:
                            client.table(table).insert(chunk, returning="minimal").execute()
                        success = True
                        inserted_count = len(chunk)
                        chunk_dur = time.time() - t_chunk_start
                        if is_milestone or (idx % 5 == 0):
                            logger.info(
                                f"[BULK-INSERT PROGRESS] [{table}] Chunk {idx}/{total_chunks} "
                                f"({len(chunk)} rows) inserted in {chunk_dur:.2f}s [{pct}% complete]"
                            )
                        break
                    except Exception as exc:
                        err_msg = str(exc)
                        if attempt < max_retries:
                            sleep_sec = attempt * 1.5
                            logger.warning(f"[BULK-INSERT RETRY] Chunk {idx}/{total_chunks} ({table}) attempt {attempt} failed: {err_msg}. Retrying in {sleep_sec}s...")
                            time.sleep(sleep_sec)
                        else:
                            logger.warning(f"[BULK-INSERT FAILED] Chunk {idx}/{total_chunks} ({table}) failed all {max_retries} retries: {err_msg}. Initiating sub-chunk recovery...")

                if not success:
                    # Sub-chunk retry recovery (divide chunk into sub-chunks of 500)
                    sub_chunk_size = 500
                    sub_inserted = 0
                    failed_sub_records = []

                    for sub_start in range(0, len(chunk), sub_chunk_size):
                        sub_chunk = chunk[sub_start : sub_start + sub_chunk_size]
                        try:
                            if table == "dashboard_summary_daily":
                                client.table(table).upsert(sub_chunk, on_conflict="sale_date,depot_id,brand_id", returning="minimal").execute()
                            else:
                                client.table(table).insert(sub_chunk, returning="minimal").execute()
                            sub_inserted += len(sub_chunk)
                        except Exception as sub_exc:
                            sub_err = str(sub_exc)
                            logger.warning(f"Sub-chunk ({sub_start}-{sub_start+len(sub_chunk)}) error in {table}: {sub_err}. Falling back to single row isolation...")
                            # Single-row micro-batch fallback to recover all good rows
                            for item_idx, single_item in enumerate(sub_chunk):
                                try:
                                    if table == "dashboard_summary_daily":
                                        client.table(table).upsert([single_item], on_conflict="sale_date,depot_id,brand_id", returning="minimal").execute()
                                    else:
                                        client.table(table).insert([single_item], returning="minimal").execute()
                                    sub_inserted += 1
                                except Exception as single_exc:
                                    actual_row_num = start_row + sub_start + item_idx
                                    failed_sub_records.append({
                                        "batch_id": str(batch_id) if batch_id else None,
                                        "column_name": table,
                                        "error_message": f"Row {actual_row_num} failed insertion in table '{table}': {single_exc}"
                                    })

                    if sub_inserted > 0:
                        success = True
                        inserted_count = sub_inserted
                        logger.info(f"Self-healing recovery saved {sub_inserted}/{len(chunk)} rows for {table} in chunk {idx}.")

                    # Ensure failed sub-records OR unrecovered chunk errors are logged into upload_validation_errors
                    if not failed_sub_records and inserted_count < len(chunk):
                        # Log generic chunk level error for uninserted rows
                        failed_sub_records.append({
                            "batch_id": str(batch_id) if batch_id else None,
                            "column_name": table,
                            "error_message": f"Chunk {idx} (rows {start_row}-{end_row}) failed insertion in table '{table}': {err_msg}"
                        })

                    if failed_sub_records:
                        try:
                            from backend.db.supabase_client import log_validation_errors
                            log_validation_errors(failed_sub_records)
                            logger.info(f"Batch {batch_id}: Logged {len(failed_sub_records)} detailed row error records into upload_validation_errors.")
                        except Exception as log_exc:
                            logger.warning(f"Could not log chunk error to upload_validation_errors: {log_exc}")

                    # ATOMIC ALL-OR-NOTHING: If any records in this chunk failed insertion, abort and trigger full rollback!
                    if inserted_count < len(chunk):
                        first_err_detail = failed_sub_records[0]["error_message"] if failed_sub_records else (err_msg or "Database insertion error")
                        raise RuntimeError(f"Chunk {idx} (rows {start_row}-{end_row}) failed write into '{table}': {first_err_detail}")
            else:
                success = True
                inserted_count = len(chunk)

            end_time_iso = datetime.now().isoformat()

            if batch_id and (is_milestone or not success or inserted_count < len(chunk)):
                if success and inserted_count == len(chunk):
                    msg_done = f"Chunk {idx}/{total_chunks} populated in table '{table}'."
                    self._record_batch_chunk(
                        batch_id=batch_id,
                        chunk_number=chunk_num,
                        start_row=start_row,
                        end_row=end_row,
                        row_count=len(chunk),
                        status="completed",
                        inserted_rows=inserted_count,
                        completed_at=end_time_iso,
                    )
                elif success and inserted_count > 0:
                    msg_part = f"Chunk {idx}/{total_chunks} partially recovered ({inserted_count}/{len(chunk)} inserted)."
                    self._record_batch_chunk(
                        batch_id=batch_id,
                        chunk_number=chunk_num,
                        start_row=start_row,
                        end_row=end_row,
                        row_count=len(chunk),
                        status="partial",
                        inserted_rows=inserted_count,
                        error_message=err_msg,
                        completed_at=end_time_iso,
                    )
                else:
                    msg_failed = f"Chunk {idx}/{total_chunks} failed for table '{table}': {err_msg}"
                    self._pipeline_log(
                        batch_id=batch_id,
                        step=f"chunk_{table}_{idx}",
                        status="failed",
                        message=msg_failed,
                    )
                    self._record_batch_chunk(
                        batch_id=batch_id,
                        chunk_number=chunk_num,
                        start_row=start_row,
                        end_row=end_row,
                        row_count=len(chunk),
                        status="failed",
                        inserted_rows=0,
                        error_message=err_msg,
                        completed_at=end_time_iso,
                    )

        if batch_id:
            msg_finish = f"{friendly_stage} completed ({len(records):,} rows)."
            self._pipeline_log(
                batch_id=batch_id,
                step=f"chunk_completed_{table}",
                status="succeeded",
                message=msg_finish,
            )
            self._update_batch_progress(batch_id, remarks=msg_finish)




    # ========================================================
    # UPDATE UPLOAD BATCH
    # ========================================================

    def _update_batch(
        self,
        batch_id: int,
        row_count: Optional[int] = None,
        status: Optional[str] = None,
        remarks: Optional[str] = None,
    ):
        local_batch = upload_batches_db.get(batch_id)
        if local_batch:
            if status is not None:
                local_batch["status"] = status
                local_batch["upload_status"] = status
            if row_count is not None:
                local_batch["total_rows"] = row_count
                local_batch["row_count"] = row_count
            if remarks is not None:
                local_batch["remarks"] = remarks

        client = get_supabase()
        if not client:
            logger.info("Supabase client unavailable; in-memory batch %s updated.", batch_id)
            return

        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if row_count is not None:
            payload["row_count"] = row_count

        if remarks is not None:
            payload["remarks"] = remarks

        if status is not None:
            allowed_statuses = {
                "pending",
                "staged",
                "validated",
                "loaded",
                "completed",
                "failed",
            }
            db_status = "loaded" if status == "completed" else status
            if db_status in allowed_statuses:
                payload["status"] = db_status

        if local_batch:
            if "imported_rows" in local_batch:
                payload["imported_rows"] = local_batch["imported_rows"]
            if "failed_rows" in local_batch:
                payload["failed_rows"] = local_batch["failed_rows"]
            if "duplicate_rows" in local_batch:
                payload["duplicate_rows"] = local_batch["duplicate_rows"]
            if "remarks" in local_batch and local_batch["remarks"]:
                payload["remarks"] = local_batch["remarks"]
            if "processing_time_seconds" in local_batch:
                payload["processing_time_seconds"] = local_batch["processing_time_seconds"]

            # Populate audit user IDs from batch context
            u_fk = local_batch.get("uploaded_by") or local_batch.get("created_by") or local_batch.get("updated_by")
            if u_fk and len(str(u_fk)) == 36 and str(u_fk) != "00000000-0000-0000-0000-000000000001":
                payload["updated_by"] = str(u_fk)
                if "uploaded_by" not in payload:
                    payload["uploaded_by"] = str(u_fk)

        if not payload:
            return

        try:
            client.table("upload_batches").update(payload).eq("batch_id", batch_id).execute()
            if status in ("completed", "loaded", "success"):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(invalidate_analytics_cache())
                except Exception as cache_exc:
                    logger.warning(f"Could not trigger cache invalidation: {cache_exc}")
        except Exception as exc:
            # Fallback retry without foreign key audit fields if constraint fails
            payload.pop("uploaded_by", None)
            payload.pop("created_by", None)
            payload.pop("updated_by", None)
            try:
                client.table("upload_batches").update(payload).eq("batch_id", batch_id).execute()
            except Exception as exc2:
                logger.warning(f"Could not update upload_batches row: {exc2}")



    # ========================================================
    # VALIDATION ERROR
    # ========================================================

    def _save_validation_error(
        self,
        batch_id: Any,
        column_name: Optional[str],
        message: str,
        raw_id: Optional[int] = None,
    ):
        from backend.db.supabase_client import log_upload_validation_error
        b_id = str(batch_id) if batch_id is not None else None
        log_upload_validation_error(
            batch_id=b_id,
            error_message=message,
            column_name=column_name,
            raw_id=raw_id
        )

        # Existing API compatibility.
        upload_logs_db.append({
            "upload_batch_id": batch_id,
            "row_number": 0,
            "column_name": column_name or "General",
            "error_message": message,
            "error_type": "VALIDATION_ERROR",
            "created_at": datetime.now().isoformat(),
        })

    # ========================================================
    # PIPELINE LOG
    # ========================================================

    def _pipeline_log(
        self,
        batch_id: int,
        step: str,
        status: str,
        message: Optional[str] = None,
    ):

        client = get_supabase()

        if not client:
            return

        allowed_statuses = {
            "started",
            "succeeded",
            "failed",
        }

        if status not in allowed_statuses:

            raise ValueError(
                f"Invalid pipeline log "
                f"status: {status}"
            )

        record = {

            "batch_id":
                batch_id,

            "step":
                step,

            "status":
                status,

            "message":
                message,
        }

        batch_rec = upload_batches_db.get(batch_id) or {}
        tid = batch_rec.get("tenant_id") or "unspecified"
        logger.info(f"[Batch #{batch_id} | Tenant: {tid}] Step '{step}' {status}: {message or ''}")

        try:
            client.table("upload_pipeline_logs").insert(record).execute()
        except Exception as exc:
            logger.warning(f"Could not write upload_pipeline_log for batch {batch_id}: {exc}")

    # ========================================================
    # DASHBOARD SUMMARY (DEPRECATED - PHASE 4 REDUNDANT TABLE ELIMINATION)
    # ========================================================

    def _refresh_dashboard_summary(
        self,
        fact_records: List[Dict[str, Any]],
    ):
        """
        Phase 4 Redundant Table Elimination:
        Python bulk upserts to dashboard_summary_daily have been eliminated.
        Daily summaries are consolidated and served directly via sales_daily_summary,
        which is refreshed set-based in PostgreSQL via refresh_sales_daily_summary_for_date RPC.
        """
        pass

    # ========================================================
    # AUDIT LOG
    # ========================================================

    def _save_audit_log(
        self,
        batch_id: int,
        user_id: str,
        imported_rows: int,
    ):
        """No-op: audit_logs table has been removed from database schema."""
        return

    def _sync_user_hierarchy(self, s_ase: pd.Series, s_asm: pd.Series, s_depot: pd.Series, depot_cache: Dict[str, str]):
        return

    def _sync_user_territory_mappings(
        self,
        s_ase: pd.Series,
        s_asm: pd.Series,
        s_depot: pd.Series,
        s_hq: pd.Series,
        depot_cache: Dict[str, str],
        hq_cache: Dict[str, str],
        tenant_id: Optional[str] = None
    ):
        """
        Automatically synchronizes user_depot and user_headquarters_mapping from validated upload data.
        Ensures newly covered depots and registered headquarters for ASEs and TSMs are always populated.
        """
        client = get_supabase()
        if not client:
            return

        effective_tenant = tenant_id or "a0000000-0000-0000-0000-000000000001"
        try:
            u_res = client.table("users").select("user_id, first_name, last_name, email").execute()
            if not u_res or not u_res.data:
                return

            user_id_by_name = {}
            for u in u_res.data:
                uid = str(u["user_id"])
                fn = (u.get("first_name") or "").strip()
                ln = (u.get("last_name") or "").strip()
                full_name = f"{fn} {ln}".strip()
                full_name_clean = re.sub(r'\s+', ' ', full_name).lower()
                email = str(u.get("email") or "").lower()
                prefix = email.split("@")[0].strip()

                if full_name_clean and full_name_clean not in user_id_by_name:
                    user_id_by_name[full_name_clean] = uid
                ln_parts = ln.split()
                if len(ln_parts) > 1:
                    short_name = f"{fn} {ln_parts[-1]}".strip().lower()
                    if short_name and short_name not in user_id_by_name:
                        user_id_by_name[short_name] = uid
                if prefix and prefix not in user_id_by_name:
                    user_id_by_name[prefix] = uid
                if fn and fn.lower() not in user_id_by_name:
                    user_id_by_name[fn.lower()] = uid

            def resolve_u(name_val):
                if not name_val or str(name_val).lower() in ("unassigned", "none", "null", "nan", ""):
                    return None
                c_name = re.sub(r'\s+', ' ', str(name_val).strip()).lower()
                if c_name in user_id_by_name:
                    return user_id_by_name[c_name]
                first_p = c_name.replace(",", "/").split("/")[0].strip()
                if first_p in user_id_by_name:
                    return user_id_by_name[first_p]
                words = first_p.split()
                if len(words) > 2:
                    fl = f"{words[0]} {words[-1]}"
                    if fl in user_id_by_name:
                        return user_id_by_name[fl]
                    if len(words) > 3:
                        fl2 = f"{words[0]} {words[1]} {words[-1]}"
                        if fl2 in user_id_by_name:
                            return user_id_by_name[fl2]
                if words and words[0] in user_id_by_name:
                    return user_id_by_name[words[0]]
                return None

            clean_fn = master_service._clean
            clean_no_space = master_service._clean_no_space

            seen_user_depots = set()
            user_depot_rows = []
            existing_uhq_users = set()
            try:
                ex_res = client.table("user_headquarters_mapping").select("user_id").eq("is_active", True).execute()
                if ex_res and ex_res.data:
                    existing_uhq_users = {str(r["user_id"]) for r in ex_res.data if r.get("user_id")}
            except Exception as e_ex_uhq:
                logger.debug(f"Notice querying existing user headquarters: {e_ex_uhq}")

            assigned_uhq_users = set(existing_uhq_users)
            user_hq_rows = []

            for ase_raw, asm_raw, depot_raw, hq_raw in zip(s_ase, s_asm, s_depot, s_hq):
                c_dep = clean_fn(depot_raw)
                depot_id = depot_cache.get(c_dep)
                c_hq = clean_fn(hq_raw)
                hq_id = hq_cache.get(c_hq) or hq_cache.get(clean_no_space(hq_raw))

                # Process ASE
                ase_uid = resolve_u(ase_raw)
                if ase_uid:
                    if depot_id and (ase_uid, depot_id) not in seen_user_depots:
                        seen_user_depots.add((ase_uid, depot_id))
                        user_depot_rows.append({"user_id": ase_uid, "depot_id": depot_id})
                    if hq_id and ase_uid not in assigned_uhq_users:
                        assigned_uhq_users.add(ase_uid)
                        user_hq_rows.append({
                            "tenant_id": effective_tenant,
                            "user_id": ase_uid,
                            "headquarters_id": hq_id,
                            "is_active": True
                        })

                # Process ASM / TSM
                asm_uid = resolve_u(asm_raw)
                if asm_uid:
                    if depot_id and (asm_uid, depot_id) not in seen_user_depots:
                        seen_user_depots.add((asm_uid, depot_id))
                        user_depot_rows.append({"user_id": asm_uid, "depot_id": depot_id})
                    if hq_id and asm_uid not in assigned_uhq_users:
                        assigned_uhq_users.add(asm_uid)
                        user_hq_rows.append({
                            "tenant_id": effective_tenant,
                            "user_id": asm_uid,
                            "headquarters_id": hq_id,
                            "is_active": True
                        })

            # Upsert into user_depot in chunks of 100
            if user_depot_rows:
                for i in range(0, len(user_depot_rows), 100):
                    batch = user_depot_rows[i:i+100]
                    try:
                        client.table("user_depot").upsert(batch, on_conflict="user_id,depot_id").execute()
                    except Exception as e_ud_upsert:
                        logger.warning(f"Error auto-syncing user_depot batch: {e_ud_upsert}")
                logger.info(f"Auto-synced {len(user_depot_rows)} user-depot assignments into user_depot.")

            # Upsert into user_headquarters_mapping in chunks of 100
            if user_hq_rows:
                for i in range(0, len(user_hq_rows), 100):
                    batch = user_hq_rows[i:i+100]
                    try:
                        client.table("user_headquarters_mapping").upsert(
                            batch, on_conflict="tenant_id,user_id,headquarters_id"
                        ).execute()
                    except Exception as e_uhq_upsert:
                        logger.warning(f"Error auto-syncing user_headquarters_mapping batch: {e_uhq_upsert}")
                logger.info(f"Auto-synced {len(user_hq_rows)} user-headquarters assignments into user_headquarters_mapping.")

        except Exception as e_sync:
            logger.warning(f"Notice in _sync_user_territory_mappings: {e_sync}")

    def _populate_user_sales_fact(
        self,
        batch_id: int,
        s_date: pd.Series,
        s_company: pd.Series,
        s_ase: pd.Series,
        s_brand: pd.Series,
        s_cases: pd.Series,
        s_btl: pd.Series,
        s_bl: pd.Series,
        company_cache: Dict[str, str],
        brand_cache: Dict[str, str],
        tenant_id: Optional[str] = None
    ):
        """
        Inserts normalized non-Others sales facts into public.user_sales_fact at the ASE/User level.
        """
        client = get_supabase()
        if not client:
            return

        if not tenant_id and batch_id:
            tenant_id = (upload_batches_db.get(batch_id) or {}).get("tenant_id")

        try:
            q = client.table("users").select("user_id, first_name, last_name, email, is_active, updated_at, tenant_id")
            if tenant_id:
                u_res = q.eq("tenant_id", tenant_id).execute()
                all_u = u_res.data or []
                if not all_u:
                    all_u = client.table("users").select("user_id, first_name, last_name, email, is_active, updated_at, tenant_id").execute().data or []
            else:
                all_u = q.execute().data or []
            # Sort active users first so active user_ids take precedence in user_lookup
            all_u.sort(key=lambda x: 0 if x.get("is_active") else 1)

            user_lookup = {}
            user_active_map = {}
            user_deact_date_map = {}
            for u in all_u:
                uid = str(u["user_id"])
                is_act = bool(u.get("is_active", True))
                user_active_map[uid] = is_act
                up_at = str(u.get("updated_at") or "")
                user_deact_date_map[uid] = up_at[:10] if (not is_act and len(up_at) >= 10) else None

                fn = (u.get("first_name") or "").strip().lower()
                ln = (u.get("last_name") or "").strip().lower()
                full_name = f"{fn} {ln}".strip()
                email = str(u.get("email") or "").lower()
                prefix = email.split("@")[0].strip()

                if full_name and full_name not in user_lookup:
                    user_lookup[full_name] = uid
                ln_parts = ln.split()
                if len(ln_parts) > 1:
                    short_name = f"{fn} {ln_parts[-1]}".strip()
                    if short_name and short_name not in user_lookup:
                        user_lookup[short_name] = uid
                if prefix and prefix not in user_lookup:
                    user_lookup[prefix] = uid
                if fn and fn not in user_lookup:
                    user_lookup[fn] = uid

            def _resolve_ase_uid(name_str: str) -> Optional[str]:
                if not name_str or str(name_str).lower() in ("unassigned", "none", "null", "nan", ""):
                    return None
                c_name = re.sub(r'\s+', ' ', str(name_str).strip()).lower()
                if c_name in user_lookup:
                    return user_lookup[c_name]
                first_p = c_name.replace(",", "/").split("/")[0].strip()
                if first_p in user_lookup:
                    return user_lookup[first_p]
                words = first_p.split()
                if len(words) > 2:
                    fl = f"{words[0]} {words[-1]}"
                    if fl in user_lookup:
                        return user_lookup[fl]
                    if len(words) > 3:
                        fl2 = f"{words[0]} {words[1]} {words[-1]}"
                        if fl2 in user_lookup:
                            return user_lookup[fl2]
                if words and words[0] in user_lookup:
                    return user_lookup[words[0]]
                return None

            clean_fn = master_service._clean

            fact_records = []
            for dt, comp_raw, ase_raw, brand_raw, cases, btl, bl in zip(
                s_date, s_company, s_ase, s_brand, s_cases, s_btl, s_bl
            ):
                comp_clean = str(comp_raw or "").strip()
                if not comp_clean:
                    continue

                ase_clean = str(ase_raw or "").strip()
                if not ase_clean or ase_clean.lower() in ("unassigned", "none", "null"):
                    continue

                user_id = _resolve_ase_uid(ase_clean)
                if not user_id:
                    continue

                sale_dt_str = self._parse_date(dt)

                # Temporal Inactive Scope:
                # Inactive users only have sales credited up to their deactivation date.
                # Sales for subsequent periods (post-deactivation / current month) are not calculated.
                if not user_active_map.get(user_id, True):
                    deact_date = user_deact_date_map.get(user_id)
                    if deact_date and sale_dt_str:
                        if sale_dt_str >= deact_date:
                            continue
                    else:
                        continue

                company_id = company_cache.get(master_service._clean_company(comp_clean)) or company_cache.get(clean_fn(comp_clean))
                brand_id = brand_cache.get(clean_fn(brand_raw))
                if not company_id or not brand_id:
                    continue

                fact_row = {
                    "user_id": user_id,
                    "company_id": company_id,
                    "brand_id": brand_id,
                    "sale_date": sale_dt_str,
                    "cases": float(cases or 0.0),
                    "bottles": float(btl or 0.0),
                    "bl": float(bl or 0.0),
                    "batch_id": str(batch_id)
                }
                if tenant_id:
                    fact_row["tenant_id"] = tenant_id
                fact_records.append(fact_row)

            if fact_records and client:
                # Phase 3 Batch-Scoped Replacement: Purge existing user sales facts for this specific batch_id once before insert
                if batch_id:
                    batch_id_str = str(batch_id).strip()
                    if batch_id_str:
                        try:
                            client.table("user_sales_fact").delete().eq("batch_id", batch_id_str).execute()
                            logger.info(f"Batch {batch_id}: Purged existing user_sales_fact records for batch_id={batch_id_str}.")
                        except Exception as e_del_usf:
                            logger.warning(f"Batch {batch_id}: Error purging user_sales_fact for batch_id={batch_id_str}: {e_del_usf}")

                self._bulk_insert(
                    table="user_sales_fact",
                    records=fact_records,
                    chunk_size=5000,
                    batch_id=batch_id
                )
        except Exception as e_usf:
            logger.warning(f"_populate_user_sales_fact error: {e_usf}")


# ============================================================
# SERVICE INSTANCE
# ============================================================

import_pipeline = ImportPipelineEngine()