import time
import json
import asyncio
import hashlib
import functools
import logging
from typing import Any, Callable, Optional, Dict
from fastapi import Response, Request

from backend.db.redis_client import (
    safe_get,
    safe_set,
    safe_delete,
    safe_delete_pattern,
    is_redis_available
)
from backend.core.config import settings

logger = logging.getLogger("cache_service")


def build_cache_key(prefix: str, identifier: str = "", params: Optional[Dict[str, Any]] = None) -> str:
    """
    Construct a deterministic Redis key with prefix and hashed parameter query string.
    Example: 'rll:analytics:brand-performance:a1b2c3d4'
    """
    key_parts = ["rll", prefix]
    if identifier:
        key_parts.append(identifier)
    
    if params:
        # Sort keys to ensure consistent hash representation
        sorted_str = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(sorted_str.encode("utf-8")).hexdigest()[:12]
        key_parts.append(param_hash)
        
    return ":".join(key_parts)


_L1_MEMORY_CACHE: Dict[str, tuple] = {}
_L1_DEFAULT_TTL = 300.0  # 5 minutes


async def get_json_cache(key: str) -> Optional[Any]:
    """
    Two-Tier Fast Edge Cache:
    1. Reads from L1 In-Memory Cache (sub-0.1ms latency).
    2. Falls back to L2 Redis Cloud (sub-5ms in-VPC latency) and warms L1.
    """
    now = time.time()
    if key in _L1_MEMORY_CACHE:
        ts, val = _L1_MEMORY_CACHE[key]
        if now - ts < _L1_DEFAULT_TTL:
            return val
        _L1_MEMORY_CACHE.pop(key, None)

    raw_val = await safe_get(key)
    if not raw_val:
        return None
    try:
        val = json.loads(raw_val)
        _L1_MEMORY_CACHE[key] = (now, val)
        return val
    except Exception as e:
        logger.warning(f"Failed to parse cached JSON for key '{key}': {e}")
        return None


async def set_json_cache(key: str, data: Any, ttl: Optional[int] = None) -> bool:
    """Serialize and store JSON value in L1 In-Memory and L2 Redis with specified TTL."""
    _L1_MEMORY_CACHE[key] = (time.time(), data)
    try:
        serialized = json.dumps(data, default=str)
        return await safe_set(key, serialized, ttl=ttl)
    except Exception as e:
        logger.warning(f"Failed to serialize data for cache set on key '{key}': {e}")
        return False


async def delete_cache(key: str) -> bool:
    """Delete a specific cache key from both L1 memory and L2 Redis."""
    _L1_MEMORY_CACHE.pop(key, None)
    return await safe_delete(key)


async def invalidate_analytics_cache() -> int:
    """
    Invalidate all analytics, dashboard, and mobile cache keys across the platform.
    Called automatically upon new Excel file uploads to prevent serving stale data.
    """
    _L1_MEMORY_CACHE.clear()
    analytics_count = await safe_delete_pattern("rll:analytics:*")
    dashboard_count = await safe_delete_pattern("rll:dashboard:*")
    mobile_count = await safe_delete_pattern("rll:mobile:*")
    total_purged = analytics_count + dashboard_count + mobile_count
    
    # Also invalidate in-memory mobile sales cache
    try:
        from backend.mobile.router import clear_sales_response_cache
        clear_sales_response_cache()
    except Exception as e:
        logger.warning(f"Notice clearing in-memory mobile sales cache: {e}")

    logger.info(f"Invalidated {total_purged} cached analytics, dashboard & mobile entries.")
    return total_purged


def invalidate_analytics_cache_sync() -> int:
    """Synchronous wrapper for invalidate_analytics_cache to use in background sync tasks."""
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.create_task(invalidate_analytics_cache())
            return 1
        else:
            return loop.run_until_complete(invalidate_analytics_cache())
    except Exception as e:
        logger.warning(f"Error executing sync cache invalidation: {e}")
        return 0


