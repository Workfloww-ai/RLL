import logging
import asyncio
import time
import copy
import re
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status, Header
from pydantic import BaseModel
from backend.core.security import create_access_token, get_current_user, RoleChecker, normalize_role_name
from backend.services.token_service import (
    create_token_pair,
    refresh_session_async,
    revoke_refresh_token_async,
)
from backend.db.client import get_supabase
from backend.db.supabase_client import resolve_latest_sale_date
from backend.db.company_aliases import normalize_company_name, is_pinned_company
from backend.services.company_cascading_service import is_others_company
from backend.services.activity_log_service import auth_log_service

# Centralized Mobile Access Authorization Policies
MOBILE_ACCESS_ROLES = [
    "tsm",
    "ase",
    "leader",
    "territory_executive",
    "admin",
    "super_admin",
    "developer",
]
MOBILE_ACCESS_ROLES_NORMALIZED = {normalize_role_name(r) for r in MOBILE_ACCESS_ROLES}

MOBILE_ADMIN_ROLES = [
    "admin",
    "super_admin",
    "developer",
]
MOBILE_ADMIN_ROLES_NORMALIZED = {normalize_role_name(r) for r in MOBILE_ADMIN_ROLES}

mobile_access_checker = RoleChecker(MOBILE_ACCESS_ROLES)
mobile_admin_checker = RoleChecker(MOBILE_ADMIN_ROLES)


def resolve_user_mobile_roles(client, user_id: str) -> tuple[str, List[str]]:
    """
    Authoritatively resolves active user roles from Supabase `user_roles`.
    Applies deterministic priority ordering and strict active-status filtering.
    Returns (authoritative_role_name, active_roles_list).
    """
    active_roles: List[str] = []
    authoritative_role = "unassigned"
    try:
        ur_res = client.table("user_roles").select(
            "user_id, role_id, is_active, roles(role_id, role_name)"
        ).eq("user_id", str(user_id)).execute()
        if ur_res.data:
            for ur in ur_res.data:
                if ur.get("is_active") is True:
                    role_obj = ur.get("roles") or {}
                    rname = role_obj.get("role_name")
                    if rname and isinstance(rname, str) and rname.strip():
                        active_roles.append(rname.strip())

            role_priority = [
                "super_admin", "superadmin", "super admin",
                "admin", "developer", "leader", "team_leader", "team leader",
                "tsm", "ase", "territory_executive", "territory executive", "viewer"
            ]
            for prio in role_priority:
                matched = next((r for r in active_roles if r.lower() == prio or normalize_role_name(r) == prio), None)
                if matched:
                    authoritative_role = matched
                    break
            if authoritative_role == "unassigned" and active_roles:
                authoritative_role = active_roles[0]
    except Exception as e_role:
        logger.warning(f"Failed to query active roles for user {user_id}: {e_role}")

    return authoritative_role, active_roles

from backend.db.supabase_client import (
    call_mobile_sales_rpc,
    call_mobile_tsm_sales_rpc,
    call_mobile_sales_json_rpc,
    call_mobile_tsm_sales_json_rpc,
    # Reload uvicorn cache for TSM and ASE company level aggregation
)
from backend.core.config import settings
from backend.services.otp_service import (
    generate_6digit_otp,
    generate_4digit_otp,
    send_dovesoft_sms,
    send_otp_sms,
    store_otp_in_db,
    verify_otp_from_db,
    mask_phone,
    mask_email
)
from supabase import create_client

logger = logging.getLogger(__name__)

# Master lookups in-memory cache with 24-hour TTL and Stale-While-Revalidate (SWR) support
_MASTER_CACHE: Dict[str, Any] = {
    "timestamp": 0,
    "data": None,
    "latest_sale_date": None
}
_MASTER_CACHE_TTL = 86400  # 24-hour TTL for static master data lookups (companies, depots, HQs)
_MASTER_REFRESH_IN_PROGRESS = False

# Sales endpoint response cache with 15-minute TTL for instant screen loading (<150ms)
_SALES_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}
_SALES_RESPONSE_TTL = 86400  # 24 hours TTL for mobile sales analytics responses (invalidated on new file upload)


def _fetch_single_tsm_lookup(user_id: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    if not client or not user_id:
        return None
    try:
        u_res = client.table("users").select("user_id, first_name, last_name, email").eq("user_id", user_id).execute()
        if not u_res.data:
            return None
        u = u_res.data[0]
        full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "TSM Manager"
        tsm_obj = {
            "id": str(user_id),
            "name": full_name,
            "hqLocation": "All Headquarters",
            "depot_ids": set(),
            "ase_ids": [],
            "data": {
                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            },
            "companies_map": {},
            "brands_map": {}
        }
        ud_res = client.table("user_depot").select("depot_id").eq("user_id", user_id).execute()
        for ud in (ud_res.data or []):
            if ud.get("depot_id"):
                tsm_obj["depot_ids"].add(str(ud["depot_id"]))

        atm_res = client.table("ase_tsm_mapping").select("ase_user_id").eq("tsm_user_id", user_id).execute()
        ase_ids = [str(atm["ase_user_id"]) for atm in (atm_res.data or []) if atm.get("ase_user_id")]
        tsm_obj["ase_ids"] = ase_ids

        if ase_ids:
            ase_ud_res = client.table("user_depot").select("depot_id").in_("user_id", ase_ids).execute()
            for ud in (ase_ud_res.data or []):
                if ud.get("depot_id"):
                    tsm_obj["depot_ids"].add(str(ud["depot_id"]))

        return tsm_obj
    except Exception as e:
        logger.warning(f"Error in _fetch_single_tsm_lookup for user_id={user_id}: {e}")
        return None

def _build_master_lookups_dict(
    companies_data: List[Dict[str, Any]],
    brands_data: List[Dict[str, Any]],
    hq_data: List[Dict[str, Any]],
    depots_data: List[Dict[str, Any]],
    roles_data: List[Dict[str, Any]],
    user_roles_data: List[Dict[str, Any]],
    users_data: List[Dict[str, Any]],
    user_depots_data: List[Dict[str, Any]],
    uhq_data: List[Dict[str, Any]],
    atm_data: List[Dict[str, Any]],
    latest_sale_date: Optional[str] = None
) -> Dict[str, Any]:
    companies_lookup: Dict[str, str] = {}
    companies_category_lookup: Dict[str, str] = {}
    for c in (companies_data or []):
        if c.get("company_id") and c.get("company_name"):
            cid = str(c["company_id"])
            cname = c["company_name"]
            cat = str(c.get("category") or "").strip()
            if not cat:
                cat = "Others" if cname.strip().lower() in ("others", "other") or cname.strip().lower().startswith("comp_") else "RLL"
            companies_lookup[cid] = cname
            companies_category_lookup[cid] = cat

    brands_lookup: Dict[str, Dict[str, Any]] = {}
    for b in (brands_data or []):
        if b.get("brand_id") and b.get("brand_name"):
            brands_lookup[str(b["brand_id"])] = {
                "name": b["brand_name"],
                "company_id": str(b["company_id"]) if b.get("company_id") else None
            }

    hq_lookup: Dict[str, str] = {}
    for h in (hq_data or []):
        if h.get("headquarters_id") and h.get("name"):
            hq_lookup[str(h["headquarters_id"])] = h["name"]

    master_companies = {}
    for c_id_raw, c_name in companies_lookup.items():
        if not c_name or is_others_company(c_name):
            continue
        norm_name = normalize_company_name(c_name)
        c_key = norm_name.lower().replace(" ", "-").replace("/", "-")
        master_companies[c_key] = {
            "id": c_key,
            "company_id": str(c_id_raw),
            "name": norm_name,
            "isPinned": is_pinned_company(norm_name, c_key),
            "hqLocation": "All Headquarters",
            "data": {
                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            },
            "brands_map": {}
        }

    master_depots = {}
    for d in (depots_data or []):
        d_id = str(d.get("depot_id"))
        d_name = d.get("name")
        hq_id = str(d.get("headquarters_id") or "")
        hq_name = hq_lookup.get(hq_id, "Unassigned")
        master_depots[d_id] = {
            "id": d_id,
            "name": d_name,
            "hqName": hq_name,
            "data": {
                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            },
            "brands_map": {}
        }

    tsm_role_ids = []
    for r in (roles_data or []):
        rname = str(r.get("role_name", "")).upper()
        if "TSM" in rname or "TERRITORY" in rname:
            tsm_role_ids.append(str(r["role_id"]))

    tsm_user_ids = set()
    if tsm_role_ids:
        for ur in (user_roles_data or []):
            if str(ur.get("role_id")) in tsm_role_ids:
                if ur.get("user_id"):
                    tsm_user_ids.add(str(ur["user_id"]))

    users_map = {str(u["user_id"]): u for u in (users_data or []) if u.get("user_id")}

    master_tsms = {}
    tsm_name_to_id = {}
    for uid in tsm_user_ids:
        u = users_map.get(uid)
        if not u:
            continue
        email = str(u.get("email") or "").lower()
        full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "TSM Manager"
        norm_name = full_name.lower().strip()
        is_active = bool(u.get("is_active", True))
        deactivated_at = u.get("deactivated_at") or (u.get("updated_at") if not is_active else None)

        if norm_name in tsm_name_to_id:
            primary_id = tsm_name_to_id[norm_name]
            if ".com" in email and ".co.in" not in email:
                old_obj = master_tsms.pop(primary_id, None)
                tsm_name_to_id[norm_name] = uid
                existing_aliases = old_obj.get("alias_ids", set()) if old_obj else set()
                master_tsms[uid] = {
                    "id": uid,
                    "name": full_name,
                    "is_active": is_active,
                    "deactivated_at": deactivated_at,
                    "hqLocation": "All Headquarters",
                    "depot_ids": old_obj.get("depot_ids", set()) if old_obj else set(),
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "companies_map": {},
                    "brands_map": {},
                    "alias_ids": existing_aliases | {primary_id, uid}
                }
            else:
                master_tsms[primary_id]["alias_ids"].add(uid)
        else:
            tsm_name_to_id[norm_name] = uid
            master_tsms[uid] = {
                "id": uid,
                "name": full_name,
                "is_active": is_active,
                "deactivated_at": deactivated_at,
                "hqLocation": "All Headquarters",
                "depot_ids": set(),
                "data": {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                },
                "companies_map": {},
                "brands_map": {},
                "alias_ids": {uid}
            }

    user_depots_map = {}
    for ud in (user_depots_data or []):
        uid = str(ud.get("user_id"))
        did = str(ud.get("depot_id"))
        if uid not in user_depots_map:
            user_depots_map[uid] = set()
        user_depots_map[uid].add(did)

    user_hqs_map = {}
    user_hq_ids_map = {}
    for r in (uhq_data or []):
        uid = str(r.get("user_id"))
        hid = str(r.get("headquarters_id"))
        h_name = hq_lookup.get(hid)
        if uid and hid:
            if uid not in user_hq_ids_map:
                user_hq_ids_map[uid] = []
                user_hqs_map[uid] = []
            if hid not in user_hq_ids_map[uid]:
                user_hq_ids_map[uid].append(hid)
            if h_name and h_name not in user_hqs_map[uid]:
                user_hqs_map[uid].append(h_name)

    tsm_ase_lookup = {}
    for atm in (atm_data or []):
        raw_tid = str(atm.get("tsm_user_id"))
        aid = str(atm.get("ase_user_id"))
        tid = raw_tid
        for master_id, t_obj in master_tsms.items():
            if raw_tid in t_obj.get("alias_ids", set()):
                tid = master_id
                break
        if tid not in tsm_ase_lookup:
            tsm_ase_lookup[tid] = set()
        tsm_ase_lookup[tid].add(aid)

    ase_names_lookup = {}
    for aid_set in tsm_ase_lookup.values():
        for aid in aid_set:
            au = users_map.get(str(aid))
            if au:
                ase_names_lookup[str(aid)] = f"{au.get('first_name', '')} {au.get('last_name', '')}".strip() or "ASE"

    for tid, t_obj in master_tsms.items():
        if tid not in ase_names_lookup:
            ase_names_lookup[tid] = t_obj.get('name', 'TSM')

    tsm_depot_lookup = {}
    for tid, t_obj in master_tsms.items():
        for alias_id in t_obj.get("alias_ids", {tid}):
            t_obj["depot_ids"].update(user_depots_map.get(alias_id, set()))
        ase_ids_for_tsm = tsm_ase_lookup.get(tid, set())
        t_obj["ase_ids"] = list(ase_ids_for_tsm)
        for aid in ase_ids_for_tsm:
            t_obj["depot_ids"].update(user_depots_map.get(aid, set()))
        for did in t_obj["depot_ids"]:
            if did not in tsm_depot_lookup:
                tsm_depot_lookup[did] = set()
            tsm_depot_lookup[did].add(tid)

    # Build comprehensive user_alias_map
    user_alias_map = {}
    all_users = users_data or []
    active_users = [u for u in all_users if u.get("is_active")]

    def _clean_str(s):
        return "".join(c for c in str(s or "").lower() if c.isalnum())

    def _first_word(s):
        parts = str(s or "").strip().lower().replace(".", " ").replace("_", " ").split()
        return _clean_str(parts[0]) if parts else ""

    active_by_full = {_clean_str(f"{u.get('first_name','')} {u.get('last_name','')}"): str(u["user_id"]) for u in active_users}
    active_by_first = {_first_word(u.get('first_name','')): str(u["user_id"]) for u in active_users if _first_word(u.get('first_name',''))}
    active_by_prefix = {_first_word(str(u.get('email') or '').split('@')[0]): str(u["user_id"]) for u in active_users if _first_word(str(u.get('email') or '').split('@')[0])}

    for u in all_users:
        uid = str(u["user_id"])
        if u.get("is_active"):
            user_alias_map[uid] = uid
        else:
            fn = str(u.get("first_name") or "").strip()
            ln = str(u.get("last_name") or "").strip()
            full_name = f"{fn} {ln}".strip()
            email = str(u.get("email") or "")
            prefix = email.split("@")[0]

            act_id = (
                active_by_full.get(_clean_str(full_name)) or
                active_by_prefix.get(_first_word(prefix)) or
                active_by_first.get(_first_word(fn)) or
                active_by_first.get(_first_word(full_name))
            )
            if act_id:
                user_alias_map[uid] = act_id
            else:
                user_alias_map[uid] = uid

    hq_name_to_id = {}
    for k, v in hq_lookup.items():
        if v:
            clean_v = v.strip().lower()
            hq_name_to_id[clean_v] = k
            no_sp_v = re.sub(r'[\s\-_.]+', '', clean_v)
            if no_sp_v:
                hq_name_to_id[no_sp_v] = k

    return {
        "companies_lookup": companies_lookup,
        "companies_category_lookup": companies_category_lookup,
        "brands_lookup": brands_lookup,
        "hq_lookup": hq_lookup,
        "hq_name_to_id": hq_name_to_id,
        "master_companies": master_companies,
        "master_depots": master_depots,
        "master_tsms": master_tsms,
        "tsm_depot_lookup": tsm_depot_lookup,
        "user_depots_map": user_depots_map,
        "tsm_ase_lookup": tsm_ase_lookup,
        "ase_names_lookup": ase_names_lookup,
        "user_alias_map": user_alias_map,
        "user_hqs_map": user_hqs_map,
        "user_hq_ids_map": user_hq_ids_map,
        "latest_sale_date": latest_sale_date,
        "users_map": users_map
    }


def _fetch_fresh_master_lookups() -> Dict[str, Any]:
    client = get_supabase()
    if not client:
        return {}

    # Attempt 1: Ultra-fast bundled RPC (1 single roundtrip, Migration 046)
    try:
        b_res = client.rpc("get_master_metadata_bundle").execute()
        if b_res.data and isinstance(b_res.data, dict) and b_res.data.get("companies"):
            bd = b_res.data
            user_roles_data = bd.get("user_roles") or []
            uhq_data = bd.get("user_headquarters_mapping") or []
            # Fallback check: if bundle only returned active user_roles, fetch full user_roles so deactivated personnel past sales are preserved
            has_inactive_ur = any(ur.get("is_active") is False for ur in user_roles_data)
            if not has_inactive_ur and client:
                try:
                    all_ur = client.table("user_roles").select("user_id, role_id, is_active").execute()
                    if all_ur.data:
                        user_roles_data = all_ur.data
                except Exception as e_ur_fetch:
                    logger.warning(f"Notice fetching complete user_roles: {e_ur_fetch}")
            has_inactive_uhq = any(uhq.get("is_active") is False for uhq in uhq_data)
            if not has_inactive_uhq and client:
                try:
                    all_uhq = client.table("user_headquarters_mapping").select("user_id, headquarters_id, is_active").execute()
                    if all_uhq.data:
                        uhq_data = all_uhq.data
                except Exception as e_uhq_fetch:
                    logger.warning(f"Notice fetching complete user_headquarters_mapping: {e_uhq_fetch}")

            logger.info("⚡ Master metadata bundle loaded via single get_master_metadata_bundle RPC.")
            return _build_master_lookups_dict(
                companies_data=bd.get("companies") or [],
                brands_data=bd.get("brands") or [],
                hq_data=bd.get("headquarters") or [],
                depots_data=bd.get("depots") or [],
                roles_data=bd.get("roles") or [],
                user_roles_data=user_roles_data,
                users_data=bd.get("users") or [],
                user_depots_data=bd.get("user_depot") or [],
                uhq_data=uhq_data,
                atm_data=bd.get("ase_tsm_mapping") or [],
                latest_sale_date=bd.get("latest_sale_date")
            )
    except Exception as e_bundle:
        logger.debug(f"get_master_metadata_bundle notice ({e_bundle}), executing concurrent fallback...")

    # Attempt 2: High-concurrency fallback (parallel execution via ThreadPoolExecutor)
    try:
        with ThreadPoolExecutor(max_workers=9) as executor:
            f_lookups = executor.submit(lambda: client.rpc("get_master_lookups_json").execute().data)
            f_companies = executor.submit(lambda: client.table("companies").select("company_id, company_name, category").execute().data or [])
            f_roles = executor.submit(lambda: client.table("roles").select("role_id, role_name").execute().data or [])
            f_user_roles = executor.submit(lambda: client.table("user_roles").select("user_id, role_id, is_active").execute().data or [])
            f_users = executor.submit(lambda: client.table("users").select("user_id, first_name, last_name, email, is_active, updated_at").execute().data or [])
            f_user_depots = executor.submit(lambda: client.table("user_depot").select("user_id, depot_id").execute().data or [])
            f_uhq = executor.submit(lambda: client.table("user_headquarters_mapping").select("user_id, headquarters_id, is_active").execute().data or [])
            f_atm = executor.submit(lambda: client.table("ase_tsm_mapping").select("tsm_user_id, ase_user_id").execute().data or [])
            f_max_date = executor.submit(lambda: [{"sale_date": resolve_latest_sale_date(client)}])

            lookups_data = f_lookups.result() or {}
            companies_data = f_companies.result() or lookups_data.get("companies") or []
            roles_data = f_roles.result()
            user_roles_data = f_user_roles.result()
            users_data = f_users.result()
            user_depots_data = f_user_depots.result()
            uhq_data = f_uhq.result()
            atm_data = f_atm.result()
            max_date_data = f_max_date.result()

            resolved_max_date = max_date_data[0].get("sale_date") if max_date_data else None

            return _build_master_lookups_dict(
                companies_data=companies_data,
                brands_data=lookups_data.get("brands") or [],
                hq_data=lookups_data.get("headquarters") or [],
                depots_data=lookups_data.get("depots") or [],
                roles_data=roles_data,
                user_roles_data=user_roles_data,
                users_data=users_data,
                user_depots_data=user_depots_data,
                uhq_data=uhq_data,
                atm_data=atm_data,
                latest_sale_date=resolved_max_date
            )
    except Exception as e_fallback:
        logger.error(f"Error in concurrent master lookups fallback: {e_fallback}")
        return {}


def _trigger_background_master_refresh():
    """Triggers asynchronous non-blocking background refresh of master lookups (SWR pattern)."""
    global _MASTER_REFRESH_IN_PROGRESS
    if _MASTER_REFRESH_IN_PROGRESS:
        return
    _MASTER_REFRESH_IN_PROGRESS = True
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_refresh_master_cache())
    except RuntimeError:
        import threading
        threading.Thread(target=_thread_refresh_master_cache, daemon=True).start()


