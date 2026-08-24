import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("deduplication")

class RequestDeduplicator:
    """
    In-flight request deduplication manager.
    Prevents cache stampedes / thundering herd problem by ensuring that 
    concurrent identical API requests execute the underlying DB query only once,
    while all waiting concurrent requests receive the single shared result.
    """
    def __init__(self):
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def execute(self, key: str, func: Callable, *args, **kwargs) -> Any:
        """
        Execute func(*args, **kwargs) with deduplication keyed by string `key`.
        If a request with `key` is already running, wait for its result.
        """
        async with self._lock:
            if key in self._in_flight:
                logger.info(f"Deduplication HIT for key '{key}'. Awaiting in-flight execution...")
                future = self._in_flight[key]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[key] = future
                asyncio.create_task(self._run_task(key, future, func, *args, **kwargs))

        return await future

    async def _run_task(self, key: str, future: asyncio.Future, func: Callable, *args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            
            if not future.done():
                future.set_result(result)
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)

deduplicator = RequestDeduplicator()