async def prewarm_cache_egress(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Phase 5 Post-Ingestion Redis Edge Pre-Warming:
    Calculates and populates top Redis keys:
    - rll:analytics:overview:*
    - rll:mobile:companies:*
    - rll:mobile:groups:*
    - rll:mobile:sales:*
    Ensures the very next mobile/web request is served from Redis in < 5ms.
    """
    results: Dict[str, Any] = {
        "mobile_companies": 0,
        "mobile_groups": 0,
        "analytics_overview": 0,
        "target_date": target_date
    }

    # Resolve target date if not provided
    resolved_date = target_date
    if not resolved_date:
        try:
            from backend.db.client import get_supabase
            client = get_supabase()
            if client:
                max_res = client.table("sales_daily_summary").select("sale_date").order("sale_date", desc=True).limit(1).execute()
                if max_res.data and max_res.data[0].get("sale_date"):
                    resolved_date = str(max_res.data[0]["sale_date"])
        except Exception as e_dt:
            logger.warning(f"prewarm_cache_egress: could not resolve latest sale date: {e_dt}")

    if not resolved_date:
        from datetime import datetime
        resolved_date = datetime.utcnow().strftime("%Y-%m-%d")

    results["target_date"] = resolved_date

    # 1. Pre-warm mobile companies (rll:mobile:companies:*)
    try:
        from backend.services.mobile_companies_service import get_companies_summary
        periods = ["Daily", "MTD", "YTD"]
        comp_count = 0
        for p in periods:
            comp_list, r_date, timing = get_companies_summary(
                period=p,
                date_to=resolved_date,
                selected_hq="All Headquarters"
            )
            if comp_list:
                payload = {
                    "status": "success",
                    "period": p,
                    "count": len(comp_list),
                    "latest_sale_date": r_date or resolved_date,
                    "companies": comp_list,
                    "cache_status": "HIT",
                    "process_time_ms": timing.get("total_service_ms", 1.0),
                    "db_time_ms": 0.0,
                    "mount_time_ms": 0.0,
                    "python_time_ms": 0.0
                }
                # Pre-warm resolved date and 'latest' aliases with both capitalized and lower periods
                for p_var in [p, p.lower()]:
                    for d_var in [resolved_date, "latest"]:
                        r_key = f"rll:mobile:companies:{p_var}:All Headquarters:{d_var}:all"
                        await set_json_cache(r_key, payload, ttl=900)
                comp_count += 1
        results["mobile_companies"] = comp_count
    except Exception as e_comp:
        logger.warning(f"prewarm_cache_egress mobile companies notice: {e_comp}")

    # 2. Pre-warm mobile cascading groups (rll:mobile:groups:*)
    try:
        from backend.services.mobile_cascading_service import get_cascading_groups
        groups_count = 0
        for p in ["Daily", "MTD", "YTD"]:
            groups_res = get_cascading_groups(
                date_to=resolved_date,
                period=p,
                selected_hq="All Headquarters"
            )
            if groups_res:
                for p_var in [p, p.lower()]:
                    for d_var in [resolved_date, "latest"]:
                        for hq_var in ["All Headquarters", "All"]:
                            g_key = f"rll:mobile:groups:{d_var}:{p_var}:{hq_var}"
                            await set_json_cache(g_key, groups_res, ttl=900)
                groups_count += 1
        results["mobile_groups"] = groups_count
    except Exception as e_grp:
        logger.warning(f"prewarm_cache_egress mobile groups notice: {e_grp}")

    # 3. Pre-warm analytics dashboard overview (rll:analytics:overview:*)
    try:
        from backend.analytics.service import analytics_service
        ov_count = 0
        for p in ["daily", "mtd", "ytd"]:
            try:
                overview_data = analytics_service.get_dashboard(period=p, to_date=resolved_date)
                if overview_data:
                    # Model dump or dict
                    ov_dict = overview_data.model_dump() if hasattr(overview_data, "model_dump") else overview_data
                    await set_json_cache(f"rll:analytics:overview:{p}:{resolved_date}", ov_dict, ttl=600)
                    await set_json_cache(f"rll:analytics:overview:{p}:latest", ov_dict, ttl=600)
                    ov_count += 1
            except Exception as e_ov_sub:
                logger.debug(f"prewarm overview sub error for {p}: {e_ov_sub}")
        results["analytics_overview"] = ov_count
    except Exception as e_ov:
        logger.warning(f"prewarm_cache_egress analytics overview notice: {e_ov}")

    # 4. Pre-warm mobile sales canonical cache responses
    try:
        from backend.services.mobile_sales_service import prewarm_mobile_sales
        m_res = prewarm_mobile_sales()
        results["mobile_sales"] = m_res
    except Exception as e_m:
        logger.warning(f"prewarm_cache_egress mobile sales notice: {e_m}")

    logger.info(f"Phase 5 Edge Cache Pre-Warming completed successfully: {results}")
    return results


def prewarm_cache_egress_sync(target_date: Optional[str] = None) -> Dict[str, Any]:
    """Synchronous wrapper for prewarm_cache_egress to call after ingestion summary generation."""
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.create_task(prewarm_cache_egress(target_date=target_date))
            return {"status": "task_scheduled", "target_date": target_date}
        else:
            return loop.run_until_complete(prewarm_cache_egress(target_date=target_date))
    except Exception as e:
        logger.warning(f"Error executing prewarm_cache_egress_sync: {e}")
        return {"status": "error", "error": str(e)}




def cache_response(prefix: str, ttl: Optional[int] = None):
    """
    Async decorator for FastAPI route handlers to cache JSON endpoint responses.
    
    Usage:
        @router.get("/brand-performance")
        @cache_response(prefix="analytics", ttl=300)
        async def get_brand_performance(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # If Redis is not connected/enabled, bypass cache
            if not await is_redis_available():
                return await func(*args, **kwargs)

            # Look for Request object in kwargs or args to build key from query params & path
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request:
                query_params = dict(request.query_params)
                path_str = request.url.path.strip("/").replace("/", ":")
                cache_key = build_cache_key(prefix=prefix, identifier=path_str, params=query_params)
            else:
                # Fallback key generation from kwargs
                kw_filtered = {k: v for k, v in kwargs.items() if not isinstance(v, (Request, Response))}
                cache_key = build_cache_key(prefix=prefix, identifier=func.__name__, params=kw_filtered)

            # Check cache hit
            cached_result = await get_json_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache HIT for key '{cache_key}'")
                return cached_result

            # Cache miss: execute wrapped route function
            logger.debug(f"Cache MISS for key '{cache_key}'. Executing route handler...")
            res_data = await func(*args, **kwargs)

            # Cache the freshly retrieved data asynchronously
            if res_data is not None:
                effective_ttl = ttl or settings.CACHE_DEFAULT_TTL
                await set_json_cache(cache_key, res_data, ttl=effective_ttl)

            return res_data

        return wrapper
    return decorator