async def _async_refresh_master_cache():
    global _MASTER_CACHE, _MASTER_REFRESH_IN_PROGRESS
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch_fresh_master_lookups)
        if data and data.get("master_tsms") and data.get("master_companies"):
            _MASTER_CACHE["data"] = data
            _MASTER_CACHE["timestamp"] = time.time()
            if data.get("latest_sale_date"):
                _MASTER_CACHE["latest_sale_date"] = data["latest_sale_date"]
            logger.info("✅ Master lookup cache refreshed asynchronously in background (SWR).")
    except Exception as e:
        logger.warning(f"Background master lookup refresh error: {e}")
    finally:
        _MASTER_REFRESH_IN_PROGRESS = False


def _thread_refresh_master_cache():
    global _MASTER_CACHE, _MASTER_REFRESH_IN_PROGRESS
    try:
        data = _fetch_fresh_master_lookups()
        if data and data.get("master_tsms") and data.get("master_companies"):
            _MASTER_CACHE["data"] = data
            _MASTER_CACHE["timestamp"] = time.time()
            if data.get("latest_sale_date"):
                _MASTER_CACHE["latest_sale_date"] = data["latest_sale_date"]
            logger.info("✅ Master lookup cache refreshed in background thread (SWR).")
    except Exception as e:
        logger.warning(f"Thread master lookup refresh error: {e}")
    finally:
        _MASTER_REFRESH_IN_PROGRESS = False


def invalidate_master_cache():
    """Forces invalidation of master lookups cache and triggers background re-fetch."""
    global _MASTER_CACHE
    _MASTER_CACHE["timestamp"] = 0
    _trigger_background_master_refresh()
    logger.info("🧹 Master lookup cache invalidated.")


def get_cached_master_lookups():
    """
    Returns cached master lookups instantly (<1ms).
    Uses 24-hour TTL with Stale-While-Revalidate (SWR):
    - Warm cache (<24h): returns immediately.
    - Stale cache (>=24h): returns existing data instantly and refreshes in background.
    - Cold cache (empty): fetches synchronously once, then serves warm.
    """
    now = time.time()
    cached = _MASTER_CACHE.get("data")
    if cached is not None and cached.get("master_tsms"):
        if (now - _MASTER_CACHE["timestamp"]) < _MASTER_CACHE_TTL:
            return copy.deepcopy(cached)
        # SWR: Serve stale immediately without blocking user, refresh in background
        _trigger_background_master_refresh()
        return copy.deepcopy(cached)

    data = _fetch_fresh_master_lookups()
    if data and data.get("master_tsms") and data.get("master_companies"):
        _MASTER_CACHE["data"] = data
        _MASTER_CACHE["timestamp"] = now
        if data.get("latest_sale_date"):
            _MASTER_CACHE["latest_sale_date"] = data["latest_sale_date"]
    return copy.deepcopy(_MASTER_CACHE.get("data") or data)


router = APIRouter(prefix="/mobile", tags=["Mobile App API"])

class MobileLoginRequest(BaseModel):
    email: str
    password: str
    phone_type: Optional[str] = None

class SendOTPRequest(BaseModel):
    phone: str
    email: Optional[str] = None

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str
    email: Optional[str] = None
    phone_type: Optional[str] = None

class MobileLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    user: Dict[str, Any]
    tenant_config: Optional[Dict[str, Any]] = None


@router.post("/login", response_model=MobileLoginResponse)
async def mobile_login(credentials: MobileLoginRequest, request: Request):
    """
    Mobile user authentication endpoint.
    Verifies user from Supabase 'users' table, logs session to 'user_auth_logs'.
    """
    email = credentials.email.lower().strip()
    logger.info(f"Mobile login attempt initiated for user: {email}")
    client = get_supabase()
    
    user_data = None
    
    if client:
        try:
            # 1. Verify credentials with an ephemeral Supabase Auth client to avoid mutating the global client
            temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            auth_response = temp_client.auth.sign_in_with_password({"email": email, "password": credentials.password})
            if not auth_response or not auth_response.user:
                logger.warning(f"Mobile login failed for user {email} (invalid credentials / empty response)")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

            # 2. Get user profile and role
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
            if res.data and len(res.data) > 0:
                db_user = res.data[0]
                if not db_user.get("is_active", True):
                    logger.warning(f"Mobile login failed for user {email} (deactivated account)")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is deactivated"
                    )

                # 2. Resolve Active Roles and Deterministic Priority
                role_name, active_roles = resolve_user_mobile_roles(client, db_user["user_id"])

                # 3. Guardrail: Enforce Mobile roles
                normalized_active = {normalize_role_name(r) for r in active_roles}
                if not normalized_active.intersection(MOBILE_ACCESS_ROLES_NORMALIZED):
                    logger.warning(f"Mobile login access denied for user {mask_email(email)} (roles {active_roles} lack Mobile permissions)")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access Denied: Mobile app is restricted to field personnel, administrators, and developers."
                    )

                # 4. Resolve Depot Name
                depot_name = "Jaipur Depot"
                try:
                    ud_res = client.table("user_depot").select("depot_id, depots(depot_id, name)").eq("user_id", db_user["user_id"]).execute()
                    if ud_res.data:
                        d_obj = ud_res.data[0].get("depots") or {}
                        if d_obj.get("name"):
                            depot_name = d_obj["name"]
                except Exception:
                    pass

                user_data = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email"),
                    "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone", ""),
                    "role_name": role_name,
                    "roles": active_roles,
                    "depot_name": depot_name,
                    "hq_location": "All Headquarters",
                    "tenant_id": str(db_user.get("tenant_id") or ""),
                    "company_id": str(db_user.get("company_id")) if db_user.get("company_id") else None,
                    "company_name": db_user.get("company_name"),
                    "is_active": bool(db_user.get("is_active", True))
                }
                logger.info(f"Mobile login successful for user: {mask_email(email)} with role: {role_name}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during mobile login for user {email}: {e}")
            if "Invalid login credentials" in str(e):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
            logger.warning(f"Supabase users lookup error: {e}")

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # 2. Record user's last login in user_auth_logs (updates existing user record to prevent DB bloat)
    client_ip = request.client.host if (request and request.client) else None
    user_agent = request.headers.get("user-agent") if request else None
    phone_type = auth_log_service.detect_phone_type(request, user_agent, credentials.phone_type)
    auth_log_service.dispatch_background(
        user_id=user_data["user_id"],
        email=email,
        phone_type=phone_type,
        ip_address=client_ip,
        user_agent=user_agent,
        action="LOGIN",
        status="SUCCESS",
    )

    # 3. Create Dual-Token Pair (1h Access Token + 30-day Rolling Refresh Token)
    token_pair = await create_token_pair(user_data, client_type="mobile")

    return {
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "expires_in": token_pair["expires_in"],
        "user": user_data
    }


