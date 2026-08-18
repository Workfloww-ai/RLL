"""
Mobile Sales Service
Encapsulates all business logic for the /mobile/sales endpoint.
Reads pre-aggregated rows from the PostgreSQL RPC and maps them
into the company / depot / TSM response structure.
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.db.supabase_client import call_mobile_sales_rpc, call_mobile_sales_rpc_v3, get_supabase_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response Cache (TTL-based, keyed by query params)
# ---------------------------------------------------------------------------
_SALES_CACHE: Dict[str, Tuple[float, Any]] = {}
_SALES_CACHE_TTL = 120.0  # 2 minutes


def _cache_get(key: str) -> Optional[Any]:
    if key in _SALES_CACHE:
        ts, data = _SALES_CACHE[key]
        if time.time() - ts < _SALES_CACHE_TTL:
            return data
        del _SALES_CACHE[key]
    return None


def _cache_set(key: str, data: Any) -> None:
    _SALES_CACHE[key] = (time.time(), data)


def invalidate_sales_cache() -> None:
    """Call this after a data upload to force fresh data on next request."""
    _SALES_CACHE.clear()


# ---------------------------------------------------------------------------
# Master Data Cache (companies, brands, depots, HQ — cached 10 min)
# ---------------------------------------------------------------------------
_MASTER_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "comp_db": [],
    "brand_db": [],
    "depot_db": [],
    "hq_db": [],
    "companies_by_id": {},
    "brands_by_id": {},
    "depots_by_id": {},
    "hq_by_id": {},
    "hq_by_name_lower": {},
    "latest_sale_date": None,
}
_MASTER_CACHE_TTL = 600.0  # 10 minutes


def _normalize_id(value: str) -> str:
    if not value:
        return ""
    return value.lower().replace(" ", "-").replace("/", "-")


def _load_master_data(client) -> Dict[str, Any]:
    now = time.time()
    if now - _MASTER_CACHE["timestamp"] < _MASTER_CACHE_TTL and _MASTER_CACHE["comp_db"]:
        return _MASTER_CACHE
    try:
        comp_db = client.table("companies").select("company_id, company_name, is_active").eq("is_active", True).execute().data or []
        brand_db = client.table("brands").select("brand_id, brand_name, company_id, is_active").eq("is_active", True).execute().data or []
        depot_db = client.table("depots").select("depot_id, name, headquarters_id").execute().data or []
        hq_db = client.table("headquarters").select("headquarters_id, name").execute().data or []

        _MASTER_CACHE.update({
            "timestamp": now,
            "comp_db": comp_db,
            "brand_db": brand_db,
            "depot_db": depot_db,
            "hq_db": hq_db,
            "companies_by_id": {str(c["company_id"]): c for c in comp_db if c.get("company_id")},
            "brands_by_id": {str(b["brand_id"]): b for b in brand_db if b.get("brand_id")},
            "depots_by_id": {str(d["depot_id"]): d for d in depot_db if d.get("depot_id")},
            "hq_by_id": {str(h["headquarters_id"]): h for h in hq_db if h.get("headquarters_id")},
            "hq_by_name_lower": {h["name"].lower(): str(h["headquarters_id"]) for h in hq_db if h.get("name")},
        })
    except Exception as e:
        logger.warning(f"_load_master_data: Error refreshing master cache: {e}")
    return _MASTER_CACHE


def _resolve_target_date(client, date_from: Optional[str], date_to: Optional[str]) -> str:
    """Returns the best target date from params or the latest available sale date."""
    for d in [date_to, date_from]:
        if d and isinstance(d, str) and d.strip():
            return d.strip()
    # Fetch latest from DB (cached in master cache)
    now = time.time()
    cached = _MASTER_CACHE.get("latest_sale_date")
    if not cached or (now - _MASTER_CACHE["timestamp"] > _MASTER_CACHE_TTL):
        try:
            res = client.table("dashboard_summary_daily").select("sale_date").order("sale_date", desc=True).limit(1).execute()
            if res.data and res.data[0].get("sale_date"):
                cached = res.data[0]["sale_date"]
                _MASTER_CACHE["latest_sale_date"] = cached
        except Exception as e:
            logger.warning(f"_resolve_target_date: Could not fetch max sale_date: {e}")
    return cached or time.strftime("%Y-%m-%d")


def _period_start(period: str, target_date: str) -> str:
    if period == "Daily":
        return target_date
    elif period == "MTD":
        return target_date[:7] + "-01"
    else:  # YTD
        year = int(target_date[:4])
        month = int(target_date[5:7])
        fy_year = year if month >= 4 else year - 1
        return f"{fy_year:04d}-04-01"


# ---------------------------------------------------------------------------
# Core Aggregation — maps RPC rows → companies / depots / TSMs
# ---------------------------------------------------------------------------

def build_sales_response(
    period: str,
    date_from: Optional[str],
    date_to: Optional[str],
    selected_hq: str,
) -> Dict[str, Any]:
    """
    Main entry point for /mobile/sales.
    1. Resolves dates & HQ filter.
    2. Checks response cache.
    3. Calls PostgreSQL RPC (single round-trip, DB-side GROUP BY).
    4. Maps aggregated rows into companies / depots / TSMs.
    5. Stores result in response cache.
    """
    t_start = time.perf_counter()
    client = get_supabase_client()

    # ── Date & HQ resolution ────────────────────────────────────────────────
    target_date = _resolve_target_date(client, date_from, date_to)
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.utcnow().date()
        target_date = dt.strftime("%Y-%m-%d")

    mtd_start = dt.replace(day=1).strftime("%Y-%m-%d")
    fy_year = dt.year if dt.month >= 4 else dt.year - 1
    ytd_start = f"{fy_year}-04-01"

    master = _load_master_data(client)
    companies_by_id = master["companies_by_id"]
    brands_by_id    = master["brands_by_id"]
    depots_by_id    = master["depots_by_id"]
    hq_by_id        = master["hq_by_id"]
    hq_by_name_lower = master["hq_by_name_lower"]

    selected_hq_id: Optional[str] = None
    if selected_hq != "All Headquarters":
        selected_hq_id = hq_by_name_lower.get(selected_hq.lower())

    # ── Response cache check ────────────────────────────────────────────────
    cache_key = f"{period}:{selected_hq}:{target_date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"build_sales_response: cache HIT — key={cache_key}")
        return cached

    # ── RPC call (single DB round-trip) ─────────────────────────────────────
    t_rpc = time.perf_counter()
    rows = call_mobile_sales_rpc_v3(target_date, mtd_start, ytd_start, selected_hq_id)
    t_rpc_ms = (time.perf_counter() - t_rpc) * 1000

    # If no data for target date, fall back to latest available date
    if not rows and _MASTER_CACHE.get("latest_sale_date") and target_date != _MASTER_CACHE.get("latest_sale_date"):
        fallback = _MASTER_CACHE["latest_sale_date"]
        try:
            fb_dt = datetime.strptime(fallback, "%Y-%m-%d").date()
            fb_mtd = fb_dt.replace(day=1).strftime("%Y-%m-%d")
            fb_fy = fb_dt.year if fb_dt.month >= 4 else fb_dt.year - 1
            fb_ytd = f"{fb_fy}-04-01"
            rows = call_mobile_sales_rpc_v3(fallback, fb_mtd, fb_ytd, selected_hq_id)
            if rows:
                target_date = fallback
        except Exception:
            pass

    # ── Aggregation maps ────────────────────────────────────────────────────
    companies_map: Dict[str, Dict] = {}
    depots_map: Dict[str, Dict] = {}
    tsms_map: Dict[str, Dict] = {}

    # Pre-seed companies from master so companies with 0 sales still appear
    for c in master["comp_db"]:
        c_name = c.get("company_name") or ""
        if not c_name or c_name == "Others":
            continue
        c_id = _normalize_id(c_name)
        companies_map[c_id] = {
            "id": c_id,
            "company_id": str(c["company_id"]),
            "company_name": c_name,
            "name": c_name,
            "is_active": c.get("is_active", True),
            "isPinned": c_id in ["rll", "diageo-inbrew"],
            "hqLocation": "Jaipur",
            "data": {
                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
            },
            "brands_map": {},
        }

    t_agg = time.perf_counter()
    for row in rows:
        comp_uuid  = str(row.get("company_id") or "")
        brand_uuid = str(row.get("brand_id") or "")
        depot_uuid = str(row.get("depot_id") or "")
        hq_uuid    = str(row.get("headquarters_id") or "")

        comp_meta  = companies_by_id.get(comp_uuid) or {}
        brand_meta = brands_by_id.get(brand_uuid) or {}
        depot_meta = depots_by_id.get(depot_uuid) or {}
        hq_meta    = hq_by_id.get(hq_uuid) or {}

        comp_name  = comp_meta.get("company_name") or "Others"
        if comp_name == "Others":
            continue
        brand_name = brand_meta.get("brand_name") or "Generic Brand"
        depot_name = depot_meta.get("name") or "Central Depot"
        hq_name    = hq_meta.get("name") or "Jaipur"

        # HQ post-filter (if HQ not found in master but rows still came through)
        if selected_hq != "All Headquarters" and hq_name.lower() != selected_hq.lower():
            continue

        c_id    = _normalize_id(comp_name)
        b_id    = brand_uuid or _normalize_id(brand_name)
        d_id    = depot_uuid or _normalize_id(depot_name)
        tsm_raw = f"TSM {hq_name}"
        tsm_id  = _normalize_id(tsm_raw)

        row_metrics = {
            "Daily": {
                "cases": int(row.get("daily_cases") or 0),
                "bottles": int(row.get("daily_bottles") or 0),
                "bl": float(row.get("daily_bl") or 0.0),
            },
            "MTD": {
                "cases": int(row.get("mtd_cases") or 0),
                "bottles": int(row.get("mtd_bottles") or 0),
                "bl": float(row.get("mtd_bl") or 0.0),
            },
            "YTD": {
                "cases": int(row.get("ytd_cases") or 0),
                "bottles": int(row.get("ytd_bottles") or 0),
                "bl": float(row.get("ytd_bl") or 0.0),
            },
        }

        for period_key, metrics in row_metrics.items():
            cases = metrics["cases"]
            btl = metrics["bottles"]
            bl = metrics["bl"]

            # ── Company ──────────────────────────────────────────────────────
            if c_id not in companies_map:
                companies_map[c_id] = {
                    "id": c_id, "company_id": comp_uuid, "company_name": comp_name,
                    "name": comp_name, "is_active": comp_meta.get("is_active", True),
                    "isPinned": c_id in ["rll", "diageo-inbrew"], "hqLocation": hq_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "brands_map": {},
                }
            companies_map[c_id]["hqLocation"] = hq_name
            pd = companies_map[c_id]["data"][period_key]
            pd["cases"]   += cases
            pd["bottles"] += btl
            pd["bl"]      += bl

            bm = companies_map[c_id]["brands_map"]
            if b_id not in bm:
                bm[b_id] = {
                    "id": b_id, "brand_id": brand_uuid, "brand_name": brand_name,
                    "name": brand_name, "company_id": comp_uuid,
                    "is_active": brand_meta.get("is_active", True),
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                }
            bpd = bm[b_id]["data"][period_key]
            bpd["cases"]   += cases
            bpd["bottles"] += btl
            bpd["bl"]      += bl

            # ── Depot ────────────────────────────────────────────────────────
            if d_id not in depots_map:
                depots_map[d_id] = {
                    "id": d_id, "name": depot_name, "hqName": hq_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "brands_map": {},
                }
            dpd = depots_map[d_id]["data"][period_key]
            dpd["cases"]   += cases
            dpd["bottles"] += btl
            dpd["bl"]      += bl

            dbm = depots_map[d_id]["brands_map"]
            if b_id not in dbm:
                dbm[b_id] = {
                    "brandId": b_id, "brandName": brand_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                }
            dbpd = dbm[b_id]["data"][period_key]
            dbpd["cases"]   += cases
            dbpd["bottles"] += btl
            dbpd["bl"]      += bl

            # ── TSM ──────────────────────────────────────────────────────────
            if tsm_id not in tsms_map:
                tsms_map[tsm_id] = {
                    "id": tsm_id, "name": tsm_raw, "hqLocation": hq_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "brands_map": {},
                }
            tpd = tsms_map[tsm_id]["data"][period_key]
        tpd["cases"]   += cases
        tpd["bottles"] += btl
        tpd["bl"]      += bl

        tbm = tsms_map[tsm_id]["brands_map"]
        if b_id not in tbm:
            tbm[b_id] = {
                "brandId": b_id, "brandName": brand_name,
                "data": {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD":   {"cases": 0, "bottles": 0, "bl": 0.0},
                },
            }
        tbpd = tbm[b_id]["data"][period]
        tbpd["cases"]   += cases
        tbpd["bottles"] += btl
        tbpd["bl"]      += bl

    t_agg_ms = (time.perf_counter() - t_agg) * 1000

    # ── Response formatting ──────────────────────────────────────────────────
    def _format_company(c_data: Dict) -> Dict:
        c_data["data"][period]["bl"] = round(c_data["data"][period]["bl"], 2)
        c_data["brands"] = [
            {**b, "data": {**b["data"], period: {**b["data"][period], "bl": round(b["data"][period]["bl"], 2)}}}
            for b in c_data.pop("brands_map").values()
        ]
        return c_data

    def _format_entity(e_data: Dict) -> Dict:
        e_data["data"][period]["bl"] = round(e_data["data"][period]["bl"], 2)
        e_data["brands"] = [
            {**b, "data": {**b["data"], period: {**b["data"][period], "bl": round(b["data"][period]["bl"], 2)}}}
            for b in e_data.pop("brands_map").values()
        ]
        return e_data

    formatted_companies = [_format_company(c) for c in companies_map.values()]
    formatted_depots    = [_format_entity(d)  for d in depots_map.values()]
    formatted_tsms      = [_format_entity(t)  for t in tsms_map.values()]

    t_total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"build_sales_response: period={period} target={target_date} hq='{selected_hq}' "
        f"rpc_rows={len(rows)} companies={len(formatted_companies)} "
        f"depots={len(formatted_depots)} tsms={len(formatted_tsms)} "
        f"rpc={t_rpc_ms:.1f}ms agg={t_agg_ms:.1f}ms total={t_total_ms:.1f}ms"
    )

    result = {
        "status": "success",
        "record_count": len(rows),
        "period": period,
        "companies": formatted_companies,
        "depots": formatted_depots,
        "tsms": formatted_tsms,
        "process_time_ms": round(t_total_ms, 1),
    }
    _cache_set(cache_key, result)
    return result
