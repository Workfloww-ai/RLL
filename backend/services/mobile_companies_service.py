import logging
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from backend.db.supabase_client import get_supabase_client
from backend.services.company_cascading_service import is_others_company
from backend.db.company_aliases import normalize_company_name, is_pinned_company

logger = logging.getLogger(__name__)

# Master metadata in-memory cache with 5-minute (300s) TTL to reduce DB roundtrips
_TTL = 300

_HQ_CACHE: Tuple[float, Dict[str, str]] = (0.0, {})
_MAX_DATE_CACHE: Tuple[float, str] = (0.0, "")
_MASTER_COMPANIES_CACHE: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
_MASTER_BRANDS_CACHE: Tuple[float, Dict[str, List[Dict[str, Any]]]] = (0.0, {})


def _get_hq_lookup() -> Dict[str, str]:
    global _HQ_CACHE
    now = time.time()
    if _HQ_CACHE[1] and (now - _HQ_CACHE[0]) < _TTL:
        return _HQ_CACHE[1]

    client = get_supabase_client()
    hq_map = {}
    if client:
        try:
            res = client.table("headquarters").select("headquarters_id, name").execute()
            for h in (res.data or []):
                if h.get("headquarters_id") and h.get("name"):
                    hq_map[str(h["name"]).strip().lower()] = str(h["headquarters_id"])
            _HQ_CACHE = (now, hq_map)
        except Exception as e:
            logger.warning(f"_get_hq_lookup error: {e}")
    return hq_map or _HQ_CACHE[1]


def _get_latest_sale_date() -> str:
    global _MAX_DATE_CACHE
    now = time.time()
    if _MAX_DATE_CACHE[1] and (now - _MAX_DATE_CACHE[0]) < _TTL:
        return _MAX_DATE_CACHE[1]

    client = get_supabase_client()
    target_date = ""
    if client:
        try:
            res = client.table("sales_daily_summary").select("sale_date").order("sale_date", desc=True).limit(1).execute()
            if res.data and res.data[0].get("sale_date"):
                target_date = str(res.data[0]["sale_date"])
                _MAX_DATE_CACHE = (now, target_date)
        except Exception as e:
            logger.warning(f"_get_latest_sale_date error: {e}")

    if not target_date:
        target_date = datetime.utcnow().strftime("%Y-%m-%d")
    return target_date


def _get_master_companies() -> List[Dict[str, Any]]:
    global _MASTER_COMPANIES_CACHE
    now = time.time()
    if _MASTER_COMPANIES_CACHE[1] and (now - _MASTER_COMPANIES_CACHE[0]) < _TTL:
        return _MASTER_COMPANIES_CACHE[1]

    client = get_supabase_client()
    comp_list = []
    if client:
        try:
            res = client.table("companies").select("company_id, company_name").execute()
            comp_list = res.data or []
            _MASTER_COMPANIES_CACHE = (now, comp_list)
        except Exception as e:
            logger.warning(f"_get_master_companies error: {e}")
    return comp_list or _MASTER_COMPANIES_CACHE[1]


def _get_master_brands_by_company() -> Dict[str, List[Dict[str, Any]]]:
    global _MASTER_BRANDS_CACHE
    now = time.time()
    if _MASTER_BRANDS_CACHE[1] and (now - _MASTER_BRANDS_CACHE[0]) < _TTL:
        return _MASTER_BRANDS_CACHE[1]

    client = get_supabase_client()
    brands_map: Dict[str, List[Dict[str, Any]]] = {}
    if client:
        try:
            res = client.table("brands").select("brand_id, brand_name, company_id").execute()
            for mb in (res.data or []):
                cid = str(mb.get("company_id") or "")
                bid = str(mb.get("brand_id") or "")
                bname = str(mb.get("brand_name") or "Generic Brand").strip()
                if cid and bid:
                    if cid not in brands_map:
                        brands_map[cid] = []
                    brands_map[cid].append({"brand_id": bid, "brand_name": bname})
            _MASTER_BRANDS_CACHE = (now, brands_map)
        except Exception as e:
            logger.warning(f"_get_master_brands_by_company error: {e}")
    return brands_map or _MASTER_BRANDS_CACHE[1]


