import logging
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from supabase import create_client, Client
from backend.core.config import settings
logger = logging.getLogger("supabase_client")
_client: Optional[Client] = None
def get_supabase_client() -> Optional[Client]:
    """Returns a singleton Supabase Client instance."""
    global _client
    if _client is not None:
        return _client
    url = settings.SUPABASE_URL
    key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", getattr(settings, "SUPABASE_ANON_KEY", getattr(settings, "SUPABASE_KEY", "")))
    if not url or not key:
        logger.warning(
            "SUPABASE_URL or SUPABASE key is missing. "
            "Supabase operations will be skipped (mock mode)."
        )
        return None
    try:
        _client = create_client(url, key)
        logger.info("Supabase client connected successfully.")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None
# ---------------------------------------------------------------------------
# Upload Batch Helpers
# ---------------------------------------------------------------------------
def create_upload_batch(
    source_file: str,
    load_type: str,
    covers_start: str,
    covers_end: str,
    uploaded_by: Optional[str] = None,
    created_by: Optional[str] = None,
    browser_info: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Optional[int]:
    """Creates a new upload_batches row and returns the generated batch_id."""
    """Creates a new upload_batches row with user FKs and client browser/IP metadata."""
    client = get_supabase_client()
    if not client:
        logger.info("[Mock] create_upload_batch → batch_id=1")
        return 1
    data: Dict[str, Any] = {
        "source_file": source_file,
        "load_type": load_type,
        "covers_start": covers_start,
        "covers_end": covers_end,
        "status": "pending",
        "is_active": True,
    }
    if uploaded_by:
        data["uploaded_by"] = uploaded_by
    user_fk = uploaded_by or created_by
    if user_fk:
        data["uploaded_by"] = user_fk
        data["created_by"] = user_fk
        data["updated_by"] = user_fk
    if browser_info:
        data["browser_info"] = browser_info
    if client_ip:
        data["client_ip"] = client_ip
    try:
        res = client.table("upload_batches").insert(data).execute()
        if res.data:
            return res.data[0]["batch_id"]
            batch_id = res.data[0]["batch_id"]
            try:
                client.table("audit_logs").insert({
                    "table_name": "upload_batches",
                    "record_id": str(batch_id),
                    "action": "UPLOAD_BATCH_CREATED",
                    "new_data": data,
                    "changed_by": user_fk,
                }).execute()
            except Exception as e:
                logger.warning(f"Audit log failed for batch creation: {e}")
            return batch_id
    except Exception as e:
        logger.error(f"create_upload_batch error: {e}")
        raise
    return None
def update_upload_batch(batch_id: int, status: str, row_count: Optional[int] = None) -> bool:
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] update_upload_batch batch_id={batch_id} status={status}")
        return True
    data: Dict[str, Any] = {"status": status}
    if row_count is not None:
        data["row_count"] = row_count
    try:
        client.table("upload_batches").update(data).eq("batch_id", batch_id).execute()
        return True
    except Exception as e:
        logger.error(f"update_upload_batch error: {e}")
        return False
def log_pipeline_step(batch_id: int, step: str, status: str, message: Optional[str] = None):
    """Inserts a row into upload_pipeline_logs silently without crashing ETL on log failure."""
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock Log] {step} → {status}: {message}")
        return
    try:
        client.table("upload_pipeline_logs").insert({
            "batch_id": batch_id, "step": step, "status": status, "message": message
        }).execute()
    except Exception as e:
        logger.warning(f"log_pipeline_step error for batch_id={batch_id}: {e}")
def log_validation_errors(errors: List[Dict[str, Any]]):
    """Bulk-inserts validation errors in batches of 500."""
    if not errors:
        return
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] log_validation_errors count={len(errors)}")
        return
    try:
        for i in range(0, len(errors), 500):
            client.table("upload_validation_errors").insert(errors[i:i + 500]).execute()
    except Exception as e:
        logger.error(f"log_validation_errors error: {e}")
def bulk_insert_raw_sales(records: List[Dict[str, Any]]) -> bool:
    """Bulk-inserts cleaned rows into raw_sales_upload in optimized batches."""
    if not records:
        return True
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] bulk_insert_raw_sales count={len(records)}")
        return True
    try:
        # Sub-chunk in batches of 5000 to avoid PostgREST payload limits
        for i in range(0, len(records), 5000):
            client.table("raw_sales_upload").insert(records[i:i + 5000]).execute()
        return True
    except Exception as e:
        logger.error(f"bulk_insert_raw_sales error: {e}")
        raise
def execute_in_db_resolution(batch_id: int) -> Optional[Dict[str, Any]]:
    """Calls stored procedure process_upload_batch_in_db for fast server-side set-based resolution."""
    client = get_supabase_client()
    if not client:
        return None
    try:
        res = client.rpc("process_upload_batch_in_db", {"p_batch_id": batch_id}).execute()
        return res.data
    except Exception as e:
        logger.warning(f"execute_in_db_resolution RPC failed, falling back to python resolution: {e}")
        return None
