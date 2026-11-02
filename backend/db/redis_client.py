import logging
import asyncio
import fnmatch
from typing import Optional, Dict, Any, Callable
import redis.asyncio as aioredis
import redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from backend.core.config import settings

logger = logging.getLogger("redis_client")

_redis_client: Optional[aioredis.Redis] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_reaper_task: Optional[asyncio.Task] = None


async def reap_zombie_connections(idle_threshold_seconds: int = 120) -> int:
    """
    Scans Redis client list and terminates idle zombie connections older than idle_threshold_seconds.
    Prevents connection pool starvation on capped Redis plans (e.g. 30 connections).
    Always preserves the caller's own active connection.
    """
    global _redis_client
    if not _redis_client:
        return 0

    killed = 0
    try:
        # Get client's own ID to guarantee self is never killed
        my_info = await _redis_client.client_info()
        my_id = my_info.get("id")

        clients = await _redis_client.client_list()
        for client in clients:
            client_id = client.get("id")
            if client_id == my_id:
                continue

            idle_time = int(client.get("idle", 0))
            if idle_time >= idle_threshold_seconds:
                addr = client.get("addr")
                try:
                    await _redis_client.execute_command("CLIENT", "KILL", "ID", str(client_id))
                    logger.info(f"Reaped zombie Redis client id={client_id} addr={addr} (idle {idle_time}s)")
                    killed += 1
                except Exception as e_kill:
                    logger.debug(f"Failed to kill idle client {client_id}: {e_kill}")
    except Exception as e:
        logger.debug(f"Zombie connection reaper check notice: {e}")

    return killed


async def _zombie_reaper_loop(interval_seconds: int = 60, idle_threshold_seconds: int = 120):
    """Periodic background task that sweeps zombie connections every interval_seconds."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await reap_zombie_connections(idle_threshold_seconds=idle_threshold_seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Error in zombie reaper loop: {e}")

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

            # Run startup zombie connection sweep to free up stale sockets from prior restarts
            try:
                await reap_zombie_connections(idle_threshold_seconds=120)
            except Exception as e_zomb:
                logger.debug(f"Startup zombie reaper notice: {e_zomb}")

            # Spawn periodic background reaper task
            try:
                global _reaper_task
                if _reaper_task is None or _reaper_task.done():
                    _reaper_task = asyncio.create_task(
                        _zombie_reaper_loop(interval_seconds=60, idle_threshold_seconds=120)
                    )
            except Exception as e_task:
                logger.debug(f"Could not spawn background zombie reaper: {e_task}")

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
    global _redis_client, _main_loop, _reaper_task
    if _reaper_task is not None and not _reaper_task.done():
        try:
            _reaper_task.cancel()
        except Exception:
            pass
        _reaper_task = None

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
    Fails closed: Any environment that is not explicitly an allowed non-production
    development or test environment is treated as production/staging.
    """
    env = (getattr(settings, "ENVIRONMENT", "") or "").strip().lower()
    return env not in ("dev", "development", "test", "testing", "local")


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


# Whitelist of safe, feature-scoped cache key prefixes permitted for pattern deletion.
ALLOWED_CACHE_PREFIXES = (
    "rll:analytics:",
    "rll:dashboard:",
    "rll:mobile:sales:",
    "rll:mobile:companies:",
    "rll:cache:",
)

# Protected security-sensitive prefixes that MUST NEVER be matched or deleted by pattern deletion.
PROTECTED_SECURITY_PREFIXES = (
    "rll:session:",
    "rll:revoked:",
    "rll:otp:",
    "rll:otp_attempts:",
    "rll:otp_consuming:",
    "rll:mobile_otp_attempts:",
    "rll:cooldown:",
    "rll:syslock:",
)


