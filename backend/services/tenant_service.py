"""
Tenant Service
Encapsulates loading and caching tenant white-label configuration from Supabase PostgreSQL.
Supports fallback defaults if tenant configuration row does not exist yet.
"""
import logging
import time
from typing import Any, Dict, Optional

from backend.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_TENANT_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "data": None,
}
_TENANT_CACHE_TTL = 600.0  # 10 minutes cache TTL


def get_tenant_config_service(tenant_slug: str = "rll", force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetches white-label tenant configuration (App Name, Logo URL, Favicon, Splash Screen, Pinned Company).
    """
    now = time.time()
    if not force_refresh and _TENANT_CACHE["data"] and (now - _TENANT_CACHE["timestamp"] < _TENANT_CACHE_TTL):
        return _TENANT_CACHE["data"]

    client = get_supabase_client()
    default_config = {
        "status": "success",
        "tenant_slug": tenant_slug,
        "app_name": "LucidX360",
        "logo_url": "",
        "favicon_url": "",
        "splash_screen_url": "",
        "pinned_company_name": "Rajasthan Liquor Limited",
        "excluded_companies": ["Others"],
    }

    if not client:
        _TENANT_CACHE.update({"timestamp": now, "data": default_config})
        return default_config

    try:
        # Call RPC get_tenant_config
        res = client.rpc("get_tenant_config", {"p_tenant_slug": tenant_slug}).execute()
        if res.data and isinstance(res.data, dict):
            config_data = {
                "status": "success",
                "tenant_slug": str(res.data.get("tenant_slug") or tenant_slug),
                "app_name": str(res.data.get("app_name") or "LucidX360"),
                "logo_url": str(res.data.get("logo_url") or ""),
                "favicon_url": str(res.data.get("favicon_url") or ""),
                "splash_screen_url": str(res.data.get("splash_screen_url") or ""),
                "pinned_company_name": str(res.data.get("pinned_company_name") or ""),
                "excluded_companies": res.data.get("excluded_companies") or ["Others"],
            }
            _TENANT_CACHE.update({"timestamp": now, "data": config_data})
            return config_data
    except Exception as e:
        logger.warning(f"get_tenant_config_service: RPC notice: {e}. Falling back to default settings.")

    _TENANT_CACHE.update({"timestamp": now, "data": default_config})
    return default_config