# ---------------------------------------------------------------------------
# Master Table Upsert Helpers
# Each returns a dict {name_str: id} for the resolved rows.
# ---------------------------------------------------------------------------
def _batch_upsert(client: Client, table: str, rows: List[Dict[str, Any]], on_conflict: str, chunk_size: int = 500):
    for i in range(0, len(rows), chunk_size):
        client.table(table).upsert(rows[i:i + chunk_size], on_conflict=on_conflict).execute()
def _batch_select_in(client: Client, table: str, select_cols: str, name_col: str, names: List[str], chunk_size: int = 250) -> List[Dict[str, Any]]:
    result = []
    for i in range(0, len(names), chunk_size):
        chunk_names = names[i:i + chunk_size]
        res = client.table(table).select(select_cols).in_(name_col, chunk_names).execute()
        if res.data:
            result.extend(res.data)
    return result
def _upsert_simple(
    table: str,
    name_col: str,
    id_col: str,
    names: List[str],
) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] upsert {table} names={names}")
        return {n: idx + 1 for idx, n in enumerate(names)}
    if not names:
        return {}
    rows = [{"name": n, "is_active": True} for n in names]
    try:
        _batch_upsert(client, table, rows, on_conflict="name")
        fetched = _batch_select_in(client, table, f"{id_col},{name_col}", name_col, names)
        return {r[name_col]: r[id_col] for r in fetched}
    except Exception as e:
        logger.error(f"upsert {table} error: {e}")
        raise
def upsert_headquarters(names: List[str]) -> Dict[str, int]:
    return _upsert_simple("headquarters", "name", "headquarters_id", names)
def upsert_offices(names: List[str]) -> Dict[str, int]:
    return _upsert_simple("offices", "name", "office_id", names)
def upsert_circles(names: List[str]) -> Dict[str, int]:
    return _upsert_simple("circles", "name", "circle_id", names)
def upsert_companies(names: List[str]) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        return {n: idx + 1 for idx, n in enumerate(names)}
    if not names:
        return {}
    rows = [{"company_name": n, "is_active": True} for n in names]
    try:
        _batch_upsert(client, "companies", rows, on_conflict="company_name")
        fetched = _batch_select_in(client, "companies", "company_id,company_name", "company_name", names)
        return {r["company_name"]: r["company_id"] for r in fetched}
    except Exception as e:
        logger.error(f"upsert companies error: {e}")
        raise
def upsert_brands(names: List[str]) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        return {n: idx + 1 for idx, n in enumerate(names)}
    if not names:
        return {}
    rows = [{"brand_name": n, "is_active": True} for n in names]
    try:
        _batch_upsert(client, "brands", rows, on_conflict="brand_name")
        fetched = _batch_select_in(client, "brands", "brand_id,brand_name", "brand_name", names)
        return {r["brand_name"]: r["brand_id"] for r in fetched}
    except Exception as e:
        logger.error(f"upsert brands error: {e}")
        raise