async def safe_delete_pattern(pattern: str) -> int:
    """
    Safely delete keys matching a validated, feature-scoped cache prefix (e.g. 'rll:analytics:*').
    Strictly forbids broad, wildcard, or security-sensitive pattern deletions (e.g. '*', 'rll:*').
    Preserves all security state (OTPs, rate limits, sessions, locks).
    Returns total count of deleted keys.
    """
    if not pattern or not isinstance(pattern, str):
        logger.warning("safe_delete_pattern rejected: empty or non-string pattern")
        return 0

    clean_pattern = pattern.strip()

    # Reject broad/destructive wildcards
    if clean_pattern in ("*", "rll:*", "rll*", "?", ""):
        logger.error(f"Security rejection: broad Redis deletion pattern '{clean_pattern}' is strictly prohibited.")
        return 0

    # Ensure pattern targets an allowed cache prefix
    if not any(clean_pattern.startswith(prefix) for prefix in ALLOWED_CACHE_PREFIXES):
        logger.error(f"Security rejection: pattern '{clean_pattern}' does not match any allowed cache prefix.")
        return 0

    # Ensure pattern does not target any protected security prefix
    clean_prefix = clean_pattern.rstrip("*").rstrip(":")
    if any(clean_pattern.startswith(sec) or sec.startswith(f"{clean_prefix}:") for sec in PROTECTED_SECURITY_PREFIXES):
        logger.critical(f"CRITICAL: Refusing pattern deletion targeting protected security prefix: '{clean_pattern}'")
        return 0

    # In-memory store cleanup (preserves security keys)
    with _in_memory_lock:
        to_remove = [
            k for k in _in_memory_store.keys()
            if fnmatch.fnmatch(k, clean_pattern) and not any(k.startswith(p) for p in PROTECTED_SECURITY_PREFIXES)
        ]
        for k in to_remove:
            _in_memory_store.pop(k, None)
            _in_memory_expiry.pop(k, None)

    client = get_redis()
    if client is None:
        return len(to_remove)

    async def _do_delete_pattern(r: aioredis.Redis) -> int:
        count = 0
        keys_to_delete = []
        async for key in r.scan_iter(match=clean_pattern, count=250):
            s_key = key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
            # Defense-in-depth: Never delete any key matching a protected security prefix
            if any(s_key.startswith(p) for p in PROTECTED_SECURITY_PREFIXES):
                logger.warning(f"Skipping deletion of protected key matching pattern: {s_key}")
                continue
            keys_to_delete.append(key)
            if len(keys_to_delete) >= 100:
                count += await r.delete(*keys_to_delete)
                keys_to_delete = []
        if keys_to_delete:
            count += await r.delete(*keys_to_delete)
            keys_to_delete = []

        # Fallback to direct keys lookup if scan_iter returned 0
        if count == 0:
            try:
                direct_keys = await r.keys(clean_pattern)
                for dk in direct_keys:
                    s_dk = dk.decode("utf-8", errors="ignore") if isinstance(dk, bytes) else str(dk)
                    if not any(s_dk.startswith(p) for p in PROTECTED_SECURITY_PREFIXES):
                        keys_to_delete.append(dk)
                if keys_to_delete:
                    count += await r.delete(*keys_to_delete)
            except Exception as e_direct:
                logger.debug(f"Direct keys pattern fallback notice: {e_direct}")

        logger.info(f"Deleted {count} Redis keys matching pattern '{clean_pattern}'")
        return count

    try:
        res = await _execute_redis(_do_delete_pattern)
        return int(res or 0)
    except Exception as e:
        logger.warning(f"Redis delete_pattern failed for '{clean_pattern}': {e}")
        return len(to_remove)


# ============================================================
# SYNCHRONOUS REDIS CLIENT & HELPERS
# ============================================================

_sync_redis_instance: Optional[redis.Redis] = None


def get_sync_redis() -> Optional[redis.Redis]:
    """Get or initialize thread-safe synchronous Redis client instance."""
    global _sync_redis_instance
    if not settings.REDIS_ENABLED:
        return None
    if _sync_redis_instance is not None:
        return _sync_redis_instance

    try:
        if settings.REDIS_URL:
            _sync_redis_instance = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True
            )
        elif settings.REDIS_HOST:
            _sync_redis_instance = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True
            )
        if _sync_redis_instance:
            _sync_redis_instance.ping()
        return _sync_redis_instance
    except Exception as e:
        logger.warning(f"Sync Redis initialization notice: {e}")
        return None


def sync_get(key: str) -> Optional[str]:
    """Synchronously fetch key value from Redis with in-memory fallback."""
    r = get_sync_redis()
    if r is not None:
        try:
            return r.get(key)
        except Exception as e:
            logger.warning(f"Sync Redis GET failed for '{key}': {e}")
    return _in_memory_store.get(key)


def sync_set(key: str, value: str, ttl: Optional[int] = None) -> bool:
    """Synchronously store key in Redis with optional TTL and in-memory fallback."""
    _in_memory_store[key] = value
    r = get_sync_redis()
    if r is not None:
        try:
            if ttl and ttl > 0:
                r.set(key, value, ex=ttl)
            else:
                r.set(key, value)
            return True
        except Exception as e:
            logger.warning(f"Sync Redis SET failed for '{key}': {e}")
    return True


