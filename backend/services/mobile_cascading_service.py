import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.db.supabase_client import (
    get_supabase_client,
    fetch_cascading_groups_db,
    fetch_group_licensees_db,
    fetch_licensee_brand_sales_db,
)

logger = logging.getLogger(__name__)

# Fast In-Memory TTL Cache Store
_CACHE_STORE: Dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


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


def _resolve_period_dates(
    client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> tuple[str, str]:
    if date_from and date_to:
        return date_from, date_to

    target_date_str = date_to or date_from or _get_latest_sale_date(client)

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        latest = _get_latest_sale_date(client)
        dt = datetime.strptime(latest, "%Y-%m-%d")
        target_date_str = latest

    if period == "Daily":
        return target_date_str, target_date_str
    elif period == "MTD":
        mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"
        return mtd_start, target_date_str
    elif period == "YTD":
        fy_year = dt.year if dt.month >= 4 else dt.year - 1
        fy_start = f"{fy_year:04d}-04-01"
        return fy_start, target_date_str

    return date_from or target_date_str, date_to or target_date_str


def get_cascading_groups(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        cache_key = f"groups_{d_from}_{d_to}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        res = fetch_cascading_groups_db(date_from=d_from, date_to=d_to)
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
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        cache_key = f"group_lics_{group_id}_{d_from}_{d_to}_{depot_name or ''}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        res = fetch_group_licensees_db(
            group_id=group_id,
            date_from=d_from,
            date_to=d_to,
            depot_name=depot_name
        )
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
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        cache_key = f"lic_brands_{licensee_id}_{d_from}_{d_to}_{depot_name or ''}"
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        res = fetch_licensee_brand_sales_db(
            licensee_id=licensee_id,
            date_from=d_from,
            date_to=d_to,
            depot_name=depot_name
        )
        _set_in_cache(cache_key, res)
        return res
    except Exception as e:
        logger.error(f"Error in get_licensee_brand_sales: {e}", exc_info=True)
        return []