@router.post("/send-otp")
async def send_mobile_otp(req: SendOTPRequest):
    """
    Send 6-digit OTP to user's mobile number via Dovesoft SMS Gateway.
    Verifies user is registered in Supabase 'users' table before sending.
    """
    email = (req.email or "").lower().strip()
    phone = (req.phone or "").strip()
    logger.info(f"Mobile OTP request initiated for phone: {mask_phone(phone)}, email: {mask_email(email)}")

    if not email and not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address or phone number is required")

    client = get_supabase()
    clean_phone_10 = ''.join(c for c in phone if c.isdigit())
    if len(clean_phone_10) >= 10:
        clean_phone_10 = clean_phone_10[-10:]

    # 1. Dedicated App Review Flow (Google Play Store & Apple App Store review)
    if clean_phone_10 == settings.APP_REVIEW_PHONE:
        if not settings.APP_REVIEW_MODE_ENABLED:
            logger.warning("App review OTP request rejected: review mode is disabled")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="App review mode is disabled"
            )
        logger.info(f"App review OTP requested for dedicated review phone {mask_phone(settings.APP_REVIEW_PHONE)}")
        return {
            "success": True,
            "message": "OTP verification code sent successfully.",
            "phone": f"+91{settings.APP_REVIEW_PHONE}",
            "company_name": "Rajasthan Liquor Limited (Demo)",
            "company_logo_url": None
        }

    # 2. Check if user is currently locked out before allowing another OTP to be sent
    from backend.db.redis_client import safe_set_nx, safe_get, safe_delete
    attempt_key = f"rll:mobile_otp_attempts:{clean_phone_10}"
    existing_attempts_raw = await safe_get(attempt_key, security_sensitive=True)
    try:
        existing_attempts = int(existing_attempts_raw or "0")
    except (ValueError, TypeError):
        existing_attempts = 0

    if existing_attempts >= 5:
        logger.warning(f"OTP send rejected for {mask_phone(clean_phone_10)}: account currently locked out")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account is temporarily locked out due to multiple failed verification attempts. Please try again in 5 minutes."
        )

    # 3. Enforce atomic resend cooldown (30 seconds) across workers
    cooldown_key = f"rll:otp_cooldown:{clean_phone_10}"
    cooldown_acquired = await safe_set_nx(cooldown_key, "active", ttl=30, security_sensitive=True)
    if cooldown_acquired is None:
        logger.error(f"Cannot acquire resend cooldown lock: shared Redis store unavailable in {settings.ENVIRONMENT}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS verification service temporarily unavailable. Please try again later."
        )
    if not cooldown_acquired:
        logger.warning(f"OTP resend cooldown active for phone {mask_phone(clean_phone_10)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 30 seconds before requesting another OTP code."
        )

    db_user = None
    if client:
        try:
            # 1. Lookup by email if provided
            if email:
                res = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").ilike("email", email).execute()
                if res.data:
                    db_user = res.data[0]

            # 2. Lookup by phone if not found by email
            if not db_user and clean_phone_10:
                res_phone = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").ilike("phone", f"%{clean_phone_10}%").limit(1).execute()
                if res_phone.data:
                    db_user = res_phone.data[0]
                else:
                    # Fallback robust phone lookup: strip non-digits from db phones
                    all_users_res = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").execute()
                    if all_users_res.data:
                        for u in all_users_res.data:
                            u_p = ''.join(c for c in (u.get("phone") or "") if c.isdigit())
                            if u_p and (clean_phone_10 in u_p or u_p in clean_phone_10):
                                db_user = u
                                break
        except Exception as e:
            logger.warning(f"User lookup error in send_mobile_otp: {e}")

    # Enforce registered user requirement
    if not db_user:
        await safe_delete(cooldown_key)
        logger.warning(f"Mobile OTP request failed: Phone/Email not registered (Phone: {mask_phone(phone)}, Email: {mask_email(email)})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    if not db_user.get("is_active", True):
        await safe_delete(cooldown_key)
        logger.warning(f"Mobile OTP request failed: Account is deactivated (Phone: {mask_phone(phone)}, Email: {mask_email(email)})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This user account is deactivated."
        )

    # Use registered user's phone number or input phone
    target_phone = db_user.get("phone") or phone

    # Generate 6-digit OTP
    otp_code = generate_6digit_otp()

    # Store in Supabase otp_codes table
    store_otp_in_db(target_phone, otp_code)
    store_otp_in_db(phone, otp_code)  # Store for input phone as well for verification lookup

    # Directly await SMS dispatch via Dovesoft API
    sms_sent = await send_otp_sms(target_phone, otp_code)
    logger.info(f"Mobile OTP successfully generated and sent via SMS to {mask_phone(target_phone)} (SMS sent status: {sms_sent})")

    # Resolve user company name and logo for dynamic branding
    company_name = db_user.get("company_name")
    company_id = db_user.get("company_id")
    company_logo_url = None
    if company_id:
        try:
            c_res = client.table("companies").select("company_name, logo_url").eq("company_id", company_id).limit(1).execute()
            if c_res.data:
                company_name = company_name or c_res.data[0].get("company_name")
                company_logo_url = c_res.data[0].get("logo_url")
        except Exception:
            pass
    if not company_logo_url and company_name:
        try:
            c_res = client.table("companies").select("logo_url").ilike("company_name", company_name.strip()).limit(1).execute()
            if c_res.data:
                company_logo_url = c_res.data[0].get("logo_url")
        except Exception:
            pass

    return {
        "success": True,
        "message": "OTP verification code sent successfully.",
        "phone": target_phone,
        "company_name": company_name or "Rajasthan Liquor Limited",
        "company_logo_url": company_logo_url
    }


@router.post("/verify-otp", response_model=MobileLoginResponse)
async def verify_mobile_otp(req: VerifyOTPRequest, request: Request):
    """
    Verify 6-digit OTP code sent to user's mobile number.
    Returns 30-day Access Token and scoped user profile.
    """
    email = (req.email or "").lower().strip()
    phone = (req.phone or "").strip()
    otp_code = (req.otp or "").strip()
    logger.info(f"Mobile OTP verification attempt initiated for phone: {mask_phone(phone)}")

    if not phone or not otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number and 6-digit OTP code are required")

    clean_in = ''.join(c for c in phone if c.isdigit())
    clean_10 = clean_in[-10:] if len(clean_in) >= 10 else clean_in

    # Dedicated Google Play & Apple App Store review flow (Explicitly Isolated)
    is_review_phone = (clean_10 == settings.APP_REVIEW_PHONE)
    if is_review_phone:
        if not settings.APP_REVIEW_MODE_ENABLED:
            logger.warning("App review verification rejected: review mode is disabled")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="App review mode is disabled"
            )
        if otp_code != settings.APP_REVIEW_OTP:
            logger.warning(f"App review verification failed for phone {mask_phone(clean_10)}: invalid review code")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired 6-digit OTP code"
            )

        # Isolated Demo Review Identity
        user_data = {
            "user_id": settings.APP_REVIEW_USER_ID,
            "email": settings.APP_REVIEW_EMAIL,
            "first_name": "Demo",
            "last_name": "Reviewer",
            "phone": f"+91{settings.APP_REVIEW_PHONE}",
            "role_name": "TSM",
            "role": "TSM",
            "roles": ["tsm"],
            "depot_name": "Jaipur Demo Depot",
            "hq_location": "All Headquarters",
            "tenant_id": settings.APP_REVIEW_DEMO_TENANT_ID,
            "company_id": None,
            "company_name": "Rajasthan Liquor Limited (Demo)",
            "company_logo_url": "/images/rll logo.svg",
            "is_active": True
        }

        # Issue dual-token review session
        token_pair = await create_token_pair(user_data, client_type="mobile")
        logger.info(
            f"Dedicated review session generated for {mask_phone(settings.APP_REVIEW_PHONE)} "
            f"(expires in {settings.APP_REVIEW_TOKEN_EXPIRE_HOURS}h, tenant: {settings.APP_REVIEW_DEMO_TENANT_ID})"
        )
        return {
            "access_token": token_pair["access_token"],
            "refresh_token": token_pair["refresh_token"],
            "token_type": "bearer",
            "expires_in": token_pair["expires_in"],
            "user": user_data,
            "tenant_config": {
                "tenant_id": user_data["tenant_id"],
                "app_name": "LucidX360 Demo",
                "logo_url": user_data["company_logo_url"],
                "pinned_company_name": "Rajasthan Liquor Limited (Demo)",
            }
        }

    # Distributed attempt counter across workers for normal users
    from backend.db.redis_client import safe_incr, safe_delete
    attempt_key = f"rll:mobile_otp_attempts:{clean_10}"
    attempts = await safe_incr(attempt_key, ttl=300, security_sensitive=True)
    if attempts is None:
        logger.error(f"Mobile OTP verification failed: shared rate-limit store unavailable in {settings.ENVIRONMENT}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable. Please try again later."
        )
    if attempts > 5:
        logger.warning(f"Maximum OTP verification attempts exceeded for phone {mask_phone(clean_10)} ({attempts} attempts)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts exceeded. Please try again in 5 minutes."
        )

    # Standard database OTP verification for all other numbers
    is_valid = verify_otp_from_db(phone, otp_code)
    if not is_valid:
        logger.warning(f"Mobile OTP verification failed for phone: {mask_phone(phone)} - Invalid or expired OTP code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired 6-digit OTP code")

    # Verification succeeded: clear distributed attempt counter
    await safe_delete(attempt_key)

    client = get_supabase()
    user_data = None
    if client:
        try:
            db_user = None
            if email:
                res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
                if res.data:
                    db_user = res.data[0]

            if not db_user and phone:
                res_phone = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").execute()
                if res_phone.data:
                    for u in res_phone.data:
                        u_p = ''.join(c for c in (u.get("phone") or "") if c.isdigit())
                        if u_p and (clean_10 in u_p or u_p in clean_10):
                            db_user = u
                            break

            if db_user:
                if not db_user.get("is_active", True):
                    logger.warning(f"Mobile OTP verification failed for phone: {mask_phone(phone)} - Account deactivated")
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is deactivated")

                # 2. Resolve Active Roles and Deterministic Priority
                role_name, active_roles = resolve_user_mobile_roles(client, db_user["user_id"])

                # 3. Guardrail: Enforce Mobile roles
                normalized_active = {normalize_role_name(r) for r in active_roles}
                if not normalized_active.intersection(MOBILE_ACCESS_ROLES_NORMALIZED):
                    logger.warning(
                        f"Mobile OTP access denied for user {mask_email(db_user.get('email'))}: "
                        f"active roles {active_roles} lack Mobile permissions"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access Denied: Mobile app is restricted to field personnel, administrators, and developers."
                    )

                depot_name = "Jaipur Depot"
                try:
                    ud_res = client.table("user_depot").select("depot_id").eq("user_id", db_user["user_id"]).execute()
                    if ud_res.data:
                        d_id = ud_res.data[0].get("depot_id")
                        dep_res = client.table("depots").select("name").eq("depot_id", d_id).limit(1).execute()
                        if dep_res.data:
                            depot_name = dep_res.data[0].get("name", "Jaipur Depot")
                except Exception:
                    pass

                # Resolve user's company and company logo
                company_name = db_user.get("company_name")
                company_id = db_user.get("company_id")
                tenant_id = str(db_user.get("tenant_id") or "")
                company_logo_url = None

                if company_id:
                    try:
                        c_res = client.table("companies").select("company_name, logo_url").eq("company_id", company_id).limit(1).execute()
                        if c_res.data:
                            company_name = company_name or c_res.data[0].get("company_name")
                            company_logo_url = c_res.data[0].get("logo_url")
                    except Exception:
                        pass

                if not company_logo_url and company_name:
                    try:
                        c_res = client.table("companies").select("logo_url").ilike("company_name", company_name.strip()).limit(1).execute()
                        if c_res.data:
                            company_logo_url = c_res.data[0].get("logo_url")
                    except Exception:
                        pass

                user_data = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email") or email or f"{phone}@rll.com",
                    "first_name": db_user.get("first_name", "User"),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone") or phone,
                    "role_name": role_name,
                    "roles": active_roles,
                    "depot_name": depot_name,
                    "hq_location": "All Headquarters",
                    "tenant_id": tenant_id,
                    "company_id": str(company_id) if company_id else None,
                    "company_name": company_name,
                    "company_logo_url": company_logo_url or "/images/rll logo.svg",
                    "is_active": bool(db_user.get("is_active", True))
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resolving user profile on OTP verify: {e}")
            logger.warning(f"Error resolving user profile on OTP verify: {e}")

    if not user_data:
        logger.warning(f"Mobile OTP verification failed for phone: {mask_phone(phone)} - User profile not registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    # Generate Dual-Token Pair (1h Access Token + 30-day Rolling Refresh Token)
    token_pair = await create_token_pair(user_data, client_type="mobile")
    logger.info(f"Mobile OTP verification successful for phone: {mask_phone(phone)} (User: {mask_email(user_data['email'])}, Company: {user_data['company_name']}, Role: {user_data['role_name']})")

    # Record user's last login in user_auth_logs (updates existing user record to prevent DB bloat)
    client_ip = request.client.host if (request and request.client) else None
    user_agent = request.headers.get("user-agent") if request else None
    phone_type = auth_log_service.detect_phone_type(request, user_agent, req.phone_type)
    auth_log_service.dispatch_background(
        user_id=user_data["user_id"],
        email=user_data["email"],
        phone_type=phone_type,
        ip_address=client_ip,
        user_agent=user_agent,
        action="LOGIN_OTP",
        status="SUCCESS",
    )

    return {
        "access_token": token_pair["access_token"],
        "refresh_token": token_pair["refresh_token"],
        "token_type": "bearer",
        "expires_in": token_pair["expires_in"],
        "user": user_data,
        "tenant_config": {
            "tenant_id": user_data["tenant_id"],
            "app_name": user_data["company_name"] or "LucidX360",
            "logo_url": user_data["company_logo_url"],
            "pinned_company_name": user_data["company_name"] or "Rajasthan Liquor Limited",
        }
    }


class MobileRefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_mobile_token(req: MobileRefreshTokenRequest):
    """
    Refreshes mobile access token using rolling 30-day refresh token.
    Guarantees continuous 30-day rolling session for active mobile users.
    """
    return await refresh_session_async(req.refresh_token)


class MobileLogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/logout")
async def mobile_logout(req: Optional[MobileLogoutRequest] = None):
    """
    Safely revokes the mobile refresh token upon user logout.
    """
    if req and req.refresh_token:
        await revoke_refresh_token_async(req.refresh_token)
    return {"success": True, "message": "Logged out successfully."}


@router.get("/me")
def get_mobile_user_profile(
    current_user: dict = Depends(mobile_access_checker)
):
    """
    Fetch current logged-in user profile with depot and company details.
    """
    client = get_supabase()
    sub_val = (current_user.get("sub") or current_user.get("email") or current_user.get("phone") or "").strip()
    user_id_val = current_user.get("user_id")
    if not client:
        return current_user

    if user_id_val == settings.APP_REVIEW_USER_ID or current_user.get("is_review_user") or (sub_val == settings.APP_REVIEW_EMAIL and user_id_val == settings.APP_REVIEW_USER_ID):
        if not settings.APP_REVIEW_MODE_ENABLED:
            logger.warning("Profile request rejected: App review mode is disabled")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="App review mode is disabled"
            )
        return {
            "user_id": settings.APP_REVIEW_USER_ID,
            "email": settings.APP_REVIEW_EMAIL,
            "first_name": "Demo",
            "last_name": "Reviewer",
            "phone": f"+91{settings.APP_REVIEW_PHONE}",
            "role_name": "TSM",
            "role": "TSM",
            "roles": ["tsm"],
            "depot_name": "Jaipur Demo Depot",
            "hq_location": "All Headquarters",
            "tenant_id": settings.APP_REVIEW_DEMO_TENANT_ID,
            "company_id": None,
            "company_name": "Rajasthan Liquor Limited (Demo)",
            "company_logo_url": "/images/rll logo.svg",
            "is_active": True
        }


    try:
        db_user = None
        if user_id_val:
            u_res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").eq("user_id", user_id_val).execute()
            if u_res.data:
                db_user = u_res.data[0]

        if not db_user and sub_val:
            u_res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").or_(f"email.ilike.{sub_val},phone.ilike.%{sub_val}%").execute()
            if u_res.data:
                db_user = u_res.data[0]

        if db_user:
            role_name = current_user.get("role", "TSM")
            depot_name = "Jaipur Depot"
            try:
                ud_res = client.table("user_depot").select("depot_id").eq("user_id", db_user["user_id"]).execute()
                if ud_res.data:
                    d_id = ud_res.data[0].get("depot_id")
                    dep_res = client.table("depots").select("name").eq("depot_id", d_id).limit(1).execute()
                    if dep_res.data:
                        depot_name = dep_res.data[0].get("name", "Jaipur Depot")
            except Exception:
                pass

            company_name = db_user.get("company_name") or current_user.get("company_name")
            company_id = db_user.get("company_id")
            tenant_id = str(db_user.get("tenant_id") or current_user.get("tenant_id") or "")
            company_logo_url = None

            if company_id:
                try:
                    c_res = client.table("companies").select("company_name, logo_url").eq("company_id", company_id).limit(1).execute()
                    if c_res.data:
                        company_name = company_name or c_res.data[0].get("company_name")
                        company_logo_url = c_res.data[0].get("logo_url")
                except Exception:
                    pass

            if not company_logo_url and company_name:
                try:
                    c_res = client.table("companies").select("logo_url").ilike("company_name", company_name.strip()).limit(1).execute()
                    if c_res.data:
                        company_logo_url = c_res.data[0].get("logo_url")
                except Exception:
                    pass

            return {
                "user_id": str(db_user.get("user_id")),
                "email": db_user.get("email"),
                "first_name": db_user.get("first_name", "User"),
                "last_name": db_user.get("last_name", ""),
                "phone": db_user.get("phone", ""),
                "role_name": role_name,
                "roles": current_user.get("roles") or ([role_name] if role_name != "unassigned" else []),
                "depot_name": depot_name,
                "hq_location": "All Headquarters",
                "tenant_id": tenant_id,
                "company_id": str(company_id) if company_id else None,
                "company_name": company_name,
                "company_logo_url": company_logo_url or "/images/rll logo.svg",
                "is_active": bool(db_user.get("is_active", True))
            }
    except Exception as e:
        logger.warning(f"Error fetching profile in /mobile/me: {e}")

    return current_user


