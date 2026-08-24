import json
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


async def get_json_cache(key: str) -> Optional[Any]:
    """Retrieve and deserialize JSON cached value from Redis."""
    raw_val = await safe_get(key)
    if not raw_val:
        return None
    try:
        return json.loads(raw_val)
    except Exception as e:
        logger.warning(f"Failed to parse cached JSON for key '{key}': {e}")
        return None


async def set_json_cache(key: str, data: Any, ttl: Optional[int] = None) -> bool:
    """Serialize and store JSON value in Redis with specified TTL."""
    try:
        serialized = json.dumps(data, default=str)
        return await safe_set(key, serialized, ttl=ttl)
    except Exception as e:
        logger.warning(f"Failed to serialize data for cache set on key '{key}': {e}")
        return False


async def delete_cache(key: str) -> bool:
    """Delete a specific cache key."""
    return await safe_delete(key)


async def invalidate_analytics_cache() -> int:
    """
    Invalidate all analytics, dashboard, and mobile cache keys across the platform.
    Called automatically upon new Excel file uploads to prevent serving stale data.
    """
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