async def get_companies_summary_async(
    period: str = "Daily",
    date_to: Optional[str] = None,
    selected_hq: Optional[str] = None,
    company_name: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Asynchronous, period-optimized Companies sales analytics service.
    Excludes company 'Others' strictly. Supports single company scoping.
    Executes RPC calls concurrently and caches master data in-memory.
    """
    t_start = time.perf_counter()
    client = get_supabase_client()
    if not client:
        logger.error("get_companies_summary_async: Supabase client unavailable.")
        return [], date_to or datetime.utcnow().strftime("%Y-%m-%d")

    clean_period = period.strip() if period else "Daily"
    if clean_period not in ("Daily", "MTD", "YTD"):
        clean_period = "Daily"

    # 1. Resolve HQ filter if provided
    hq_id_filter = None
    if selected_hq and selected_hq.strip() and selected_hq.strip() != "All Headquarters":
        hq_map = _get_hq_lookup()
        clean_hq_target = selected_hq.strip().lower()
        for h_name, h_id in hq_map.items():
            if h_name == clean_hq_target or clean_hq_target in h_name or h_name in clean_hq_target:
                hq_id_filter = h_id
                break

    # 2. Determine target dates
    target_date = date_to
    if not target_date:
        target_date = _get_latest_sale_date()

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.utcnow().date()
        target_date = dt.strftime("%Y-%m-%d")

    mtd_start = dt.replace(day=1).strftime("%Y-%m-%d")
    fy_year = dt.year if dt.month >= 4 else dt.year - 1
    ytd_start = f"{fy_year}-04-01"

    # Period Slicing Optimization: Tailor date parameters based on active period to prevent scan overflow
    if clean_period == "Daily":
        effective_mtd_start = target_date
        effective_ytd_start = target_date
    elif clean_period == "MTD":
        effective_mtd_start = mtd_start
        effective_ytd_start = mtd_start
    else:  # YTD
        effective_mtd_start = mtd_start
        effective_ytd_start = ytd_start

    # Build RPC parameters
    comp_rpc_params = {
        "p_target_date": target_date,
        "p_mtd_start": effective_mtd_start,
        "p_ytd_start": effective_ytd_start,
    }
    if hq_id_filter:
        comp_rpc_params["p_hq_id"] = hq_id_filter
    if company_name:
        comp_rpc_params["p_company_name"] = company_name.strip()

    # Pre-fetch master companies to ensure all active companies appear in grid
    mc_data = _get_master_companies()
    grouped_companies = {}
    for mc in mc_data:
        cid = str(mc.get("company_id") or "")
        cname = str(mc.get("company_name") or "").strip()
        if not cname or is_others_company(cname):
            continue
        if company_name and cname.lower() != company_name.strip().lower():
            continue
        norm_name = normalize_company_name(cname)
        norm_key = norm_name.lower().replace(" ", "-").replace("/", "-")
        if norm_key not in grouped_companies:
            grouped_companies[norm_key] = {
                "id": norm_key,
                "name": norm_name,
                "isPinned": is_pinned_company(norm_name, norm_key),
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

    # Collect ALL company UUIDs across grouped_companies for brand RPC parameter
    all_company_ids = []
    cid_to_norm_key = {}
    for norm_key, g in grouped_companies.items():
        for cid in g["company_ids"]:
            cid_clean = str(cid).strip().lower()
            if cid_clean and cid_clean not in all_company_ids:
                all_company_ids.append(cid_clean)
            if cid_clean:
                cid_to_norm_key[cid_clean] = norm_key

    brand_rpc_params = {
        "p_company_ids": all_company_ids,
        "p_target_date": target_date,
        "p_mtd_start": effective_mtd_start,
        "p_ytd_start": effective_ytd_start,
    }
    if hq_id_filter:
        brand_rpc_params["p_hq_id"] = hq_id_filter

    # 3. Execute Company RPC and Brand RPC concurrently via asyncio.gather
    def _fetch_company_summary():
        t0 = time.perf_counter()
        try:
            res = client.rpc("get_mobile_companies_summary", comp_rpc_params).execute()
            data = res.data or []
            logger.info(f"get_mobile_companies_summary RPC took {(time.perf_counter()-t0)*1000:.2f} ms ({len(data)} rows)")
            return data
        except Exception as e:
            logger.error(f"Error executing get_mobile_companies_summary RPC: {e}")
            return []

    def _fetch_brand_summary():
        if not all_company_ids:
            return []
        t0 = time.perf_counter()
        try:
            res = client.rpc("get_mobile_company_brands_summary", brand_rpc_params).execute()
            data = res.data or []
            logger.info(f"get_mobile_company_brands_summary RPC took {(time.perf_counter()-t0)*1000:.2f} ms ({len(data)} rows)")
            return data
        except Exception as e:
            logger.error(f"Error executing get_mobile_company_brands_summary RPC: {e}")
            return []

    comp_summary_data, all_brands_data = await asyncio.gather(
        asyncio.to_thread(_fetch_company_summary),
        asyncio.to_thread(_fetch_brand_summary)
    )

    # Process Company Summary Aggregation
    for row in comp_summary_data:
        cid = str(row.get("company_id") or "")
        cname = str(row.get("company_name") or "").strip()
        if not cname or is_others_company(cname):
            continue

        norm_name = normalize_company_name(cname)
        norm_key = norm_name.lower().replace(" ", "-").replace("/", "-")

        if norm_key not in grouped_companies:
            grouped_companies[norm_key] = {
                "id": norm_key,
                "name": norm_name,
                "isPinned": is_pinned_company(norm_name, norm_key),
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

    # Process Brand Summaries by Company
    master_brands_by_company = _get_master_brands_by_company()

    brands_by_company: Dict[str, List[Dict[str, Any]]] = {}
    for b in all_brands_data:
        raw_cid = str(b.get("company_id") or "").strip().lower()
        norm_key = cid_to_norm_key.get(raw_cid)
        if norm_key:
            if norm_key not in brands_by_company:
                brands_by_company[norm_key] = []
            brands_by_company[norm_key].append(b)

    response_list = []
    for norm_key, g in grouped_companies.items():
        brands_data = brands_by_company.get(norm_key, [])

        comp_brands_map = {}
        # Pre-populate with all master registered brands for this company (cases = 0)
        for cid in g["company_ids"]:
            for mb in master_brands_by_company.get(str(cid).strip().lower(), []):
                bid = str(mb["brand_id"]).strip().lower()
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
            bid = str(b.get("brand_id") or "").strip().lower()
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
    logger.info(f"get_companies_summary_async total execution time: {(time.perf_counter()-t_start)*1000:.2f} ms")
    return response_list, target_date


def get_companies_summary(
    period: str = "Daily",
    date_to: Optional[str] = None,
    selected_hq: Optional[str] = None,
    company_name: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """Synchronous fallback wrapper for get_companies_summary_async."""
    return asyncio.run(get_companies_summary_async(period, date_to, selected_hq, company_name))