@router.get("/headquarters")
def get_mobile_headquarters():
    """
    Fetches active headquarters from public.headquarters table in Supabase.
    Includes master cache fallback to guarantee 0 HTTP 500 errors.
    """
    try:
        client = get_supabase()
        if client:
            res = client.table("headquarters").select("headquarters_id, name, is_active").eq("is_active", True).order("name").execute()
            hq_data = res.data or []
            if hq_data:
                hq_names = ["All Headquarters"] + [h["name"] for h in hq_data if h.get("name")]
                return {
                    "status": "success",
                    "count": len(hq_names),
                    "headquarters": hq_names
                }
    except Exception as e:
        logger.warning(f"Direct DB query failed in /mobile/headquarters, falling back to master cache: {e}")

    # Fallback 1: Try master cache lookups
    try:
        master_cache = get_cached_master_lookups()
        hq_lookup = master_cache.get("hq_lookup", {})
        if hq_lookup:
            unique_hqs = sorted(list(set(hq_lookup.values())))
            hq_names = ["All Headquarters"] + [h for h in unique_hqs if h and h != "Unassigned"]
            return {
                "status": "success",
                "count": len(hq_names),
                "headquarters": hq_names
            }
    except Exception as e_cache:
        logger.warning(f"Master cache fallback failed in /mobile/headquarters: {e_cache}")

    # Fallback 2: Static Headquarters fallback
    default_hqs = [
        "All Headquarters", "Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur",
        "Bhilwara", "Bikaner", "Bundi", "Chittorgarh", "Churu", "Dausa", "Dholpur",
        "Dungarpur", "Hanumangarh", "Jaipur", "Jaisalmer", "Jalore", "Jhalawar",
        "Jhunjhunu", "Jodhpur", "Karauli", "Kota", "Nagaur", "Pali", "Pratapgarh",
        "Rajsamand", "Sawai Madhopur", "Sikar", "Sirohi", "Sri Ganganagar", "Tonk", "Udaipur"
    ]
    return {
        "status": "success",
        "count": len(default_hqs),
        "headquarters": default_hqs
    }


_COMPANIES_LOCKS: Dict[str, asyncio.Lock] = {}
_COMPANIES_LOCKS_GUARD = asyncio.Lock()

async def _get_companies_stampede_lock(key: str) -> asyncio.Lock:
    async with _COMPANIES_LOCKS_GUARD:
        if key not in _COMPANIES_LOCKS:
            _COMPANIES_LOCKS[key] = asyncio.Lock()
        return _COMPANIES_LOCKS[key]


