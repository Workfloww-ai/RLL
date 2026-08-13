import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

def _get_latest_sale_date(client) -> str:
    """Helper to fetch the latest available sale date from sales_fact."""
    try:
        res = client.table("sales_fact").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0].get("sale_date") or "2026-05-31"
    except Exception as e:
        logger.warning(f"Error fetching latest sale date: {e}")
    return "2026-05-31"


def _resolve_period_dates(
    client,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> tuple[str, str]:
    """
    Calculates start and end dates based on selected period (Daily / MTD / YTD) or custom dates.
    YTD starts on April 1st of current financial year.
    """
    # High priority: MTD hardcoded to 1st May 2026 -> 31st May 2026
    if period == "MTD":
        return "2026-05-01", "2026-05-31"

    target_date_str = date_to or date_from or _get_latest_sale_date(client)

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        latest = _get_latest_sale_date(client)
        dt = datetime.strptime(latest, "%Y-%m-%d")
        target_date_str = latest

    if period == "Daily":
        return target_date_str, target_date_str
    elif period == "YTD":
        fy_year = dt.year if dt.month >= 4 else dt.year - 1
        fy_start = f"{fy_year}-04-01"
        return fy_start, target_date_str
    
    d_from = date_from or target_date_str
    d_to = date_to or target_date_str
    return d_from, d_to



def get_cascading_groups(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch active groups mapped with total licensees, linked depots, total cases, and total bottles.
    Strictly excludes company 'Others' and calculates sales for requested period (Daily/MTD/YTD).
    """
    client = get_supabase()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)

        # 1. Fetch active groups from master table
        g_res = client.table("groups").select("group_id, group_name").eq("is_active", True).execute()
        all_groups = {g["group_id"]: g["group_name"] for g in (g_res.data or [])}

        # 2. Fetch licensees to build group -> licensee mapping
        l_res = client.table("licensees").select("licensee_id, group_id, licensee_name").eq("is_active", True).execute()
        group_lics_map: Dict[str, set] = {}
        for lic in (l_res.data or []):
            gid = lic.get("group_id")
            lid = lic.get("licensee_id")
            if gid and lid:
                if gid not in group_lics_map:
                    group_lics_map[gid] = set()
                group_lics_map[gid].add(lid)

        # 3. Query sales_fact joining brands & companies to EXCLUDE company 'Others'
        sf_res = client.table("sales_fact").select(
            "licensee_id, total_case, total_btl, sale_date, depots(name), brands(brand_id, brand_name, company_id, companies(company_name)), licensees(group_id)"
        ).gte("sale_date", d_from).lte("sale_date", d_to).limit(5000).execute()

        sales_records = sf_res.data or []

        group_metrics: Dict[str, Dict[str, Any]] = {}

        for sf in sales_records:
            # Exclude company 'Others'
            brand_obj = sf.get("brands") or {}
            comp_obj = brand_obj.get("companies") if isinstance(brand_obj, dict) else {}
            cname = comp_obj.get("company_name", "") if isinstance(comp_obj, dict) else ""
            if cname and cname.lower().strip() == "others":
                continue

            lic_obj = sf.get("licensees") or {}
            gid = lic_obj.get("group_id") if isinstance(lic_obj, dict) else None
            if not gid or gid not in all_groups:
                continue

            if gid not in group_metrics:
                group_metrics[gid] = {
                    "cases": 0.0,
                    "bottles": 0.0,
                    "depots": set()
                }

            group_metrics[gid]["cases"] += float(sf.get("total_case") or 0)
            group_metrics[gid]["bottles"] += float(sf.get("total_btl") or 0)

            depot_obj = sf.get("depots") or {}
            dname = depot_obj.get("name") if isinstance(depot_obj, dict) else None
            if dname:
                group_metrics[gid]["depots"].add(dname)

        results = []
        for gid, gname in all_groups.items():
            lic_count = len(group_lics_map.get(gid, set()))
            metrics = group_metrics.get(gid, {"cases": 0.0, "bottles": 0.0, "depots": set()})

            if lic_count > 0 or metrics["cases"] > 0:
                results.append({
                    "group_id": gid,
                    "group_name": gname,
                    "total_licensees": lic_count,
                    "linked_depots": sorted(list(metrics["depots"])),
                    "total_cases": round(metrics["cases"], 2),
                    "total_bottles": round(metrics["bottles"], 2)
                })

        # Sort groups with highest sales first
        results.sort(key=lambda x: (x["total_cases"], x["total_licensees"]), reverse=True)
        return results

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
    Fetch licensees for a group mapped with trade, depots, total cases, and total bottles.
    Excludes company 'Others' and filters by requested period (Daily/MTD/YTD).
    """
    client = get_supabase()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)

        # 1. Get licensees master list under group
        res = client.table("licensees").select("licensee_id, licensee_name, trade, group_id").eq("group_id", group_id).eq("is_active", True).execute()
        master_licensees = res.data or []

        lic_map: Dict[str, Dict[str, Any]] = {
            l["licensee_id"]: {
                "licensee_id": str(l["licensee_id"]),
                "licensee_name": l["licensee_name"],
                "trade": l.get("trade") or "Off",
                "depots": set(),
                "total_cases": 0.0,
                "total_bottles": 0.0
            }
            for l in master_licensees
        }

        # 2. Query sales_fact for this group via single inner join
        sf_res = client.table("sales_fact").select(
            "licensee_id, total_case, total_btl, sale_date, depots(name), brands(brand_id, brand_name, company_id, companies(company_name)), licensees!inner(licensee_id, licensee_name, trade, group_id)"
        ).eq("licensees.group_id", group_id).gte("sale_date", d_from).lte("sale_date", d_to).limit(5000).execute()

        sales_records = sf_res.data or []

        for sf in sales_records:
            # Exclude company 'Others'
            brand_obj = sf.get("brands") or {}
            comp_obj = brand_obj.get("companies") if isinstance(brand_obj, dict) else {}
            cname = comp_obj.get("company_name", "") if isinstance(comp_obj, dict) else ""
            if cname and cname.lower().strip() == "others":
                continue

            lid = sf.get("licensee_id")
            if not lid:
                continue

            depot_obj = sf.get("depots") or {}
            dname = depot_obj.get("name") if isinstance(depot_obj, dict) else None

            # Filter by depot if depot_name specified
            if depot_name and dname and dname.lower() != depot_name.lower():
                continue

            if lid not in lic_map:
                lic_obj = sf.get("licensees") or {}
                lname = lic_obj.get("licensee_name") if isinstance(lic_obj, dict) else "Unknown"
                trade = lic_obj.get("trade") if isinstance(lic_obj, dict) else "Off"
                lic_map[lid] = {
                    "licensee_id": str(lid),
                    "licensee_name": lname,
                    "trade": trade or "Off",
                    "depots": set(),
                    "total_cases": 0.0,
                    "total_bottles": 0.0
                }

            if dname:
                lic_map[lid]["depots"].add(dname)
            lic_map[lid]["total_cases"] += float(sf.get("total_case") or 0)
            lic_map[lid]["total_bottles"] += float(sf.get("total_btl") or 0)

        results = []
        for lid, item in lic_map.items():
            if depot_name and len(item["depots"]) == 0 and item["total_cases"] == 0:
                continue
            results.append({
                "licensee_id": item["licensee_id"],
                "licensee_name": item["licensee_name"],
                "trade": item["trade"],
                "licensee_depots": sorted(list(item["depots"])),
                "total_cases": round(item["total_cases"], 2),
                "total_bottles": round(item["total_bottles"], 2)
            })

        results.sort(key=lambda x: x["total_cases"], reverse=True)
        return results

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
    Excludes company 'Others' and filters by requested period (Daily/MTD/YTD).
    """
    client = get_supabase()
    if not client:
        return []

    try:
        d_from, d_to = _resolve_period_dates(client, date_from, date_to, period)

        sf_res = client.table("sales_fact").select(
            "licensee_id, brand_id, total_case, total_btl, sale_date, depots(name), brands(brand_id, brand_name, company_id, companies(company_name))"
        ).eq("licensee_id", licensee_id).gte("sale_date", d_from).lte("sale_date", d_to).execute()

        sales_records = sf_res.data or []

        brand_map: Dict[str, Dict[str, Any]] = {}

        for sf in sales_records:
            brand_obj = sf.get("brands") or {}
            comp_obj = brand_obj.get("companies") if isinstance(brand_obj, dict) else {}
            cname = comp_obj.get("company_name", "") if isinstance(comp_obj, dict) else ""

            # Exclude company 'Others'
            if cname and cname.lower().strip() == "others":
                continue

            depot_obj = sf.get("depots") or {}
            dname = depot_obj.get("name") if isinstance(depot_obj, dict) else None

            # Filter by depot if specified
            if depot_name and dname and dname.lower() != depot_name.lower():
                continue

            bid = brand_obj.get("brand_id") or sf.get("brand_id")
            bname = brand_obj.get("brand_name") or "Unknown Brand"

            if not bid:
                continue

            if bid not in brand_map:
                brand_map[bid] = {
                    "brand_id": str(bid),
                    "brand_name": bname,
                    "company_name": cname or "Other",
                    "total_cases": 0.0,
                    "total_bottles": 0.0,
                    "sales_depots": set()
                }

            if dname:
                brand_map[bid]["sales_depots"].add(dname)

            brand_map[bid]["total_cases"] += float(sf.get("total_case") or 0)
            brand_map[bid]["total_bottles"] += float(sf.get("total_btl") or 0)

        results = []
        for bid, item in brand_map.items():
            results.append({
                "brand_id": item["brand_id"],
                "brand_name": item["brand_name"],
                "company_name": item["company_name"],
                "total_cases": round(item["total_cases"], 2),
                "total_bottles": round(item["total_bottles"], 2),
                "sales_depots": sorted(list(item["sales_depots"]))
            })

        results.sort(key=lambda x: x["total_cases"], reverse=True)
        return results

    except Exception as e:
        logger.error(f"Error in get_licensee_brand_sales: {e}", exc_info=True)
        return []
