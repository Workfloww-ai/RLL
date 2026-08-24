import logging
from typing import Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from backend.core.config import settings

logger = logging.getLogger("redis_client")

_redis_client: Optional[aioredis.Redis] = None

async def init_redis() -> Optional[aioredis.Redis]:
    """
    Initialize async Redis connection pool.
    Supports Redis Cloud connection strings (REDIS_URL) or individual host/port/password params.
    """
    global _redis_client
    if not settings.REDIS_ENABLED:
        logger.info("Redis caching is disabled in configuration settings.")
        return None

    try:
        if settings.REDIS_URL:
            logger.info("Initializing Redis client via REDIS_URL configuration.")
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
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
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
        
        if _redis_client:
            # Ping Redis to verify connection health
            await _redis_client.ping()
            logger.info("Successfully connected to Redis Cloud server.")
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
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            logger.info("Closed Redis connection pool.")
        except Exception as e:
            logger.warning(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None


def get_redis() -> Optional[aioredis.Redis]:
    """Get global Redis client instance."""
    return _redis_client


async def is_redis_available() -> bool:
    """Check if Redis connection is active and responsive."""
    global _redis_client
    if _redis_client is None:
        return False
    try:
        await _redis_client.ping()
        return True
    except Exception:
        return False


async def safe_get(key: str) -> Optional[str]:
    """Safely fetch key value from Redis. Returns None if key missing or Redis unavailable."""
    client = get_redis()
    if client is None:
        return None
    try:
        return await client.get(key)
    except Exception as e:
        logger.warning(f"Redis GET failed for key '{key}': {e}")
        return None


async def safe_set(key: str, value: str, ttl: Optional[int] = None) -> bool:
    """Safely store key-value pair in Redis with optional TTL (seconds). Returns True on success."""
    client = get_redis()
    if client is None:
        return False
    try:
        ttl = ttl or settings.CACHE_DEFAULT_TTL
        await client.set(key, value, ex=ttl)
        return True
    except Exception as e:
        logger.warning(f"Redis SET failed for key '{key}': {e}")
        return False


async def safe_delete(key: str) -> bool:
    """Safely delete key from Redis. Returns True on success."""
    client = get_redis()
    if client is None:
        return False
    try:
        await client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis DELETE failed for key '{key}': {e}")
        return False


async def safe_delete_pattern(pattern: str) -> int:
    """
    Safely delete all keys matching pattern (e.g. 'rll:analytics:*').
    Returns total count of deleted keys.
    """
    client = get_redis()
    if client is None:
        return 0
    try:
        count = 0
        keys = []
        async for key in client.scan_iter(match=pattern, count=100):
            keys.append(key)
            if len(keys) >= 100:
                count += await client.delete(*keys)
                keys = []
        if keys:
            count += await client.delete(*keys)
        logger.info(f"Deleted {count} Redis keys matching pattern '{pattern}'")
        return count
    except Exception as e:
        logger.warning(f"Redis delete_pattern failed for '{pattern}': {e}")
        return 0