@router.get("/companies")
async def get_mobile_companies(
    period: str = Query("Daily", description="Sales period: Daily, MTD, YTD"),
    date_to: Optional[str] = Query(None, alias="date"),
    selected_hq: Optional[str] = Query(None, alias="selected_hq"),
    refresh: bool = Query(False, description="Bypass cache on explicit refresh"),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetches period-specific company sales analytics (Daily, MTD, YTD).
    Excludes Company 'Others' strictly. Scopes to user's assigned company if applicable.
    Caches response in Redis with single-flight stampede protection.
    """
    from backend.services.mobile_companies_service import get_companies_summary_async
    from backend.services.cache_service import get_json_cache, set_json_cache
    from backend.services.tenant_service import get_include_others_setting_async

    t_start = time.perf_counter()

    clean_period = period.strip() if period else "Daily"
    clean_hq = selected_hq.strip() if selected_hq else "All Headquarters"
    clean_date = date_to.strip() if date_to else "latest"

    # User company scoping: if user has assigned company, scope sales data strictly to that company
    user_role = (current_user.get("role_name") or current_user.get("role") or "").lower()
    user_company = current_user.get("company_name")
    effective_company = user_company if (user_company and user_role not in ["admin", "super_admin", "super admin", "developer"]) else None

    inc_others_str = "inc1" if await get_include_others_setting_async() else "inc0"
    redis_key = f"rll:mobile:companies:{clean_period}:{clean_hq}:{clean_date}:{effective_company or 'all'}:{inc_others_str}"

    t0 = time.perf_counter()
    if not refresh:
        cached_payload = await get_json_cache(redis_key)
        t_cache_hit = (time.perf_counter() - t0) * 1000
        if cached_payload is not None:
            logger.info(f"get_mobile_companies TELEMETRY: Cache HIT in {t_cache_hit:.2f} ms | Key: {redis_key}")
            return cached_payload
    else:
        t_cache_hit = (time.perf_counter() - t0) * 1000

    # Single-flight stampede lock protection
    lock = await _get_companies_stampede_lock(redis_key)
    async with lock:
        # Re-check cache inside lock in case another request built it while we waited
        if not refresh:
            t_lock_recheck = time.perf_counter()
            cached_payload = await get_json_cache(redis_key)
            if cached_payload is not None:
                logger.info(f"get_mobile_companies TELEMETRY: Cache HIT (Stampede Waiter) in {(time.perf_counter()-t_lock_recheck)*1000:.2f} ms | Key: {redis_key}")
                return cached_payload

        try:
            t_service_start = time.perf_counter()
            companies_list, resolved_date = await get_companies_summary_async(
                period=clean_period,
                date_to=date_to,
                selected_hq=selected_hq,
                company_name=effective_company
            )
            t_service_ms = (time.perf_counter() - t_service_start) * 1000

            payload = {
                "status": "success",
                "period": clean_period,
                "count": len(companies_list),
                "latest_sale_date": resolved_date,
                "companies": companies_list
            }

            t_write_start = time.perf_counter()
            if len(companies_list) > 0:
                await set_json_cache(redis_key, payload, ttl=86400)  # 24 hours TTL (invalidated on new file upload)
            t_write_ms = (time.perf_counter() - t_write_start) * 1000

            t_total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                f"get_mobile_companies TELEMETRY Cache MISS: Total={t_total_ms:.2f}ms | "
                f"CacheLookup={t_cache_hit:.2f}ms | Service={t_service_ms:.2f}ms | CacheWrite={t_write_ms:.2f}ms"
            )
            return payload
        except Exception as e:
            logger.error(f"Error fetching mobile companies analytics: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))



@router.get("/companies/{company_id}/brands")
def get_company_brands(
    company_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetches brands belonging to a specific company from public.brands table using company_id (UUID or Name).
    """
    client = get_supabase()
    try:
        target_company_id = company_id
        if len(company_id) != 36 or "-" not in company_id:
            c_res = client.table("companies").select("company_id, company_name").ilike("company_name", company_id.replace("-", " ")).execute()
            if c_res.data and len(c_res.data) > 0:
                target_company_id = str(c_res.data[0]["company_id"])

        res = client.table("brands").select("brand_id, brand_name, company_id, is_active, created_at").eq("company_id", target_company_id).eq("is_active", True).order("brand_name").execute()
        brands_data = res.data or []

        return {
            "status": "success",
            "company_id": company_id,
            "count": len(brands_data),
            "brands": [
                {
                    "brand_id": str(b.get("brand_id")),
                    "brand_name": b.get("brand_name"),
                    "company_id": str(b.get("company_id")),
                    "is_active": b.get("is_active", True),
                    "created_at": b.get("created_at")
                }
                for b in brands_data
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching brands for company {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sales")
async def get_mobile_sales(
    request: Request,
    date_from: Optional[str] = Query(None, description="Start Date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End Date YYYY-MM-DD"),
    period: str = Query("Daily", description="Daily | MTD | YTD"),
    selected_hq: str = Query("All Headquarters", description="Headquarters filter"),
    level: Optional[str] = Query(None, description="level filter: companies | depots | tsms"),
    page: Optional[int] = Query(None, description="Page number for depots pagination (1-indexed)"),
    page_size: Optional[int] = Query(None, description="Page size for depots pagination (1 to 100)"),
    test_limit: Optional[int] = Query(None, description="Diagnostic payload scaling test limit"),
    tsm_include_others: Optional[bool] = Query(None, description="Toggle to include or exclude others/competitor companies on TSM screen"),
    current_user: dict = Depends(mobile_access_checker)
):
    """
    Returns real aggregated sales data for Companies, Depots, and TSMs directly calculated from Supabase.
    Computes distinct, dynamic metrics for Daily, MTD, and YTD with database-level HQ filtering.
    Supports level filtering (companies/depots/tsms), period pruning, and depot pagination.
    Instruments every stage of execution with microsecond timing.
    """
    import json
    import uuid
    import math
    from fastapi import Response
    from fastapi.responses import JSONResponse

    clean_level = None
    if level is not None and str(level).strip():
        clean_level = str(level).strip().lower()
        if clean_level not in ["companies", "depots", "tsms"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level parameter '{level}'. Must be one of: companies, depots, tsms"
            )

    if page is not None and page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page parameter must be an integer >= 1"
        )

    if page_size is not None and (page_size < 1 or page_size > 100):
        raise HTTPException(
            status_code=400,
            detail="Page size parameter must be between 1 and 100"
        )

    t_api_start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:8]}"

    # A & B. Auth timing
    t_auth_start = time.perf_counter()
    user_role = (current_user.get("role_name") or current_user.get("role") or "").lower()
    user_id = current_user.get("user_id")
    user_tenant_id = current_user.get("tenant_id")
    if not user_tenant_id or not str(user_tenant_id).strip():
        logger.warning(f"Unauthorized: user {user_id} has no valid tenant_id association.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: User profile has no valid tenant association"
        )
    
    # Apply Data Visibility Toggle
    from backend.db.redis_client import safe_get
    restriction_setting = await safe_get("rll:setting:tsm_ase_data_restriction_enabled")
    is_restricted = str(restriction_setting).strip().lower() != "false" # Defaults to true
    
    if not is_restricted and user_role in ["tsm", "ase", "territory executive"]:
        # When restriction is OFF, TSM/ASE behave like Leaders
        logger.info(f"Data restriction OFF: Upgrading role of {user_id} from {user_role} to leader")
        user_role = "leader"
        
    t_auth_end = time.perf_counter()
    auth_duration_ms = round((t_auth_end - t_auth_start) * 1000, 2)

    client = get_supabase()
    raw_period = (period or "Daily").strip().upper()
    if raw_period == "DAILY":
        selected_period = "Daily"
    elif raw_period in ["MTD", "MONTHLY"]:
        selected_period = "MTD"
    elif raw_period in ["YTD", "YEARLY"]:
        selected_period = "YTD"
    else:
        selected_period = "Daily"

    from backend.services.tenant_service import get_include_others_setting_async, get_include_others_in_tsm_sales_async
    inc_others_str = "inc1" if await get_include_others_setting_async() else "inc0"
    tsm_inc_str = "tsm_default" if tsm_include_others is None else ("tsm_inc1" if tsm_include_others else "tsm_inc0")
    effective_cache_uid = "global" if user_role in ["leader", "admin", "super_admin", "developer"] else (user_id or "global")
    cache_key = f"{selected_period}:{clean_level or 'all'}:{page or 'all'}:{page_size or 'all'}:{selected_hq}:{date_from}:{date_to}:{user_role}:{effective_cache_uid}:{test_limit or 'all'}:{inc_others_str}:{tsm_inc_str}"
    
    # D. Sales response cache timing
    t_sales_cache_start = time.perf_counter()
    now_ts = time.time()

    # ── Stampede Protection (Single-Flight Lock) ─────────────────────────────
    if not hasattr(get_mobile_sales, "_stampede_locks"):
        get_mobile_sales._stampede_locks = {}
        get_mobile_sales._stampede_guard = asyncio.Lock()

    async with get_mobile_sales._stampede_guard:
        if cache_key not in get_mobile_sales._stampede_locks:
            get_mobile_sales._stampede_locks[cache_key] = asyncio.Lock()
        stampede_lock = get_mobile_sales._stampede_locks[cache_key]

    async with stampede_lock:
        now_ts = time.time()
        if cache_key in _SALES_RESPONSE_CACHE:
            entry = _SALES_RESPONSE_CACHE[cache_key]
            if now_ts - entry["timestamp"] < _SALES_RESPONSE_TTL:
                t_sales_cache_end = time.perf_counter()
                sales_cache_duration_ms = round((t_sales_cache_end - t_sales_cache_start) * 1000, 2)
                t_api_end = time.perf_counter()
                total_api_ms = round((t_api_end - t_api_start) * 1000, 2)

                cached_data = entry["data"]
                cached_bytes = len(json.dumps(cached_data).encode("utf-8"))
                cached_kb = round(cached_bytes / 1024, 2)
                cached_mb = round(cached_bytes / (1024 * 1024), 2)

                return JSONResponse(
                    content=cached_data,
                    headers={
                        "X-Request-ID": request_id,
                        "X-Backend-Duration-Ms": str(total_api_ms),
                        "X-Response-Size-Bytes": str(cached_bytes),
                        "X-Sales-Cache-Status": "HIT"
                    }
                )

        redis_key = f"rll:mobile:sales:{cache_key}"
        try:
            from backend.services.cache_service import get_json_cache
            redis_cached_data = await get_json_cache(redis_key)
            if redis_cached_data:
                if isinstance(redis_cached_data, dict):
                    redis_cached_data["process_time_ms"] = 0.0
                _SALES_RESPONSE_CACHE[cache_key] = {
                    "timestamp": time.time(),
                    "data": redis_cached_data
                }
                t_api_end = time.perf_counter()
                total_api_ms = round((t_api_end - t_api_start) * 1000, 2)
                raw_str = json.dumps(redis_cached_data) if isinstance(redis_cached_data, (dict, list)) else str(redis_cached_data)
                return Response(
                    content=raw_str,
                    media_type="application/json",
                    headers={
                        "X-Request-ID": request_id,
                        "X-Backend-Duration-Ms": str(total_api_ms),
                        "X-Response-Size-Bytes": str(len(raw_str.encode('utf-8'))),
                        "X-Sales-Cache-Status": "REDIS_HIT"
                    }
                )
        except Exception as e_redis:
            logger.warning(f"Redis cache check failed: {e_redis}")

        t_sales_cache_end = time.perf_counter()
        sales_cache_duration_ms = round((t_sales_cache_end - t_sales_cache_start) * 1000, 2)

        # C. Master cache lookup timing
        t_master_start = time.perf_counter()
        master_cache_hit = _MASTER_CACHE.get("data") is not None and (time.time() - _MASTER_CACHE.get("timestamp", 0)) < _MASTER_CACHE_TTL
        master_cache = get_cached_master_lookups()
        t_master_end = time.perf_counter()
        master_cache_duration_ms = round((t_master_end - t_master_start) * 1000, 2)

        companies_lookup = master_cache["companies_lookup"]
        companies_category_lookup = master_cache.get("companies_category_lookup", {})
        brands_lookup = master_cache["brands_lookup"]
        hq_lookup = master_cache["hq_lookup"]
        master_companies = master_cache["master_companies"]
        master_depots = master_cache["master_depots"]
        master_tsms = master_cache["master_tsms"]
        tsm_depot_lookup = master_cache["tsm_depot_lookup"]
        user_depots_map = master_cache["user_depots_map"]
        tsm_ase_lookup = master_cache["tsm_ase_lookup"]
        ase_names_lookup = master_cache["ase_names_lookup"]
        user_hqs_map = master_cache.get("user_hqs_map", {})

        allowed_depots = set()
        if user_role == "tsm":
            if user_id in master_tsms:
                allowed_depots.update(master_tsms[user_id]["depot_ids"])
            else:
                single_tsm = _fetch_single_tsm_lookup(user_id)
                if single_tsm:
                    allowed_depots.update(single_tsm.get("depot_ids", set()))
        elif user_role == "ase":
            allowed_depots = set(user_depots_map.get(user_id, []))

        # Cached latest sale date resolution (0ms DB calls on cache hit)
        latest_sale_date = _MASTER_CACHE.get("latest_sale_date")
        if not latest_sale_date or (time.time() - _MASTER_CACHE.get("timestamp", 0)) >= _MASTER_CACHE_TTL:
            latest_sale_date = resolve_latest_sale_date(client)
            _MASTER_CACHE["latest_sale_date"] = latest_sale_date

        end_date = latest_sale_date
        if date_to and date_to.strip():
            end_date = date_to.strip()
        elif date_from and date_from.strip():
            end_date = date_from.strip()

        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except Exception:
            end_dt = datetime.utcnow().date()
            end_date = end_dt.strftime("%Y-%m-%d")

        daily_start = end_date
        if selected_period == "Daily":
            mtd_start = end_date
            ytd_start = end_date
        elif selected_period == "MTD":
            mtd_start = end_dt.replace(day=1).strftime("%Y-%m-%d")
            ytd_start = mtd_start
        else:
            mtd_start = end_dt.replace(day=1).strftime("%Y-%m-%d")
            fy_year = end_dt.year if end_dt.month >= 4 else end_dt.year - 1
            ytd_start = f"{fy_year}-04-01"

        target_hq_id = None
        if selected_hq and selected_hq.strip() and selected_hq.strip() != "All Headquarters":
            clean_hq_target = selected_hq.strip().lower()
            no_sp_target = re.sub(r'[\s\-_.]+', '', clean_hq_target)
            target_hq_id = master_cache.get("hq_name_to_id", {}).get(clean_hq_target) or master_cache.get("hq_name_to_id", {}).get(no_sp_target)

        # ── Early Level Slicing & Parallel RPC Execution ───────────────────────
        comp_rpc_params = {
            "p_target_date": end_date,
            "p_mtd_start": mtd_start,
            "p_ytd_start": ytd_start,
        }
        if target_hq_id:
            comp_rpc_params["p_hq_id"] = target_hq_id

        # Pre-resolve active company UUIDs for brand RPC
        brand_company_ids = [
            str(cid_raw).strip().lower()
            for cid_raw, cname_raw in companies_lookup.items()
            if cname_raw and not is_others_company(cname_raw)
        ]
        brand_params = {
            "p_company_ids": brand_company_ids,
            "p_target_date": end_date,
            "p_mtd_start": mtd_start,
            "p_ytd_start": ytd_start,
        }
        if target_hq_id:
            brand_params["p_hq_id"] = target_hq_id

        company_records = []
        depot_records = []
        brands_data = []
        all_usf_records = []
        rpc_trace_info: Dict[str, Any] = {}
        tsm_rpc_trace: Dict[str, Any] = {}

        # Pre-build member_to_tsms mapping from master lookups
        user_alias_map = master_cache.get("user_alias_map", {})
        member_to_tsms = {}
        ase_assigned_tsm = {}

        for tid, t_obj in master_tsms.items():
            if tid not in member_to_tsms:
                member_to_tsms[tid] = set()
            member_to_tsms[tid].add(tid)
            for aid in tsm_ase_lookup.get(tid, set()):
                if aid == tid:
                    continue
                if aid not in ase_assigned_tsm:
                    ase_assigned_tsm[aid] = tid
                    if aid not in member_to_tsms:
                        member_to_tsms[aid] = set()
                    member_to_tsms[aid].add(tid)

        # Expand member_to_tsms to include all alias user_ids
        for inactive_id, active_id in user_alias_map.items():
            if active_id in member_to_tsms:
                if inactive_id not in member_to_tsms:
                    member_to_tsms[inactive_id] = set()
                member_to_tsms[inactive_id].update(member_to_tsms[active_id])

        scoped_user_ids = None
        if selected_hq and selected_hq != "All Headquarters":
            clean_sel_hq = selected_hq.strip().lower()
            clean_sel_no_space = re.sub(r'[\s\-_.]+', '', clean_sel_hq)
            matched_uids = [
                uid for uid, hq_list in user_hqs_map.items()
                if any(h.strip().lower() == clean_sel_hq or re.sub(r'[\s\-_.]+', '', h).lower() == clean_sel_no_space for h in hq_list)
            ]
            scoped_user_ids = matched_uids

        # Enforce role-based user scoping for TSM and ASE roles when data restriction is active
        if user_role == "tsm":
            t_obj = master_tsms.get(user_id)
            permitted_uids = (set(t_obj.get("alias_ids", {user_id})) | set(t_obj.get("ase_ids", []))) if t_obj else {user_id}
            if scoped_user_ids is None:
                scoped_user_ids = list(permitted_uids)
            else:
                scoped_user_ids = [uid for uid in scoped_user_ids if uid in permitted_uids]
        elif user_role in ["ase", "territory executive"]:
            permitted_uids = {user_id}
            if scoped_user_ids is None:
                scoped_user_ids = list(permitted_uids)
            else:
                scoped_user_ids = [uid for uid in scoped_user_ids if uid in permitted_uids]
        elif scoped_user_ids is None and member_to_tsms:
            # For All Headquarters viewed by unrestricted roles (Admin, Super Admin, Director):
            # Scope to the known fleet users (TSMs, ASEs, and aliases) so PostgreSQL seeks directly
            # to active sales personnel via index instead of scanning millions of unrelated sales fact rows.
            scoped_user_ids = list(member_to_tsms.keys())

        t_rpc_start = time.perf_counter()

        def _exec_companies_rpc():
            res = client.rpc("get_mobile_companies_summary", comp_rpc_params).execute()
            return res.data or []

        def _exec_sales_json_rpc():
            return call_mobile_sales_json_rpc(end_date, mtd_start, ytd_start, target_hq_id, trace_info=rpc_trace_info)

        def _exec_brands_rpc():
            if not brand_company_ids:
                return []
            try:
                res = client.rpc("get_mobile_company_brands_summary", brand_params).execute()
                return res.data or []
            except Exception as e_brands:
                logger.error(f"Error calling get_mobile_company_brands_summary RPC: {e_brands}")
                rpc_trace_info["brands_rpc_error"] = str(e_brands)
                return []

        user_tenant_id = current_user.get("tenant_id")

        def _exec_tsm_rpc():
            try:
                return call_mobile_tsm_sales_json_rpc(
                    end_date,
                    mtd_start,
                    ytd_start,
                    user_ids=scoped_user_ids,
                    hq_id=target_hq_id,
                    tenant_id=user_tenant_id,
                    trace_info=tsm_rpc_trace,
                )
            except Exception as e_tsm:
                logger.error(f"Error calling call_mobile_tsm_sales_json_rpc: {e_tsm}")
                tsm_rpc_trace["tsm_rpc_error"] = str(e_tsm)
                rpc_trace_info["tsm_rpc_error"] = str(e_tsm)
                return []

        if clean_level == "companies":
            comp_res, b_res = await asyncio.gather(
                asyncio.to_thread(_exec_companies_rpc),
                asyncio.to_thread(_exec_brands_rpc)
            )
            company_records = comp_res
            brands_data = b_res
        elif clean_level == "depots":
            sales_payload = await asyncio.to_thread(_exec_sales_json_rpc)
            depot_records = sales_payload.get("depots") or []
        elif clean_level == "tsms":
            all_usf_records = await asyncio.to_thread(_exec_tsm_rpc)
        else:  # Full response (clean_level is None)
            comp_res, sales_payload, b_res, usf_res = await asyncio.gather(
                asyncio.to_thread(_exec_companies_rpc),
                asyncio.to_thread(_exec_sales_json_rpc),
                asyncio.to_thread(_exec_brands_rpc),
                asyncio.to_thread(_exec_tsm_rpc)
            )
            company_records = comp_res
            depot_records = sales_payload.get("depots") or []
            brands_data = b_res
            all_usf_records = usf_res

        t_rpc_end = time.perf_counter()
        rpc_duration_ms = round((t_rpc_end - t_rpc_start) * 1000, 2)
        rpc_trace_info["sales_rpc_duration_ms"] = rpc_duration_ms
        if tsm_rpc_trace.get("tsm_rpc_error"):
            rpc_trace_info["tsm_rpc_error"] = tsm_rpc_trace["tsm_rpc_error"]

        total_records_processed = len(company_records) + len(depot_records) + len(brands_data) + len(all_usf_records)

        # ── Python Transformation Timing (Strictly separate from RPC wait!) ───
        t_transform_start = time.perf_counter()



    grouped_comp_rows = {}
    for cid_raw, cname_raw in companies_lookup.items():
        if not cname_raw or is_others_company(cname_raw):
            continue
        norm_name = normalize_company_name(cname_raw)
        comp_id = norm_name.lower().replace(" ", "-").replace("/", "-")
        if comp_id not in grouped_comp_rows:
            grouped_comp_rows[comp_id] = {
                "id": comp_id,
                "name": norm_name,
                "isPinned": is_pinned_company(norm_name, comp_id),
                "hqLocation": selected_hq or "All Headquarters",
                "company_ids": [str(cid_raw)],
                "data": {
                    "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                },
                "brands_map": {}
            }
        else:
            if str(cid_raw) not in grouped_comp_rows[comp_id]["company_ids"]:
                grouped_comp_rows[comp_id]["company_ids"].append(str(cid_raw))

    for row in company_records:
        cid = str(row.get("company_id") or "")
        cname = str(row.get("company_name") or "").strip()
        if not cname or is_others_company(cname):
            continue

        norm_name = normalize_company_name(cname)
        comp_id = norm_name.lower().replace(" ", "-").replace("/", "-")

        if comp_id not in grouped_comp_rows:
            grouped_comp_rows[comp_id] = {
                "id": comp_id,
                "name": norm_name,
                "isPinned": is_pinned_company(norm_name, comp_id),
                "hqLocation": selected_hq or "All Headquarters",
                "company_ids": [cid] if cid else [],
                "data": {
                    "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                },
                "brands_map": {}
            }
        else:
            if cid and cid not in grouped_comp_rows[comp_id]["company_ids"]:
                grouped_comp_rows[comp_id]["company_ids"].append(cid)

        g = grouped_comp_rows[comp_id]
        g["data"]["Daily"]["cases"] += float(row.get("daily_cases") or 0.0)
        g["data"]["Daily"]["bottles"] += float(row.get("daily_bottles") or 0.0)
        g["data"]["Daily"]["bl"] += float(row.get("daily_bl") or 0.0)
        g["data"]["MTD"]["cases"] += float(row.get("mtd_cases") or 0.0)
        g["data"]["MTD"]["bottles"] += float(row.get("mtd_bottles") or 0.0)
        g["data"]["MTD"]["bl"] += float(row.get("mtd_bl") or 0.0)
        g["data"]["YTD"]["cases"] += float(row.get("ytd_cases") or 0.0)
        g["data"]["YTD"]["bottles"] += float(row.get("ytd_bottles") or 0.0)
        g["data"]["YTD"]["bl"] += float(row.get("ytd_bl") or 0.0)

    # Collect all company UUIDs across grouped companies to fetch brand summaries in a SINGLE RPC call
    all_company_ids = []
    raw_to_comp_id = {}
    for comp_id, g in grouped_comp_rows.items():
        for cid in g["company_ids"]:
            cid_clean = str(cid).strip().lower()
            if cid_clean and cid_clean not in all_company_ids:
                all_company_ids.append(cid_clean)
            if cid_clean:
                raw_to_comp_id[cid_clean] = comp_id

    # Pre-populate brands_map with ALL master registered brands for each company (so 0-sale brands are counted and listed)
    for bid, binfo in brands_lookup.items():
        b_comp_id = str(binfo.get("company_id") or "").strip().lower()
        if b_comp_id and b_comp_id in raw_to_comp_id:
            comp_id = raw_to_comp_id[b_comp_id]
            if comp_id in grouped_comp_rows:
                g = grouped_comp_rows[comp_id]
                bid_str = str(bid).strip().lower()
                if bid_str not in g["brands_map"]:
                    g["brands_map"][bid_str] = {
                        "id": bid_str,
                        "name": binfo.get("name") or "Generic Brand",
                        "data": {
                            "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                            "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                            "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        }
                    }

        for b in brands_data:
            raw_cid = str(b.get("company_id") or "").strip().lower()
            comp_id = raw_to_comp_id.get(raw_cid)
            if not comp_id or comp_id not in grouped_comp_rows:
                continue

            g = grouped_comp_rows[comp_id]
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

            if bid not in g["brands_map"]:
                g["brands_map"][bid] = {
                    "id": bid,
                    "name": bname,
                    "data": {
                        "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    }
                }
            bm = g["brands_map"][bid]
            bm["data"]["Daily"]["cases"] += b_daily_cases
            bm["data"]["Daily"]["bottles"] += b_daily_bottles
            bm["data"]["Daily"]["bl"] += b_daily_bl
            bm["data"]["MTD"]["cases"] += b_mtd_cases
            bm["data"]["MTD"]["bottles"] += b_mtd_bottles
            bm["data"]["MTD"]["bl"] += b_mtd_bl
            bm["data"]["YTD"]["cases"] += b_ytd_cases
            bm["data"]["YTD"]["bottles"] += b_ytd_bottles
            bm["data"]["YTD"]["bl"] += b_ytd_bl

    # Store in master_companies
    for comp_id, g in grouped_comp_rows.items():
        master_companies[comp_id] = {
            "id": comp_id,
            "name": g["name"],
            "isPinned": g["isPinned"],
            "hqLocation": g["hqLocation"],
            "data": {
                "Daily": {"cases": round(g["data"]["Daily"]["cases"], 2), "bottles": round(g["data"]["Daily"]["bottles"], 2), "bl": round(g["data"]["Daily"]["bl"], 2)},
                "MTD": {"cases": round(g["data"]["MTD"]["cases"], 2), "bottles": round(g["data"]["MTD"]["bottles"], 2), "bl": round(g["data"]["MTD"]["bl"], 2)},
                "YTD": {"cases": round(g["data"]["YTD"]["cases"], 2), "bottles": round(g["data"]["YTD"]["bottles"], 2), "bl": round(g["data"]["YTD"]["bl"], 2)},
            },
            "brands_map": g["brands_map"]
        }

    for row in depot_records:
        raw_depot_id = str(row.get("depot_id") or "")
        depot_info = master_depots.get(raw_depot_id) or {}
        depot_name = depot_info.get("name") or "Central Depot"
        target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")

        if user_role in ["tsm", "ase"] and target_depot_id not in allowed_depots:
            continue

        b_id_raw = str(row.get("brand_id") or "")
        b_info = brands_lookup.get(b_id_raw, {})
        brand_name = b_info.get("name") or "Generic Brand"
        brand_id = b_id_raw or brand_name.lower().replace(" ", "-")

        raw_hq_id = str(row.get("headquarters_id") or "")
        hq_name = hq_lookup.get(raw_hq_id) or depot_info.get("hq_name") or "All Headquarters"

        target_depot = master_depots.get(raw_depot_id)
        if not target_depot:
            target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")
            if target_depot_id not in master_depots:
                master_depots[target_depot_id] = {
                    "id": target_depot_id,
                    "name": depot_name,
                    "hqName": hq_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "brands_map": {}
                }
            target_depot = master_depots[target_depot_id]

        row_metrics = {
            "Daily": {
                "cases": float(row.get("daily_cases") or 0.0),
                "bottles": float(row.get("daily_bottles") or 0.0),
                "bl": float(row.get("daily_bl") or 0.0),
            },
            "MTD": {
                "cases": float(row.get("mtd_cases") or 0.0),
                "bottles": float(row.get("mtd_bottles") or 0.0),
                "bl": float(row.get("mtd_bl") or 0.0),
            },
            "YTD": {
                "cases": float(row.get("ytd_cases") or 0.0),
                "bottles": float(row.get("ytd_bottles") or 0.0),
                "bl": float(row.get("ytd_bl") or 0.0),
            },
        }

        for period_key, metrics in row_metrics.items():
            target_depot["data"][period_key]["cases"] += metrics["cases"]
            target_depot["data"][period_key]["bottles"] += metrics["bottles"]
            target_depot["data"][period_key]["bl"] += metrics["bl"]

            db_map = target_depot["brands_map"]
            if brand_id not in db_map:
                db_map[brand_id] = {
                    "brandId": brand_id,
                    "brandName": brand_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    }
                }
            db_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
            db_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
            db_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

    user_alias_map = master_cache.get("user_alias_map", {})
    users_map = master_cache.get("users_map", {})
    member_to_tsms = {}
    ase_assigned_tsm = {}

    for tid, t_obj in master_tsms.items():
        if tid not in member_to_tsms:
            member_to_tsms[tid] = set()
        member_to_tsms[tid].add(tid)
        
        for aid in tsm_ase_lookup.get(tid, set()):
            if aid == tid:
                continue
            # Enforce 1-to-1 ASE to TSM mapping so an ASE's sales are NEVER double-counted across multiple TSMs
            if aid not in ase_assigned_tsm:
                ase_assigned_tsm[aid] = tid
                if aid not in member_to_tsms:
                    member_to_tsms[aid] = set()
                member_to_tsms[aid].add(tid)
            else:
                logger.warning(f"⚠️ [PERMANENT GUARDRAIL] ASE {aid} is mapped to multiple TSMs ({ase_assigned_tsm[aid]} vs {tid}). Retaining primary TSM {ase_assigned_tsm[aid]}.")

    # Expand member_to_tsms to include all alias user_ids
    for inactive_id, active_id in user_alias_map.items():
        if active_id in member_to_tsms:
            if inactive_id not in member_to_tsms:
                member_to_tsms[inactive_id] = set()
            member_to_tsms[inactive_id].update(member_to_tsms[active_id])

    all_known_ase_ids = {aid for aids in tsm_ase_lookup.values() for aid in aids}
    # Also track direct sales made by TSMs acting as ASEs
    for tid in master_tsms.keys():
        all_known_ase_ids.add(tid)
    ase_sales = {
        aid: {
            "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
            "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
        }
        for aid in all_known_ase_ids
    }
    ase_comp_sets = {aid: {"Daily": set(), "MTD": set(), "YTD": set()} for aid in all_known_ase_ids}
    tsm_comp_sets = {tid: {"Daily": set(), "MTD": set(), "YTD": set()} for tid in master_tsms.keys()}
    ase_company_maps = {aid: {} for aid in all_known_ase_ids}
    ase_brand_maps = {aid: {} for aid in all_known_ase_ids}

    # Initialize companies_map on master_tsms
    for tid in master_tsms.keys():
        master_tsms[tid]["companies_map"] = {}
        master_tsms[tid]["brands_map"] = {}
        master_tsms[tid]["data"] = {
            "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
            "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
            "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
        }



    # Determine effective TSM include others toggle
    if tsm_include_others is not None:
        effective_tsm_include = tsm_include_others
    else:
        effective_tsm_include = await get_include_others_in_tsm_sales_async()

    for row in all_usf_records:
        c_id_raw = str(row.get("company_id") or "")
        comp_name = companies_lookup.get(c_id_raw)
        if not comp_name:
            continue
        comp_cat = companies_category_lookup.get(c_id_raw) or ("Others" if is_others_company(comp_name) else "RLL")
        is_comp_others = (comp_cat.strip().lower() == "others" or is_others_company(comp_name, comp_cat))

        if not effective_tsm_include and is_comp_others:
            continue

        raw_uid = str(row.get("user_id") or "")
        uid = user_alias_map.get(raw_uid, raw_uid)
        target_tsm_ids = member_to_tsms.get(raw_uid) or member_to_tsms.get(uid, set())
        if not target_tsm_ids:
            continue

        b_id_raw = str(row.get("brand_id") or "")
        b_info = brands_lookup.get(b_id_raw, {})
        brand_name = b_info.get("name") or "Generic Brand"
        brand_id = b_id_raw or brand_name.lower().replace(" ", "-")

        usf_metrics = {
            "Daily": {
                "cases": float(row.get("daily_cases") or 0.0),
                "bottles": float(row.get("daily_bottles") or 0.0),
                "bl": float(row.get("daily_bl") or 0.0),
            },
            "MTD": {
                "cases": float(row.get("mtd_cases") or 0.0),
                "bottles": float(row.get("mtd_bottles") or 0.0),
                "bl": float(row.get("mtd_bl") or 0.0),
            },
            "YTD": {
                "cases": float(row.get("ytd_cases") or 0.0),
                "bottles": float(row.get("ytd_bottles") or 0.0),
                "bl": float(row.get("ytd_bl") or 0.0),
            },
        }

        # Check if user is inactive: if so, Daily sales on or after deactivation date are not credited
        u_record = users_map.get(uid, {})
        u_is_active = bool(u_record.get("is_active", True))
        u_deact_date = str(u_record.get("deactivated_at") or u_record.get("updated_at") or "")[:10] if not u_is_active else None

        for period_key, metrics in usf_metrics.items():
            if metrics["cases"] > 0 or metrics["bottles"] > 0:
                if uid in ase_sales:
                    # Inactive ASE guard: do not credit daily sales on or after deactivation date
                    if not (period_key == "Daily" and u_deact_date and end_date and end_date >= u_deact_date):
                        ase_sales[uid][period_key]["cases"] += metrics["cases"]
                        ase_sales[uid][period_key]["bottles"] += metrics["bottles"]
                        ase_sales[uid][period_key]["bl"] += metrics["bl"]
                        ase_comp_sets[uid][period_key].add(c_id_raw)

                        # ASE Company level
                        ac_map = ase_company_maps[uid]
                        if c_id_raw not in ac_map:
                            ac_map[c_id_raw] = {
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "name": comp_name,
                                "category": comp_cat,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        ac_map[c_id_raw]["data"][period_key]["cases"] += metrics["cases"]
                        ac_map[c_id_raw]["data"][period_key]["bottles"] += metrics["bottles"]
                        ac_map[c_id_raw]["data"][period_key]["bl"] += metrics["bl"]

                        # ASE Brand level
                        ab_map = ase_brand_maps[uid]
                        if brand_id not in ab_map:
                            ab_map[brand_id] = {
                                "brandId": brand_id,
                                "brandName": brand_name,
                                "name": brand_name,
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        ab_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
                        ab_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
                        ab_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

                for tid in target_tsm_ids:
                    if tid in master_tsms:
                        t_obj = master_tsms[tid]
                        t_is_active = bool(t_obj.get("is_active", True))
                        t_deact_date = str(t_obj.get("deactivated_at") or "")[:10] if not t_is_active else None
                        # Inactive TSM guard: do not credit daily sales on or after deactivation date
                        if period_key == "Daily" and t_deact_date and end_date and end_date >= t_deact_date:
                            continue

                        t_obj["data"][period_key]["cases"] += metrics["cases"]
                        t_obj["data"][period_key]["bottles"] += metrics["bottles"]
                        t_obj["data"][period_key]["bl"] += metrics["bl"]
                        tsm_comp_sets[tid][period_key].add(c_id_raw)

                        # TSM Company level
                        tc_map = t_obj["companies_map"]
                        if c_id_raw not in tc_map:
                            tc_map[c_id_raw] = {
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "name": comp_name,
                                "category": comp_cat,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        tc_map[c_id_raw]["data"][period_key]["cases"] += metrics["cases"]
                        tc_map[c_id_raw]["data"][period_key]["bottles"] += metrics["bottles"]
                        tc_map[c_id_raw]["data"][period_key]["bl"] += metrics["bl"]

                        # TSM Brand level
                        tb_map = t_obj["brands_map"]
                        if brand_id not in tb_map:
                            tb_map[brand_id] = {
                                "brandId": brand_id,
                                "brandName": brand_name,
                                "name": brand_name,
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        tb_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
                        tb_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
                        tb_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

    formatted_companies = []
    for c_id, c_data in master_companies.items():
        all_b = list(c_data.pop("brands_map", {}).values())
        active_b = [
            b for b in all_b
            if (b.get("data", {}).get(selected_period, {}).get("cases", 0) > 0 or
                b.get("data", {}).get(selected_period, {}).get("bottles", 0) > 0)
        ]
        c_data["brands"] = active_b if active_b else all_b
        clean_sel_no_space = re.sub(r'[\s\-_.]+', '', selected_hq).lower() if selected_hq else ""
        if selected_hq != "All Headquarters" and c_data.get("hqLocation") and c_data["hqLocation"] != "All Headquarters":
            c_loc_no_space = re.sub(r'[\s\-_.]+', '', c_data["hqLocation"]).lower()
            if c_data["hqLocation"].lower() != selected_hq.lower() and c_loc_no_space != clean_sel_no_space:
                continue
        formatted_companies.append(c_data)

    formatted_depots = []
    for d_id, d_data in master_depots.items():
        all_b = list(d_data.pop("brands_map", {}).values())
        d_data["brands"] = [
            b for b in all_b
            if (b.get("data", {}).get(selected_period, {}).get("cases", 0) > 0 or
                b.get("data", {}).get(selected_period, {}).get("bottles", 0) > 0)
        ]
        if selected_hq != "All Headquarters" and d_data.get("hqName"):
            d_name_no_space = re.sub(r'[\s\-_.]+', '', d_data["hqName"]).lower()
            if d_data["hqName"].lower() != selected_hq.lower() and d_name_no_space != clean_sel_no_space:
                continue
        formatted_depots.append(d_data)

    formatted_tsms = []
    for t_id, raw_t_data in master_tsms.items():
        t_data = dict(raw_t_data)
        t_data["companies"] = list(t_data.get("companies_map", {}).values())
        # Omit massive 665-brand arrays from TSM and ASE payloads to shrink payload by 96.6% (from 5.5MB down to 190KB)
        t_data.pop("brands_map", None)

        t_data["companyCount"] = {
            "Daily": len(tsm_comp_sets.get(t_id, {}).get("Daily", set())),
            "MTD": len(tsm_comp_sets.get(t_id, {}).get("MTD", set())),
            "YTD": len(tsm_comp_sets.get(t_id, {}).get("YTD", set())),
        }
        depot_ids_list = list(t_data.get("depot_ids", set()))
        t_data.pop("depot_ids", None)
        t_data.pop("alias_ids", None)
        t_data.pop("companies_map", None)

        assigned_hq_names = []
        for alias_id in raw_t_data.get("alias_ids", {t_id}):
            for h in user_hqs_map.get(alias_id, []):
                if h not in assigned_hq_names:
                    assigned_hq_names.append(h)

        if assigned_hq_names:
            t_data["hqLocation"] = ", ".join(assigned_hq_names)
            t_data["assignedHqs"] = assigned_hq_names
        else:
            t_data["hqLocation"] = "Unassigned"
            t_data["assignedHqs"] = []

        if selected_hq and selected_hq != "All Headquarters":
            clean_sel_hq = selected_hq.strip().lower()
            clean_sel_no_space = re.sub(r'[\s\-_.]+', '', clean_sel_hq)
            matches_hq = any(
                h.strip().lower() == clean_sel_hq or re.sub(r'[\s\-_.]+', '', h).lower() == clean_sel_no_space
                for h in assigned_hq_names
            )
            if not matches_hq:
                continue

        raw_ase_ids = t_data.pop("ase_ids", [])
        # If the TSM directly made sales as an ASE (dual-role), ensure they are shown in their ASE breakdown
        t_alias_ids = raw_t_data.get("alias_ids") or {t_id}
        has_direct_sales = False
        direct_aid = t_id
        for cand_id in [t_id] + [aid for aid in t_alias_ids if aid != t_id]:
            cand_sales = ase_sales.get(cand_id)
            if cand_sales and any(
                cand_sales.get(p, {}).get("cases", 0) > 0 or cand_sales.get(p, {}).get("bottles", 0) > 0
                for p in ["Daily", "MTD", "YTD"]
            ):
                has_direct_sales = True
                direct_aid = cand_id
                break
        if has_direct_sales and not any(aid in raw_ase_ids for aid in t_alias_ids):
            raw_ase_ids = [direct_aid] + list(raw_ase_ids)
        t_data["ases"] = [
            {
                "id": aid,
                "name": ase_names_lookup.get(aid, "ASE"),
                "hqLocation": ", ".join(user_hqs_map.get(aid, [])) if user_hqs_map.get(aid) else "Unassigned",
                "assignedHqs": user_hqs_map.get(aid, []),
                "data": ase_sales.get(aid, {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                }),
                "companyCount": {
                    "Daily": len(ase_comp_sets.get(aid, {}).get("Daily", set())),
                    "MTD": len(ase_comp_sets.get(aid, {}).get("MTD", set())),
                    "YTD": len(ase_comp_sets.get(aid, {}).get("YTD", set())),
                },
                "companies": list(ase_company_maps.get(aid, {}).values()),
            }
            for aid in raw_ase_ids
        ]

        # Inactive ASE filter: prune inactive ASEs with 0 sales for the active period
        t_data["ases"] = [
            ase for ase in t_data.get("ases", [])
            if (bool(users_map.get(ase.get("id"), {}).get("is_active", True)) or
                ase.get("data", {}).get(selected_period, {}).get("cases", 0) > 0 or
                ase.get("data", {}).get(selected_period, {}).get("bottles", 0) > 0)
        ]

        # Filter out TSM cards with 0 cases and 0 bottles for the active period
        tsm_period_cases = t_data.get("data", {}).get(selected_period, {}).get("cases", 0)
        tsm_period_bottles = t_data.get("data", {}).get(selected_period, {}).get("bottles", 0)
        if tsm_period_cases == 0 and tsm_period_bottles == 0:
            continue

        formatted_tsms.append(t_data)

    # Apply controlled payload test limit if requested
    if test_limit and test_limit > 0:
        logger.info(f"🧪 [DIAGNOSTIC TEST] Slicing companies, depots, and tsms to limit={test_limit}")
        formatted_companies = formatted_companies[:test_limit]
        formatted_depots = formatted_depots[:test_limit]
        formatted_tsms = formatted_tsms[:test_limit]

    t_transform_end = time.perf_counter()
    transform_duration_ms = round((t_transform_end - t_transform_start) * 1000, 2)

    total_cases = sum(comp.get("data", {}).get(selected_period, {}).get("cases", 0) for comp in formatted_companies)
    total_bottles = sum(comp.get("data", {}).get(selected_period, {}).get("bottles", 0) for comp in formatted_companies)

    def _prune_period_dict(data_dict: dict, active_period: str) -> dict:
        if not isinstance(data_dict, dict):
            return data_dict
        target_key = "Daily"
        if active_period == "MTD":
            target_key = "MTD"
        elif active_period == "YTD":
            target_key = "YTD"

        if target_key in data_dict:
            return {target_key: data_dict[target_key]}
        return data_dict

    # Apply period pruning to leaf brands to keep payload lean, while preserving Daily, MTD, YTD in entity data nodes
    if clean_level in [None, "companies"]:
        for comp in formatted_companies:
            for b in comp.get("brands", []):
                if "data" in b:
                    b["data"] = _prune_period_dict(b["data"], selected_period)

    # Apply pagination to depots if requested
    paginated_depots = formatted_depots
    pagination_meta = None
    if page is not None or page_size is not None:
        eff_page = page if page is not None else 1
        eff_page_size = page_size if page_size is not None else 15
        total_depots = len(formatted_depots)
        total_pages = math.ceil(total_depots / eff_page_size) if total_depots > 0 else 0
        start_idx = (eff_page - 1) * eff_page_size
        end_idx = start_idx + eff_page_size
        paginated_depots = formatted_depots[start_idx:end_idx]
        pagination_meta = {
            "page": eff_page,
            "page_size": eff_page_size,
            "total": total_depots,
            "total_pages": total_pages,
            "has_next": eff_page < total_pages,
            "has_previous": eff_page > 1
        }

    depot_list_for_pruning = paginated_depots if (page is not None or page_size is not None) else formatted_depots
    if clean_level in [None, "depots"]:
        for depot in depot_list_for_pruning:
            for b in depot.get("brands", []):
                if "data" in b:
                    b["data"] = _prune_period_dict(b["data"], selected_period)


    payload = {
        "status": "success",
        "latest_sale_date": latest_sale_date,
        "record_count": total_records_processed,
        "process_time_ms": transform_duration_ms,
        "period": selected_period,
    }

    if clean_level == "companies":
        payload["companies"] = formatted_companies
    elif clean_level == "depots":
        payload["depots"] = paginated_depots
        if pagination_meta:
            payload["pagination"] = pagination_meta
    elif clean_level == "tsms":
        payload["tsms"] = formatted_tsms
    else:  # clean_level is None (full response for backward compatibility)
        payload["companies"] = formatted_companies
        payload["depots"] = paginated_depots
        payload["tsms"] = formatted_tsms
        if pagination_meta:
            payload["pagination"] = pagination_meta

    # Guardrail: Do NOT cache if primary RPCs experienced read timeouts or errors
    rpc_had_error = bool(rpc_trace_info.get("sales_rpc_error") or tsm_rpc_trace.get("tsm_rpc_error"))
    has_valid_sales = (len(formatted_companies) > 0 and (total_cases > 0 or total_bottles > 0)) or len(formatted_tsms) > 0 or len(formatted_depots) > 0

    if not rpc_had_error and has_valid_sales:
        _SALES_RESPONSE_CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": payload
        }
        try:
            from backend.services.cache_service import set_json_cache
            await set_json_cache(f"rll:mobile:sales:{cache_key}", payload, ttl=86400)  # 24 hours TTL (invalidated on new file upload)
        except Exception as e_redis_set:
            logger.warning(f"Failed to store sales payload in Redis: {e_redis_set}")
    else:
        logger.warning(f"⚠️ [CACHE_BYPASS] Skipping sales cache for {cache_key} (rpc_had_error={rpc_had_error}, has_valid_sales={has_valid_sales})")

    # J, K, L. Serialization & Response timing
    t_serialize_start = time.perf_counter()
    json_bytes_data = json.dumps(payload).encode("utf-8")
    t_serialize_end = time.perf_counter()
    serialization_duration_ms = round((t_serialize_end - t_serialize_start) * 1000, 2)

    response_bytes = len(json_bytes_data)
    response_kb = round(response_bytes / 1024, 2)
    response_mb = round(response_bytes / (1024 * 1024), 2)

    total_rpc_ms = round(rpc_trace_info.get("sales_rpc_duration_ms", 0) + tsm_rpc_trace.get("tsm_rpc_duration_ms", 0), 2)
    total_rpc_bytes = rpc_trace_info.get("sales_rpc_payload_bytes", 0) + tsm_rpc_trace.get("tsm_rpc_payload_bytes", 0)
    rpc_kb = round(total_rpc_bytes / 1024, 2)
    rpc_mb = round(total_rpc_bytes / (1024 * 1024), 2)

    t_api_end = time.perf_counter()
    total_api_ms = round((t_api_end - t_api_start) * 1000, 2)

    # Calculate Data Volume Counts (Section 7)
    total_companies_count = len(formatted_companies)
    total_brands_count = sum(len(c.get("brands", [])) for c in formatted_companies)
    total_depots_count = len(formatted_depots)
    total_tsms_count = len(formatted_tsms)
    total_ases_count = sum(len(t.get("ases", [])) for t in formatted_tsms)

    logger.info(
        f"\n==================================================\n"
        f"RLL PERFORMANCE TRACE\n"
        f"==================================================\n"
        f"Request ID:\n{request_id}\n\n"
        f"Endpoint:\n/mobile/sales\n\n"
        f"Filters:\nHQ: {selected_hq}\nDepot: All\nCompany: All\nDate: {end_date}\nPeriod: {selected_period}\n\n"
        f"--------------------------------------------------\n"
        f"BACKEND\n"
        f"--------------------------------------------------\n"
        f"Authentication:\n{auth_duration_ms:.1f} ms\n\n"
        f"Master cache:\n{master_cache_duration_ms:.1f} ms\n{'HIT' if master_cache_hit else 'MISS'}\n\n"
        f"Sales cache:\n{sales_cache_duration_ms:.1f} ms\nMISS\n\n"
        f"Supabase RPC:\n{total_rpc_ms:.1f} ms\n\n"
        f"RPC payload:\n{rpc_kb} KB / {rpc_mb:.2f} MB\n\n"
        f"RPC deserialization:\n0.1 ms\n\n"
        f"Python transformation:\n{transform_duration_ms:.1f} ms\n\n"
        f"JSON serialization:\n{serialization_duration_ms:.1f} ms\n\n"
        f"Final API response:\n{response_kb} KB / {response_mb:.2f} MB\n\n"
        f"Total FastAPI time:\n{total_api_ms:.1f} ms\n\n"
        f"--------------------------------------------------\n"
        f"DATA VOLUME METRICS\n"
        f"--------------------------------------------------\n"
        f"Total JSON objects: {total_records_processed}\n"
        f"Companies: {total_companies_count}\n"
        f"Brands: {total_brands_count}\n"
        f"Depots: {total_depots_count}\n"
        f"TSMs: {total_tsms_count}\n"
        f"ASEs: {total_ases_count}\n"
        f"Daily records: {len(company_records)}\n"
        f"MTD records: {len(depot_records)}\n"
        f"YTD records: {len(all_usf_records)}\n"
        f"Total JSON payload: {response_mb:.2f} MB\n"
        f"=================================================="
    )

    return JSONResponse(
        content=payload,
        headers={
            "X-Request-ID": request_id,
            "X-Backend-Duration-Ms": str(total_api_ms),
            "X-Response-Size-Bytes": str(response_bytes),
            "X-Sales-Cache-Status": "MISS"
        }
    )


@router.get("/cascading/groups")
async def get_cascading_groups_endpoint(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    selected_hq: Optional[str] = Query(None, description="Filter by Headquarters name")
):
    """
    Mobile endpoint: Fetch active groups with total licensees, linked depots, and sales summaries using optimized JSON RPC.
    """
    from backend.services.mobile_cascading_service import get_cascading_groups
    return await get_cascading_groups(date_from=date_from, date_to=date_to, period=period, selected_hq=selected_hq)


@router.get("/cascading/groups/{group_id}/brands")
async def get_group_brands_endpoint(
    group_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name"),
    selected_hq: Optional[str] = Query(None, description="Filter by HQ name")
):
    """
    Mobile endpoint: Fetch aggregated brand-wise sales for all licensees in a group.
    """
    from backend.services.mobile_cascading_service import get_group_brand_sales
    return await get_group_brand_sales(
        group_id=group_id,
        date_from=date_from,
        date_to=date_to,
        period=period,
        depot_name=depot_name,
        selected_hq=selected_hq
    )


@router.get("/cascading/groups/{group_id}/licensees")
async def get_group_licensees_endpoint(
    group_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name"),
    selected_hq: Optional[str] = Query(None, description="Filter by HQ name")
):
    """
    Mobile endpoint: Fetch licensees for a group with specific depot breakdown and sales stats.
    """
    from backend.services.mobile_cascading_service import get_group_licensees
    return await get_group_licensees(
        group_id=group_id,
        date_from=date_from,
        date_to=date_to,
        period=period,
        depot_name=depot_name,
        selected_hq=selected_hq
    )


@router.get("/cascading/licensees/{licensee_id}/brand-sales")
async def get_licensee_brand_sales_endpoint(
    licensee_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name"),
    selected_hq: Optional[str] = Query(None, description="Filter by HQ name")
):
    """
    Mobile endpoint: Fetch brand-wise sales breakdown for a licensee.
    """
    from backend.services.mobile_cascading_service import get_licensee_brand_sales
    return await get_licensee_brand_sales(
        licensee_id=licensee_id,
        date_from=date_from,
        date_to=date_to,
        period=period,
        depot_name=depot_name,
        selected_hq=selected_hq
    )


@router.get("/cascading/company-brands")
def get_company_brands_endpoint(
    company_id: str = Query(..., description="Target Company UUID or slug"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    hq_name: Optional[str] = Query(None, description="Optional Headquarter filter"),
):
    """
    Mobile endpoint: Fetch brand sales breakdown for a selected company.
    """
    from backend.services.company_cascading_service import get_company_brands_sales_service
    from backend.services.mobile_companies_service import _get_latest_sale_date

    clean_to = date_to.strip() if date_to and date_to.strip() else ""
    clean_from = date_from.strip() if date_from and date_from.strip() else ""
    if not clean_to:
        clean_to = _get_latest_sale_date()
    if not clean_from:
        clean_from = clean_to

    return get_company_brands_sales_service(
        company_id=company_id,
        date_from=clean_from,
        date_to=clean_to,
        hq_name=hq_name,
    )


@router.get("/cascading/brand-licensees")
def get_brand_licensees_endpoint(
    brand_id: str = Query(..., description="Target Brand UUID"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    hq_name: Optional[str] = Query(None, description="Optional Headquarter filter"),
):
    """
    Mobile endpoint: Fetch licensee sales breakdown for a selected brand.
    """
    from backend.services.company_cascading_service import get_brand_licensees_sales_service
    from backend.services.mobile_companies_service import _get_latest_sale_date

    clean_to = date_to.strip() if date_to and date_to.strip() else ""
    clean_from = date_from.strip() if date_from and date_from.strip() else ""
    if not clean_to:
        clean_to = _get_latest_sale_date()
    if not clean_from:
        clean_from = clean_to

    return get_brand_licensees_sales_service(
        brand_id=brand_id,
        date_from=clean_from,
        date_to=clean_to,
        hq_name=hq_name,
    )



def clear_sales_response_cache():
    """Clear all in-memory master lookups & mobile sales response caches."""
    global _MASTER_CACHE, _SALES_RESPONSE_CACHE
    _MASTER_CACHE["timestamp"] = 0
    _MASTER_CACHE["data"] = None
    _SALES_RESPONSE_CACHE.clear()
    logger.info("🧹 Cleared in-memory mobile sales response & master caches.")


async def warm_master_cache():
    """Pre-warm master lookups cache asynchronously during application startup."""
    try:
        logger.info("🔥 Pre-warming master lookup cache during startup...")
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch_fresh_master_lookups)
        global _MASTER_CACHE
        if data and data.get("master_tsms"):
            _MASTER_CACHE["data"] = data
            _MASTER_CACHE["timestamp"] = time.time()
            if data.get("latest_sale_date"):
                _MASTER_CACHE["latest_sale_date"] = data["latest_sale_date"]
            logger.info("✅ Master lookup cache pre-warmed successfully.")
    except Exception as e:
        logger.warning(f"Failed to pre-warm master lookup cache on startup: {e}")


@router.api_route("/cache/clear", methods=["GET", "POST"])
async def clear_mobile_cache_endpoint(
    current_user: dict = Depends(mobile_admin_checker)
):
    """
    Clear all in-memory and Redis sales/analytics caches (Admin only).
    Does NOT flush database or delete any security/session state.
    """
    clear_sales_response_cache()
    from backend.services.cache_service import invalidate_analytics_cache
    try:
        await invalidate_analytics_cache()
    except Exception as e:
        logger.warning(f"Notice purging Redis cache via endpoint: {e}")

    logger.info(f"🧹 Sales & analytics caches cleared by admin {current_user.get('email')}.")
    return {
        "status": "success",
        "message": "Sales and analytics caches cleared successfully."
    }


@router.get("/tenant-config")
def get_mobile_tenant_config_endpoint(
    tenant_slug: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_tenant_slug: Optional[str] = Header(None, alias="X-Tenant-Slug"),
):
    """
    Mobile endpoint: Returns dynamic white-label tenant configuration with tenant_id.
    """
    from backend.services.tenant_service import get_tenant_config_service
    effective_id = tenant_id or x_tenant_id
    effective_slug = tenant_slug or x_tenant_slug or "rll"
    return get_tenant_config_service(tenant_slug=effective_slug, tenant_id=effective_id)




