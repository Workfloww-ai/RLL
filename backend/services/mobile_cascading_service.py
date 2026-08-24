import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.db.supabase_client import (
    get_supabase_client,
    fetch_cascading_groups_json_db,
    fetch_group_licensees_json_db,
    fetch_licensee_brand_sales_json_db,
)

logger = logging.getLogger(__name__)

# Fast In-Memory TTL Cache Store
_CACHE_STORE: Dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 60  # 60 seconds


def _get_from_cache(cache_key: str) -> Optional[Any]:
    if cache_key in _CACHE_STORE:
        timestamp, data = _CACHE_STORE[cache_key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return data
        del _CACHE_STORE[cache_key]
    return None


def _set_in_cache(cache_key: str, data: Any):
    _CACHE_STORE[cache_key] = (time.time(), data)


def _get_latest_sale_date(client) -> str:
    """Helper to fetch the latest available sale date dynamically from sales_fact."""
    try:
        res = client.table("sales_fact").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0 and res.data[0].get("sale_date"):
            return str(res.data[0].get("sale_date"))
    except Exception as e:
        logger.warning(f"Error fetching latest sale date: {e}")
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_multi_period_dates(
    client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> tuple[str, str, str]:
    """Resolves target_date, mtd_start, and ytd_start dates for single-pass multi-period queries."""
    target_date_str = date_to or date_from or _get_latest_sale_date(client)

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        latest = _get_latest_sale_date(client)
        dt = datetime.strptime(latest, "%Y-%m-%d")
        target_date_str = latest

    if date_from and date_from.strip():
        mtd_start = date_from.strip()
    else:
        mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"

    fy_year = dt.year if dt.month >= 4 else dt.year - 1
    ytd_start = f"{fy_year:04d}-04-01"

    return target_date_str, mtd_start, ytd_start



def _map_period_metrics(records: List[Dict[str, Any]], selected_period: Optional[str]) -> List[Dict[str, Any]]:
    """Dynamically maps active period metric (Daily, MTD, YTD) into total_cases and total_bottles."""
    raw_p = (selected_period or "MTD").strip().upper()
    if raw_p == "DAILY":
        p_key = "daily"
    elif raw_p == "YTD":
        p_key = "ytd"
    else:
        p_key = "mtd"

    mapped = []
    for r in records:
        cases_key = f"{p_key}_cases"
        bottles_key = f"{p_key}_bottles"

        # Read the period-specific value directly — no fallback to other periods.
        # Falling back to total_cases (which is aliased to MTD in SQL) would show
        # wrong data when the selected period has genuine zero sales.
        try:
            cases_val = float(r.get(cases_key) or 0.0)
        except (ValueError, TypeError):
            cases_val = 0.0

        try:
            bottles_val = float(r.get(bottles_key) or 0.0)
        except (ValueError, TypeError):
            bottles_val = 0.0

        r_copy = dict(r)
        r_copy["total_cases"] = round(cases_val, 2)
        r_copy["total_bottles"] = round(bottles_val, 2)
        mapped.append(r_copy)

    mapped.sort(key=lambda x: (x.get("total_cases", 0.0), x.get("total_licensees", 0)), reverse=True)
    return mapped


def get_cascading_groups(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"groups_json_{target_date}_{period or 'MTD'}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        raw_groups = fetch_cascading_groups_json_db(
            target_date=target_date,
            mtd_start=mtd_start,
            ytd_start=ytd_start
        )
        res = _map_period_metrics(raw_groups, period)
        _set_in_cache(cache_key, res)
        return res
    except Exception as e:
        logger.error(f"Error in get_cascading_groups: {e}", exc_info=True)
        return []


def get_group_licensees(
    group_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"group_lics_json_{group_id}_{target_date}_{period or 'MTD'}_{depot_name or ''}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        raw_lics = fetch_group_licensees_json_db(
            group_id=group_id,
            target_date=target_date,
            mtd_start=mtd_start,
            ytd_start=ytd_start,
            depot_name=depot_name
        )
        res = _map_period_metrics(raw_lics, period)
        _set_in_cache(cache_key, res)
        return res
    except Exception as e:
        logger.error(f"Error in get_group_licensees: {e}", exc_info=True)
        return []


def get_licensee_brand_sales(
    licensee_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"lic_brands_json_{licensee_id}_{target_date}_{period or 'MTD'}_{depot_name or ''}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        raw_brands = fetch_licensee_brand_sales_json_db(
            licensee_id=licensee_id,
            target_date=target_date,
            mtd_start=mtd_start,
            ytd_start=ytd_start,
            depot_name=depot_name
        )
        res = _map_period_metrics(raw_brands, period)
        _set_in_cache(cache_key, res)
        return res
    except Exception as e:
        logger.error(f"Error in get_licensee_brand_sales: {e}", exc_info=True)
        return []
