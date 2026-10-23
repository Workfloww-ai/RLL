import logging
import asyncio
from typing import Optional, Dict, Any, Callable
import redis.asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from backend.core.config import settings

logger = logging.getLogger("redis_client")

_redis_client: Optional[aioredis.Redis] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None

async def init_redis() -> Optional[aioredis.Redis]:
    """
    Initialize async Redis connection pool.
    Supports Redis Cloud connection strings (REDIS_URL) or individual host/port/password params.
    """
    global _redis_client, _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
    except Exception:
        pass

    if not settings.REDIS_ENABLED:
        logger.info("Redis caching is disabled in configuration settings.")
        return None

    try:
        if settings.REDIS_URL:
            logger.info("Initializing Redis client via REDIS_URL configuration.")
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
        elif settings.REDIS_HOST:
            logger.info(f"Initializing Redis client via host {settings.REDIS_HOST}:{settings.REDIS_PORT}.")
            _redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                db=settings.REDIS_DB,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
        
        if _redis_client:
            # Ping Redis to verify connection health
            await _redis_client.ping()
            logger.info("Successfully connected to Redis Cloud server.")
            
            # Flush existing stale uncompressed cache keys on startup as requested
            try:
                await _redis_client.flushdb(asynchronous=True)
                logger.info("🧹 Flushed all legacy Redis cache keys on server startup.")
            except Exception as e_flush:
                logger.warning(f"Flush Redis on startup notice: {e_flush}")
                
            return _redis_client

            
    except (RedisError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(
            f"Failed to connect to Redis server: {e}. "
            f"Application will operate with graceful degradation (direct DB access)."
        )
        _redis_client = None
    except Exception as e:
        logger.error(f"Unexpected error initializing Redis client: {e}")
        _redis_client = None

    return None


async def close_redis() -> None:
    """Close Redis client connection pool during application shutdown."""
    global _redis_client, _main_loop
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            logger.info("Closed Redis connection pool.")
        except Exception as e:
            logger.warning(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None
            _main_loop = None


def get_redis() -> Optional[aioredis.Redis]:
    """Get global Redis client instance."""
    return _redis_client


async def _execute_redis(coro_fn: Callable[[aioredis.Redis], Any]) -> Any:
    """
    Executes a coroutine against _redis_client.
    If called from a worker thread or different asyncio event loop from the one
    that created _redis_client, safely dispatches via run_coroutine_threadsafe to _main_loop.
    """
    global _redis_client, _main_loop
    if _redis_client is None:
        return None

    try:
        curr_loop = asyncio.get_running_loop()
    except RuntimeError:
        curr_loop = None

    # Auto-register main loop if not yet stored
    if _main_loop is None and curr_loop is not None:
        _main_loop = curr_loop

    if _main_loop and _main_loop.is_running() and curr_loop != _main_loop:
        fut = asyncio.run_coroutine_threadsafe(coro_fn(_redis_client), _main_loop)
        if curr_loop is not None:
            return await asyncio.wrap_future(fut)
        else:
            return fut.result(timeout=5)
    else:
        return await coro_fn(_redis_client)


async def is_redis_available() -> bool:
    """Check if Redis connection is active and responsive."""
    global _redis_client
    if _redis_client is None:
        return False
    try:
        res = await _execute_redis(lambda r: r.ping())
        return bool(res)
    except Exception:
        return False


import time
import threading

_in_memory_lock = threading.Lock()
_in_memory_store: Dict[str, str] = {}
_in_memory_expiry: Dict[str, float] = {}

# Atomic Lua script for strictly monotonic increment and TTL establishment in a single Redis execution
LUA_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return current
"""

# Atomic Lua script for single-use get-and-delete
LUA_GETDEL = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
end
return val
"""


def is_production_or_staging() -> bool:
    """
    Check if the current application environment is production or staging.
    In production and staging, security-sensitive operations (authentication rate limits,
    lockout counters, and resend cooldowns) strictly require the shared Redis store.
    Per-process in-memory fallback is refused for security-sensitive operations in these environments.
    """
    env = (getattr(settings, "ENVIRONMENT", "") or "").strip().lower()
    return env in ["production", "prod", "staging"]


async def safe_get(key: str, security_sensitive: bool = False) -> Optional[str]:
    """
    Safely fetch key value from Redis.
    In production/staging with security_sensitive=True, refuses in-memory fallback if Redis is unavailable.
    """
    client = get_redis()
    if client is not None:
        try:
            val = await _execute_redis(lambda r: r.get(key))
            if val is not None:
                return val
        except Exception as e:
            logger.warning(f"Redis GET failed for key '{key}': {e}")
            if security_sensitive and is_production_or_staging():
                logger.error(f"Failing closed: shared Redis GET failed for security key '{key}' in {settings.ENVIRONMENT}")
                return None

    # Enforce fail-closed for security operations in production/staging
    if security_sensitive and is_production_or_staging():
        logger.error(f"Failing closed: Redis unavailable for security_sensitive GET '{key}' in {settings.ENVIRONMENT}")
        return None

    # In-memory fallback allowed for development/test/local or non-security caching
    with _in_memory_lock:
        now = time.time()
        exp = _in_memory_expiry.get(key)
        if exp is not None and now > exp:
            _in_memory_store.pop(key, None)
            _in_memory_expiry.pop(key, None)
            return None
        return _in_memory_store.get(key)


async def safe_set(key: str, value: str, ttl: Optional[int] = None, security_sensitive: bool = False) -> bool:
    """
    Safely store key-value pair in Redis with optional TTL (seconds).
    In production/staging with security_sensitive=True, fails closed if Redis is unavailable.
    """
    effective_ttl = ttl or settings.CACHE_DEFAULT_TTL
    client = get_redis()
    if client is not None:
        try:
            await _execute_redis(lambda r: r.set(key, value, ex=effective_ttl))
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for key '{key}': {e}")
            if security_sensitive and is_production_or_staging():
                logger.error(f"Failing closed: shared Redis SET failed for security key '{key}' in {settings.ENVIRONMENT}")
                return False

    if security_sensitive and is_production_or_staging():
        logger.error(f"Failing closed: Redis unavailable for security_sensitive SET '{key}' in {settings.ENVIRONMENT}")
        return False

    with _in_memory_lock:
        _in_memory_store[key] = value
        if effective_ttl:
            _in_memory_expiry[key] = time.time() + effective_ttl
        else:
            _in_memory_expiry.pop(key, None)
    return True


async def safe_set_nx(key: str, value: str, ttl: Optional[int] = None, security_sensitive: bool = False) -> Optional[bool]:
    """
    Atomically set key if it does not already exist (NX) with TTL.
    Returns:
      - True if key was set (lock acquired).
      - False if key already exists (lock denied).
      - None if Redis is unavailable in production/staging and security_sensitive=True (fail-closed).
    """
    effective_ttl = ttl or settings.CACHE_DEFAULT_TTL
    client = get_redis()
    if client is not None:
        try:
            res = await _execute_redis(lambda r: r.set(key, value, ex=effective_ttl, nx=True))
            if res:
                return True
            return False
        except Exception as e:
            logger.error(f"Redis SET NX failed for key '{key}': {e}")
            if security_sensitive and is_production_or_staging():
                logger.critical(f"CRITICAL: Shared Redis SET NX failed for security lock '{key}' in {settings.ENVIRONMENT}. Failing closed.")
                return None

    # Strict environment enforcement: Reject in-memory rate-limits/locks in production/staging
    if security_sensitive and is_production_or_staging():
        logger.critical(f"CRITICAL: Shared Redis store is unavailable in {settings.ENVIRONMENT} for security lock '{key}'. Refusing in-memory fallback (failing closed).")
        return None

    # Development / test in-memory fallback
    with _in_memory_lock:
        now = time.time()
        exp = _in_memory_expiry.get(key)
        if exp is not None and now > exp:
            _in_memory_store.pop(key, None)
            _in_memory_expiry.pop(key, None)

        if key in _in_memory_store:
            return False
        _in_memory_store[key] = value
        if effective_ttl:
            _in_memory_expiry[key] = now + effective_ttl
        return True


async def safe_incr(key: str, ttl: Optional[int] = None, security_sensitive: bool = False) -> Optional[int]:
    """
    Atomically increment an integer key with atomic TTL establishment using Redis Lua script.
    Guarantees:
      - Strictly monotonic increments across application workers.
      - TTL is established atomically on key creation (current == 1) and never unexpectedly extended.
      - In production/staging with security_sensitive=True, returns None if Redis is unavailable (fail closed).
      - Development/test environments fall back to thread-safe in-memory store.
    """
    effective_ttl = ttl or settings.CACHE_DEFAULT_TTL
    client = get_redis()
    if client is not None:
        try:
            res = await _execute_redis(lambda r: r.eval(LUA_INCR_EXPIRE, 1, key, effective_ttl))
            if res is not None:
                return int(res)
        except Exception as e:
            logger.error(f"Redis atomic INCR script failed for key '{key}': {e}")
            if security_sensitive and is_production_or_staging():
                logger.critical(f"CRITICAL: Shared Redis atomic INCR failed for security counter '{key}' in {settings.ENVIRONMENT}. Failing closed.")
                return None

    # Strict environment enforcement: Reject per-process in-memory counters in production/staging
    if security_sensitive and is_production_or_staging():
        logger.critical(f"CRITICAL: Shared Redis store is unavailable in {settings.ENVIRONMENT} for security counter '{key}'. Refusing in-memory fallback (failing closed).")
        return None

    # Development / test in-memory fallback
    with _in_memory_lock:
        now = time.time()
        exp = _in_memory_expiry.get(key)
        if exp is not None and now > exp:
            _in_memory_store.pop(key, None)
            _in_memory_expiry.pop(key, None)

        try:
            cur = int(_in_memory_store.get(key, "0"))
        except (ValueError, TypeError):
            cur = 0
        new_val = cur + 1
        _in_memory_store[key] = str(new_val)
        if effective_ttl and key not in _in_memory_expiry:
            _in_memory_expiry[key] = now + effective_ttl
        return new_val


async def safe_get_and_delete(key: str, security_sensitive: bool = False) -> Optional[str]:
    """
    Atomically retrieve and delete key using Redis Lua script.
    Guarantees single-use consumption across concurrent workers.
    """
    client = get_redis()
    if client is not None:
        try:
            res = await _execute_redis(lambda r: r.eval(LUA_GETDEL, 1, key))
            if res is not None:
                return str(res)
        except Exception as e:
            logger.error(f"Redis GETDEL failed for key '{key}': {e}")
            if security_sensitive and is_production_or_staging():
                return None

    if security_sensitive and is_production_or_staging():
        return None

    with _in_memory_lock:
        now = time.time()
        exp = _in_memory_expiry.pop(key, None)
        val = _in_memory_store.pop(key, None)
        if exp is not None and now > exp:
            return None
        return val


async def safe_delete(key: str, security_sensitive: bool = False) -> bool:
    """Safely delete key from Redis and in-memory fallback."""
    with _in_memory_lock:
        _in_memory_store.pop(key, None)
        _in_memory_expiry.pop(key, None)
    client = get_redis()
    if client is None:
        if security_sensitive and is_production_or_staging():
            logger.error(f"Failing closed: Redis unavailable for security_sensitive DELETE '{key}' in {settings.ENVIRONMENT}")
            return False
        return True
    try:
        await _execute_redis(lambda r: r.delete(key))
        return True
    except Exception as e:
        logger.warning(f"Redis DELETE failed for key '{key}': {e}")
        if security_sensitive and is_production_or_staging():
            return False
        return True


async def safe_delete_pattern(pattern: str) -> int:
    """
    Safely delete all keys matching pattern (e.g. 'rll:analytics:*').
    Returns total count of deleted keys.
    """
    client = get_redis()
    if client is None:
        return 0

    async def _do_delete_pattern(r: aioredis.Redis) -> int:
        count = 0
        keys = []
        async for key in r.scan_iter(match=pattern, count=100):
            keys.append(key)
            if len(keys) >= 100:
                count += await r.delete(*keys)
                keys = []
        if keys:
            count += await r.delete(*keys)
        logger.info(f"Deleted {count} Redis keys matching pattern '{pattern}'")
        return count

    try:
        res = await _execute_redis(_do_delete_pattern)
        return int(res or 0)
    except Exception as e:
        logger.warning(f"Redis delete_pattern failed for '{pattern}': {e}")
        return 0