def sync_delete(key: str) -> bool:
    """Synchronously delete key from Redis and in-memory store."""
    _in_memory_store.pop(key, None)
    r = get_sync_redis()
    if r is not None:
        try:
            r.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Sync Redis DELETE failed for '{key}': {e}")
    return True


def sync_ttl(key: str) -> int:
    """Synchronously get TTL in seconds (-2 if not exists, -1 if no expiry)."""
    r = get_sync_redis()
    if r is not None:
        try:
            return r.ttl(key)
        except Exception:
            pass
    return -2


PERMITTED_TEST_ENVIRONMENTS = ("test", "testing")


def is_safe_test_redis_target() -> bool:
    """
    Verify that the configured Redis instance is a dedicated, explicitly configured
    disposable test instance before allowing destructive test operations (flush).
    Rejects remote or production Redis targets unless explicitly approved via TEST_REDIS_URL.
    """
    test_url = (getattr(settings, "TEST_REDIS_URL", "") or "").strip()
    redis_url = (getattr(settings, "REDIS_URL", "") or "").strip()
    redis_host = (getattr(settings, "REDIS_HOST", "") or "").strip().lower()

    # Reject known production or cloud host indicators unconditionally
    combined_target = f"{redis_url} {redis_host}".lower()
    for ind in ("redis-cloud", "redislabs", "elasticache", "upstash", "production", "prod", "supabase"):
        if ind in combined_target:
            return False

    # Scenario A: Dedicated TEST_REDIS_URL explicitly configured matching REDIS_URL
    if test_url:
        if redis_url and redis_url == test_url:
            return True
        if not redis_url and test_url.endswith(f":{settings.REDIS_PORT}/{settings.REDIS_DB}"):
            return True

    # Scenario B: Local loopback disposable instance with no remote REDIS_URL
    if not redis_url:
        if redis_host in ("localhost", "127.0.0.1", "::1"):
            return True

    if redis_url:
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(redis_url)
            hostname = (parsed.hostname or "").lower()
            if hostname in ("localhost", "127.0.0.1", "::1"):
                return True
        except Exception:
            return False

    return False


async def flush_redis_for_testing() -> bool:
    """
    Test-only helper to reset state in dedicated, disposable test environments.
    Strictly forbidden and blocked in production, staging, development, or unverified environments.
    Requires:
      1. ENVIRONMENT must be explicitly 'test' or 'testing'.
      2. ALLOW_TEST_REDIS_FLUSH must be set to True.
      3. Redis target must be an approved, isolated test instance (never remote/production).
    """
    env = (getattr(settings, "ENVIRONMENT", "") or "").strip().lower()
    if env not in PERMITTED_TEST_ENVIRONMENTS:
        logger.critical(f"Security violation: flush_redis_for_testing called in non-test environment '{env}'! Refusing.")
        raise RuntimeError(
            f"flush_redis_for_testing is strictly prohibited in environment '{env}'. "
            f"Permitted test environments: {PERMITTED_TEST_ENVIRONMENTS}."
        )

    allow_flush = getattr(settings, "ALLOW_TEST_REDIS_FLUSH", False)
    if not allow_flush:
        logger.critical("Security violation: flush_redis_for_testing called without ALLOW_TEST_REDIS_FLUSH=True! Refusing.")
        raise RuntimeError(
            "flush_redis_for_testing requires explicit test isolation authorization: "
            "ALLOW_TEST_REDIS_FLUSH must be explicitly set to True."
        )

    if not is_safe_test_redis_target():
        logger.critical("Security violation: flush_redis_for_testing attempted against unapproved or remote Redis target! Refusing.")
        raise RuntimeError(
            "flush_redis_for_testing cannot target unapproved, remote, or production Redis instances. "
            "A dedicated, explicitly isolated test Redis instance is required."
        )

    with _in_memory_lock:
        _in_memory_store.clear()
        _in_memory_expiry.clear()

    client = get_redis()
    if client is not None:
        try:
            await _execute_redis(lambda r: r.flushdb(asynchronous=False))
            logger.info("Test-only Redis flush completed on verified disposable test instance.")
            return True
        except Exception as e:
            logger.warning(f"flush_redis_for_testing failed: {e}")
            return False
    return True
