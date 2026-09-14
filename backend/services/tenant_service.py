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

_TENANT_CACHE: Dict[str, Any] = {}
_TENANT_CACHE_TTL = 600.0  # 10 minutes cache TTL


def get_tenant_config_service(
    tenant_slug: Optional[str] = "rll",
    tenant_id: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetches white-label tenant configuration (Tenant ID, App Name, Logo URL, Favicon, Splash Screen, Pinned Company).
    Accepts tenant_slug, tenant_id, or defaults to canonical tenant.
    """
    now = time.time()
    cache_key = f"{tenant_slug or 'default'}:{tenant_id or 'none'}"

    if not force_refresh and cache_key in _TENANT_CACHE:
        entry = _TENANT_CACHE[cache_key]
        if now - entry["timestamp"] < _TENANT_CACHE_TTL:
            return entry["data"]

    client = get_supabase_client()
    default_config = {
        "status": "success",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "tenant_slug": tenant_slug or "rll",
        "app_name": "LucidX360",
        "logo_url": "/images/rll logo.svg",
        "favicon_url": "",
        "splash_screen_url": "",
        "pinned_company_name": "Rajasthan Liquor Limited",
        "excluded_companies": ["Others"],
    }

    if not client:
        _TENANT_CACHE[cache_key] = {"timestamp": now, "data": default_config}
        return default_config

    try:
        rpc_params: Dict[str, Any] = {
            "p_tenant_slug": tenant_slug or None,
            "p_tenant_id": tenant_id if (tenant_id and len(str(tenant_id)) == 36 and "-" in str(tenant_id)) else None,
        }
        res = client.rpc("get_tenant_config", rpc_params).execute()
        if res.data and isinstance(res.data, dict):
            config_data = {
                "status": "success",
                "tenant_id": str(res.data.get("tenant_id") or "a0000000-0000-0000-0000-000000000001"),
                "tenant_slug": str(res.data.get("tenant_slug") or tenant_slug or "rll"),
                "app_name": str(res.data.get("app_name") or "LucidX360"),
                "logo_url": str(res.data.get("logo_url") or "/images/rll logo.svg"),
                "favicon_url": str(res.data.get("favicon_url") or ""),
                "splash_screen_url": str(res.data.get("splash_screen_url") or ""),
                "pinned_company_name": str(res.data.get("pinned_company_name") or "Rajasthan Liquor Limited"),
                "excluded_companies": res.data.get("excluded_companies") or ["Others"],
            }
            _TENANT_CACHE[cache_key] = {"timestamp": now, "data": config_data}
            return config_data
    except Exception as e:
        logger.warning(f"get_tenant_config_service: RPC notice: {e}. Falling back to default settings.")

    _TENANT_CACHE[cache_key] = {"timestamp": now, "data": default_config}
    return default_config
