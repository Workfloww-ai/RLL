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
            custom_http_client = httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(90.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=30.0)
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
