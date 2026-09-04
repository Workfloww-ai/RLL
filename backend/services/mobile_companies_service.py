import logging
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
    Uses sales_daily_summary as the single source of truth.
    """
    client = get_supabase_client()
    if not client:
        logger.error("get_companies_summary: Supabase client unavailable.")
        return []

    clean_period = period.strip() if period else "Daily"
    if clean_period not in ("Daily", "MTD", "YTD"):
        clean_period = "Daily"

    # Resolve HQ filter if provided
    hq_id_filter = None
    if selected_hq and selected_hq != "All Headquarters":
        hq_res = client.table("headquarters").select("headquarters_id").ilike("name", selected_hq.strip()).execute()
        if hq_res.data:
            hq_id_filter = hq_res.data[0]["headquarters_id"]

    # Determine target dates
    target_date = date_to
    if not target_date:
        # Get latest sale date from daily summary
        max_res = client.table("sales_daily_summary").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if max_res.data and max_res.data[0].get("sale_date"):
            target_date = max_res.data[0]["sale_date"]
        else:
            target_date = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.utcnow().date()
        target_date = dt.strftime("%Y-%m-%d")

    mtd_start = dt.replace(day=1).strftime("%Y-%m-%d")
    fy_year = dt.year if dt.month >= 4 else dt.year - 1
    ytd_start = f"{fy_year}-04-01"

    # 1. Call Canonical Company Summary RPC
    rpc_params = {
        "p_target_date": target_date,
        "p_mtd_start": mtd_start,
        "p_ytd_start": ytd_start,
    }
    if hq_id_filter:
        rpc_params["p_hq_id"] = hq_id_filter

    try:
        comp_summary_res = client.rpc("get_mobile_companies_summary", rpc_params).execute()
        comp_summary_data = comp_summary_res.data or []
    except Exception as e:
        logger.error(f"Error calling get_mobile_companies_summary RPC: {e}")
        return []

    # 2. Company Aliases Normalization (Willam vs William)
    COMPANY_ALIASES = {
        "willam grants": "William Grants",
        "william grants": "William Grants",
        "william grants & sons": "William Grants"
    }

    # 2. Fetch all registered master companies to ensure all companies are shown irrespective of HQ sales
    grouped_companies = {}
    try:
        mc_res = client.table("companies").select("company_id, company_name").execute()
        for mc in (mc_res.data or []):
            cid = str(mc.get("company_id") or "")
            cname = str(mc.get("company_name") or "").strip()
            if not cname or cname.lower() == "others":
                continue
            norm_name = COMPANY_ALIASES.get(cname.lower(), cname)
            norm_key = norm_name.lower().replace(" ", "-").replace("/", "-")
            if norm_key not in grouped_companies:
                grouped_companies[norm_key] = {
                    "id": norm_key,
                    "name": norm_name,
                    "isPinned": norm_key in ("rll", "diageo-inbrew") or norm_name.upper() == "RLL",
                    "hqLocation": selected_hq or "All Headquarters",
                    "company_ids": [],
                    "daily_cases": 0.0,
                    "daily_bottles": 0.0,
                    "daily_bl": 0.0,
                    "mtd_cases": 0.0,
                    "mtd_bottles": 0.0,
                    "mtd_bl": 0.0,
                    "ytd_cases": 0.0,
                    "ytd_bottles": 0.0,
                    "ytd_bl": 0.0,
                }
            if cid and cid not in grouped_companies[norm_key]["company_ids"]:
                grouped_companies[norm_key]["company_ids"].append(cid)
    except Exception as e_mc:
        logger.warning(f"Error fetching master companies: {e_mc}")

    for row in comp_summary_data:
        cid = str(row.get("company_id") or "")
        cname = str(row.get("company_name") or "").strip()
        if not cname or cname.lower() == "others":
            continue

        norm_name = COMPANY_ALIASES.get(cname.lower(), cname)
        norm_key = norm_name.lower().replace(" ", "-").replace("/", "-")

        if norm_key not in grouped_companies:
            grouped_companies[norm_key] = {
                "id": norm_key,
                "name": norm_name,
                "isPinned": norm_key in ("rll", "diageo-inbrew") or norm_name.upper() == "RLL",
                "hqLocation": selected_hq or "All Headquarters",
                "company_ids": [cid] if cid else [],
                "daily_cases": 0.0,
                "daily_bottles": 0.0,
                "daily_bl": 0.0,
                "mtd_cases": 0.0,
                "mtd_bottles": 0.0,
                "mtd_bl": 0.0,
                "ytd_cases": 0.0,
                "ytd_bottles": 0.0,
                "ytd_bl": 0.0,
            }
        else:
            if cid and cid not in grouped_companies[norm_key]["company_ids"]:
                grouped_companies[norm_key]["company_ids"].append(cid)

        g = grouped_companies[norm_key]
        g["daily_cases"] += float(row.get("daily_cases") or 0.0)
        g["daily_bottles"] += float(row.get("daily_bottles") or 0.0)
        g["daily_bl"] += float(row.get("daily_bl") or 0.0)
        g["mtd_cases"] += float(row.get("mtd_cases") or 0.0)
        g["mtd_bottles"] += float(row.get("mtd_bottles") or 0.0)
        g["mtd_bl"] += float(row.get("mtd_bl") or 0.0)
        g["ytd_cases"] += float(row.get("ytd_cases") or 0.0)
        g["ytd_bottles"] += float(row.get("ytd_bottles") or 0.0)
        g["ytd_bl"] += float(row.get("ytd_bl") or 0.0)

    # 3. Fetch master brands per company to ensure 0-sale brands are included in brand count and drilldown
    master_brands_by_company = {}
    try:
        mb_res = client.table("brands").select("brand_id, brand_name, company_id").execute()
        for mb in (mb_res.data or []):
            cid = str(mb.get("company_id") or "")
            bid = str(mb.get("brand_id") or "")
            bname = str(mb.get("brand_name") or "Generic Brand").strip()
            if cid and bid:
                if cid not in master_brands_by_company:
                    master_brands_by_company[cid] = []
                master_brands_by_company[cid].append({"brand_id": bid, "brand_name": bname})
    except Exception as e_mb:
        logger.warning(f"Error fetching master_brands_by_company: {e_mb}")

    response_list = []
    for norm_key, g in grouped_companies.items():
        brand_params = {
            "p_company_ids": g["company_ids"],
            "p_target_date": target_date,
            "p_mtd_start": mtd_start,
            "p_ytd_start": ytd_start,
        }
        if hq_id_filter:
            brand_params["p_hq_id"] = hq_id_filter

        try:
            brand_res = client.rpc("get_mobile_company_brands_summary", brand_params).execute()
            brands_data = brand_res.data or []
        except Exception as e_brands:
            logger.error(f"Error calling get_mobile_company_brands_summary RPC for {g['name']}: {e_brands}")
            brands_data = []

        comp_brands_map = {}
        # Pre-populate with all master registered brands for this company (cases = 0)
        for cid in g["company_ids"]:
            for mb in master_brands_by_company.get(cid, []):
                bid = mb["brand_id"]
                if bid not in comp_brands_map:
                    comp_brands_map[bid] = {
                        "id": bid,
                        "name": mb["brand_name"],
                        "cases": 0.0,
                        "bottles": 0.0,
                        "data": {
                            "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                            "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                            "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        }
                    }

        for b in brands_data:
            bid = str(b.get("brand_id") or "")
            bname = str(b.get("brand_name") or "Generic Brand").strip()
            
            b_daily_cases = float(b.get("daily_cases") or 0.0)
            b_daily_bottles = float(b.get("daily_bottles") or 0.0)
            b_daily_bl = float(b.get("daily_bl") or 0.0)
            
            b_mtd_cases = float(b.get("mtd_cases") or 0.0)
            b_mtd_bottles = float(b.get("mtd_bottles") or 0.0)
            b_mtd_bl = float(b.get("mtd_bl") or 0.0)
            
            b_ytd_cases = float(b.get("ytd_cases") or 0.0)
            b_ytd_bottles = float(b.get("ytd_bottles") or 0.0)
            b_ytd_bl = float(b.get("ytd_bl") or 0.0)

            if clean_period == "Daily":
                b_cases = round(b_daily_cases, 2)
                b_btls = round(b_daily_bottles, 2)
            elif clean_period == "MTD":
                b_cases = round(b_mtd_cases, 2)
                b_btls = round(b_mtd_bottles, 2)
            else:
                b_cases = round(b_ytd_cases, 2)
                b_btls = round(b_ytd_bottles, 2)

            if bid not in comp_brands_map:
                comp_brands_map[bid] = {
                    "id": bid,
                    "name": bname,
                    "cases": b_cases,
                    "bottles": b_btls,
                    "data": {
                        "Daily": {"cases": round(b_daily_cases, 2), "bottles": round(b_daily_bottles, 2), "bl": round(b_daily_bl, 2)},
                        "MTD": {"cases": round(b_mtd_cases, 2), "bottles": round(b_mtd_bottles, 2), "bl": round(b_mtd_bl, 2)},
                        "YTD": {"cases": round(b_ytd_cases, 2), "bottles": round(b_ytd_bottles, 2), "bl": round(b_ytd_bl, 2)},
                    }
                }
            else:
                entry = comp_brands_map[bid]
                entry["cases"] += b_cases
                entry["bottles"] += b_btls
                entry["data"]["Daily"]["cases"] += round(b_daily_cases, 2)
                entry["data"]["Daily"]["bottles"] += round(b_daily_bottles, 2)
                entry["data"]["Daily"]["bl"] += round(b_daily_bl, 2)
                entry["data"]["MTD"]["cases"] += round(b_mtd_cases, 2)
                entry["data"]["MTD"]["bottles"] += round(b_mtd_bottles, 2)
                entry["data"]["MTD"]["bl"] += round(b_mtd_bl, 2)
                entry["data"]["YTD"]["cases"] += round(b_ytd_cases, 2)
                entry["data"]["YTD"]["bottles"] += round(b_ytd_bottles, 2)
                entry["data"]["YTD"]["bl"] += round(b_ytd_bl, 2)

        comp_brands = list(comp_brands_map.values())
        comp_brands.sort(key=lambda x: x["cases"], reverse=True)

        if clean_period == "Daily":
            p_cases = g["daily_cases"]
            p_bottles = g["daily_bottles"]
        elif clean_period == "MTD":
            p_cases = g["mtd_cases"]
            p_bottles = g["mtd_bottles"]
        else:
            p_cases = g["ytd_cases"]
            p_bottles = g["ytd_bottles"]

        response_list.append({
            "id": g["id"],
            "company_id": g["company_ids"][0] if g["company_ids"] else None,
            "name": g["name"],
            "isPinned": g["isPinned"],
            "hqLocation": g["hqLocation"],
            "cases": round(p_cases, 2),
            "bottles": round(p_bottles, 2),
            "data": {
                "Daily": {"cases": round(g["daily_cases"], 2), "bottles": round(g["daily_bottles"], 2), "bl": round(g["daily_bl"], 2)},
                "MTD": {"cases": round(g["mtd_cases"], 2), "bottles": round(g["mtd_bottles"], 2), "bl": round(g["mtd_bl"], 2)},
                "YTD": {"cases": round(g["ytd_cases"], 2), "bottles": round(g["ytd_bottles"], 2), "bl": round(g["ytd_bl"], 2)},
            },
            "brands": comp_brands
        })

    response_list.sort(key=lambda x: (not x["isPinned"], -x["cases"]))
    return response_list
