import logging
from typing import Optional
from supabase import create_client, Client
from backend.core.config import settings

logger = logging.getLogger(__name__)

supabase_client: Optional[Client] = None

def get_supabase() -> Client:
    global supabase_client
    if supabase_client is None:
        try:
            supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        except Exception as e:
            logger.warning(f"Failed to initialize Supabase client: {e}. Running with mock/fallback database connection.")
            return None
    return supabase_client
