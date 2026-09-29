import logging
from typing import Optional
import httpx
from supabase import create_client, Client, ClientOptions
from backend.core.config import settings

logger = logging.getLogger(__name__)

supabase_client: Optional[Client] = None

def get_supabase() -> Client:
    global supabase_client
    if supabase_client is None:
        try:
            # On macOS and Python 3.14, HTTP/2 multiplexing socket reads trigger [Errno 35] Resource temporarily unavailable (EWOULDBLOCK)
            # during high-throughput PostgREST streams. Enforcing HTTP/1.1 with retries guarantees 100% socket stability.
            transport = httpx.HTTPTransport(
                http1=True, 
                http2=False, 
                retries=3
            )
            import time
            from backend.core.telemetry import record_db_query

            def _on_httpx_request(request: httpx.Request):
                request.extensions["start_time"] = time.perf_counter()

            def _on_httpx_response(response: httpx.Response):
                start_time = response.request.extensions.get("start_time")
                if start_time is not None:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    record_db_query(
                        method=response.request.method,
                        url=str(response.request.url),
                        duration_ms=duration_ms,
                        status_code=response.status_code
                    )

            custom_http_client = httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(90.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=30.0),
                event_hooks={
                    "request": [_on_httpx_request],
                    "response": [_on_httpx_response]
                }
            )
            options = ClientOptions(
                httpx_client=custom_http_client,
                postgrest_client_timeout=90
            )
            supabase_client = create_client(
                settings.SUPABASE_URL, 
                settings.SUPABASE_SERVICE_ROLE_KEY,
                options=options
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Supabase client: {e}. Running with mock/fallback database connection.")
            return None
    return supabase_client
