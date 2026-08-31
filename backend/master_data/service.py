import logging
import re
from decimal import Decimal
from typing import Dict, Optional, List, Any

from backend.db.client import get_supabase

logger = logging.getLogger(__name__)


class MasterService:
    """
    Resolves values coming from the Government Excel file to IDs
    in the Supabase master/dimension tables.

    Excel:
        LICENSEE_NAME
        Trade
        Group Name
        DEO_OFFICE_NAME
        CIRCLE_OFFICE_NAME
        DEPOT_NAME
        BRAND_NAME
        PACKING_IN_ML

    Supabase:
        groups
        offices
        circles
        depots
        licensees
        brands
        packagings
    """

    def __init__(self):
        self._group_cache: Dict[str, int] = {}
        self._office_cache: Dict[str, int] = {}
        self._circle_cache: Dict[str, int] = {}
        self._headquarter_cache: Dict[str, int] = {}
        self._company_cache: Dict[str, int] = {}
        self._depot_cache: Dict[str, int] = {}
        self._licensee_cache: Dict[str, int] = {}
        self._brand_cache: Dict[str, int] = {}
        self._packaging_cache: Dict[str, int] = {}

    def get_offices(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("offices").select("office_id, name, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []

    def get_circles(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("circles").select("circle_id, office_id, headquarters_id, name, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []

    def get_depots(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("depots").select("depot_id, name, headquarters_id, office_id, circle_id, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []

    def get_licensees(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("licensees").select("licensee_id, licensee_name, trade, group_id, headquarters_id, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []

    def get_brands(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("brands").select("brand_id, brand_name, company_id, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []

    def get_headquarters(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("headquarters").select("headquarters_id, name, is_active").execute()
                if res.data:
                    return res.data
            except Exception as e:
                logger.warning(f"Failed to fetch headquarters from Supabase: {e}")
        return []

    def get_depots_with_hq(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if not client:
            return []

        try:
            # 1. Fetch depots
            dep_res = client.table("depots").select("depot_id, name, headquarters_id, office_id, circle_id, is_active").execute()
            depots_data = dep_res.data or []

            # 2. Fetch headquarters map
            hq_res = client.table("headquarters").select("headquarters_id, name, is_active").execute()
            hq_map = {str(h["headquarters_id"]): h.get("name", "Unassigned") for h in (hq_res.data or []) if h.get("headquarters_id")}

            # 3. Fetch users map
            users_res = client.table("users").select("user_id, first_name, last_name, email, is_active").execute()
            users_map = {}
            for u in (users_res.data or []):
                uid = str(u["user_id"])
                fn = u.get("first_name") or ""
                ln = u.get("last_name") or ""
                full_name = f"{fn} {ln}".strip() or u.get("email") or "Unnamed User"
                users_map[uid] = {
                    "user_id": uid,
                    "name": full_name,
                    "email": u.get("email") or ""
                }

            # 4. Fetch user roles map
            roles_res = client.table("roles").select("role_id, role_name").execute()
            roles_map = {str(r["role_id"]): r.get("role_name", "ASE") for r in (roles_res.data or []) if r.get("role_id")}

            user_roles_res = client.table("user_roles").select("user_id, role_id, is_active").execute()
            user_role_map = {}
            for ur in (user_roles_res.data or []):
                if ur.get("is_active", True):
                    uid = str(ur["user_id"])
                    rid = str(ur.get("role_id") or "")
                    user_role_map[uid] = roles_map.get(rid, "ASE")

            # 5. Fetch user_depot mapping
            user_depot_res = client.table("user_depot").select("user_id, depot_id").execute()
            depot_user_map: Dict[str, List[Dict[str, Any]]] = {}

            for ud in (user_depot_res.data or []):
                did = str(ud.get("depot_id") or "")
                uid = str(ud.get("user_id") or "")
                if did and uid in users_map:
                    u_info = dict(users_map[uid])
                    u_info["role"] = user_role_map.get(uid, "ASE")
                    if did not in depot_user_map:
                        depot_user_map[did] = []
                    depot_user_map[did].append(u_info)

            # Build result list
            result = []
            for d in depots_data:
                did = str(d["depot_id"])
                hq_id = str(d.get("headquarters_id") or "")
                hq_name = hq_map.get(hq_id, "Unassigned")

                assigned_users = depot_user_map.get(did, [])
                if assigned_users:
                    for u_info in assigned_users:
                        result.append({
                            "depot_id": did,
                            "name": d.get("name", "Unassigned"),
                            "headquarters_id": hq_id,
                            "headquarters_name": hq_name,
                            "is_active": d.get("is_active", True),
                            "assigned_user_id": u_info["user_id"],
                            "depot_user": u_info["name"],
                            "depot_user_role": u_info["role"],
                            "depot_user_email": u_info["email"],
                            "hq_user": "Unassigned",
                            "hq_user_email": ""
                        })
                else:
                    result.append({
                        "depot_id": did,
                        "name": d.get("name", "Unassigned"),
                        "headquarters_id": hq_id,
                        "headquarters_name": hq_name,
                        "is_active": d.get("is_active", True),
                        "assigned_user_id": None,
                        "depot_user": "Unassigned",
                        "depot_user_role": "ASE",
                        "depot_user_email": None,
                        "hq_user": "Unassigned",
                        "hq_user_email": None
                    })

            return result
        except Exception as e:
            logger.error(f"Error fetching depots with HQ in master_service: {e}")
            return []

        raw_depots = self.get_depots()
        for d in raw_depots:
            if "headquarters_name" not in d:
                d["headquarters_name"] = "Unassigned"
            if "depot_user" not in d:
                d["depot_user"] = "Unassigned"
            if "hq_user" not in d:
                d["hq_user"] = "Unassigned"
        return raw_depots

    def update_depot(self, depot_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                assigned_user_id = payload.pop("assigned_user_id", "NO_CHANGE")

                if payload:
                    res = client.table("depots").update(payload).eq("depot_id", depot_id).execute()
                else:
                    res = client.table("depots").select("depot_id, name, headquarters_id, office_id, circle_id, is_active").eq("depot_id", depot_id).execute()

                if assigned_user_id != "NO_CHANGE":
                    # Update user_depot mapping
                    client.table("user_depot").delete().eq("depot_id", depot_id).execute()
                    if assigned_user_id and str(assigned_user_id).strip().lower() not in ("unassigned", "none", "", "null"):
                        client.table("user_depot").insert({"user_id": str(assigned_user_id), "depot_id": depot_id}).execute()

                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Failed to update depot {depot_id}: {e}")
        return None

    def delete_depot(self, depot_id: int) -> bool:
        client = get_supabase()
        if client:
            try:
                client.table("user_depot").delete().eq("depot_id", depot_id).execute()
                client.table("depots").delete().eq("depot_id", depot_id).execute()
                return True
            except Exception as e:
                logger.error(f"Failed to delete depot {depot_id}: {e}")
        return False

    def get_packing_sizes(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("packagings").select("packaging_id, packing_raw, bottle_size_ml, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.get_packagings()

    def get_packagings(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("packagings").select("packaging_id, packing_raw, bottle_size_ml, is_active").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return []


    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _clean(value) -> str:
        """
        Normalize Excel text for matching.

        Example:
            " R.S.B.C.L. - Sikar Depot (CWC) "
        becomes:
            "r.s.b.c.l. - sikar depot (cwc)"
        """
        if value is None:
            return ""

        value = str(value).strip()

        if value.lower() in {"nan", "none", "null"}:
            return ""

        # collapse repeated whitespace
        value = " ".join(value.split())

        return value.lower()

    @staticmethod
    def _clean_company(value) -> str:
        """
        Aggressive normalization specifically for company names.
        Strips punctuation, special chars, common suffix noise words (ltd, pvt, inc, co, and, the, s),
        and collapses whitespace into a single contiguous token.

        Example:
            "William Grant & Sons" -> "williamgrant"
            "willam grants"       -> "williamgrant"
        """
        if value is None:
            return ""

        val_str = str(value).strip().lower()
        if val_str in {"nan", "none", "null"}:
            return ""

        # Remove punctuation & special characters
        val_str = re.sub(r"[^a-z0-9\s]", " ", val_str)

        # Remove noise suffix words
        val_str = re.sub(r"\b(pvt|ltd|inc|co|and|the|india|s)\b", " ", val_str)

        # Collapse all whitespace into a single token
        return "".join(val_str.split())

    @staticmethod
    def _display(value) -> str:
        """Clean value while preserving original capitalization."""
        if value is None:
            return ""

        value = str(value).strip()

        if value.lower() in {"nan", "none", "null"}:
            return ""

        return " ".join(value.split())

    @staticmethod
    def _extract_bottle_size_ml(packing_raw: str) -> Decimal:
        """
        Examples:

        Nips (180 ml)
            -> 180

        quarts (750 ml)
            -> 750

        Nips-IMFL pet (180 ml)
            -> 180

        90 ML(100 Bottles) (90 ml)
            -> 90
        """

        text = str(packing_raw or "")

        matches = re.findall(
            r"(\d+(?:\.\d+)?)\s*ml",
            text,
            flags=re.IGNORECASE
        )

        if not matches:
            logger.warning(
                "Could not determine bottle size from packing: %s",
                packing_raw
            )
            return Decimal("0")

        # Last ml value is generally the actual bottle size
        return Decimal(matches[-1])

    @staticmethod
    def _extract_units_per_case(packing_raw: str) -> Optional[int]:
        """
        Example:

        90 ML(100 Bottles) (90 ml)
            -> 100

        If Excel doesn't specify units per case, return None.
        """

        text = str(packing_raw or "")

        match = re.search(
            r"(\d+)\s*bottles?",
            text,
            flags=re.IGNORECASE
        )

        if match:
            return int(match.group(1))

        return None

    # ---------------------------------------------------------
    # Prefetch
    # ---------------------------------------------------------

    def prefetch_all_caches(self):
        """
        Load master tables once before processing thousands of rows.

        This prevents one Supabase SELECT for every Excel row.
        """

        client = get_supabase()

        if not client:
            logger.warning("Supabase client unavailable.")
            return

        try:
            # ---------------- GROUPS ----------------
            g_offset = 0
            while True:
                res_g = (
                    client
                    .table("groups")
                    .select("group_id,group_name")
                    .range(g_offset, g_offset + 999)
                    .execute()
                )
                rows_g = res_g.data or []
                for row in rows_g:
                    key = self._clean(row.get("group_name"))
                    if key:
                        self._group_cache[key] = row["group_id"]
                if len(rows_g) < 1000:
                    break
                g_offset += 1000

            # ---------------- OFFICES ----------------

            result = (
                client
                .table("offices")
                .select("office_id,name")
                .execute()
            )

            for row in result.data or []:
                key = self._clean(row.get("name"))

                if key:
                    self._office_cache[key] = row["office_id"]

            # ---------------- CIRCLES ----------------

            result = (
                client
                .table("circles")
                .select("circle_id,name")
                .execute()
            )

            for row in result.data or []:
                key = self._clean(row.get("name"))

                if key:
                    self._circle_cache[key] = row["circle_id"]

            # ---------------- DEPOTS ----------------

            result = (
                client
                .table("depots")
                .select("depot_id,name")
                .execute()
            )

            for row in result.data or []:
                key = self._clean(row.get("name"))

                if key:
                    self._depot_cache[key] = row["depot_id"]

            # ---------------- LICENSEES ----------------
            l_offset = 0
            while True:
                res_l = (
                    client
                    .table("licensees")
                    .select("licensee_id,licensee_name")
                    .range(l_offset, l_offset + 999)
                    .execute()
                )
                rows_l = res_l.data or []
                for row in rows_l:
                    key = self._clean(row.get("licensee_name"))
                    if key:
                        self._licensee_cache[key] = row["licensee_id"]
                if len(rows_l) < 1000:
                    break
                l_offset += 1000

            # ---------------- BRANDS ----------------

            result = (
                client
                .table("brands")
                .select("brand_id,brand_name")
                .execute()
            )

            for row in result.data or []:
                key = self._clean(row.get("brand_name"))

                if key:
                    self._brand_cache[key] = row["brand_id"]

            # ---------------- PACKAGINGS ----------------

            result = (
                client
                .table("packagings")
                .select("packaging_id,packing_raw")
                .execute()
            )

            for row in result.data or []:
                key = self._clean(row.get("packing_raw"))

                if key:
                    self._packaging_cache[key] = row["packaging_id"]

            logger.info(
                "Successfully prefetched master caches: Groups=%d, Offices=%d, Circles=%d, Depots=%d, Licensees=%d, Brands=%d, Packagings=%d.",
                len(self._group_cache),
                len(self._office_cache),
                len(self._circle_cache),
                len(self._depot_cache),
                len(self._licensee_cache),
                len(self._brand_cache),
                len(self._packaging_cache),
            )

        except Exception:
            logger.exception("Failed to prefetch Supabase master caches.")
            raise

    # ---------------------------------------------------------
    # Bulk Master Resolutions
    # ---------------------------------------------------------

    def bulk_resolve_groups(self, names: List[str]) -> Dict[str, int]:
        client = get_supabase()
        missing = {}
        for name in names:
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._group_cache:
                missing[key] = display

        if missing and client:
            payloads = [{"group_name": disp, "is_active": True} for disp in missing.values()]
            try:
                res = client.table("groups").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("group_name"))
                    if k:
                        self._group_cache[k] = row["group_id"]
            except Exception as e_grp:
                logger.warning(f"bulk_resolve_groups insert notice: {e_grp}")
                try:
                    res = client.table("groups").select("group_id,group_name").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("group_name"))
                        if k:
                            self._group_cache[k] = row["group_id"]
                except Exception:
                    pass

        return self._group_cache

    def bulk_resolve_offices(self, names: List[str]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for name in names:
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._office_cache:
                missing[key] = display

        if missing and client:
            payloads = [{"name": disp, "is_active": True} for disp in missing.values()]
            try:
                res = client.table("offices").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("name"))
                    if k:
                        self._office_cache[k] = row["office_id"]
            except Exception as e_off:
                logger.warning(f"bulk_resolve_offices insert notice: {e_off}")
                try:
                    res = client.table("offices").select("office_id,name").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("name"))
                        if k:
                            self._office_cache[k] = row["office_id"]
                except Exception:
                    pass

        return self._office_cache

    def bulk_resolve_circles(self, names: List[str]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for name in names:
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._circle_cache:
                missing[key] = display

        if missing and client:
            payloads = [{"name": disp, "is_active": True} for disp in missing.values()]
            try:
                res = client.table("circles").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("name"))
                    if k:
                        self._circle_cache[k] = row["circle_id"]
            except Exception as e_cir:
                logger.warning(f"bulk_resolve_circles insert notice: {e_cir}")
                try:
                    res = client.table("circles").select("circle_id,name").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("name"))
                        if k:
                            self._circle_cache[k] = row["circle_id"]
                except Exception:
                    pass

        return self._circle_cache

    def bulk_resolve_headquarters(self, names: List[str]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for name in names:
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._headquarter_cache:
                missing[key] = display

        if missing and client:
            payloads = [{"name": disp, "is_active": True} for disp in missing.values()]
            try:
                res = client.table("headquarters").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("name"))
                    if k:
                        self._headquarter_cache[k] = row.get("headquarters_id") or row.get("id")
            except Exception as e_hq:
                logger.warning(f"bulk_resolve_headquarters insert notice: {e_hq}")
                try:
                    res = client.table("headquarters").select("headquarters_id, name").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("name"))
                        if k:
                            self._headquarter_cache[k] = row.get("headquarters_id") or row.get("id")
                except Exception:
                    pass

        return self._headquarter_cache

    def bulk_resolve_companies(self, names: List[str]) -> Dict[str, Any]:
        client = get_supabase()
        from backend.db.company_aliases import get_company_aliases, upsert_company_alias

        # 1. Ensure master company cache and alias mappings are loaded
        if client and not self._company_cache:
            try:
                res = client.table("companies").select("company_id, company_name").execute()
                for row in (res.data or []):
                    c_name = row.get("company_name")
                    c_id = str(row.get("company_id"))
                    if c_name and c_id:
                        k_clean = self._clean(c_name)
                        k_norm = self._clean_company(c_name)
                        self._company_cache[k_clean] = c_id
                        self._company_cache[k_norm] = c_id
            except Exception as e:
                logger.warning(f"Error fetching companies in bulk_resolve_companies: {e}")

            alias_map = get_company_aliases()
            for norm_key, c_id in alias_map.items():
                self._company_cache[norm_key] = str(c_id)

        missing = {}
        for name in names:
            display = self._display(name)
            k_clean = self._clean(name)
            k_norm = self._clean_company(name)

            if k_norm in self._company_cache:
                resolved_id = self._company_cache[k_norm]
                self._company_cache[k_clean] = resolved_id
                continue
            if k_clean in self._company_cache:
                resolved_id = self._company_cache[k_clean]
                self._company_cache[k_norm] = resolved_id
                continue

            missing[name] = (k_clean, k_norm, display)

        if missing and client:
            for name, (k_clean, k_norm, disp) in missing.items():
                try:
                    payload = {"company_name": disp, "is_active": True}
                    res = client.table("companies").insert(payload).execute()
                    if res.data:
                        c_id = str(res.data[0].get("company_id") or res.data[0].get("id"))
                        self._company_cache[k_clean] = c_id
                        self._company_cache[k_norm] = c_id
                        upsert_company_alias(raw_name=name, norm_key=k_norm, company_id=c_id, source="auto")
                except Exception as e_comp:
                    logger.warning(f"bulk_resolve_companies insert notice for {name}: {e_comp}")

        return self._company_cache

    def bulk_resolve_depots(self, depot_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for item in depot_items:
            name = item.get("depot_name")
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._depot_cache:
                missing[key] = {
                    "name": display,
                    "office_id": item.get("office_id"),
                    "circle_id": item.get("circle_id"),
                    "headquarters_id": item.get("headquarters_id"),
                    "is_active": True
                }

        if missing and client:
            payloads = list(missing.values())
            try:
                res = client.table("depots").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("name"))
                    if k:
                        self._depot_cache[k] = row["depot_id"]
            except Exception as e_dep:
                logger.warning(f"bulk_resolve_depots insert notice: {e_dep}")
                try:
                    res = client.table("depots").select("depot_id,name").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("name"))
                        if k:
                            self._depot_cache[k] = row["depot_id"]
                except Exception:
                    pass

        return self._depot_cache

    def bulk_resolve_licensees(self, licensee_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for item in licensee_items:
            name = item.get("licensee_name")
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._licensee_cache:
                trade = self._display(item.get("trade"))
                if trade.lower() == "off":
                    trade = "Off"
                elif trade.lower() == "on":
                    trade = "On"
                else:
                    trade = "Off"

                missing[key] = {
                    "licensee_name": display,
                    "trade": trade,
                    "group_id": item.get("group_id"),
                    "depot_id": item.get("depot_id"),
                    "headquarters_id": item.get("headquarters_id"),
                    "office_id": item.get("office_id"),
                    "circle_id": item.get("circle_id"),
                    "is_active": True
                }

        if missing and client:
            payloads = list(missing.values())
            # Insert missing items in safe chunks of 200 to prevent single-row constraint failures from aborting the entire batch
            for chunk_start in range(0, len(payloads), 200):
                chunk = payloads[chunk_start:chunk_start + 200]
                try:
                    res = client.table("licensees").insert(chunk).execute()
                    for row in res.data or []:
                        k = self._clean(row.get("licensee_name"))
                        if k:
                            self._licensee_cache[k] = row["licensee_id"]
                except Exception as e_lic:
                    logger.warning(f"bulk_resolve_licensees chunk insert notice: {e_lic}")
                    # Fallback to item-by-item insert if chunk contains a conflict
                    for single_item in chunk:
                        try:
                            res_single = client.table("licensees").insert(single_item).execute()
                            if res_single.data:
                                k = self._clean(res_single.data[0].get("licensee_name"))
                                if k:
                                    self._licensee_cache[k] = res_single.data[0]["licensee_id"]
                        except Exception:
                            try:
                                minimal_item = {
                                    "licensee_name": single_item.get("licensee_name"),
                                    "trade": single_item.get("trade", "Off"),
                                    "group_id": single_item.get("group_id"),
                                    "is_active": True
                                }
                                res_min = client.table("licensees").insert(minimal_item).execute()
                                if res_min.data:
                                    k = self._clean(res_min.data[0].get("licensee_name"))
                                    if k:
                                        self._licensee_cache[k] = res_min.data[0]["licensee_id"]
                            except Exception:
                                pass


            # Always refresh cache from DB for full coverage
            try:
                l_offset = 0
                while True:
                    res = client.table("licensees").select("licensee_id,licensee_name").range(l_offset, l_offset + 999).execute()
                    rows = res.data or []
                    for row in rows:
                        k = self._clean(row.get("licensee_name"))
                        if k:
                            self._licensee_cache[k] = row["licensee_id"]
                    if len(rows) < 1000:
                        break
                    l_offset += 1000
            except Exception as e_fetch:
                logger.warning(f"bulk_resolve_licensees fetch notice: {e_fetch}")

        return self._licensee_cache

    def bulk_resolve_brands(self, brand_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for item in brand_items:
            name = item.get("brand_name")
            display = self._display(name)
            key = self._clean(name)
            if key and key not in self._brand_cache:
                missing[key] = {
                    "brand_name": display,
                    "company_id": item.get("company_id"),
                    "is_active": True
                }

        if missing and client:
            payloads = list(missing.values())
            for chunk_start in range(0, len(payloads), 200):
                chunk = payloads[chunk_start:chunk_start + 200]
                try:
                    res = client.table("brands").insert(chunk).execute()
                    for row in res.data or []:
                        k = self._clean(row.get("brand_name"))
                        if k:
                            self._brand_cache[k] = row["brand_id"]
                except Exception as e_brd:
                    logger.warning(f"bulk_resolve_brands chunk insert notice: {e_brd}")
                    for single_item in chunk:
                        try:
                            res_single = client.table("brands").insert(single_item).execute()
                            if res_single.data:
                                k = self._clean(res_single.data[0].get("brand_name"))
                                if k:
                                    self._brand_cache[k] = res_single.data[0]["brand_id"]
                        except Exception:
                            pass

            try:
                res = client.table("brands").select("brand_id,brand_name").execute()
                for row in res.data or []:
                    k = self._clean(row.get("brand_name"))
                    if k:
                        self._brand_cache[k] = row["brand_id"]
            except Exception as e_fetch:
                logger.warning(f"bulk_resolve_brands fetch notice: {e_fetch}")

        return self._brand_cache

    def bulk_resolve_packagings(self, packing_raws: List[str]) -> Dict[str, Any]:
        client = get_supabase()
        missing = {}
        for raw in packing_raws:
            display = self._display(raw)
            key = self._clean(raw)
            if key and key not in self._packaging_cache:
                bottle_size_ml = self._extract_bottle_size_ml(display)
                units_per_case = self._extract_units_per_case(display)
                missing[key] = {
                    "packing_raw": display,
                    "bottle_size_ml": float(bottle_size_ml),
                    "units_per_case": units_per_case,
                    "is_active": True
                }

        if missing and client:
            payloads = list(missing.values())
            try:
                res = client.table("packagings").insert(payloads).execute()
                for row in res.data or []:
                    k = self._clean(row.get("packing_raw"))
                    if k:
                        self._packaging_cache[k] = row["packaging_id"]
            except Exception as e_pkg:
                logger.warning(f"bulk_resolve_packagings insert notice: {e_pkg}")
                try:
                    res = client.table("packagings").select("packaging_id,packing_raw").execute()
                    for row in res.data or []:
                        k = self._clean(row.get("packing_raw"))
                        if k:
                            self._packaging_cache[k] = row["packaging_id"]
                except Exception:
                    pass

        return self._packaging_cache



    # ---------------------------------------------------------
    # Groups
    # ---------------------------------------------------------

    def resolve_group_id(self, group_name: str) -> int:

        display_name = self._display(group_name)
        key = self._clean(group_name)

        if not key:
            raise ValueError("Group Name is empty.")

        if key in self._group_cache:
            return self._group_cache[key]

        client = get_supabase()

        payload = {
            "group_name": display_name,
            "is_active": True
        }

        try:
            result = (
                client
                .table("groups")
                .insert(payload)
                .execute()
            )

            group_id = result.data[0]["group_id"]

            self._group_cache[key] = group_id

            return group_id

        except Exception:
            # Another row/process may have inserted it first.
            result = (
                client
                .table("groups")
                .select("group_id,group_name")
                .eq("group_name", display_name)
                .execute()
            )

            if result.data:
                group_id = result.data[0]["group_id"]
                self._group_cache[key] = group_id
                return group_id

            raise

    # ---------------------------------------------------------
    # Offices
    # ---------------------------------------------------------

    def resolve_office_id(self, office_name: str) -> int:

        display_name = self._display(office_name)
        key = self._clean(office_name)

        if not key:
            raise ValueError("DEO_OFFICE_NAME is empty.")

        if key in self._office_cache:
            return self._office_cache[key]

        client = get_supabase()

        payload = {
            "name": display_name,
            "is_active": True
        }

        try:
            result = (
                client
                .table("offices")
                .insert(payload)
                .execute()
            )

            office_id = result.data[0]["office_id"]

            self._office_cache[key] = office_id

            return office_id

        except Exception:
            result = (
                client
                .table("offices")
                .select("office_id,name")
                .eq("name", display_name)
                .execute()
            )

            if result.data:
                office_id = result.data[0]["office_id"]
                self._office_cache[key] = office_id
                return office_id

            raise

    # ---------------------------------------------------------
    # Circles
    # ---------------------------------------------------------

    def resolve_circle_id(self, circle_name: str) -> int:

        display_name = self._display(circle_name)
        key = self._clean(circle_name)

        if not key:
            raise ValueError("CIRCLE_OFFICE_NAME is empty.")

        if key in self._circle_cache:
            return self._circle_cache[key]

        client = get_supabase()

        payload = {
            "name": display_name,
            "is_active": True
        }

        try:
            result = (
                client
                .table("circles")
                .insert(payload)
                .execute()
            )

            circle_id = result.data[0]["circle_id"]

            self._circle_cache[key] = circle_id

            return circle_id

        except Exception:
            result = (
                client
                .table("circles")
                .select("circle_id,name")
                .eq("name", display_name)
                .execute()
            )

            if result.data:
                circle_id = result.data[0]["circle_id"]
                self._circle_cache[key] = circle_id
                return circle_id

            raise

    # ---------------------------------------------------------
    # Depots
    # ---------------------------------------------------------

    def resolve_depot_id(
        self,
        depot_name: str,
        office_id: Optional[int] = None,
        circle_id: Optional[int] = None,
        headquarters_id: Optional[int] = None
    ) -> int:

        display_name = self._display(depot_name)
        key = self._clean(depot_name)

        if not key:
            raise ValueError("DEPOT_NAME is empty.")

        if key in self._depot_cache:
            return self._depot_cache[key]

        client = get_supabase()

        payload = {
            "name": display_name,
            "office_id": office_id,
            "circle_id": circle_id,
            "headquarters_id": headquarters_id,
            "is_active": True
        }

        try:
            result = (
                client
                .table("depots")
                .insert(payload)
                .execute()
            )

            depot_id = result.data[0]["depot_id"]

            self._depot_cache[key] = depot_id

            return depot_id

        except Exception:
            result = (
                client
                .table("depots")
                .select("depot_id,name")
                .eq("name", display_name)
                .execute()
            )

            if result.data:
                depot_id = result.data[0]["depot_id"]
                self._depot_cache[key] = depot_id
                return depot_id

            raise

    # ---------------------------------------------------------
    # Licensees
    # ---------------------------------------------------------

    def resolve_licensee_id(
        self,
        licensee_name: str,
        trade_type: str,
        group_name: str,
        group_id: Optional[int] = None,
        office_id: Optional[int] = None,
        circle_id: Optional[int] = None,
        headquarters_id: Optional[int] = None
    ) -> int:

        display_name = self._display(licensee_name)
        key = self._clean(licensee_name)

        if not key:
            raise ValueError("LICENSEE_NAME is empty.")

        if key in self._licensee_cache:
            return self._licensee_cache[key]

        trade = self._display(trade_type)

        # Database CHECK allows only Off / On
        if trade.lower() == "off":
            trade = "Off"
        elif trade.lower() == "on":
            trade = "On"
        else:
            raise ValueError(
                f"Invalid Trade value '{trade_type}'. Expected Off or On."
            )

        group_display = self._display(group_name)

        if not group_display:
            raise ValueError("Group Name is empty.")

        client = get_supabase()

        payload = {
            "licensee_name": display_name,
            "trade": trade,
            "group_id": group_id,
            "headquarters_id": headquarters_id,
            "office_id": office_id,
            "circle_id": circle_id,
            "is_active": True
        }

        try:
            result = (
                client
                .table("licensees")
                .insert(payload)
                .execute()
            )

            licensee_id = result.data[0]["licensee_id"]

            self._licensee_cache[key] = licensee_id

            return licensee_id

        except Exception:
            result = (
                client
                .table("licensees")
                .select("licensee_id,licensee_name")
                .eq("licensee_name", display_name)
                .execute()
            )

            if result.data:
                licensee_id = result.data[0]["licensee_id"]
                self._licensee_cache[key] = licensee_id
                return licensee_id

            raise

    # ---------------------------------------------------------
    # Brands
    # ---------------------------------------------------------

    def resolve_brand_id(
        self,
        brand_name: str,
        company_id: Optional[int] = None
    ) -> int:

        display_name = self._display(brand_name)
        key = self._clean(brand_name)

        if not key:
            raise ValueError("BRAND_NAME is empty.")

        if key in self._brand_cache:
            return self._brand_cache[key]

        client = get_supabase()

        payload = {
            "brand_name": display_name,
            "company_id": company_id,
            "is_active": True
        }

        try:
            result = (
                client
                .table("brands")
                .insert(payload)
                .execute()
            )

            brand_id = result.data[0]["brand_id"]

            self._brand_cache[key] = brand_id

            return brand_id

        except Exception:
            result = (
                client
                .table("brands")
                .select("brand_id,brand_name")
                .eq("brand_name", display_name)
                .execute()
            )

            if result.data:
                brand_id = result.data[0]["brand_id"]
                self._brand_cache[key] = brand_id
                return brand_id

            raise

    # ---------------------------------------------------------
    # Packagings
    # ---------------------------------------------------------

    def resolve_packaging_id(self, packing_raw: str) -> int:

        display_name = self._display(packing_raw)
        key = self._clean(packing_raw)

        if not key:
            raise ValueError("PACKING_IN_ML is empty.")

        if key in self._packaging_cache:
            return self._packaging_cache[key]

        client = get_supabase()

        bottle_size_ml = self._extract_bottle_size_ml(display_name)
        units_per_case = self._extract_units_per_case(display_name)

        payload = {
            "packing_raw": display_name,
            "bottle_size_ml": float(bottle_size_ml),
            "units_per_case": units_per_case,
            "is_active": True
        }

        try:
            result = (
                client
                .table("packagings")
                .insert(payload)
                .execute()
            )

            packaging_id = result.data[0]["packaging_id"]

            self._packaging_cache[key] = packaging_id

            return packaging_id

        except Exception:
            result = (
                client
                .table("packagings")
                .select("packaging_id,packing_raw")
                .eq("packing_raw", display_name)
                .execute()
            )

            if result.data:
                packaging_id = result.data[0]["packaging_id"]
                self._packaging_cache[key] = packaging_id
                return packaging_id

            raise


master_service = MasterService()
