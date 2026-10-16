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
    "companies": {},        # id -> name
    "companies_rev": {},    # name_lower -> id
    "brands": {},           # id -> {brand_name, company_id}
    "brands_rev": {},       # brand_name_lower -> id
    "depots": {},           # id -> name
    "depots_rev": {},       # name_lower -> id
    "hq": {},               # id -> name
    "hq_rev": {},           # name_lower -> id
    "tsms": {},             # id -> name
    "tsms_rev": {},         # name_lower -> id
    "tsms_list": [],        # list of {id, name, entity_type, email, subtext}
    "groups": {},           # id -> name
    "groups_rev": {},       # name_lower -> id
    "licensees": {},        # id -> {name, depot_id, headquarters_id, hq_name, depot_name}
    "licensees_rev": {},    # name_lower -> id
    "licensees_list": [],   # list of {id, name, entity_type, depot_id, hq_id, hq_name, depot_name, subtext}
    "ases": {},             # id -> {name, email}
    "ases_rev": {},         # name_lower -> id
    "ases_list": [],        # list of {id, name, entity_type, email, subtext}
    "others_company_id": None,
    "latest_sale_date": None,
}
_MASTER_TTL = 600.0


class ChatbotSummaryRepository:
    """High-performance repository for sales analytics chatbot queries."""

    @classmethod
    def _execute_paginated_query(cls, query, batch_size: int = 5000) -> List[Dict[str, Any]]:
        """
        Executes a Supabase PostgREST query with bounded parallel range pagination
        to fetch ALL matching rows without truncation or sequential latency penalties.
        """
        # 1. Fetch initial batch (0 .. batch_size - 1)
        res = query.range(0, batch_size - 1).execute()
        rows = res.data or []
        if not rows or len(rows) < batch_size:
            return rows

        all_rows = list(rows)
        
        # 2. Fetch remaining pages in parallel with bounded concurrency (max 4 workers)
        from concurrent.futures import ThreadPoolExecutor

        def fetch_page(off: int) -> List[Dict[str, Any]]:
            try:
                page_res = query.range(off, off + batch_size - 1).execute()
                return page_res.data or []
            except Exception as e:
                logger.error(f"_execute_paginated_query page fetch error at offset {off}: {e}")
                return []

        # Prepare page offsets (e.g. 5000, 10000, 15000, ...) up to reasonable ceiling (75,000 rows)
        offset = batch_size
        offsets_to_fetch = []
        for _ in range(1, 15):
            offsets_to_fetch.append(offset)
            offset += batch_size

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_page, off) for off in offsets_to_fetch]
            for fut in futures:
                page_data = fut.result()
                if page_data:
                    all_rows.extend(page_data)
                    if len(page_data) < batch_size:
                        break
                else:
                    break

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
        """Loads and caches master lookup tables concurrently with explicit column selection."""
        now = time.time()
        if now - _MASTER_CACHE["timestamp"] < _MASTER_TTL and _MASTER_CACHE["companies"]:
            return _MASTER_CACHE

        client = get_supabase_client()
        if not client:
            return _MASTER_CACHE

        try:
            from concurrent.futures import ThreadPoolExecutor

            def f_companies():
                return client.table("companies").select("company_id, company_name, is_active").eq("is_active", True).execute().data or []

            def f_brands():
                return client.table("brands").select("brand_id, brand_name, company_id, is_active").eq("is_active", True).execute().data or []

            def f_hq():
                return client.table("headquarters").select("headquarters_id, name").execute().data or []

            def f_depots():
                return client.table("depots").select("depot_id, name, headquarters_id").execute().data or []

            def f_users():
                return client.table("users").select("user_id, first_name, last_name, email").execute().data or []

            def f_groups():
                return client.table("groups").select("group_id, group_name").execute().data or []

            def f_licensees():
                try:
                    all_lic = []
                    page_size = 1000
                    start = 0
                    while True:
                        page_data = (
                            client.table("licensees")
                            .select("licensee_id, licensee_name, depot_id, headquarters_id")
                            .range(start, start + page_size - 1)
                            .execute()
                            .data or []
                        )
                        all_lic.extend(page_data)
                        if len(page_data) < page_size:
                            break
                        start += page_size
                    return all_lic
                except Exception as e_l:
                    logger.warning(f"Error fetching licensees in master lookups: {e_l}")
                    return []

            def f_roles_and_hierarchy():
                try:
                    r_res = client.table("roles").select("role_id, role_name").execute().data or []
                    ase_role_ids = {str(r["role_id"]) for r in r_res if "ase" in (r.get("role_name") or "").lower()}
                    tsm_role_ids = {str(r["role_id"]) for r in r_res if "tsm" in (r.get("role_name") or "").lower()}
                    ur_res = client.table("user_roles").select("user_id, role_id, is_active").execute().data or []
                    ase_uids = {str(ur["user_id"]) for ur in ur_res if ur.get("is_active", True) and str(ur.get("role_id")) in ase_role_ids}
                    tsm_uids = {str(ur["user_id"]) for ur in ur_res if ur.get("is_active", True) and str(ur.get("role_id")) in tsm_role_ids}
                    try:
                        atm_res = client.table("ase_tsm_mapping").select("ase_user_id, tsm_user_id").execute().data or []
                        for atm in atm_res:
                            if atm.get("ase_user_id"):
                                ase_uids.add(str(atm["ase_user_id"]))
                            if atm.get("tsm_user_id"):
                                tsm_uids.add(str(atm["tsm_user_id"]))
                    except Exception:
                        pass
                    return ase_uids, tsm_uids
                except Exception as e_r:
                    logger.warning(f"Error fetching ASE/TSM roles: {e_r}")
                    return set(), set()

            with ThreadPoolExecutor(max_workers=8) as executor:
                t_comp = executor.submit(f_companies)
                t_brand = executor.submit(f_brands)
                t_hq = executor.submit(f_hq)
                t_depot = executor.submit(f_depots)
                t_user = executor.submit(f_users)
                t_group = executor.submit(f_groups)
                t_lic = executor.submit(f_licensees)
                t_roles = executor.submit(f_roles_and_hierarchy)

                comp_data = t_comp.result()
                brand_data = t_brand.result()
                hq_data = t_hq.result()
                depot_data = t_depot.result()
                user_data = t_user.result()
                group_data = t_group.result()
                lic_data = t_lic.result()
                ase_uids, tsm_uids = t_roles.result()

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

            brands = {}
            brands_rev = {}
            for b in brand_data:
                bid = str(b.get("brand_id"))
                bname = (b.get("brand_name") or "").strip()
                cid = str(b.get("company_id"))
                brands[bid] = {"name": bname, "company_id": cid}
                brands_rev[bname.lower()] = bid

            hq = {}
            hq_rev = {}
            for h in hq_data:
                hid = str(h.get("headquarters_id"))
                hname = (h.get("name") or "").strip()
                hq[hid] = hname
                hq_rev[hname.lower()] = hid

            depots = {}
            depots_rev = {}
            for d in depot_data:
                did = str(d.get("depot_id"))
                dname = (d.get("name") or "").strip()
                depots[did] = dname
                depots_rev[dname.lower()] = did

            tsms = {}
            tsms_rev = {}
            tsms_list = []
            ases = {}
            ases_rev = {}
            ases_list = []
            for u in user_data:
                uid = str(u.get("user_id"))
                fname = (u.get("first_name") or "").strip()
                lname = (u.get("last_name") or "").strip()
                email = (u.get("email") or "").strip()
                fullname = f"{fname} {lname}".strip() or email or "Unknown Salesperson"

                is_ase = (uid in ase_uids) if ase_uids else False
                is_tsm = (uid in tsm_uids) if tsm_uids else False
                if not is_ase and not is_tsm:
                    is_tsm = True

                tsms[uid] = fullname
                tsms_rev[fullname.lower()] = uid

                if is_ase:
                    ases[uid] = {"name": fullname, "email": email}
                    ases_rev[fullname.lower()] = uid
                    ases_list.append({
                        "id": uid,
                        "name": fullname,
                        "entity_type": "ase",
                        "email": email,
                        "subtext": f"Area Sales Executive • {email}" if email else "Area Sales Executive",
                    })

                if is_tsm:
                    tsms_list.append({
                        "id": uid,
                        "name": fullname,
                        "entity_type": "tsm",
                        "email": email,
                        "subtext": f"Territory Sales Manager • {email}" if email else "Territory Sales Manager",
                    })

            groups = {}
            groups_rev = {}
            groups_list = []
            for g in group_data:
                gid = str(g.get("group_id"))
                gname = (g.get("group_name") or "").strip()
                if gid and gname:
                    groups[gid] = gname
                    groups_rev[gname.lower()] = gid
                    groups_list.append({
                        "id": gid,
                        "name": gname,
                        "entity_type": "group",
                        "subtext": "Group",
                    })

            licensees = {}
            licensees_rev = {}
            licensees_list = []
            for lic in lic_data:
                lid = str(lic.get("licensee_id") or "")
                lname = (lic.get("licensee_name") or "").strip()
                if not lid or not lname:
                    continue
                did = str(lic.get("depot_id") or "")
                hid = str(lic.get("headquarters_id") or "")
                hq_name = hq.get(hid, "")
                depot_name = depots.get(did, "")
                licensees[lid] = {
                    "name": lname,
                    "depot_id": did,
                    "headquarters_id": hid,
                    "hq_name": hq_name,
                    "depot_name": depot_name,
                }
                licensees_rev[lname.lower()] = lid
                subtext_parts = ["Outlet"]
                if hq_name:
                    subtext_parts.append(f"{hq_name} HQ")
                if depot_name:
                    subtext_parts.append(depot_name)
                licensees_list.append({
                    "id": lid,
                    "name": lname,
                    "entity_type": "licensee",
                    "depot_id": did,
                    "hq_id": hid,
                    "hq_name": hq_name,
                    "depot_name": depot_name,
                    "subtext": " • ".join(subtext_parts),
                })

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
                "tsms_list": tsms_list,
                "ases": ases,
                "ases_rev": ases_rev,
                "ases_list": ases_list,
                "licensees": licensees,
                "licensees_rev": licensees_rev,
                "licensees_list": licensees_list,
                "groups": groups,
                "groups_rev": groups_rev,
                "groups_list": groups_list,
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
    def find_matching_entities(
        cls,
        query_text: str,
        target_types: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Sub-millisecond fuzzy and token entity search across licensees and ASEs.
        Handles typo variations (e.g. 'abhishekh' -> 'Abhishek') and multi-matches (e.g. 'wines' -> all matching wine licensees).
        Returns ranked list of candidate entities with Zomato-style quick select metadata.
        """
        import difflib
        import re

        if not query_text or not query_text.strip():
            return []

        master = cls._load_master_lookups()
        clean_q = query_text.lower().strip()

        # Stop words: generic domain fluff and Hinglish/broken English filler words (keep 'wine' / 'wines'!)
        stop_words = {
            "sale", "sales", "sel", "sail", "summary", "performance", "of", "on", "for", "in", "at", "the",
            "a", "an", "daily", "mtd", "ytd", "today", "show", "me", "tell", "what", "is", "are",
            "about", "detail", "details", "cases", "bottles", "data", "click", "view", "give", "please",
            "pls", "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "pe", "aur", "kya", "tha", "thi",
            "hai", "batao", "dikhao", "dekho", "karo", "kitna", "kitni", "chahiye", "bhejo", "bataiye",
            "dikhaye", "shop", "shops", "theka", "theke", "dukan", "dukaan", "licensee", "licensees",
            "licencee", "licencees", "license", "licence", "group", "groups", "syndicate", "ase", "ases",
            "tsm", "tsms", "executive", "executives", "with", "to", "from", "by", "all", "so", "s"
        }
        date_words = {
            "january", "february", "march", "april", "may", "june", "july", "august", "september",
            "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug",
            "sep", "sept", "oct", "nov", "dec", "31st", "1st", "2nd", "3rd", "4th", "5th",
            "6th", "7th", "8th", "9th", "10th", "11th", "12th", "13th", "14th", "15th", "16th",
            "17th", "18th", "19th", "20th", "21st", "22nd", "23rd", "24th", "25th", "26th",
            "27th", "28th", "29th", "30th"
        }

        all_tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", clean_q) if len(t) >= 2]
        meaningful_tokens = [t for t in all_tokens if t not in stop_words and t not in date_words and not t.isdigit()]

        search_tokens = meaningful_tokens if meaningful_tokens else [t for t in all_tokens if t not in stop_words and not t.isdigit()]
        if not search_tokens:
            return []

        types_to_search = target_types or ["licensee", "group", "ase", "tsm"]
        pools = []
        if "group" in types_to_search:
            pools.extend(master.get("groups_list", []))
        if "licensee" in types_to_search:
            pools.extend(master.get("licensees_list", []))
        if "ase" in types_to_search:
            pools.extend(master.get("ases_list", []))
        if "tsm" in types_to_search:
            pools.extend(master.get("tsms_list", []))

        candidates: List[Dict[str, Any]] = []
        seen_ids = set()
        search_str = " ".join(search_tokens)
        search_compact = "".join(search_tokens)

        for item in pools:
            iid = str(item["id"])
            if iid in seen_ids:
                continue

            name = item["name"]
            name_lower = name.lower()
            name_compact = re.sub(r"[^a-z0-9]", "", name_lower)
            name_tokens = set(re.findall(r"[a-zA-Z0-9]+", name_lower))

            score = 0.0

            # 1. Exact full match or prefix match with suffix ID
            if name_lower == clean_q or name_lower == search_str or name_lower.startswith(search_str + "-") or name_lower.startswith(search_str + " "):
                score = 1.0
            # 2. Exact substring phrase match or compact compound match (e.g. "bijaram" in "bijaram1907054")
            elif search_str in name_lower or (len(search_compact) >= 5 and search_compact in name_compact):
                score = 0.98
            else:
                # 3. Multi-token coverage calculation
                token_match_scores = []
                for st in search_tokens:
                    best_st = 0.0
                    for nt in name_tokens:
                        if st == nt:
                            best_st = 1.0
                            break
                        elif len(st) >= 4 and len(nt) >= 4 and (st in nt or nt in st):
                            best_st = max(best_st, 0.92)
                        else:
                            r = difflib.SequenceMatcher(None, st, nt).ratio()
                            if r >= 0.70 and r > best_st:
                                best_st = r
                    token_match_scores.append(best_st)

                if token_match_scores:
                    min_s = min(token_match_scores)
                    avg_s = sum(token_match_scores) / len(token_match_scores)

                    # For multi-token searches, EVERY token must have at least 0.65 similarity
                    if len(search_tokens) > 1 and min_s < 0.65:
                        score = 0.0
                    else:
                        score = avg_s

            if score >= 0.70:
                seen_ids.add(iid)
                candidates.append({
                    "id": iid,
                    "name": name,
                    "entity_type": item.get("entity_type", "licensee"),
                    "subtext": item.get("subtext") or "",
                    "score": round(score, 3),
                })

        # If exact matches (score >= 0.98) exist, discard partial substring or typo matches (< 0.98)
        has_exact = any(c["score"] >= 0.98 for c in candidates)
        if has_exact:
            candidates = [c for c in candidates if c["score"] >= 0.98]
        elif any(c["score"] >= 0.90 for c in candidates):
            candidates = [c for c in candidates if c["score"] >= 0.85]

        candidates.sort(key=lambda x: (x["score"], -len(x["name"])), reverse=True)

        group_c = [c for c in candidates if c.get("entity_type") == "group"]
        lic_c = [c for c in candidates if c.get("entity_type") == "licensee"]
        ase_c = [c for c in candidates if c.get("entity_type") in ("ase", "tsm_ase")]
        tsm_c = [c for c in candidates if c.get("entity_type") == "tsm"]

        if tsm_c or ase_c or group_c:
            return tsm_c[:5] + ase_c[:5] + group_c[:5] + lic_c[:25]

        return candidates[:limit]

    @classmethod
    def enrich_candidates_with_period_sales(
        cls,
        candidates: List[Dict[str, Any]],
        period: str,
        target_date: str,
        selected_hq: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Enriches candidate licensees with actual sales cases and bottles in the requested period.
        Filters to active candidates with sales > 0 and sorts by sales descending.
        Falls back to original candidates if none have recorded sales.
        """
        if not candidates:
            return []

        client = get_supabase_client()
        if not client:
            return candidates

        lic_ids = [str(c["id"]) for c in candidates if c.get("entity_type") == "licensee"]
        group_ids = [str(c["id"]) for c in candidates if c.get("entity_type") == "group"]
        ase_ids = [str(c["id"]) for c in candidates if c.get("entity_type") in ("ase", "tsm_ase")]
        tsm_ids = [str(c["id"]) for c in candidates if c.get("entity_type") == "tsm"]
        if not lic_ids and not group_ids and not ase_ids and not tsm_ids:
            return candidates

        try:
            from datetime import datetime
            dt = datetime.strptime(target_date, "%Y-%m-%d")
        except Exception:
            from datetime import datetime
            dt = datetime.utcnow()
            target_date = dt.strftime("%Y-%m-%d")

        if period == "Daily":
            start_date = target_date
        elif period == "MTD":
            start_date = dt.replace(day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            fy_year = dt.year if dt.month >= 4 else dt.year - 1
            start_date = f"{fy_year}-04-01"
        else:
            start_date = target_date

        try:
            hq_id = cls.resolve_hq_id(selected_hq)
            sales_agg: Dict[str, Dict[str, float]] = {}
            for i in range(0, len(lic_ids), 100):
                batch_ids = lic_ids[i:i + 100]
                q = (
                    client.table("sales_daily_summary")
                    .select("licensee_id, company_id, total_cases, total_bottles")
                    .gte("sale_date", start_date)
                    .lte("sale_date", target_date)
                    .in_("licensee_id", batch_ids)
                )
                if hq_id:
                    q = q.eq("headquarters_id", hq_id)
                res = q.execute()
                for r in (res.data or []):
                    # STRICT RULE: Company 'Others' is 100% excluded from all sales calculations
                    if cls._should_exclude_company(company_id=r.get("company_id")):
                        continue
                    lid = str(r["licensee_id"])
                    if lid not in sales_agg:
                        sales_agg[lid] = {"cases": 0.0, "bottles": 0.0}
                    sales_agg[lid]["cases"] += float(r.get("total_cases") or 0.0)
                    sales_agg[lid]["bottles"] += float(r.get("total_bottles") or 0.0)

            group_sales_agg: Dict[str, Dict[str, float]] = {}
            for i in range(0, len(group_ids), 100):
                batch_gids = group_ids[i:i + 100]
                q_g = (
                    client.table("sales_daily_summary")
                    .select("group_id, company_id, total_cases, total_bottles")
                    .gte("sale_date", start_date)
                    .lte("sale_date", target_date)
                    .in_("group_id", batch_gids)
                )
                if hq_id:
                    q_g = q_g.eq("headquarters_id", hq_id)
                res_g = q_g.execute()
                for r in (res_g.data or []):
                    if cls._should_exclude_company(company_id=r.get("company_id")):
                        continue
                    gid = str(r["group_id"])
                    if gid not in group_sales_agg:
                        group_sales_agg[gid] = {"cases": 0.0, "bottles": 0.0}
                    group_sales_agg[gid]["cases"] += float(r.get("total_cases") or 0.0)
                    group_sales_agg[gid]["bottles"] += float(r.get("total_bottles") or 0.0)

            ase_sales_agg: Dict[str, Dict[str, float]] = {}
            for i in range(0, len(ase_ids), 100):
                batch_aids = ase_ids[i:i + 100]
                q_a = (
                    client.table("sales_daily_summary")
                    .select("ase_user_id, company_id, total_cases, total_bottles")
                    .gte("sale_date", start_date)
                    .lte("sale_date", target_date)
                    .in_("ase_user_id", batch_aids)
                )
                if hq_id:
                    q_a = q_a.eq("headquarters_id", hq_id)
                res_a = q_a.execute()
                for r in (res_a.data or []):
                    if cls._should_exclude_company(company_id=r.get("company_id")):
                        continue
                    aid = str(r["ase_user_id"])
                    if aid not in ase_sales_agg:
                        ase_sales_agg[aid] = {"cases": 0.0, "bottles": 0.0}
                    ase_sales_agg[aid]["cases"] += float(r.get("total_cases") or 0.0)
                    ase_sales_agg[aid]["bottles"] += float(r.get("total_bottles") or 0.0)

            tsm_sales_agg: Dict[str, Dict[str, float]] = {}
            for i in range(0, len(tsm_ids), 100):
                batch_tids = tsm_ids[i:i + 100]
                q_t = (
                    client.table("sales_daily_summary")
                    .select("tsm_user_id, company_id, total_cases, total_bottles")
                    .gte("sale_date", start_date)
                    .lte("sale_date", target_date)
                    .in_("tsm_user_id", batch_tids)
                )
                if hq_id:
                    q_t = q_t.eq("headquarters_id", hq_id)
                res_t = q_t.execute()
                for r in (res_t.data or []):
                    if cls._should_exclude_company(company_id=r.get("company_id")):
                        continue
                    tid = str(r["tsm_user_id"])
                    if tid not in tsm_sales_agg:
                        tsm_sales_agg[tid] = {"cases": 0.0, "bottles": 0.0}
                    tsm_sales_agg[tid]["cases"] += float(r.get("total_cases") or 0.0)
                    tsm_sales_agg[tid]["bottles"] += float(r.get("total_bottles") or 0.0)

            active = []
            for c in candidates:
                cid = str(c["id"])
                c_copy = dict(c)
                etype = c.get("entity_type")
                if etype == "tsm":
                    t_data = tsm_sales_agg.get(cid, {})
                    c_copy["cases"] = t_data.get("cases", 0.0)
                    c_copy["bottles"] = int(t_data.get("bottles", 0))
                    c_copy["subtext"] = c.get("subtext") or "Territory Sales Manager"
                    active.append(c_copy)
                elif etype in ("ase", "tsm_ase"):
                    a_data = ase_sales_agg.get(cid, {})
                    c_copy["cases"] = a_data.get("cases", 0.0)
                    c_copy["bottles"] = int(a_data.get("bottles", 0))
                    c_copy["subtext"] = c.get("subtext") or "Area Sales Executive"
                    active.append(c_copy)
                elif etype == "group":
                    g_data = group_sales_agg.get(cid, {})
                    c_copy["cases"] = g_data.get("cases", 0.0)
                    c_copy["bottles"] = int(g_data.get("bottles", 0))
                    c_copy["subtext"] = "Group"
                    active.append(c_copy)
                elif etype == "licensee":
                    if cid in sales_agg and sales_agg[cid]["cases"] > 0:
                        cases = sales_agg[cid]["cases"]
                        bottles = int(sales_agg[cid]["bottles"])
                        c_copy["cases"] = cases
                        c_copy["bottles"] = bottles
                        hq_name = c.get("hq_name") or ""
                        c_copy["subtext"] = c.get("subtext") or (f"Outlet • {hq_name} HQ" if hq_name else "Outlet")
                        active.append(c_copy)
                else:
                    active.append(c_copy)

            # Sort: TSM first, then ASE, then groups, then licensees by cases descending
            active.sort(key=lambda x: (
                3 if x.get("entity_type") == "tsm" else 2 if x.get("entity_type") in ("ase", "tsm_ase") else 1 if x.get("entity_type") == "group" else 0,
                x.get("cases", 0.0)
            ), reverse=True)
            return active
        except Exception as e:
            logger.warning(f"Error enriching candidates with period sales: {e}")
            return []

    @classmethod
    def get_multi_licensee_summary(
        cls,
        licensee_ids: List[str],
        period: str,
        target_date: str,
        selected_hq: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates aggregate sales for multiple licensees and produces a ranked comparison table.
        """
        client = get_supabase_client()
        master = cls._load_master_lookups()
        if not client or not licensee_ids:
            return {"total_cases": 0.0, "total_bottles": 0, "record_count": 0, "rows": []}

        try:
            from datetime import datetime
            dt = datetime.strptime(target_date, "%Y-%m-%d")
        except Exception:
            from datetime import datetime
            dt = datetime.utcnow()
            target_date = dt.strftime("%Y-%m-%d")

        if period == "Daily":
            start_date = target_date
        elif period == "MTD":
            start_date = dt.replace(day=1).strftime("%Y-%m-%d")
        elif period == "YTD":
            fy_year = dt.year if dt.month >= 4 else dt.year - 1
            start_date = f"{fy_year}-04-01"
        else:
            start_date = target_date

        try:
            hq_id = cls.resolve_hq_id(selected_hq)
            sales_by_lic: Dict[str, Dict[str, float]] = {}
            for i in range(0, len(licensee_ids), 100):
                batch_ids = licensee_ids[i:i + 100]
                q = (
                    client.table("sales_daily_summary")
                    .select("licensee_id, company_id, total_cases, total_bottles")
                    .gte("sale_date", start_date)
                    .lte("sale_date", target_date)
                    .in_("licensee_id", batch_ids)
                )
                if hq_id:
                    q = q.eq("headquarters_id", hq_id)
                res = q.execute()
                for r in (res.data or []):
                    # STRICT RULE: Company 'Others' is 100% excluded
                    if cls._should_exclude_company(company_id=r.get("company_id")):
                        continue
                    lid = str(r["licensee_id"])
                    if lid not in sales_by_lic:
                        sales_by_lic[lid] = {"cases": 0.0, "bottles": 0.0}
                    sales_by_lic[lid]["cases"] += float(r.get("total_cases") or 0.0)
                    sales_by_lic[lid]["bottles"] += float(r.get("total_bottles") or 0.0)

            total_cases = sum(d["cases"] for d in sales_by_lic.values())
            total_bottles = int(sum(d["bottles"] for d in sales_by_lic.values()))

            sorted_lics = sorted(sales_by_lic.items(), key=lambda x: x[1]["cases"], reverse=True)
            rows = []
            for rank, (lid, data) in enumerate(sorted_lics, start=1):
                lic_meta = master.get("licensees", {}).get(lid, {})
                name = lic_meta.get("name") or lid
                hq_name = lic_meta.get("hq_name") or "-"
                rows.append({
                    "rank": rank,
                    "name": name,
                    "hq": hq_name,
                    "cases": f"{data['cases']:,.2f}",
                    "bottles": f"{int(data['bottles']):,}",
                })

            return {
                "total_cases": round(total_cases, 2),
                "total_bottles": total_bottles,
                "record_count": len(sorted_lics),
                "rows": rows,
            }
        except Exception as e:
            logger.warning(f"Error computing multi-licensee summary: {e}")
            return {"total_cases": 0.0, "total_bottles": 0, "record_count": 0, "rows": []}

    @classmethod
    def resolve_entity_id(cls, entity_type: str, entity_name: str) -> Optional[str]:
        """Resolves entity name to ID based on type (company, brand, depot, hq, tsm, group, licensee, ase)."""
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
        elif entity_type == "licensee":
            lid = master.get("licensees_rev", {}).get(clean_name)
            if lid:
                return lid
            clean_lic = clean_name.replace("licensee", "").strip()
            if master.get("licensees_rev", {}).get(clean_lic):
                return master["licensees_rev"][clean_lic]
            cands = cls.find_matching_entities(clean_name, target_types=["licensee"], limit=1)
            if cands and cands[0]["score"] >= 0.85:
                return cands[0]["id"]
            return None
        elif entity_type in ("ase", "tsm_ase"):
            aid = master.get("ases_rev", {}).get(clean_name)
            if aid:
                return aid
            clean_ase = clean_name.replace("ase", "").strip()
            if master.get("ases_rev", {}).get(clean_ase):
                return master["ases_rev"][clean_ase]
            cands = cls.find_matching_entities(clean_name, target_types=["ase"], limit=1)
            if cands and cands[0]["score"] >= 0.85:
                return cands[0]["id"]
            return None
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

        master = cls._load_master_lookups()
        clean = entity_name.strip().lower()

        # 1. Exact lookups first: ASE, Group, Brand, Company, TSM, Depot, Licensee
        if clean in master.get("ases_rev", {}):
            return "ase", master["ases_rev"][clean]
        if clean in master.get("groups_rev", {}):
            return "group", master["groups_rev"][clean]
        if clean in master.get("brands_rev", {}):
            return "brand", master["brands_rev"][clean]
        if clean in master.get("companies_rev", {}):
            return "company", master["companies_rev"][clean]
        if clean in master.get("tsms_rev", {}):
            return "tsm", master["tsms_rev"][clean]
        if clean in master.get("depots_rev", {}):
            return "depot", master["depots_rev"][clean]
        if clean in master.get("licensees_rev", {}):
            return "licensee", master["licensees_rev"][clean]

        # 2. Strict / fuzzy checks for high-level entities before licensees
        aid = cls.resolve_entity_id("ase", entity_name)
        if aid:
            return "ase", aid
        
        gid = cls.resolve_entity_id("group", entity_name)
        if gid:
            return "group", gid
            
        bid = cls.resolve_entity_id("brand", entity_name)
        if bid:
            return "brand", bid
            
        cid = cls.resolve_entity_id("company", entity_name)
        if cid:
            return "company", cid
            
        tid = cls.resolve_entity_id("tsm", entity_name)
        if tid:
            return "tsm", tid
            
        did = cls.resolve_entity_id("depot", entity_name)
        if did:
            return "depot", did

        # Check licensee fuzzy last
        lid = cls.resolve_entity_id("licensee", entity_name)
        if lid:
            return "licensee", lid

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
        licensee_id: Optional[str] = None,
        ase_user_id: Optional[str] = None,
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
            if licensee_id:
                query = query.eq("licensee_id", licensee_id)
            if ase_user_id:
                query = query.eq("ase_user_id", ase_user_id)

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
            else "licensee_id" if entity_type == "licensee"
            else "ase_user_id" if entity_type in ("ase", "tsm_ase")
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
                elif entity_type == "licensee":
                    lic_obj = master.get("licensees", {}).get(eid)
                    name = lic_obj["name"] if lic_obj else "Unknown Licensee"
                elif entity_type in ("ase", "tsm_ase"):
                    ase_obj = master.get("ases", {}).get(eid)
                    name = ase_obj["name"] if ase_obj else "Unknown ASE"

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
    # 2b. GET ENTITY BRAND BREAKDOWN (Top Brands Sold for Licensee or ASE)
    # -------------------------------------------------------------------------
    @classmethod
    def get_entity_brand_breakdown(
        cls,
        entity_type: str,  # "licensee" or "ase"
        entity_id: str,
        period: str = "Daily",
        target_date: Optional[str] = None,
        selected_hq: Optional[str] = "All Headquarters",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Returns top selling brands ranked by volume for a specific Licensee or ASE."""
        client = get_supabase_client()
        master = cls._load_master_lookups()
        t_date = target_date or cls.resolve_latest_date()
        hq_id = cls.resolve_hq_id(selected_hq)

        table_name = "sales_daily_summary" if period == "Daily" else "sales_monthly_summary"
        dt = datetime.strptime(t_date, "%Y-%m-%d").date()

        try:
            query = client.table(table_name).select(
                "brand_id, company_id, total_cases, total_bottles"
            )

            if period == "Daily":
                query = query.eq("sale_date", t_date)
            else:
                m_start = dt.replace(day=1).strftime("%Y-%m-%d")
                query = query.gte("month_start", m_start if period == "MTD" else f"{dt.year if dt.month >= 4 else dt.year - 1}-04-01").lte("month_start", t_date)

            if hq_id:
                query = query.eq("headquarters_id", hq_id)

            if entity_type == "licensee":
                query = query.eq("licensee_id", entity_id)
            elif entity_type in ("ase", "tsm_ase"):
                query = query.eq("ase_user_id", entity_id)
            elif entity_type == "tsm":
                query = query.eq("tsm_user_id", entity_id)

            rows = cls._execute_paginated_query(query)
            brand_metrics: Dict[str, Dict[str, float]] = {}
            for r in rows:
                if cls._should_exclude_company(company_id=r.get("company_id")):
                    continue
                bid = str(r.get("brand_id") or "").strip()
                if not bid:
                    continue
                cases = float(r.get("total_cases") or 0.0)
                bottles = float(r.get("total_bottles") or 0.0)
                if bid not in brand_metrics:
                    brand_metrics[bid] = {"cases": 0.0, "bottles": 0.0}
                brand_metrics[bid]["cases"] += cases
                brand_metrics[bid]["bottles"] += bottles

            results = []
            for bid, metrics in brand_metrics.items():
                b_obj = master.get("brands", {}).get(bid)
                bname = b_obj["name"] if b_obj else "Unknown Brand"
                results.append({
                    "id": bid,
                    "name": bname,
                    "cases": round(metrics["cases"], 2),
                    "bottles": int(round(metrics["bottles"])),
                })

            results.sort(key=lambda x: x["cases"], reverse=True)
            return results[:limit]
        except Exception as e:
            logger.error(f"SummaryRepository: get_entity_brand_breakdown error: {e}")
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

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_curr = executor.submit(cls.get_sales_summary, period, t_date, selected_hq, company_id, None, None, tsm_user_id, group_id)
            f_prev = executor.submit(cls.get_sales_summary, period, c_date, selected_hq, company_id, None, None, tsm_user_id, group_id)
            curr_sales = f_curr.result()
            prev_sales = f_prev.result()

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

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_curr = executor.submit(cls.get_top_entities, entity_type, period, t_date, selected_hq, 200, company_id, group_id, tsm_user_id)
            f_prev = executor.submit(cls.get_top_entities, entity_type, period, c_date, selected_hq, 200, company_id, group_id, tsm_user_id)
            curr_list = f_curr.result()
            prev_list = f_prev.result()

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
