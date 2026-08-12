from typing import Dict, Any, Optional
import logging
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)


def get_company_aliases() -> Dict[str, str]:
    """
    Fetches all company aliases from public.company_aliases.
    Returns a dictionary mapping norm_key -> company_id.
    """
    client = get_supabase()
    if not client:
        return {}

    try:
        res = client.table("company_aliases").select("norm_key, company_id").execute()
        return {
            str(row["norm_key"]): str(row["company_id"])
            for row in (res.data or [])
            if row.get("norm_key") and row.get("company_id")
        }
    except Exception as e:
        logger.warning(f"get_company_aliases error: {e}")
        return {}


def upsert_company_alias(
    raw_name: str,
    norm_key: str,
    company_id: str,
    source: str = "auto"
) -> bool:
    """
    Inserts a company alias into public.company_aliases.
    If norm_key already exists, ignores or updates it.
    """
    client = get_supabase()
    if not client or not norm_key or not company_id:
        return False

    try:
        payload = {
            "raw_name": raw_name,
            "norm_key": norm_key,
            "company_id": company_id,
            "source": source
        }
        client.table("company_aliases").upsert(payload, on_conflict="norm_key").execute()
        return True
    except Exception as e:
        logger.warning(f"upsert_company_alias error for {raw_name} ({norm_key}): {e}")
        return False
