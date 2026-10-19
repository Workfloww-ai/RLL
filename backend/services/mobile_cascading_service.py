import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.db.supabase_client import (
    get_supabase_client,
    fetch_cascading_groups_json_db,
    fetch_group_brand_sales_json_db,
    fetch_group_licensees_json_db,
    fetch_licensee_brand_sales_json_db,
)
from backend.services.cache_service import get_json_cache, set_json_cache

logger = logging.getLogger(__name__)

# Fast In-Memory TTL Cache Store (Fallback)
_CACHE_STORE: Dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

# Single-Flight Stampede Lock per cache key
_CASCADING_LOCKS: Dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()

_LATEST_DATE_CACHE: Optional[str] = None
_LATEST_DATE_CACHE_TIME: float = 0.0

async def _get_stampede_lock(key: str) -> asyncio.Lock:
    async with _LOCKS_GUARD:
        if key not in _CASCADING_LOCKS:
            _CASCADING_LOCKS[key] = asyncio.Lock()
        return _CASCADING_LOCKS[key]


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
    """Helper to fetch the latest available sale date dynamically with 5-minute caching."""
    global _LATEST_DATE_CACHE, _LATEST_DATE_CACHE_TIME
    now = time.time()
    if _LATEST_DATE_CACHE and (now - _LATEST_DATE_CACHE_TIME) < 300.0:
        return _LATEST_DATE_CACHE

    try:
        res = client.table("sales_daily_summary").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0 and res.data[0].get("sale_date"):
            _LATEST_DATE_CACHE = str(res.data[0].get("sale_date"))
            _LATEST_DATE_CACHE_TIME = now
            return _LATEST_DATE_CACHE
    except Exception as e:
        logger.warning(f"Error fetching latest sale date: {e}")
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_multi_period_dates(
    client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> tuple[str, str, str]:
    """
    Resolves target_date, mtd_start, and ytd_start dates for single-pass multi-period queries.
    MTD start is ALWAYS the 1st day of the target month.
    YTD start is ALWAYS April 1 of the target financial year.
    """
    target_date_str = date_to or date_from or _get_latest_sale_date(client)

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        latest = _get_latest_sale_date(client)
        dt = datetime.strptime(latest, "%Y-%m-%d")
        target_date_str = latest

    # MTD start is strictly 1st day of target month
    mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"

    # YTD start is strictly April 1 of target financial year
    fy_year = dt.year if dt.month >= 4 else dt.year - 1
    ytd_start = f"{fy_year:04d}-04-01"

    return target_date_str, mtd_start, ytd_start


def _map_period_metrics(records: List[Dict[str, Any]], selected_period: Optional[str]) -> List[Dict[str, Any]]:
    """Dynamically maps active period metric (Daily, MTD, YTD) into total_cases, total_bottles, total_licensees, and total_brands."""
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
        lic_key = f"{p_key}_licensees"
        brand_key = f"{p_key}_brands"

        try:
            cases_val = float(r.get(cases_key) or 0.0)
        except (ValueError, TypeError):
            cases_val = 0.0

        try:
            bottles_val = float(r.get(bottles_key) or 0.0)
        except (ValueError, TypeError):
            bottles_val = 0.0

        lic_val = r.get(lic_key)
        if lic_val is None:
            lic_val = r.get("total_licensees") or 0

        brand_val = r.get(brand_key)
        if brand_val is None:
            brand_val = r.get("total_brands") or 0

        r_copy = dict(r)
        r_copy["total_cases"] = round(cases_val, 2)
        r_copy["total_bottles"] = round(bottles_val, 2)
        r_copy["total_licensees"] = int(lic_val)
        r_copy["total_brands"] = int(brand_val)
        mapped.append(r_copy)

    mapped.sort(key=lambda x: (x.get("total_cases", 0.0), x.get("total_licensees", 0)), reverse=True)
    return mapped


async def get_cascading_groups(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    selected_hq: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"groups_json_{target_date}_{period or 'MTD'}_{selected_hq or 'All'}"

        # 1. Fast Redis Lookup
        redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
        if redis_cached is not None:
            return redis_cached

        # 2. In-Memory Cache Lookup
        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        # 3. Single-Flight Lock for Stampede Protection
        lock = await _get_stampede_lock(cache_key)
        async with lock:
            # Re-check cache inside lock
            redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
            if redis_cached is not None:
                return redis_cached
            cached = _get_from_cache(cache_key)
            if cached is not None:
                return cached

            raw_groups = await asyncio.to_thread(
                fetch_cascading_groups_json_db,
                target_date=target_date,
                mtd_start=mtd_start,
                ytd_start=ytd_start,
                hq_name=selected_hq
            )
            res = _map_period_metrics(raw_groups, period)
            _set_in_cache(cache_key, res)
            await set_json_cache(f"rll:cascading:{cache_key}", res, ttl=300)
            return res
    except Exception as e:
        logger.error(f"Error in get_cascading_groups: {e}", exc_info=True)
        return []


async def get_group_brand_sales(
    group_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None,
    selected_hq: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    hq = selected_hq or depot_name
    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"group_brands_json_{group_id}_{target_date}_{period or 'MTD'}_{hq or ''}"

        redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
        if redis_cached is not None:
            return redis_cached

        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        lock = await _get_stampede_lock(cache_key)
        async with lock:
            redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
            if redis_cached is not None:
                return redis_cached
            cached = _get_from_cache(cache_key)
            if cached is not None:
                return cached

            raw_brands = await asyncio.to_thread(
                fetch_group_brand_sales_json_db,
                group_id=group_id,
                target_date=target_date,
                mtd_start=mtd_start,
                ytd_start=ytd_start,
                depot_name=hq
            )
            res = _map_period_metrics(raw_brands, period)
            _set_in_cache(cache_key, res)
            await set_json_cache(f"rll:cascading:{cache_key}", res, ttl=300)
            return res
    except Exception as e:
        logger.error(f"Error in get_group_brand_sales: {e}", exc_info=True)
        return []


async def get_group_licensees(
    group_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None,
    selected_hq: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    hq = selected_hq or depot_name
    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"group_lics_json_{group_id}_{target_date}_{period or 'MTD'}_{hq or ''}"

        redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
        if redis_cached is not None:
            return redis_cached

        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        lock = await _get_stampede_lock(cache_key)
        async with lock:
            redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
            if redis_cached is not None:
                return redis_cached
            cached = _get_from_cache(cache_key)
            if cached is not None:
                return cached

            raw_lics = await asyncio.to_thread(
                fetch_group_licensees_json_db,
                group_id=group_id,
                target_date=target_date,
                mtd_start=mtd_start,
                ytd_start=ytd_start,
                depot_name=hq
            )
            res = _map_period_metrics(raw_lics, period)
            _set_in_cache(cache_key, res)
            await set_json_cache(f"rll:cascading:{cache_key}", res, ttl=300)
            return res
    except Exception as e:
        logger.error(f"Error in get_group_licensees: {e}", exc_info=True)
        return []


async def get_licensee_brand_sales(
    licensee_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None,
    selected_hq: Optional[str] = None
) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []

    hq = selected_hq or depot_name
    try:
        target_date, mtd_start, ytd_start = _resolve_multi_period_dates(client, date_from, date_to, period)
        cache_key = f"licensee_brands_json_{licensee_id}_{target_date}_{period or 'MTD'}_{hq or ''}"

        redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
        if redis_cached is not None:
            return redis_cached

        cached = _get_from_cache(cache_key)
        if cached is not None:
            return cached

        lock = await _get_stampede_lock(cache_key)
        async with lock:
            redis_cached = await get_json_cache(f"rll:cascading:{cache_key}")
            if redis_cached is not None:
                return redis_cached
            cached = _get_from_cache(cache_key)
            if cached is not None:
                return cached

            raw_brands = await asyncio.to_thread(
                fetch_licensee_brand_sales_json_db,
                licensee_id=licensee_id,
                target_date=target_date,
                mtd_start=mtd_start,
                ytd_start=ytd_start,
                depot_name=hq
            )
            res = _map_period_metrics(raw_brands, period)
            _set_in_cache(cache_key, res)
            await set_json_cache(f"rll:cascading:{cache_key}", res, ttl=300)
            return res
    except Exception as e:
        logger.error(f"Error in get_licensee_brand_sales: {e}", exc_info=True)
        return []