def upsert_packagings(packing_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        return {r["packing_raw"]: idx + 1 for idx, r in enumerate(packing_rows)}
    if not packing_rows:
        return {}
    rows = [
        {
            "packing_raw": r["packing_raw"],
            "bottle_size_ml": r.get("bottle_size_ml") or 0.0,
            "is_active": True,
        }
        for r in packing_rows
    ]
    raw_names = [r["packing_raw"] for r in packing_rows]
    try:
        _batch_upsert(client, "packagings", rows, on_conflict="packing_raw")
        fetched = _batch_select_in(client, "packagings", "packaging_id,packing_raw", "packing_raw", raw_names)
        return {r["packing_raw"]: r["packaging_id"] for r in fetched}
    except Exception as e:
        logger.error(f"upsert packagings error: {e}")
        raise
def upsert_depots(depot_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        return {r["name"]: idx + 1 for idx, r in enumerate(depot_rows)}
    if not depot_rows:
        return {}
    rows = [{**r, "is_active": True} for r in depot_rows]
    names = [r["name"] for r in depot_rows]
    try:
        _batch_upsert(client, "depots", rows, on_conflict="name")
        fetched = _batch_select_in(client, "depots", "depot_id,name", "name", names)
        return {r["name"]: r["depot_id"] for r in fetched}
    except Exception as e:
        logger.error(f"upsert depots error: {e}")
        raise
def upsert_licensees(licensee_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    client = get_supabase_client()
    if not client:
        return {r["licensee_name"]: idx + 1 for idx, r in enumerate(licensee_rows)}
    if not licensee_rows:
        return {}
    rows = [{**r, "is_active": True} for r in licensee_rows]
    names = [r["licensee_name"] for r in licensee_rows]
    try:
        _batch_upsert(client, "licensees", rows, on_conflict="licensee_name")
        fetched = _batch_select_in(client, "licensees", "licensee_id,licensee_name", "licensee_name", names)
        return {r["licensee_name"]: r["licensee_id"] for r in fetched}
    except Exception as e:
        logger.error(f"upsert licensees error: {e}")
        raise
# ---------------------------------------------------------------------------
# Sales Fact Helpers
# ---------------------------------------------------------------------------
def ensure_calendar_dates(dates: List[str]) -> bool:
    """Ensures dim_calendar contains rows for the supplied sale dates."""
    normalized_dates = sorted({str(d).strip() for d in dates if str(d).strip()})
    if not normalized_dates:
        return True
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] ensure_calendar_dates count={len(normalized_dates)}")
        return True
    try:
        from datetime import datetime
        rows = []
        for d in normalized_dates:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                m = dt.month
                y = dt.year
                fy_start = y if m >= 4 else y - 1
                fy_label = f"{fy_start}-{str(fy_start + 1)[-2:]}"
                fy_month = (m - 3) if m >= 4 else (m + 9)

                rows.append({
                    "date_id": d,
                    "year": y,
                    "quarter": (m - 1) // 3 + 1,
                    "month": m,
                    "month_name": dt.strftime("%B"),
                    "day": dt.day,
                    "day_of_week": dt.isoweekday(),
                    "day_name": dt.strftime("%A"),
                    "is_weekend": dt.isoweekday() in (6, 7),
                    "financial_year_start": fy_start,
                    "financial_year_label": fy_label,
                    "financial_month": fy_month,
                    "is_active": True,
                })
            except Exception:
                continue
        if rows:
            client.table("dim_calendar").upsert(rows, on_conflict="date_id").execute()
        return True
    except Exception as e:
        logger.warning(f"ensure_calendar_dates error (non-fatal): {e}")
        return False
def bulk_insert_sales_fact(records: List[Dict[str, Any]]) -> bool:
    """Bulk-inserts resolved rows into sales_fact."""
    if not records:
        return True
    sale_dates = [
        str(r.get("sale_date", "") or "").strip()
        for r in records
        if str(r.get("sale_date", "") or "").strip()
    ]
    ensure_calendar_dates(sale_dates)
    client = get_supabase_client()
    if not client:
        logger.info(f"[Mock] bulk_insert_sales_fact count={len(records)}")
        return True
    try:
        for i in range(0, len(records), 2500):
            client.table("sales_fact").insert(records[i:i + 2500]).execute()
        return True
    except Exception as e:
        logger.error(f"bulk_insert_sales_fact error: {e}")
        raise
def get_raw_sales_for_batch(batch_id: int, page: int = 0, page_size: int = 5000) -> List[Dict[str, Any]]:
    """
    Fetches a page of raw_sales_upload rows for a given batch_id.
    Returns empty list when page is beyond the data.
    """
    client = get_supabase_client()
    if not client:
        return []
    try:
        start = page * page_size
        res = (
            client.table("raw_sales_upload")
            .select("raw_id, batch_id, sale_date_raw, company_raw, licensee_raw, trade_raw, group_name_raw, hq_raw, deo_office_raw, circle_office_raw, depot_raw, ase_raw, asm_tsm_raw, brand_name_raw, packing_raw, total_case, total_btl, total_bl")
            .eq("batch_id", batch_id)
            .range(start, start + page_size - 1)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"get_raw_sales_for_batch error: {e}")
        return []
# ---------------------------------------------------------------------------
# Status Reporting
# ---------------------------------------------------------------------------
def get_batch_details(batch_id: Any) -> Dict[str, Any]:
    """Fetches batch info, pipeline logs, and error count for status reporting."""
    client = get_supabase_client()
    if not client:
        return {
            "batch_id": batch_id,
            "status": "loaded (mock)",
            "row_count": None,
            "logs": [],
            "error_count": 0,
        }
    try:
        batch_res = client.table("upload_batches").select("batch_id, source_file, file_name, storage_path, status, upload_status, row_count, total_rows, imported_rows, remarks, created_at").eq("batch_id", batch_id).execute()
        logs_res = (
            client.table("upload_pipeline_logs")
            .select("log_id, batch_id, step, status, message, logged_at")
            .eq("batch_id", batch_id)
            .order("log_id")
            .execute()
        )
        err_res = (
            client.table("upload_validation_errors")
            .select("error_id", count="exact")
            .eq("batch_id", batch_id)
            .execute()
        )
        batch_info = batch_res.data[0] if batch_res.data else {}
        return {
            "batch_id": batch_id,
            "source_file": batch_info.get("source_file"),
            "status": batch_info.get("status"),
            "row_count": batch_info.get("row_count"),
            "created_at": batch_info.get("created_at"),
            "logs": logs_res.data or [],
            "error_count": err_res.count if err_res.count is not None else len(err_res.data or []),
        }
    except Exception as e:
        logger.error(f"get_batch_details error: {e}")
        return {"batch_id": batch_id, "error": str(e)}