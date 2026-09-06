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

def is_others_company(company_name: Optional[str]) -> bool:
    """Helper to check if company name matches 'Others' exclusion criteria."""
    if not company_name:
        return False
    name = company_name.strip().lower()
    return name == "others" or name == "others company" or name.startswith("others ")


def get_company_brands_sales_service(
    company_id: str,
    date_from: str,
    date_to: str,
    hq_name: Optional[str] = None,
    exclude_company: str = "Others"
) -> List[Dict[str, Any]]:
    """
    Fetches brand sales metrics for a selected company.
    Strictly excludes 'Others' company brands and 0-sale items.
    """
    if not company_id:
        return []

    try:
        raw_data = fetch_company_brand_sales_db(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            hq_name=hq_name,
            exclude_company=exclude_company,
        )
        
        result = []
        for item in raw_data:
            comp_name = item.get("company_name", "")
            if is_others_company(comp_name):
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
    Strictly excludes 0-sale licensees.
    """
    if not brand_id:
        return []

    try:
        raw_data = fetch_brand_licensees_sales_db(
            brand_id=brand_id,
            date_from=date_from,
            date_to=date_to,
            hq_name=hq_name,
            exclude_company=exclude_company,
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
