"""
Sales Analytics Chatbot Summary Repository.
Direct, high-performance database access layer for sales read-models:
- `sales_daily_summary`
- `sales_monthly_summary`

Database Rules Enforced:
1. NO `SELECT *` — Explicit column selections only.
2. NO `count=exact` or full scan of `sales_fact`.
3. Parameterized queries with bounded `LIMIT`.
4. STRICT exclusion of Company "Others" across all queries.
5. In-memory master lookup caching (10-minute TTL).
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.db.supabase_client import get_supabase_client
from backend.services.company_cascading_service import is_others_company

logger = logging.getLogger(__name__)

# Master Lookup Cache (10-min TTL)
_MASTER_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "companies": {},      # id -> name
    "companies_rev": {},  # name_lower -> id
    "brands": {},         # id -> {brand_name, company_id}
    "brands_rev": {},     # brand_name_lower -> id
    "depots": {},         # id -> name
    "depots_rev": {},     # name_lower -> id
    "hq": {},             # id -> name
    "hq_rev": {},         # name_lower -> id
    "tsms": {},           # id -> name
    "tsms_rev": {},       # name_lower -> id
    "others_company_id": None,
    "latest_sale_date": None,
}
_MASTER_TTL = 600.0


class ChatbotSummaryRepository:
    """High-performance repository for sales analytics chatbot queries."""

    @classmethod
    def _execute_paginated_query(cls, query, batch_size: int = 1000) -> List[Dict[str, Any]]:
        """Executes a Supabase PostgREST query with range-based pagination to fetch ALL matching rows without truncation."""
        all_rows = []
        offset = 0
        while True:
            res = query.range(offset, offset + batch_size - 1).execute()
            rows = res.data or []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < batch_size:
                break
            offset += batch_size
        return all_rows

    @classmethod
    def _should_exclude_company(cls, company_id: Optional[str] = None, company_name: Optional[str] = None) -> bool:
        """
        Determines whether a record belonging to company_id/company_name should be excluded.
        Dynamically respects the 'Include Others Company' developer toggle:
        - If toggle is ON: returns False (do NOT exclude 'Others')
        - If toggle is OFF: returns True if company is 'Others' (exclude 'Others')
        """
        from backend.services.tenant_service import get_include_others_setting_sync
        from backend.services.company_cascading_service import is_others_company

        if get_include_others_setting_sync():
            return False

        master = cls._load_master_lookups()
        others_id = master.get("others_company_id")

        if company_id and others_id and str(company_id) == str(others_id):
            return True

        if company_name and is_others_company(company_name):
            return True

        cname = master.get("companies", {}).get(str(company_id or ""))
        if cname and is_others_company(cname):
            return True

        return False

    @classmethod
    def _load_master_lookups(cls) -> Dict[str, Any]:
        """Loads and caches master lookup tables with explicit column selection."""
        now = time.time()
        if now - _MASTER_CACHE["timestamp"] < _MASTER_TTL and _MASTER_CACHE["companies"]:
            return _MASTER_CACHE

        client = get_supabase_client()
        if not client:
            return _MASTER_CACHE

        try:
            # 1. Companies
            comp_res = (
                client.table("companies")
                .select("company_id, company_name, is_active")
                .eq("is_active", True)
                .execute()
            )
            comp_data = comp_res.data or []
            companies = {}
            companies_rev = {}
            others_id = None

            for c in comp_data:
                cid = str(c.get("company_id"))
                cname = (c.get("company_name") or "").strip()
                if cname.lower() in ("others", "other"):
                    others_id = cid
                companies[cid] = cname
                companies_rev[cname.lower()] = cid

            # 2. Brands
            brand_res = (
                client.table("brands")
                .select("brand_id, brand_name, company_id, is_active")
                .eq("is_active", True)
                .execute()
            )
            brand_data = brand_res.data or []
            brands = {}
            brands_rev = {}
            for b in brand_data:
                bid = str(b.get("brand_id"))
                bname = (b.get("brand_name") or "").strip()
                cid = str(b.get("company_id"))
                brands[bid] = {"name": bname, "company_id": cid}
                brands_rev[bname.lower()] = bid

            # 3. Headquarters
            hq_res = client.table("headquarters").select("headquarters_id, name").execute()
            hq_data = hq_res.data or []
            hq = {}
            hq_rev = {}
            for h in hq_data:
                hid = str(h.get("headquarters_id"))
                hname = (h.get("name") or "").strip()
                hq[hid] = hname
                hq_rev[hname.lower()] = hid

            # 4. Depots
            depot_res = client.table("depots").select("depot_id, name, headquarters_id").execute()
            depot_data = depot_res.data or []
            depots = {}
            depots_rev = {}
            for d in depot_data:
                did = str(d.get("depot_id"))
                dname = (d.get("name") or "").strip()
                depots[did] = dname
                depots_rev[dname.lower()] = did

            # 5. TSM Users
            user_res = (
                client.table("users")
                .select("user_id, first_name, last_name, email")
                .execute()
            )
            user_data = user_res.data or []
            tsms = {}
            tsms_rev = {}
            for u in user_data:
                uid = str(u.get("user_id"))
                fname = (u.get("first_name") or "").strip()
                lname = (u.get("last_name") or "").strip()
                fullname = f"{fname} {lname}".strip() or u.get("email") or "Unknown TSM"
                tsms[uid] = fullname
                tsms_rev[fullname.lower()] = uid

            # 6. Groups
            group_res = (
                client.table("groups")
                .select("group_id, group_name")
                .execute()
            )
            group_data = group_res.data or []
            groups = {}
            groups_rev = {}
            for g in group_data:
                gid = str(g.get("group_id"))
                gname = (g.get("group_name") or "").strip()
                if gid and gname:
                    groups[gid] = gname
                    groups_rev[gname.lower()] = gid

            _MASTER_CACHE.update({
                "timestamp": now,
                "companies": companies,
                "companies_rev": companies_rev,
                "brands": brands,
                "brands_rev": brands_rev,
                "depots": depots,
                "depots_rev": depots_rev,
                "hq": hq,
                "hq_rev": hq_rev,
                "tsms": tsms,
                "tsms_rev": tsms_rev,
                "groups": groups,
                "groups_rev": groups_rev,
                "others_company_id": others_id,
            })
        except Exception as e:
            logger.warning(f"SummaryRepository: Error refreshing master lookup cache: {e}")

        return _MASTER_CACHE

    @classmethod
    def resolve_latest_date(cls) -> str:
        """Returns latest sale_date available in sales_daily_summary."""
        now = time.time()
        cached_date = _MASTER_CACHE.get("latest_sale_date")
        if cached_date and (now - _MASTER_CACHE["timestamp"] < 300.0):
            return cached_date

        client = get_supabase_client()
        if not client:
            return datetime.utcnow().strftime("%Y-%m-%d")

        try:
            res = (
                client.table("sales_daily_summary")
                .select("sale_date")
                .order("sale_date", desc=True)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("sale_date"):
                dt_str = res.data[0]["sale_date"]
                _MASTER_CACHE["latest_sale_date"] = dt_str
                return dt_str
        except Exception as e:
            logger.warning(f"SummaryRepository: Error resolving latest date: {e}")

        return datetime.utcnow().strftime("%Y-%m-%d")

    @classmethod
    def resolve_hq_id(cls, selected_hq: Optional[str]) -> Optional[str]:
        """Resolves headquarters name to ID."""
        if not selected_hq or selected_hq == "All Headquarters":
            return None
        master = cls._load_master_lookups()
        return master["hq_rev"].get(selected_hq.strip().lower())

    @classmethod
    def resolve_entity_id(cls, entity_type: str, entity_name: str) -> Optional[str]:
        """Resolves entity name to ID based on type (company, brand, depot, hq, tsm, group)."""
        master = cls._load_master_lookups()
        clean_name = entity_name.strip().lower()
        if entity_type == "company":
            return master["companies_rev"].get(clean_name)
        elif entity_type == "brand":
            return master["brands_rev"].get(clean_name)
        elif entity_type == "depot":
            return master["depots_rev"].get(clean_name)
        elif entity_type == "hq":
            return master["hq_rev"].get(clean_name)
        elif entity_type == "tsm":
            uid = master["tsms_rev"].get(clean_name)
            if uid:
                return uid
            clean_tsm = clean_name.replace("tsm", "").strip().lower()
            if master["tsms_rev"].get(clean_tsm):
                return master["tsms_rev"].get(clean_tsm)
            clean_parts = [p for p in clean_tsm.split() if len(p) >= 3]
            for k, v in master["tsms_rev"].items():
                if clean_tsm in k or (clean_parts and len(clean_parts) > 1 and all(p in k for p in clean_parts)):
                    return v
            import difflib
            close = difflib.get_close_matches(clean_tsm, list(master["tsms_rev"].keys()), n=1, cutoff=0.60)
            if close:
                return master["tsms_rev"].get(close[0])
        elif entity_type in ("group", "licensee_group"):
            clean_grp = clean_name.replace("group", "").strip().lower()

            # 1. Exact lookup
            gid = master["groups_rev"].get(clean_name) or master["groups_rev"].get(clean_grp) or master["groups_rev"].get(f"{clean_grp} group")
            if gid:
                return gid

            # 2. Strict token matching (requires all non-stop query words to match)
            query_tokens = set(w for w in clean_grp.split() if len(w) >= 2 and w not in ("group", "groups", "the", "of", "in"))
            if not query_tokens:
                return None

            best_gid = None
            best_score = 0.0

            for k, v in master["groups_rev"].items():
                g_key_clean = k.replace(" group", "").strip().lower()
                g_tokens = set(g_key_clean.split())
                matched_tokens = query_tokens.intersection(g_tokens)
                if not matched_tokens:
                    continue
                # If query has multiple words (e.g. "akhe singh", "jitendra kumar"), all tokens MUST match!
                if len(query_tokens) > 1 and len(matched_tokens) < len(query_tokens):
                    continue
                score = len(matched_tokens) / max(len(g_tokens), 1.0)
                if score > best_score:
                    best_score = score
                    best_gid = v

            if best_gid:
                return best_gid

            return None

    @classmethod
    def resolve_entity_type_and_id(cls, entity_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolves entity name to both its type and ID across all entity categories."""
        if not entity_name:
            return None, None
        
        # Check group first
        gid = cls.resolve_entity_id("group", entity_name)
        if gid:
            return "group", gid
            
        # Check brand
        bid = cls.resolve_entity_id("brand", entity_name)
        if bid:
            return "brand", bid
            
        # Check company
        cid = cls.resolve_entity_id("company", entity_name)
        if cid:
            return "company", cid
            
        # Check tsm
        tid = cls.resolve_entity_id("tsm", entity_name)
        if tid:
            return "tsm", tid
            
        # Check depot
        did = cls.resolve_entity_id("depot", entity_name)
        if did:
            return "depot", did
            
        return None, None

    # -------------------------------------------------------------------------
    # 1. GET SALES SUMMARY
    # -------------------------------------------------------------------------
    @classmethod
    def get_sales_summary(
        cls,
        period: str = "Daily",
        target_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        company_id: Optional[str] = None,
        brand_id: Optional[str] = None,
        depot_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        allowed_hqs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Calculates total sales cases, bottles, and liquid volume (BL) for period and entity filters."""
        client = get_supabase_client()
        master = cls._load_master_lookups()
        others_id = master["others_company_id"]
        t_date = target_date or cls.resolve_latest_date()
        hq_id = cls.resolve_hq_id(selected_hq)

        table_name = "sales_daily_summary" if period == "Daily" else "sales_monthly_summary"
        
        # Build range filters based on period
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()
        if period == "Daily":
            start_date = t_date
            end_date = t_date
        elif period == "MTD":
            start_date = dt.replace(day=1).strftime("%Y-%m-%d")
            end_date = t_date
        else:  # YTD (Fiscal year April 1 to Target Date)
            fy_year = dt.year if dt.month >= 4 else dt.year - 1
            start_date = f"{fy_year}-04-01"
            end_date = t_date

        try:
            # Query aggregated metrics with explicit column selection
            query = client.table(table_name).select(
                "company_id, total_cases, total_bottles, total_bl"
            )

            if period == "Daily":
                query = query.eq("sale_date", t_date)
            else:
                m_start = dt.replace(day=1).strftime("%Y-%m-%d")
                query = query.gte("month_start", start_date if period == "YTD" else m_start).lte("month_start", end_date)

            if hq_id:
                query = query.eq("headquarters_id", hq_id)
            if company_id:
                query = query.eq("company_id", company_id)
            if brand_id:
                query = query.eq("brand_id", brand_id)
            if depot_id:
                query = query.eq("depot_id", depot_id)
            if tsm_user_id:
                query = query.eq("tsm_user_id", tsm_user_id)
            if group_id:
                query = query.eq("group_id", group_id)

            # Paginate & aggregate in Python while strictly excluding 'Others'
            tot_cases = 0.0
            tot_bottles = 0.0
            tot_bl = 0.0
            row_count = 0

            rows = cls._execute_paginated_query(query)
            for r in rows:
                if cls._should_exclude_company(company_id=r.get("company_id")):
                    continue
                tot_cases += float(r.get("total_cases") or 0.0)
                tot_bottles += float(r.get("total_bottles") or 0.0)
                tot_bl += float(r.get("total_bl") or 0.0)
                row_count += 1

            return {
                "period": period,
                "target_date": t_date,
                "start_date": start_date,
                "end_date": end_date,
                "selected_hq": selected_hq or "All Headquarters",
                "total_cases": round(tot_cases, 2),
                "total_bottles": int(round(tot_bottles)),
                "total_bl": round(tot_bl, 2),
                "record_count": row_count,
            }
        except Exception as e:
            logger.error(f"SummaryRepository: get_sales_summary error: {e}")
            return {
                "period": period,
                "target_date": t_date,
                "selected_hq": selected_hq or "All Headquarters",
                "total_cases": 0.0,
                "total_bottles": 0,
                "total_bl": 0.0,
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # 2. GET TOP ENTITIES (Brands / Companies / Depots / TSMs)
    # -------------------------------------------------------------------------
    @classmethod
    def get_top_entities(
        cls,
        entity_type: str = "brand",  # brand, company, depot, tsm
        period: str = "Daily",
        target_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        limit: int = 10,
        company_id: Optional[str] = None,
        group_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns Top N entities ranked by total sales cases."""
        client = get_supabase_client()
        master = cls._load_master_lookups()
        others_id = master["others_company_id"]
        t_date = target_date or cls.resolve_latest_date()
        hq_id = cls.resolve_hq_id(selected_hq)

        id_col = (
            "brand_id" if entity_type == "brand"
            else "company_id" if entity_type == "company"
            else "depot_id" if entity_type == "depot"
            else "group_id" if entity_type in ("group", "licensee_group")
            else "tsm_user_id"
        )

        if entity_type == "company":
            dt = datetime.strptime(t_date, "%Y-%m-%d").date()
            m_start = dt.replace(day=1).strftime("%Y-%m-%d")
            fy_year = dt.year if dt.month >= 4 else dt.year - 1
            y_start = f"{fy_year}-04-01"

            comp_params = {
                "p_target_date": t_date,
                "p_mtd_start": m_start,
                "p_ytd_start": y_start,
            }
            if hq_id:
                comp_params["p_hq_id"] = hq_id

            try:
                res = client.rpc("get_mobile_companies_summary", comp_params).execute()
                data = res.data or []
                results = []
                for r in data:
                    cname = (r.get("company_name") or "").strip()
                    cid = str(r.get("company_id") or "")
                    if not cname or cls._should_exclude_company(company_id=cid, company_name=cname):
                        continue

                    val_key = "daily_cases" if period == "Daily" else "mtd_cases" if period == "MTD" else "ytd_cases"
                    cases = float(r.get(val_key) or 0.0)
                    bottles = int(round(float(r.get(val_key.replace("cases", "bottles")) or 0.0)))

                    results.append({
                        "id": cid,
                        "name": cname,
                        "cases": round(cases, 2),
                        "bottles": bottles,
                    })

                results.sort(key=lambda x: x["cases"], reverse=True)
                return results[:limit]
            except Exception as e_comp:
                logger.error(f"SummaryRepository get_top_entities company RPC error: {e_comp}")

        table_name = "sales_daily_summary" if period == "Daily" else "sales_monthly_summary"
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()

        try:
            query = client.table(table_name).select(
                f"{id_col}, company_id, total_cases, total_bottles"
            )

            if period == "Daily":
                query = query.eq("sale_date", t_date)
            else:
                m_start = dt.replace(day=1).strftime("%Y-%m-%d")
                query = query.eq("month_start", m_start)

            if hq_id:
                query = query.eq("headquarters_id", hq_id)
            if company_id:
                query = query.eq("company_id", company_id)
            if group_id:
                query = query.eq("group_id", group_id)
            if tsm_user_id:
                query = query.eq("tsm_user_id", tsm_user_id)

            # Aggregate in memory by target entity ID
            entity_metrics: Dict[str, Dict[str, float]] = {}
            rows = cls._execute_paginated_query(query)
            for r in rows:
                eid = str(r.get(id_col) or "").strip()
                if not eid or eid.lower() in ("none", "null", "unknown", ""):
                    continue
                if cls._should_exclude_company(company_id=r.get("company_id")):
                    continue

                cases = float(r.get("total_cases") or 0.0)
                bottles = float(r.get("total_bottles") or 0.0)

                if eid not in entity_metrics:
                    entity_metrics[eid] = {"cases": 0.0, "bottles": 0.0}
                entity_metrics[eid]["cases"] += cases
                entity_metrics[eid]["bottles"] += bottles

            # Resolve names & sort descending
            results = []
            for eid, metrics in entity_metrics.items():
                name = "Unknown"
                if entity_type == "brand":
                    b_obj = master["brands"].get(eid)
                    name = b_obj["name"] if b_obj else "Unknown Brand"
                elif entity_type == "company":
                    name = master["companies"].get(eid, "Unknown Company")
                elif entity_type == "depot":
                    name = master["depots"].get(eid, "Unknown Depot")
                elif entity_type == "tsm":
                    name = master["tsms"].get(eid, "Unknown TSM")
                elif entity_type in ("group", "licensee_group"):
                    name = master["groups"].get(eid, "Unknown Group")

                results.append({
                    "id": eid,
                    "name": name,
                    "cases": round(metrics["cases"], 2),
                    "bottles": int(round(metrics["bottles"])),
                })

            results.sort(key=lambda x: x["cases"], reverse=True)

            # Fallback: if 0 results returned for unspecified target_date (e.g. today with 0 sales), fallback to latest date with data
            if not results and not target_date:
                latest_with_data = cls.resolve_latest_date()
                if latest_with_data and latest_with_data != t_date:
                    return cls.get_top_entities(
                        entity_type=entity_type,
                        period=period,
                        target_date=latest_with_data,
                        selected_hq=selected_hq,
                        limit=limit,
                        company_id=company_id,
                        group_id=group_id,
                        tsm_user_id=tsm_user_id,
                    )

            return results[:limit]
        except Exception as e:
            logger.error(f"SummaryRepository: get_top_entities error: {e}")
            return []

    # -------------------------------------------------------------------------
    # 3. GET ENTITY BREAKDOWN
    # -------------------------------------------------------------------------
    @classmethod
    def get_breakdown(
        cls,
        entity_type: str = "company",
        period: str = "Daily",
        target_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        company_id: Optional[str] = None,
        group_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns complete sales breakdown grouped by entity type."""
        return cls.get_top_entities(
            entity_type=entity_type,
            period=period,
            target_date=target_date,
            selected_hq=selected_hq,
            limit=100,
            company_id=company_id,
            group_id=group_id,
            tsm_user_id=tsm_user_id,
        )

    # -------------------------------------------------------------------------
    # 4. COMPARE PERIODS (Month-Over-Month / Date-Over-Date)
    # -------------------------------------------------------------------------
    @classmethod
    def compare_periods(
        cls,
        period: str = "Daily",
        target_date: Optional[str] = None,
        compare_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        company_id: Optional[str] = None,
        group_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compares target date/period sales against previous date/period."""
        t_date = target_date or cls.resolve_latest_date()
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()

        if not compare_date:
            if period == "Daily":
                c_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                first_of_month = dt.replace(day=1)
                last_month_end = first_of_month - timedelta(days=1)
                c_date = last_month_end.strftime("%Y-%m-%d")
        else:
            c_date = compare_date

        curr_sales = cls.get_sales_summary(period=period, target_date=t_date, selected_hq=selected_hq, company_id=company_id, group_id=group_id, tsm_user_id=tsm_user_id)
        prev_sales = cls.get_sales_summary(period=period, target_date=c_date, selected_hq=selected_hq, company_id=company_id, group_id=group_id, tsm_user_id=tsm_user_id)

        curr_cases = curr_sales["total_cases"]
        prev_cases = prev_sales["total_cases"]

        diff_cases = round(curr_cases - prev_cases, 2)
        pct_change = round(((curr_cases - prev_cases) / prev_cases * 100.0), 2) if prev_cases > 0 else 0.0

        return {
            "period": period,
            "selected_hq": selected_hq or "All Headquarters",
            "current": {
                "date": t_date,
                "cases": curr_cases,
                "bottles": curr_sales["total_bottles"],
            },
            "previous": {
                "date": c_date,
                "cases": prev_cases,
                "bottles": prev_sales["total_bottles"],
            },
            "variance": {
                "cases": diff_cases,
                "pct_change": pct_change,
                "direction": "up" if diff_cases > 0 else "down" if diff_cases < 0 else "flat",
            }
        }

    # -------------------------------------------------------------------------
    # 5. GET MOVERS (Top Gainers & Top Losers)
    # -------------------------------------------------------------------------
    @classmethod
    def get_movers(
        cls,
        entity_type: str = "brand",
        period: str = "Daily",
        target_date: Optional[str] = None,
        compare_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        limit: int = 5,
        company_id: Optional[str] = None,
        group_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Identifies growing (gainers) and declining (losers) entities between dates."""
        t_date = target_date or cls.resolve_latest_date()
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()

        if not compare_date:
            c_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            c_date = compare_date

        curr_list = cls.get_top_entities(entity_type=entity_type, period=period, target_date=t_date, selected_hq=selected_hq, limit=200, company_id=company_id, group_id=group_id, tsm_user_id=tsm_user_id)
        prev_list = cls.get_top_entities(entity_type=entity_type, period=period, target_date=c_date, selected_hq=selected_hq, limit=200, company_id=company_id, group_id=group_id, tsm_user_id=tsm_user_id)

        prev_map = {item["id"]: item["cases"] for item in prev_list}

        movers = []
        for item in curr_list:
            eid = item["id"]
            c_cases = item["cases"]
            p_cases = prev_map.get(eid, 0.0)
            diff = round(c_cases - p_cases, 2)
            pct = round((diff / p_cases * 100.0), 2) if p_cases > 0 else (100.0 if c_cases > 0 else 0.0)

            movers.append({
                "id": eid,
                "name": item["name"],
                "current_cases": c_cases,
                "previous_cases": p_cases,
                "diff_cases": diff,
                "pct_change": pct,
            })

        gainers = [m for m in movers if m["diff_cases"] > 0]
        gainers.sort(key=lambda x: x["diff_cases"], reverse=True)

        losers = [m for m in movers if m["diff_cases"] < 0]
        losers.sort(key=lambda x: x["diff_cases"])

        return {
            "entity_type": entity_type,
            "current_date": t_date,
            "previous_date": c_date,
            "gainers": gainers[:limit],
            "losers": losers[:limit],
        }

    # -------------------------------------------------------------------------
    # 6. GET CONTRIBUTION (% Share)
    # -------------------------------------------------------------------------
    @classmethod
    def get_contribution(
        cls,
        entity_type: str = "company",
        period: str = "Daily",
        target_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        limit: int = 10,
        company_id: Optional[str] = None,
        group_id: Optional[str] = None,
        tsm_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Calculates volume contribution percentage share per entity."""
        entities = cls.get_top_entities(entity_type=entity_type, period=period, target_date=target_date, selected_hq=selected_hq, limit=100, company_id=company_id, group_id=group_id, tsm_user_id=tsm_user_id)
        total_vol = sum(e["cases"] for e in entities)

        contributions = []
        for e in entities:
            share_pct = round((e["cases"] / total_vol * 100.0), 2) if total_vol > 0 else 0.0
            contributions.append({
                "id": e["id"],
                "name": e["name"],
                "cases": e["cases"],
                "share_pct": share_pct,
            })

        return contributions[:limit]

    # -------------------------------------------------------------------------
    # 7. GET TREND (Time Series)
    # -------------------------------------------------------------------------
    @classmethod
    def get_trend(
        cls,
        period: str = "Daily",
        num_days: int = 7,
        selected_hq: Optional[str] = "All Headquarters",
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetches multi-day or multi-month sales trend in a single database request."""
        client = get_supabase_client()
        master = cls._load_master_lookups()
        others_id = master["others_company_id"]
        t_date = cls.resolve_latest_date()
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()
        start_date = (dt - timedelta(days=num_days - 1)).strftime("%Y-%m-%d")
        hq_id = cls.resolve_hq_id(selected_hq)

        date_map: Dict[str, Dict[str, float]] = {
            (dt - timedelta(days=i)).strftime("%Y-%m-%d"): {"cases": 0.0, "bottles": 0.0}
            for i in range(num_days - 1, -1, -1)
        }

        try:
            query = (
                client.table("sales_daily_summary")
                .select("sale_date, company_id, total_cases, total_bottles")
                .gte("sale_date", start_date)
                .lte("sale_date", t_date)
            )
            if hq_id:
                query = query.eq("headquarters_id", hq_id)

            rows = cls._execute_paginated_query(query)
            for r in rows:
                if cls._should_exclude_company(company_id=r.get("company_id")):
                    continue
                sdate = str(r.get("sale_date") or "")
                if sdate in date_map:
                    date_map[sdate]["cases"] += float(r.get("total_cases") or 0.0)
                    date_map[sdate]["bottles"] += float(r.get("total_bottles") or 0.0)
        except Exception as e:
            logger.error(f"SummaryRepository: get_trend error: {e}")

        trend_points = [
            {
                "date": d,
                "label": datetime.strptime(d, "%Y-%m-%d").strftime("%b %d"),
                "cases": round(m["cases"], 2),
                "bottles": int(round(m["bottles"])),
            }
            for d, m in sorted(date_map.items())
        ]

        return {
            "period": period,
            "selected_hq": selected_hq or "All Headquarters",
            "trend": trend_points,
        }
