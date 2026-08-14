import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.db.supabase_client import (
    get_supabase_client,
    fetch_cascading_groups_db,
    fetch_group_licensees_db,
    fetch_licensee_brand_sales_db,
)

logger = logging.getLogger(__name__)


def _get_latest_sale_date(client) -> str:
    """Helper to fetch the latest available sale date dynamically from sales_fact."""
    try:
        res = client.table("sales_fact").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0 and res.data[0].get("sale_date"):
            return str(res.data[0].get("sale_date"))
    except Exception as e:
        logger.warning(f"Error fetching latest sale date: {e}")
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_period_dates(
    client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> tuple[str, str]:
    """
    Calculates start and end dates based on selected period (Daily / MTD / YTD) or custom dates.
    Priority:
      1. If both date_from and date_to are provided, use explicit date range.
      2. Otherwise, calculate dynamically from target_date based on period (Daily/MTD/YTD).
    """
    if date_from and date_to:
        return date_from, date_to

    target_date_str = date_to or date_from or _get_latest_sale_date(client)

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        latest = _get_latest_sale_date(client)
        dt = datetime.strptime(latest, "%Y-%m-%d")
        target_date_str = latest

    if period == "Daily":
        return target_date_str, target_date_str
    elif period == "MTD":
        mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"
        return mtd_start, target_date_str
    elif period == "YTD":
        fy_year = dt.year if dt.month >= 4 else dt.year - 1
        fy_start = f"{fy_year:04d}-04-01"
        return fy_start, target_date_str

    return date_from or target_date_str, date_to or target_date_str


def get_cascading_groups(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch active groups mapped with total licensees count, linked depots, total cases, and total bottles.
    Sums total cases and total bottles directly from sales_fact via database RPC aggregation.
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        return fetch_cascading_groups_db(date_from=d_from, date_to=d_to)
    except Exception as e:
        logger.error(f"Error in get_cascading_groups: {e}", exc_info=True)
        return []


def get_group_licensees(
    group_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch licensees for a group mapped with trade, depot, total cases, and total bottles.
    Sums total cases and total bottles directly from sales_fact via database RPC aggregation.
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        return fetch_group_licensees_db(
            group_id=group_id,
            date_from=d_from,
            date_to=d_to,
            depot_name=depot_name
        )
    except Exception as e:
        logger.error(f"Error in get_group_licensees: {e}", exc_info=True)
        return []


def get_licensee_brand_sales(
    licensee_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    depot_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch brand-wise sales breakdown for a licensee.
    Sums total cases and total bottles directly from sales_fact via database RPC aggregation.
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)
        return fetch_licensee_brand_sales_db(
            licensee_id=licensee_id,
            date_from=d_from,
            date_to=d_to,
            depot_name=depot_name
        )
    except Exception as e:
        logger.error(f"Error in get_licensee_brand_sales: {e}", exc_info=True)
        return []
