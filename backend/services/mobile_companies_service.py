import logging
import collections
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

def get_companies_summary(
    period: str = "Daily",
    date_to: Optional[str] = None,
    selected_hq: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Period-specific Companies sales analytics service.
    Excludes company 'Others' strictly.
    Returns list of company objects structured for mobile UI.
    """
    client = get_supabase_client()
    if not client:
        logger.error("get_companies_summary: Supabase client unavailable.")
        return []

    clean_period = period.strip() if period else "Daily"
    if clean_period not in ("Daily", "MTD", "YTD"):
        clean_period = "Daily"

    # 1. Resolve master maps (companies, brands, headquarters)
    comp_res = client.table("companies").select("company_id, company_name").execute()
    companies_map: Dict[str, str] = {}
    excluded_comp_ids = set()

    for c in (comp_res.data or []):
        cid = str(c["company_id"])
        cname = str(c.get("company_name", "")).strip()
        if not cname or cname.lower() == "others":
            excluded_comp_ids.add(cid)
            continue
        companies_map[cid] = cname

    brand_res = client.table("brands").select("brand_id, brand_name, company_id").execute()
    brand_comp_map: Dict[str, str] = {}
    brand_name_map: Dict[str, str] = {}

    for b in (brand_res.data or []):
        bid = str(b["brand_id"])
        cid = str(b.get("company_id") or "")
        bname = str(b.get("brand_name", "")).strip()
        brand_comp_map[bid] = cid
        brand_name_map[bid] = bname or f"Brand {bid[:8]}"

    # Resolve HQ filter if provided
    hq_id_filter = None
    if selected_hq and selected_hq != "All Headquarters":
        hq_res = client.table("headquarters").select("headquarters_id").ilike("name", selected_hq.strip()).execute()
        if hq_res.data:
            hq_id_filter = hq_res.data[0]["headquarters_id"]

    # 2. Determine target dates
    target_date = date_to
    if not target_date:
        max_res = client.table("sales_monthly_summary").select("month_start").order("month_start", desc=True).limit(1).execute()
        if max_res.data and max_res.data[0].get("month_start"):
            target_date = max_res.data[0]["month_start"]
        else:
            target_date = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.utcnow().date()
        target_date = dt.strftime("%Y-%m-%d")

    mtd_start = dt.replace(day=1).strftime("%Y-%m-%d")

    # 3. Query appropriate summary table based on period
    company_totals = collections.defaultdict(lambda: {"cases": 0.0, "bottles": 0.0})
    brand_totals = collections.defaultdict(lambda: {"cases": 0.0, "bottles": 0.0})

    if clean_period == "Daily":
        # Check if target_date exists in sales_daily_summary, otherwise fallback to latest available sale_date
        effective_date = target_date
        check_res = client.table("sales_daily_summary").select("sale_date").eq("sale_date", target_date).limit(1).execute()
        if not (check_res.data and len(check_res.data) > 0):
            latest_res = client.table("sales_daily_summary").select("sale_date").order("sale_date", desc=True).limit(1).execute()
            if latest_res.data and latest_res.data[0].get("sale_date"):
                effective_date = latest_res.data[0]["sale_date"]

        offset = 0
        limit = 2000
        while True:
            q = client.table("sales_daily_summary").select("company_id, brand_id, total_cases, total_bottles").eq("sale_date", effective_date)
            if hq_id_filter:
                q = q.eq("headquarters_id", hq_id_filter)
            res = q.range(offset, offset + limit - 1).execute()
            batch = res.data or []
            for r in batch:
                cid = str(r.get("company_id") or "")
                bid = str(r.get("brand_id") or "")
                if cid in excluded_comp_ids or (bid and brand_comp_map.get(bid) in excluded_comp_ids):
                    continue
                if not cid and bid:
                    cid = brand_comp_map.get(bid, "")
                if cid in excluded_comp_ids:
                    continue

                cases = float(r.get("total_cases") or 0.0)
                bottles = float(r.get("total_bottles") or 0.0)

                company_totals[cid]["cases"] += cases
                company_totals[cid]["bottles"] += bottles

                if bid:
                    key = (cid, bid)
                    brand_totals[key]["cases"] += cases
                    brand_totals[key]["bottles"] += bottles

            if len(batch) < limit:
                break
            offset += limit
            if offset > 100000:
                break

    elif clean_period in ("MTD", "YTD"):
        offset = 0
        limit = 2000
        while True:
            q = client.table("sales_monthly_summary").select("company_id, brand_id, total_cases, total_bottles")
            if clean_period == "MTD":
                q = q.eq("month_start", mtd_start)
            else:
                fy_year = dt.year if dt.month >= 4 else dt.year - 1
                ytd_start = f"{fy_year}-04-01"
                q = q.gte("month_start", ytd_start).lte("month_start", mtd_start)

            if hq_id_filter:
                q = q.eq("headquarters_id", hq_id_filter)

            res = q.range(offset, offset + limit - 1).execute()
            batch = res.data or []
            for r in batch:
                cid = str(r.get("company_id") or "")
                bid = str(r.get("brand_id") or "")
                if cid in excluded_comp_ids or (bid and brand_comp_map.get(bid) in excluded_comp_ids):
                    continue
                if not cid and bid:
                    cid = brand_comp_map.get(bid, "")
                if cid in excluded_comp_ids:
                    continue

                cases = float(r.get("total_cases") or 0.0)
                bottles = float(r.get("total_bottles") or 0.0)

                company_totals[cid]["cases"] += cases
                company_totals[cid]["bottles"] += bottles

                if bid:
                    key = (cid, bid)
                    brand_totals[key]["cases"] += cases
                    brand_totals[key]["bottles"] += bottles

            if len(batch) < limit:
                break
            offset += limit
            if offset > 300000:
                break

    # 4. Construct response objects structured for Company interface
    response_list = []
    for cid, cname in companies_map.items():
        if cid in excluded_comp_ids:
            continue

        c_cases = round(company_totals[cid]["cases"], 2)
        c_bottles = round(company_totals[cid]["bottles"], 2)

        comp_brands = []
        for (b_cid, bid), b_metrics in brand_totals.items():
            if b_cid == cid:
                b_name = brand_name_map.get(bid, f"Brand {bid[:8]}")
                b_cases = round(b_metrics["cases"], 2)
                b_btls = round(b_metrics["bottles"], 2)
                comp_brands.append({
                    "id": bid,
                    "name": b_name,
                    "cases": b_cases,
                    "bottles": b_btls,
                    "data": {
                        clean_period: {"cases": b_cases, "bottles": b_btls, "bl": 0.0}
                    }
                })

        comp_brands.sort(key=lambda x: x["cases"], reverse=True)

        c_key = cname.lower().replace(" ", "-").replace("/", "-")
        is_pinned = c_key in ("rll", "diageo-inbrew") or cname.upper() == "RLL"

        response_list.append({
            "id": c_key,
            "company_id": cid,
            "name": cname,
            "isPinned": is_pinned,
            "hqLocation": selected_hq or "All Headquarters",
            "cases": c_cases,
            "bottles": c_bottles,
            "data": {
                clean_period: {"cases": c_cases, "bottles": c_bottles, "bl": 0.0}
            },
            "brands": comp_brands
        })

    response_list.sort(key=lambda x: (not x["isPinned"], -x["cases"]))
    return response_list
