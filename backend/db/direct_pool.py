import os
import ssl
import logging
import asyncio
from typing import Optional, List, Dict, Any, Sequence
from contextlib import asynccontextmanager

import asyncpg
from backend.core.config import settings

logger = logging.getLogger(__name__)

class DirectPostgresPoolManager:
    """
    Phase 4: Direct PostgreSQL Connection Pool Manager.
    Maintains an asyncpg connection pool directly to PostgreSQL port 5432/6543
    for ultra-high-speed binary COPY streaming (100k+ rows/sec).
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

    def get_dsn(self) -> Optional[str]:
        """Resolves direct PostgreSQL DSN from settings or environment."""
        dsn = settings.DATABASE_URL or settings.DIRECT_URL or os.environ.get("DATABASE_URL") or os.environ.get("DIRECT_URL")
        if not dsn:
            return None
        
        clean_dsn = dsn.strip()
        # asyncpg requires postgresql:// scheme rather than postgres://
        if clean_dsn.startswith("postgres://"):
            clean_dsn = "postgresql://" + clean_dsn[len("postgres://"):]
        return clean_dsn

    def is_available(self) -> bool:
        """Returns True if a direct PostgreSQL connection string is configured."""
        return bool(self.get_dsn())

    async def get_pool(self) -> Optional[asyncpg.Pool]:
        """Lazily initializes and returns the asyncpg connection pool."""
        if self._pool is not None:
            return self._pool

        dsn = self.get_dsn()
        if not dsn:
            return None

        async with self._lock:
            if self._pool is not None:
                return self._pool

            try:
                # Configure SSL for Supabase / Cloud Postgres
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

                # Strip sslmode query parameter if present to avoid asyncpg parameter conflict
                clean_dsn = dsn.split("?")[0]

                logger.info("Initializing asyncpg direct PostgreSQL connection pool...")
                self._pool = await asyncpg.create_pool(
                    dsn=clean_dsn,
                    min_size=1,
                    max_size=10,
                    command_timeout=120.0,
                    statement_cache_size=0,
                    ssl=ssl_ctx
                )
                logger.info("Direct PostgreSQL asyncpg pool established successfully.")
                return self._pool
            except Exception as e:
                logger.warning(f"Failed to initialize direct PostgreSQL asyncpg pool: {e}. Falling back to standard pipeline.")
                return None

    @asynccontextmanager
    async def acquire_connection(self):
        """Acquires a single connection from the direct pool."""
        pool = await self.get_pool()
        if not pool:
            yield None
            return

        async with pool.acquire() as conn:
            yield conn

    async def close(self):
        """Gracefully closes all connections in the pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Direct PostgreSQL asyncpg pool closed.")


# Singleton pool manager instance
direct_postgres_pool = DirectPostgresPoolManager()
