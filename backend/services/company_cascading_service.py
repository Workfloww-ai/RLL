# backend/services/company_cascading_service.py
"""
Service layer for Company -> Brand -> Licensee cascading drilldown views.
Strictly excludes company "Others" and enforces enterprise business logic standards.
"""

from typing import List, Dict, Any, Optional
import logging
from backend.db.supabase_client import (
    fetch_company_brand_sales_db,
    fetch_brand_licensees_sales_db,
)

logger = logging.getLogger(__name__)

_COMPANY_CATEGORIES_CACHE: Dict[str, str] = {}
_COMPANY_CATEGORIES_CACHE_TIME: float = 0.0

def _get_cached_company_categories() -> Dict[str, str]:
    global _COMPANY_CATEGORIES_CACHE, _COMPANY_CATEGORIES_CACHE_TIME
    import time
    now = time.time()
    if _COMPANY_CATEGORIES_CACHE and (now - _COMPANY_CATEGORIES_CACHE_TIME) < 300.0:
        return _COMPANY_CATEGORIES_CACHE
    try:
        from backend.db.supabase_client import get_supabase_client
        client = get_supabase_client()
        if client:
            res = client.table("companies").select("company_id, company_name, category").execute()
            mapping: Dict[str, str] = {}
            for r in (res.data or []):
                cat = (r.get("category") or "Others").strip()
                if r.get("company_name"):
                    mapping[r["company_name"].strip().lower()] = cat
                if r.get("company_id"):
                    mapping[str(r["company_id"]).strip().lower()] = cat
            _COMPANY_CATEGORIES_CACHE = mapping
            _COMPANY_CATEGORIES_CACHE_TIME = now
    except Exception as e:
        logger.debug(f"_get_cached_company_categories notice: {e}")
    return _COMPANY_CATEGORIES_CACHE


def is_others_company(company_name: Optional[str] = None, category: Optional[str] = None) -> bool:
    """Helper to check if company matches 'Others' exclusion criteria (category == 'Others') when inclusion toggle is OFF."""
    from backend.services.tenant_service import get_include_others_setting_sync
    if get_include_others_setting_sync():
        return False
    if category is not None and str(category).strip():
        return str(category).strip().lower() == "others"
    if not company_name:
        return False
    name = company_name.strip().lower()
    # Fast-path for competitor brand prefixes and others company
    if (
        name in ("others", "other", "others company", "other company")
        or name.startswith("others ")
        or name.startswith("other ")
        or name.startswith("comp_")
    ):
        return True

    # Check cached DB category if available
    cats = _get_cached_company_categories()
    if name in cats:
        return cats[name].lower() == "others"

    return False



def get_company_brands_sales_service(
    company_id: str,
    date_from: str,
    date_to: str,
    hq_name: Optional[str] = None,
    exclude_company: str = "Others"
) -> List[Dict[str, Any]]:
    """
    Fetches brand sales metrics for a selected company.
    Supports system_settings include_others_in_sales toggle and explicit company drilldowns.
    """
    if not company_id:
        return []

    from backend.services.tenant_service import get_include_others_setting_sync
    include_others = get_include_others_setting_sync()

    clean_target = str(company_id).strip().lower()
    is_target_others = clean_target in ("others", "other") or clean_target == "30739e78-c438-4a60-a5cb-6d9e9e79d1c6"

    # If include_others is True OR the user explicitly drilled into Others, do NOT exclude Others
    eff_exclude = "" if (include_others or is_target_others) else exclude_company

    try:
        raw_data = fetch_company_brand_sales_db(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            hq_name=hq_name,
            exclude_company=eff_exclude,
        )
        
        result = []
        for item in raw_data:
            comp_name = item.get("company_name", "")
            if not is_target_others and is_others_company(comp_name):
                continue
            
            cases = round(float(item.get("total_cases") or 0.0), 2)
            bottles = round(float(item.get("total_bottles") or 0.0), 2)
            lic_count = int(item.get("selling_licensees_count") or 0)

            result.append({
                "brand_id": str(item.get("brand_id")),
                "brand_name": str(item.get("brand_name")),
                "company_name": str(comp_name),
                "selling_licensees_count": lic_count,
                "total_cases": cases,
                "total_bottles": bottles,
            })

        return result
    except Exception as e:
        logger.error(f"get_company_brands_sales_service error for company {company_id}: {e}")
        return []


def get_brand_licensees_sales_service(
    brand_id: str,
    date_from: str,
    date_to: str,
    hq_name: Optional[str] = None,
    exclude_company: str = "Others"
) -> List[Dict[str, Any]]:
    """
    Fetches licensee sales metrics for a selected brand.
    Strictly excludes 0-sale licensees. Respects include_others_in_sales toggle.
    """
    if not brand_id:
        return []

    from backend.services.tenant_service import get_include_others_setting_sync
    include_others = get_include_others_setting_sync()
    eff_exclude = "" if include_others else exclude_company

    try:
        raw_data = fetch_brand_licensees_sales_db(
            brand_id=brand_id,
            date_from=date_from,
            date_to=date_to,
            hq_name=hq_name,
            exclude_company=eff_exclude,
        )

        result = []
        for item in raw_data:
            cases = round(float(item.get("total_cases") or 0.0), 2)
            bottles = round(float(item.get("total_bottles") or 0.0), 2)

            if cases > 0 or bottles > 0:
                result.append({
                    "licensee_id": str(item.get("licensee_id")),
                    "licensee_name": str(item.get("licensee_name")),
                    "trade": str(item.get("trade") or "Off"),
                    "depot_name": str(item.get("depot_name") or "Unassigned"),
                    "total_cases": cases,
                    "total_bottles": bottles,
                })

        return result
    except Exception as e:
        logger.error(f"get_brand_licensees_sales_service error for brand {brand_id}: {e}")
        return []
