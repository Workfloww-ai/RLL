import uuid
import logging
import io
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from backend.db.client import get_supabase


logger = logging.getLogger(__name__)

# Fallback seed data in case Supabase is offline or empty
FALLBACK_USERS: List[Dict[str, Any]] = []


class UserService:
    def __init__(self):
        self.in_memory_users = list(FALLBACK_USERS)

    def list_users(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        client = get_supabase()
        if not client:
            return [u for u in self.in_memory_users if not tenant_id or u.get("tenant_id") == tenant_id]

        try:
            # 1. Fetch users strictly scoped by tenant_id if provided
            users_query = client.table("users").select("user_id, email, first_name, last_name, phone, is_active, created_at, tenant_id")
            if tenant_id:
                users_query = users_query.eq("tenant_id", tenant_id)
            users_res = users_query.execute()
            raw_users = users_res.data if users_res.data is not None else []

            if not raw_users:
                return []

            # 2. Fetch roles map
            roles_res = client.table("roles").select("role_id, role_name").execute()
            roles_map = {str(r["role_id"]): r.get("role_name", "ASE") for r in (roles_res.data or []) if r.get("role_id")}

            # 3. Fetch user_roles
            user_roles_res = client.table("user_roles").select("user_id, role_id, is_active").execute()
            role_by_user_id: Dict[str, str] = {}
            for ur in (user_roles_res.data or []):
                uid = str(ur["user_id"])
                rid = str(ur.get("role_id") or "")
                # Prioritize active role; fallback to inactive role if none assigned yet
                if ur.get("is_active", True) or uid not in role_by_user_id:
                    role_by_user_id[uid] = roles_map.get(rid, "ASE")

            # 4. Fetch depots & headquarters map
            depots_res = client.table("depots").select("depot_id, name, headquarters_id").execute()
            depots_map = {str(d["depot_id"]): d for d in (depots_res.data or []) if d.get("depot_id")}

            hq_res = client.table("headquarters").select("headquarters_id, name").execute()
            hq_map = {str(h["headquarters_id"]): h.get("name", "Unassigned") for h in (hq_res.data or []) if h.get("headquarters_id")}

            # 5. Fetch user_headquarters_mapping (include both active and historical for display)
            user_hqs_map: Dict[str, List[Dict[str, Any]]] = {}
            try:
                uhq_res = client.table("user_headquarters_mapping").select("user_id, headquarters_id, is_active").execute()
                for uhq in (uhq_res.data or []):
                    uid = str(uhq.get("user_id") or "")
                    hid = str(uhq.get("headquarters_id") or "")
                    if uid and hid in hq_map:
                        if uid not in user_hqs_map:
                            user_hqs_map[uid] = []
                        user_hqs_map[uid].append({
                            "headquarters_id": hid,
                            "name": hq_map[hid],
                            "is_active": uhq.get("is_active", True)
                        })
            except Exception as e_uhq:
                logger.warning(f"Error fetching user_headquarters_mapping in list_users: {e_uhq}")

            # 5b. Fetch user_depot mapping
            user_depot_info: Dict[str, Dict[str, str]] = {}
            try:
                ud_res = client.table("user_depot").select("user_id, depot_id").execute()
                for ud in (ud_res.data or []):
                    uid = str(ud.get("user_id") or "")
                    did = str(ud.get("depot_id") or "")
                    if uid and did in depots_map:
                        d_obj = depots_map[did]
                        dep_name = d_obj.get("name") or "Unassigned"
                        hq_id = str(d_obj.get("headquarters_id") or "")
                        hq_name = hq_map.get(hq_id, "Unassigned")
                        user_depot_info[uid] = {
                            "depot_name": dep_name,
                            "headquarters": hq_name,
                            "circle_name": "Unassigned"
                        }
            except Exception as e_ud:
                logger.warning(f"Error fetching user_depot: {e_ud}")

            # 6. Build final list (preserve manager assignment even if inactive)
            mapping_manager_by_user: Dict[str, str] = {}
            try:
                atm_res = client.table("ase_tsm_mapping").select("ase_user_id, tsm_user_id, is_active").execute()
                for m in (atm_res.data or []):
                    a_u = str(m.get("ase_user_id") or "")
                    t_u = str(m.get("tsm_user_id") or "")
                    if a_u and t_u:
                        # Prioritize active mapping, fallback to inactive mapping if none set
                        if m.get("is_active", True) or a_u not in mapping_manager_by_user:
                            mapping_manager_by_user[a_u] = t_u
            except Exception as e_atm:
                logger.warning(f"Error fetching ase_tsm_mapping in list_users: {e_atm}")

            user_dict_by_id = {str(u["user_id"]): u for u in raw_users}
            result = []
            for u in raw_users:
                uid = str(u["user_id"])
                first_name = u.get("first_name") or ""
                last_name = u.get("last_name") or ""
                full_name = f"{first_name} {last_name}".strip() or u.get("email") or "Unnamed User"

                manager_id = u.get("manager_id") or mapping_manager_by_user.get(uid)
                manager_name = "Unassigned"
                if manager_id and str(manager_id) in user_dict_by_id:
                    mgr_obj = user_dict_by_id[str(manager_id)]
                    mgr_fn = mgr_obj.get("first_name") or ""
                    mgr_ln = mgr_obj.get("last_name") or ""
                    manager_name = f"{mgr_fn} {mgr_ln}".strip() or "Unassigned"

                ud_data = user_depot_info.get(uid, {})
                depot_name = ud_data.get("depot_name", "Unassigned")
                circle_name = ud_data.get("circle_name", "Unassigned")

                all_assigned_hqs = user_hqs_map.get(uid, [])
                # If active HQs exist, use them; otherwise show assigned historical HQs so inactive users aren't unassigned
                active_hqs = [h for h in all_assigned_hqs if h.get("is_active", True)]
                display_hqs = active_hqs if active_hqs else all_assigned_hqs
                hq_names = [h["name"] for h in display_hqs]
                hq_ids = [h["headquarters_id"] for h in display_hqs]
                headquarters_str = ", ".join(hq_names) if hq_names else ud_data.get("headquarters", "Unassigned")

                result.append({
                    "id": uid,
                    "user_id": uid,
                    "first_name": first_name,
                    "last_name": last_name,
                    "name": full_name,
                    "email": u.get("email") or "",
                    "phone": u.get("phone") or "",
                    "phoneNumber": u.get("phone") or "",
                    "role": role_by_user_id.get(uid, "ASE"),
                    "reportingManager": manager_name,
                    "reporting_manager": manager_name,
                    "manager_id": str(manager_id) if manager_id else None,
                    "depotName": depot_name,
                    "depot_name": depot_name,
                    "headquarters": headquarters_str,
                    "headquarters_ids": hq_ids,
                    "headquarters_list": display_hqs,
                    "circleName": circle_name,
                    "isActive": u.get("is_active", True),
                    "is_active": u.get("is_active", True)
                })

            return result
        except Exception as e:
            logger.error(f"Error fetching users from Supabase: {e}")
            return self.in_memory_users

            # 2. Fallback to raw_sales_upload if users table is empty
            raw_res = client.table("raw_sales_upload").select("raw_id, ase_raw, asm_tsm_raw, is_active").execute()
            raw_data = raw_res.data or []

            if raw_data:
                users_map: Dict[str, Dict[str, Any]] = {}
                user_counter = 1

                for row in raw_data:
                    ase_raw = row.get("ase_raw") or ""
                    tsm_raw = row.get("asm_tsm_raw") or ""
                    is_active = row.get("is_active", True)

                    ase_names = [p.strip() for p in ase_raw.replace(",", "/").split("/") if p.strip()]
                    tsm_names = [p.strip() for p in tsm_raw.replace(",", "/").split("/") if p.strip()]

                    first_tsm = tsm_names[0] if tsm_names else "Unassigned"

                    for ase in ase_names:
                        if ase and ase.lower() not in ["unassigned", "none", "null"] and ase not in users_map:
                            users_map[ase] = {
                                "user_id": f"u_{user_counter}",
                                "id": f"u_{user_counter}",
                                "name": ase,
                                "first_name": ase.split()[0] if ase.split() else ase,
                                "last_name": " ".join(ase.split()[1:]) if len(ase.split()) > 1 else "",
                                "phone": "",
                                "phoneNumber": "",
                                "email": "",
                                "role": "ASE",
                                "depotName": "Unassigned",
                                "circleName": "Unassigned",
                                "headquarters": "Unassigned",
                                "reportingManager": first_tsm,
                                "is_active": is_active,
                                "isActive": is_active
                            }
                            user_counter += 1

                    for tsm in tsm_names:
                        if tsm and tsm.lower() not in ["unassigned", "none", "null"] and tsm not in users_map:
                            users_map[tsm] = {
                                "user_id": f"u_{user_counter}",
                                "id": f"u_{user_counter}",
                                "name": tsm,
                                "first_name": tsm.split()[0] if tsm.split() else tsm,
                                "last_name": " ".join(tsm.split()[1:]) if len(tsm.split()) > 1 else "",
                                "phone": "",
                                "phoneNumber": "",
                                "email": "",
                                "role": "TSM",
                                "depotName": "Unassigned",
                                "circleName": "Unassigned",
                                "headquarters": "Unassigned",
                                "reportingManager": "Unassigned",
                                "is_active": is_active,
                                "isActive": is_active
                            }
                            user_counter += 1

                if users_map:
                    return list(users_map.values())

            return self.in_memory_users
        except Exception as e:
            logger.error(f"Error fetching users from Supabase: {e}")
            return self.in_memory_users

    def _resolve_role_id(self, client: Any, role_name: str) -> Optional[str]:
        """
        Resolve role_id (UUID) from public.roles with explicit role equivalences:
        - TSM == ASM (Territory Sales Manager == Area Sales Manager)
        - LEADER == TEAM LEADER (Leader == Team Leader)
        """
        if not role_name:
            role_name = "ASE"

        clean_role = role_name.strip().lower()

        # Explicit role equivalences: TSM == ASM, LEADER == TEAM LEADER
        mapped_target = "ASE"
        if any(k in clean_role for k in ["admin", "super"]):
            mapped_target = "ADMIN"
        elif any(k in clean_role for k in ["team leader", "team_leader", "leader", "lead", "director", "head", "state"]):
            mapped_target = "LEADER"
        elif any(k in clean_role for k in ["tsm", "asm", "territory sales manager", "area sales manager", "manager"]):
            mapped_target = "TSM"
        elif any(k in clean_role for k in ["ase", "executive", "territory executive", "sales executive", "officer", "field", "representative", "salesman"]):
            mapped_target = "ASE"

        try:
            # 1. Exact match
            res = client.table("roles").select("role_id").ilike("role_name", role_name.strip()).limit(1).execute()
            if res.data and len(res.data) > 0:
                return str(res.data[0]["role_id"])

            # 2. Mapped target match
            res_mapped = client.table("roles").select("role_id").ilike("role_name", mapped_target).limit(1).execute()
            if res_mapped.data and len(res_mapped.data) > 0:
                return str(res_mapped.data[0]["role_id"])
        except Exception as e:
            logger.warning(f"Failed to resolve role_id for '{role_name}': {e}")
        return None

    def _resolve_auth_user_id(self, client: Any, email: str, first_name: str, last_name: str) -> Optional[str]:
        """Find or create user in Supabase auth.users to satisfy fk_users_auth_id constraint."""
        email_clean = email.strip().lower()

        # 1. Check if user already exists in public.users
        try:
            res = client.table("users").select("user_id").ilike("email", email_clean).limit(1).execute()
            if res.data and len(res.data) > 0:
                return str(res.data[0]["user_id"])
        except Exception as e:
            logger.warning(f"Error checking existing user in public.users: {e}")

        # 2. Try creating user via Supabase RPC function (bypasses Auth API key format issues)
        try:
            rpc_res = client.rpc("create_auth_user_if_not_exists", {
                "p_email": email_clean,
                "p_first_name": first_name,
                "p_last_name": last_name
            }).execute()
            if rpc_res.data:
                return str(rpc_res.data)
        except Exception as rpc_err:
            logger.warning(f"RPC create_auth_user_if_not_exists error: {rpc_err}")

        # 3. Fallback to Supabase Auth Admin API
        try:
            import secrets
            secure_temp_password = secrets.token_urlsafe(32)
            auth_user = client.auth.admin.create_user({
                "email": email_clean,
                "password": secure_temp_password,
                "email_confirm": True,
                "user_metadata": {"first_name": first_name, "last_name": last_name}
            })
            if auth_user and hasattr(auth_user, 'user') and auth_user.user:
                return str(auth_user.user.id)
            elif isinstance(auth_user, dict) and "id" in auth_user:
                return str(auth_user["id"])
        except Exception:
            pass
        """Check if user exists in auth.users or public.users, or generate a deterministic user_id."""
        try:
            res = client.table("users").select("user_id").ilike("email", email).limit(1).execute()
            if res.data and len(res.data) > 0:
                return str(res.data[0]["user_id"])
        except Exception as e:
            logger.warning(f"Failed to resolve user_id for email '{email}': {e}")
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{email.lower().strip()}"))

    def _resolve_manager_user_id(self, client: Any, reporting_manager: str) -> Optional[str]:
        if not reporting_manager or reporting_manager.strip().lower() in ("unassigned", "none", "", "null", "nan"):
            return None

        mgr_clean = re.sub(r'\s+', ' ', reporting_manager.strip())

        # 1. Check if valid UUID string
        try:
            uuid.UUID(mgr_clean)
            res = client.table("users").select("user_id").eq("user_id", mgr_clean).limit(1).execute()
            if res.data:
                return str(res.data[0]["user_id"])
        except ValueError:
            pass

        # 2. Check by email
        try:
            res = client.table("users").select("user_id").ilike("email", mgr_clean).limit(1).execute()
            if res.data:
                return str(res.data[0]["user_id"])
        except Exception:
            pass

        # 3. Check by full name matching across users in DB
        try:
            res = client.table("users").select("user_id, first_name, last_name").execute()
            users_db = res.data or []
            mgr_norm = mgr_clean.lower()

            # 3a. Exact full name match (normalized whitespace)
            for u in users_db:
                full_n = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                full_n_clean = re.sub(r'\s+', ' ', full_n).lower()
                if full_n_clean == mgr_norm:
                    return str(u["user_id"])

            # 3b. Partial/Prefix name match (e.g., 'Manish Kumar' -> 'Manish Kumar Tailor')
            for u in users_db:
                full_n = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                full_n_clean = re.sub(r'\s+', ' ', full_n).lower()
                if mgr_norm in full_n_clean or full_n_clean in mgr_norm:
                    return str(u["user_id"])

            # 3c. First name or Last name substring match
            for u in users_db:
                fn = str(u.get("first_name", "")).strip().lower()
                ln = str(u.get("last_name", "")).strip().lower()
                if mgr_norm in fn or mgr_norm in ln:
                    return str(u["user_id"])

        except Exception as e:
            logger.warning(f"Failed to resolve manager '{mgr_clean}': {e}")

        return None

    def create_user(self, payload: Dict[str, Any], created_by: Optional[str] = None) -> Dict[str, Any]:
        client = get_supabase()

        first_name = str(payload.get("first_name") or payload.get("firstName") or "").strip()
        last_name = str(payload.get("last_name") or payload.get("lastName") or "").strip()
        if not first_name and payload.get("name"):
            parts = str(payload["name"]).strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        email = str(payload.get("email") or "").strip()
        phone = str(payload.get("phone") or payload.get("phoneNumber") or "").strip()
        clean_phone = re.sub(r'\D', '', phone)
        role_name = str(payload.get("role") or "").strip()
        reporting_manager = payload.get("reportingManager") or payload.get("reporting_manager") or ""
        depot_name = payload.get("depotName") or payload.get("depot_name") or "Unassigned"
        headquarters = payload.get("headquarters") or "Unassigned"
        is_active = payload.get("is_active", payload.get("isActive", True))

        if not first_name:
            raise ValueError("First Name is mandatory.")
        if not email:
            raise ValueError("Email is mandatory.")
        if not phone or len(clean_phone) != 10:
            raise ValueError("Phone Number is mandatory and must be exactly 10 digits.")
        if not role_name:
            raise ValueError("Role is mandatory.")

        phone = clean_phone
        full_name = f"{first_name} {last_name}".strip()

        # Resolve real user_id from auth.users or public.users if client is available
        user_id = None
        if client:
            user_id = self._resolve_auth_user_id(client, email, first_name, last_name)

        if not user_id:
            user_id = payload.get("id") or payload.get("user_id") or str(uuid.uuid4())

        creator_id = created_by or payload.get("created_by") or payload.get("uploaded_by")
        clean_creator_id = str(creator_id) if (creator_id and len(str(creator_id)) == 36 and str(creator_id) != "00000000-0000-0000-0000-000000000001") else None

        user_record = {
            "id": user_id,
            "user_id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "name": full_name,
            "email": email,
            "phone": phone,
            "phoneNumber": phone,
            "role": role_name,
            "reportingManager": reporting_manager or "Unassigned",
            "reporting_manager": reporting_manager or "Unassigned",
            "depotName": depot_name,
            "depot_name": depot_name,
            "headquarters": headquarters,
            "circleName": "Unassigned",
            "isActive": is_active,
            "is_active": is_active,
            "created_by": clean_creator_id,
            "updated_by": clean_creator_id
        }

        user_tenant_id = payload.get("tenant_id")
        if not user_tenant_id and clean_creator_id and client:
            try:
                c_res = client.table("users").select("tenant_id").eq("user_id", clean_creator_id).limit(1).execute()
                if c_res.data and c_res.data[0].get("tenant_id"):
                    user_tenant_id = str(c_res.data[0]["tenant_id"])
            except Exception as e_t:
                logger.warning(f"Could not resolve tenant for creator {clean_creator_id}: {e_t}")

        if user_tenant_id:
            user_record["tenant_id"] = user_tenant_id

        if not client:
            self.in_memory_users.insert(0, user_record)
            return user_record

        user_row = {
            "user_id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "is_active": is_active
        }
        if user_tenant_id:
            user_row["tenant_id"] = user_tenant_id
        if clean_creator_id:
            user_row["created_by"] = clean_creator_id
            user_row["updated_by"] = clean_creator_id

        # Resolve manager user_id if reporting_manager provided
        manager_user_id = self._resolve_manager_user_id(client, reporting_manager)

        try:
            # 1. Upsert into public.users
            client.table("users").upsert(user_row).execute()

            # 2. Insert/Update public.user_roles
            role_id = self._resolve_role_id(client, role_name)
            user_role_id = None
            if role_id:
                try:
                    client.table("user_roles").update({"is_active": False}).eq("user_id", user_id).execute()
                except Exception:
                    pass
                try:
                    ur_res = client.table("user_roles").upsert({"user_id": user_id, "role_id": role_id, "is_active": True}, on_conflict="user_id,role_id").execute()
                    user_role_id = ur_res.data[0]["user_role_id"] if ur_res.data else None
                except Exception:
                    ur_res = client.table("user_roles").select("user_role_id").eq("user_id", user_id).eq("role_id", role_id).limit(1).execute()
                    user_role_id = ur_res.data[0]["user_role_id"] if ur_res.data else None

            # 3. If manager exists, insert/update public.ase_tsm_mapping
            manager_param = payload.get("manager_id") or payload.get("managerId") or payload.get("reportingManager") or payload.get("reporting_manager")
            if manager_param and str(manager_param).strip().lower() not in ("unassigned", "none", "null", ""):
                try:
                    manager_user_id = self._resolve_manager_user_id(client, str(manager_param).strip())
                    if manager_user_id:
                        client.table("ase_tsm_mapping").delete().eq("ase_user_id", user_id).execute()
                        client.table("ase_tsm_mapping").insert({
                            "ase_user_id": user_id,
                            "tsm_user_id": manager_user_id,
                            "is_active": True
                        }).execute()
                except Exception as mgr_err:
                    logger.warning(f"Could not update ase_tsm_mapping: {mgr_err}")

            # 4. If depot_name provided, insert/update user_depot mapping
            if depot_name and depot_name != "Unassigned":
                try:
                    dep_res = client.table("depots").select("depot_id").ilike("name", depot_name.strip()).limit(1).execute()
                    if dep_res.data:
                        d_id = dep_res.data[0]["depot_id"]
                        client.table("user_depot").delete().eq("user_id", user_id).execute()
                        client.table("user_depot").insert({"user_id": user_id, "depot_id": d_id}).execute()
                except Exception as d_err:
                    logger.warning(f"Could not update user_depot mapping during create_user: {d_err}")

            # 5. If headquarters_ids provided, map user to headquarters
            if "headquarters_ids" in payload and payload["headquarters_ids"] is not None:
                try:
                    self.set_user_headquarters(user_id, payload["headquarters_ids"], updated_by=clean_creator_id)
                except Exception as hq_err:
                    logger.warning(f"Could not set user headquarters during create_user: {hq_err}")

        except Exception as e:
            logger.error(f"Error creating user in Supabase: {e}")

        user_record["id"] = user_id
        user_record["user_id"] = user_id
        self.in_memory_users.insert(0, user_record)
        return user_record

    def update_user(self, user_id: str, payload: Dict[str, Any], updated_by: Optional[str] = None) -> Dict[str, Any]:
        client = get_supabase()

        first_name = payload.get("first_name") or payload.get("firstName")
        last_name = payload.get("last_name") or payload.get("lastName")
        if first_name is None and payload.get("name"):
            parts = str(payload["name"]).strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        if first_name is not None and not str(first_name).strip():
            raise ValueError("First Name is mandatory.")

        if "email" in payload:
            email_val = str(payload["email"]).strip()
            if not email_val:
                raise ValueError("Email is mandatory.")

        if "phone" in payload or "phoneNumber" in payload:
            ph_val = str(payload.get("phone", payload.get("phoneNumber")) or "").strip()
            clean_ph = re.sub(r'\D', '', ph_val)
            if not ph_val or len(clean_ph) != 10:
                raise ValueError("Phone Number is mandatory and must be exactly 10 digits.")
            payload["phone"] = clean_ph
            payload["phoneNumber"] = clean_ph

        if "role" in payload and not str(payload["role"]).strip():
            raise ValueError("Role is mandatory.")

        # Update in memory cache
        for idx, u in enumerate(self.in_memory_users):
            if u.get("id") == user_id or u.get("user_id") == user_id:
                if first_name: self.in_memory_users[idx]["first_name"] = first_name
                if last_name: self.in_memory_users[idx]["last_name"] = last_name
                if first_name or last_name:
                    fn = first_name or u.get("first_name", "")
                    ln = last_name or u.get("last_name", "")
                    self.in_memory_users[idx]["name"] = f"{fn} {ln}".strip()
                if "phone" in payload or "phoneNumber" in payload:
                    ph = payload.get("phone", payload.get("phoneNumber"))
                    self.in_memory_users[idx]["phone"] = ph
                    self.in_memory_users[idx]["phoneNumber"] = ph
                if "role" in payload:
                    self.in_memory_users[idx]["role"] = payload["role"]
                if "reporting_manager" in payload or "reportingManager" in payload:
                    rm = payload.get("reporting_manager", payload.get("reportingManager"))
                    self.in_memory_users[idx]["reporting_manager"] = rm
                    self.in_memory_users[idx]["reportingManager"] = rm

        if not client:
            return payload

        user_update: Dict[str, Any] = {}
        if first_name is not None: user_update["first_name"] = first_name
        if last_name is not None: user_update["last_name"] = last_name
        if "phone" in payload or "phoneNumber" in payload:
            user_update["phone"] = payload.get("phone", payload.get("phoneNumber"))
        if "email" in payload:
            user_update["email"] = payload["email"]
        is_active_val = payload.get("is_active", payload.get("isActive"))
        if is_active_val is not None:
            user_update["is_active"] = bool(is_active_val)
            user_update["updated_at"] = datetime.now(timezone.utc).isoformat()

        updator_id = updated_by or payload.get("updated_by") or payload.get("uploaded_by") or payload.get("created_by")
        clean_updator_id = str(updator_id) if (updator_id and len(str(updator_id)) == 36 and str(updator_id) != "00000000-0000-0000-0000-000000000001") else None
        if clean_updator_id:
            user_update["updated_by"] = clean_updator_id

        manager_param = payload.get("manager_id") or payload.get("managerId") or payload.get("reportingManager") or payload.get("reporting_manager")
        has_manager_field = any(k in payload for k in ("manager_id", "managerId", "reportingManager", "reporting_manager"))
        manager_user_id = None
        if has_manager_field and manager_param:
            if str(manager_param).strip().lower() not in ("unassigned", "none", "null", ""):
                manager_user_id = self._resolve_manager_user_id(client, str(manager_param).strip())

        try:
            if user_update:
                client.table("users").update(user_update).eq("user_id", user_id).execute()

            if is_active_val is not None:
                new_status = bool(is_active_val)
                try:
                    client.table("user_roles").update({"is_active": new_status}).eq("user_id", user_id).execute()
                except Exception as e_ur:
                    logger.warning(f"Could not update user_roles is_active to {new_status} for {user_id}: {e_ur}")

                try:
                    client.table("ase_tsm_mapping").update({"is_active": new_status}).or_(f"ase_user_id.eq.{user_id},tsm_user_id.eq.{user_id}").execute()
                except Exception as e_atm:
                    logger.warning(f"Could not update ase_tsm_mapping is_active to {new_status} for {user_id}: {e_atm}")

                try:
                    client.table("user_headquarters_mapping").update({
                        "is_active": new_status,
                        "updated_at": user_update.get("updated_at", datetime.now(timezone.utc).isoformat())
                    }).eq("user_id", user_id).execute()
                except Exception as e_uhq:
                    logger.warning(f"Could not update user_headquarters_mapping is_active to {new_status} for {user_id}: {e_uhq}")

            role_name = payload.get("role")
            user_role_id = None
            if role_name:
                role_id = self._resolve_role_id(client, role_name)
                if role_id:
                    try:
                        client.table("user_roles").update({"is_active": False}).eq("user_id", user_id).execute()
                    except Exception as e_role_deact:
                        logger.warning(f"Could not deactivate old roles for {user_id}: {e_role_deact}")
                    
                    ur_res = client.table("user_roles").upsert({"user_id": user_id, "role_id": role_id, "is_active": True}, on_conflict="user_id,role_id").execute()
                    user_role_id = ur_res.data[0]["user_role_id"] if ur_res.data else None

            # Upsert or clear public.ase_tsm_mapping if manager field was provided
            if has_manager_field:
                try:
                    if manager_user_id:
                        client.table("ase_tsm_mapping").delete().eq("ase_user_id", user_id).execute()
                        client.table("ase_tsm_mapping").insert({
                            "ase_user_id": user_id,
                            "tsm_user_id": manager_user_id,
                            "is_active": True
                        }).execute()
                    else:
                        # Manager explicitly unassigned or cleared
                        client.table("ase_tsm_mapping").delete().eq("ase_user_id", user_id).execute()
                except Exception as e:
                    logger.warning(f"Could not update ase_tsm_mapping during update_user: {e}")

            # Update user_depot if depotName or depot_name in payload
            depot_name_update = payload.get("depotName") or payload.get("depot_name")
            if depot_name_update is not None:
                if str(depot_name_update).strip().lower() in ("unassigned", "none", "", "null"):
                    client.table("user_depot").delete().eq("user_id", user_id).execute()
                else:
                    try:
                        dep_res = client.table("depots").select("depot_id").ilike("name", str(depot_name_update).strip()).limit(1).execute()
                        if dep_res.data:
                            d_id = dep_res.data[0]["depot_id"]
                            client.table("user_depot").delete().eq("user_id", user_id).execute()
                            client.table("user_depot").insert({"user_id": user_id, "depot_id": d_id}).execute()
                    except Exception as d_err:
                        logger.warning(f"Could not update user_depot during update_user: {d_err}")

            # Update headquarters assignments if headquarters_ids provided in payload
            if "headquarters_ids" in payload and payload["headquarters_ids"] is not None:
                try:
                    self.set_user_headquarters(user_id, payload["headquarters_ids"], updated_by=clean_updator_id)
                except Exception as hq_err:
                    logger.warning(f"Could not update user headquarters during update_user: {hq_err}")

        except Exception as e:
            logger.error(f"Error updating user {user_id} in Supabase: {e}")

        # Return refreshed user record
        all_users = self.list_users()
        for u in all_users:
            if u.get("id") == user_id or u.get("user_id") == user_id:
                return u
        return payload

    def get_user_headquarters(self, user_id: str) -> Dict[str, Any]:
        """Fetch all active headquarters assigned to a user."""
        client = get_supabase()
        if not client:
            return {"user_id": user_id, "headquarters_ids": [], "headquarters": [], "headquarters_names": []}

        # Verify user exists
        user_res = client.table("users").select("user_id, first_name, last_name, tenant_id").eq("user_id", user_id).limit(1).execute()
        if not user_res.data:
            raise ValueError(f"User '{user_id}' does not exist.")

        # Fetch HQ lookup
        hq_res = client.table("headquarters").select("headquarters_id, name").execute()
        hq_map = {str(h["headquarters_id"]): h.get("name", "Unassigned") for h in (hq_res.data or [])}

        uhq_res = client.table("user_headquarters_mapping").select("mapping_id, headquarters_id, is_active").eq("user_id", user_id).eq("is_active", True).execute()
        active_mappings = uhq_res.data or []

        hq_ids = [str(m["headquarters_id"]) for m in active_mappings if m.get("headquarters_id")]
        hqs = [{"headquarters_id": hid, "name": hq_map.get(hid, "Unknown")} for hid in hq_ids]
        hq_names = [h["name"] for h in hqs]

        return {
            "user_id": user_id,
            "headquarters_ids": hq_ids,
            "headquarters": hqs,
            "headquarters_names": hq_names,
            "headquarters_display": ", ".join(hq_names) if hq_names else "Unassigned"
        }

    def set_user_headquarters(self, user_id: str, headquarters_ids: List[str], updated_by: Optional[str] = None) -> Dict[str, Any]:
        """Atomically set/replace active headquarters for a user (supports single, multiple, or empty list)."""
        client = get_supabase()
        if not client:
            return {"user_id": user_id, "headquarters_ids": headquarters_ids, "headquarters": []}

        # 1. Verify user exists and retrieve tenant
        user_res = client.table("users").select("user_id, first_name, last_name, tenant_id, is_active").eq("user_id", user_id).limit(1).execute()
        if not user_res.data:
            raise ValueError(f"User '{user_id}' does not exist.")
        user = user_res.data[0]
        user_tenant_id = user.get("tenant_id")
        if not user_tenant_id and updated_by:
            try:
                admin_res = client.table("users").select("tenant_id").eq("user_id", str(updated_by)).limit(1).execute()
                if admin_res.data and admin_res.data[0].get("tenant_id"):
                    user_tenant_id = admin_res.data[0]["tenant_id"]
            except Exception:
                pass

        # 2. De-duplicate requested HQ IDs while preserving order
        clean_hq_ids = []
        for hid in (headquarters_ids or []):
            s_hid = str(hid).strip()
            if s_hid and s_hid not in clean_hq_ids:
                clean_hq_ids.append(s_hid)

        # 3. If list not empty, validate each HQ exists, is active, and matches user tenant
        hq_lookup = {}
        if clean_hq_ids:
            hq_res = client.table("headquarters").select("headquarters_id, name, is_active, tenant_id").in_("headquarters_id", clean_hq_ids).execute()
            found_hqs = hq_res.data or []
            found_ids = {str(h["headquarters_id"]): h for h in found_hqs}

            for hid in clean_hq_ids:
                if hid not in found_ids:
                    raise ValueError(f"Headquarters ID '{hid}' does not exist.")
                hq_obj = found_ids[hid]
                if not hq_obj.get("is_active", True):
                    raise ValueError(f"Headquarters '{hq_obj.get('name', hid)}' is inactive.")
                hq_tenant = hq_obj.get("tenant_id")
                if hq_tenant and user_tenant_id and str(hq_tenant) != str(user_tenant_id):
                    raise ValueError(f"Cross-tenant assignment rejected: Headquarters '{hq_obj.get('name')}' belongs to a different tenant.")
                hq_lookup[hid] = hq_obj.get("name", "Unknown")

        # 4. Atomic update: delete existing active mappings for user, then insert new ones
        client.table("user_headquarters_mapping").delete().eq("user_id", user_id).execute()

        if clean_hq_ids:
            new_rows = []
            for hid in clean_hq_ids:
                row_map = {
                    "user_id": user_id,
                    "headquarters_id": hid,
                    "is_active": True,
                    "created_by": updated_by,
                    "updated_by": updated_by
                }
                if user_tenant_id:
                    row_map["tenant_id"] = user_tenant_id
                new_rows.append(row_map)
            client.table("user_headquarters_mapping").insert(new_rows).execute()

        hq_names = [hq_lookup.get(hid, "Unknown") for hid in clean_hq_ids]
        return {
            "user_id": user_id,
            "headquarters_ids": clean_hq_ids,
            "headquarters": [{"headquarters_id": hid, "name": hq_lookup.get(hid, "Unknown")} for hid in clean_hq_ids],
            "headquarters_names": hq_names,
            "headquarters_display": ", ".join(hq_names) if hq_names else "Unassigned"
        }

    def delete_user(self, user_id: str, deleted_by: Optional[str] = None) -> bool:
        client = get_supabase()
        
        # Keep user in in-memory cache marked as inactive so it remains visible on web
        for u in self.in_memory_users:
            if u.get("id") == user_id or u.get("user_id") == user_id:
                u["is_active"] = False
                u["isActive"] = False

        if not client:
            return True

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            user_update_data: Dict[str, Any] = {"is_active": False, "updated_at": now_iso}
            clean_deleted_by = str(deleted_by) if (deleted_by and len(str(deleted_by)) == 36 and str(deleted_by) != "00000000-0000-0000-0000-000000000001") else None
            if clean_deleted_by:
                user_update_data["updated_by"] = clean_deleted_by

            try:
                client.table("users").update(user_update_data).eq("user_id", user_id).execute()
            except Exception as e:
                logger.warning(f"Could not set users.is_active=False for {user_id}: {e}")

            try:
                client.table("user_roles").update({"is_active": False}).eq("user_id", user_id).execute()
            except Exception as e:
                logger.warning(f"Could not deactivate user_roles for {user_id}: {e}")

            try:
                client.table("ase_tsm_mapping").update({"is_active": False}).or_(f"ase_user_id.eq.{user_id},tsm_user_id.eq.{user_id}").execute()
            except Exception as e:
                logger.warning(f"Could not deactivate ase_tsm_mapping for {user_id}: {e}")

            try:
                uhq_update = {"is_active": False, "updated_at": now_iso}
                if clean_deleted_by:
                    uhq_update["updated_by"] = clean_deleted_by
                client.table("user_headquarters_mapping").update(uhq_update).eq("user_id", user_id).execute()
            except Exception as e:
                logger.warning(f"Could not deactivate user_headquarters_mapping for {user_id}: {e}")

            # Note: user_depot row and users row are preserved intact to retain historical reporting and web details
            return True
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            return True

    def process_excel_roster(
        self,
        file_content: bytes,
        filename: str,
        uploaded_by: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses uploaded Excel roster and maps data using a 2-pass pipeline:
        Pass 1: Insert/Upsert users into public.users and public.user_roles (partitioned by admin tenant_id)
        Pass 2: Resolve reporting managers and map hierarchy into public.ase_tsm_mapping
        """
        client = get_supabase()
        if not tenant_id and uploaded_by and client:
            try:
                u_res = client.table("users").select("tenant_id").eq("user_id", str(uploaded_by)).limit(1).execute()
                if u_res.data and u_res.data[0].get("tenant_id"):
                    tenant_id = str(u_res.data[0]["tenant_id"])
            except Exception as e_tid:
                logger.warning(f"Could not resolve tenant_id for uploader {uploaded_by}: {e_tid}")
        try:
            filename_lower = filename.lower()
            if filename_lower.endswith('.csv'):
                df_csv = None
                for enc in ['utf-8', 'utf-8-sig', 'cp1252', 'latin1', 'iso-8859-1']:
                    try:
                        df_csv = pd.read_csv(io.BytesIO(file_content), header=None, encoding=enc, on_bad_lines='skip')
                        if df_csv is not None and not df_csv.empty:
                            break
                    except Exception:
                        continue
                sheets_to_try = [df_csv] if df_csv is not None else []
            elif filename_lower.endswith('.xlsb'):
                try:
                    xl = pd.ExcelFile(io.BytesIO(file_content), engine='pyxlsb')
                    sheets_to_try = [xl.parse(s, header=None) for s in xl.sheet_names]
                except Exception:
                    xl = pd.ExcelFile(io.BytesIO(file_content))
                    sheets_to_try = [xl.parse(s, header=None) for s in xl.sheet_names]
            else:
                xl = pd.ExcelFile(io.BytesIO(file_content))
                sheets_to_try = [xl.parse(s, header=None) for s in xl.sheet_names]
        except Exception as e:
            logger.error(f"Failed to read file {filename}: {e}")
            raise ValueError(f"Could not parse file '{filename}'. Please ensure it is a valid Excel or CSV file.")

        if not sheets_to_try:
            return {"status": "success", "imported_count": 0, "updated_count": 0, "message": "Uploaded file contains no sheets."}

        df_raw = None
        header_row_idx = 0
        known_keywords = ["name", "email", "phone", "role", "manager", "tsm", "ase", "designation", "contact", "mobile", "reporting", "emp", "staff", "user", "officer", "personnel"]

        # 1. Detect header row by finding the first row with at least 1 keyword match
        for sheet_df in sheets_to_try:
            raw_rows = sheet_df.values.tolist()
            for idx, row in enumerate(raw_rows[:25]):
                row_str = [str(cell).strip().lower() if cell is not None and pd.notna(cell) else "" for cell in row]
                matches = sum(1 for kw in known_keywords if any(kw in cell for cell in row_str))
                if matches >= 1:
                    header_row_idx = idx
                    df_raw = sheet_df
                    break
            if df_raw is not None:
                break

        if df_raw is None:
            df_raw = sheets_to_try[0]

        raw_rows = df_raw.values.tolist()
        if not raw_rows or len(raw_rows) <= header_row_idx:
            return {"status": "success", "imported_count": 0, "updated_count": 0, "message": "Uploaded sheet contains no data."}

        headers = [str(cell).strip() if cell is not None and pd.notna(cell) else f"Column_{i+1}" for i, cell in enumerate(raw_rows[header_row_idx])]
        data_rows = raw_rows[header_row_idx + 1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        df = df.dropna(how="all")

        # Standardize column headers for alias matching
        col_clean_map = {c: str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns}

        # Comprehensive Column Aliases
        FIRST_NAME_ALIASES = ["first_name", "firstname", "first", "given_name", "fname"]
        LAST_NAME_ALIASES = ["last_name", "lastname", "last", "surname", "family_name", "lname"]
        FULL_NAME_ALIASES = [
            "name", "full_name", "employee_name", "user_name", "staff_name", "personnel_name", 
            "person_name", "employee", "user", "emp_name", "name_of_employee", "name_of_ase", 
            "name_of_tsm", "ase_name", "tsm_name", "executive_name", "officer_name", "member_name",
            "field_executive", "staff", "personnel", "person", "member"
        ]
        EMAIL_ALIASES = ["email", "email_id", "email_address", "mail", "mail_id", "user_email"]
        PHONE_ALIASES = ["phone", "phone_number", "mobile", "mobile_number", "contact", "contact_number", "phone_no", "mobile_no", "cell"]
        ROLE_ALIASES = ["role", "role_name", "designation", "position", "user_role", "user_type", "grade", "title"]
        MANAGER_ALIASES = ["reporting_manager", "manager", "manager_name", "tsm", "tsm_name", "reporting_to", "supervisor", "reporting", "reporting_head", "manager_id", "head"]
        DEPOT_ALIASES = ["depot", "depot_name", "location", "branch", "place", "depot_location"]
        HQ_ALIASES = ["hq", "headquarter", "headquarters", "hq_name", "zone", "circle", "region"]

        manager_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in MANAGER_ALIASES)), None)
        first_name_col = next((c for c, clean in col_clean_map.items() if any(a == clean or clean.startswith(a) for a in FIRST_NAME_ALIASES)), None)
        last_name_col = next((c for c, clean in col_clean_map.items() if any(a == clean or clean.startswith(a) for a in LAST_NAME_ALIASES)), None)
        
        full_name_col = next((c for c, clean in col_clean_map.items() if any(a == clean for a in FULL_NAME_ALIASES) and c != manager_col), None)
        if not full_name_col:
            full_name_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in FULL_NAME_ALIASES) and c != manager_col), None)
        if not full_name_col and not first_name_col:
            # Fallback: pick the first column whose cleaned name contains 'name', 'emp', 'staff', or 'user' (excluding manager_col)
            full_name_col = next((c for c, clean in col_clean_map.items() if any(k in clean for k in ["name", "emp", "staff", "user", "ase", "tsm"]) and c != manager_col), None)
        if not full_name_col and not first_name_col and len(df.columns) > 0:
            # Absolute fallback: pick column 0
            full_name_col = df.columns[0]

        email_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in EMAIL_ALIASES)), None)
        phone_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in PHONE_ALIASES)), None)
        role_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in ROLE_ALIASES)), None)
        depot_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in DEPOT_ALIASES)), None)
        hq_col = next((c for c, clean in col_clean_map.items() if any(a in clean for a in HQ_ALIASES)), None)

        imported_count = 0
        pass1_records = []

        # PASS 1: Create / Upsert user details & roles in public.users and public.user_roles
        for _, row in df.iterrows():
            fn = str(row[first_name_col]).strip() if first_name_col and pd.notna(row[first_name_col]) else ""
            ln = str(row[last_name_col]).strip() if last_name_col and pd.notna(row[last_name_col]) else ""
            if not fn and full_name_col and pd.notna(row[full_name_col]):
                raw_name = str(row[full_name_col]).strip()
                if raw_name and raw_name.lower() not in ("nan", "none", "null", ""):
                    raw_name = re.sub(r'\s+', ' ', raw_name)
                    parts = raw_name.split(" ", 1)
                    fn = parts[0]
                    ln = parts[1] if len(parts) > 1 else ""

            fn = re.sub(r'\s+', ' ', fn)
            ln = re.sub(r'\s+', ' ', ln)

            if not fn or fn.lower() in ("nan", "none", "null", ""):
                logger.warning("Excel roster row skipped: First Name is mandatory.")
                continue

            email_val = str(row[email_col]).strip() if email_col and pd.notna(row[email_col]) else ""
            if not email_val or email_val.lower() in ("nan", "none", "null", ""):
                email_val = f"{fn.lower().replace(' ', '')}.{ln.lower().replace(' ', '')}@rll.com"

            phone_val = ""
            if phone_col and pd.notna(row[phone_col]):
                raw_ph = row[phone_col]
                try:
                    if isinstance(raw_ph, (float, int)):
                        phone_val = str(int(raw_ph))
                    else:
                        phone_val = str(raw_ph).strip().rstrip('.0')
                except Exception:
                    phone_val = str(raw_ph).strip()

            clean_ph = re.sub(r'\D', '', phone_val)
            if len(clean_ph) == 12 and clean_ph.startswith('91'):
                clean_ph = clean_ph[2:]
            elif len(clean_ph) == 11 and clean_ph.startswith('0'):
                clean_ph = clean_ph[1:]

            if len(clean_ph) != 10:
                clean_ph = f"9900{idx % 1000000:06d}"

            role_val = str(row[role_col]).strip() if role_col and pd.notna(row[role_col]) else "Territory Executive"
            manager_val = str(row[manager_col]).strip() if manager_col and pd.notna(row[manager_col]) else "Unassigned"
            depot_val = str(row[depot_col]).strip() if depot_col and pd.notna(row[depot_col]) else "Unassigned"
            hq_val = str(row[hq_col]).strip() if hq_col and pd.notna(row[hq_col]) else "Unassigned"

            payload = {
                "first_name": fn,
                "last_name": ln,
                "email": email_val,
                "phone": clean_ph,
                "role": role_val,
                "reporting_manager": "Unassigned",  # Will map in Pass 2
                "depot_name": depot_val,
                "headquarters": hq_val,
                "is_active": True,
                "created_by": uploaded_by,
                "uploaded_by": uploaded_by,
                "updated_by": uploaded_by,
                "tenant_id": tenant_id
            }

            try:
                res = self.create_user(payload, created_by=uploaded_by)
                if res:
                    imported_count += 1
                    pass1_records.append({
                        "user": res,
                        "target_manager": manager_val
                    })
            except ValueError as ve:
                logger.warning(f"Excel roster row for '{fn}' skipped due to validation error: {ve}")
                continue

        # PASS 2: Establish Hierarchy Mappings in public.ase_tsm_mapping and update manager_id
        for rec in pass1_records:
            mgr_target = rec["target_manager"]
            if not mgr_target or mgr_target.lower() in ("unassigned", "none", "", "nan"):
                continue

            user_obj = rec["user"]
            u_id = user_obj.get("user_id") or user_obj.get("id")

            # Update manager hierarchy and trigger public.ase_tsm_mapping update
            self.update_user(u_id, {"reporting_manager": mgr_target}, updated_by=uploaded_by)

        return {
            "status": "success",
            "imported_count": imported_count,
            "updated_count": 0,
            "message": f"Successfully processed headcount roster file '{filename}'. Imported {imported_count} employee records mapped across users, user_roles, and ase_tsm_mapping tables."
        }

    def populate_users_and_hierarchy_from_raw(self, batch_id: int) -> Dict[str, int]:
        """
        Extract unique TSM and ASE personnel from raw_sales_upload for batch_id,
        populate public.users, public.user_roles, and public.ase_tsm_mapping.
        Returns statistics of created records.
        """
        client = get_supabase()
        if not client:
            return {"users": 0, "mappings": 0}

        try:
            # 1. Query distinct raw personnel & depot mappings
            res = client.table("raw_sales_upload").select("ase_raw, asm_tsm_raw, depot_raw").eq("batch_id", batch_id).execute()
            raw_rows = res.data or []
            if not raw_rows:
                return {"users": 0, "mappings": 0}

            tsm_role_id = self._resolve_role_id(client, "TSM")
            ase_role_id = self._resolve_role_id(client, "ASE")

            # Resolve all depots in DB for matching
            depot_cache: Dict[str, str] = {}
            try:
                dep_res = client.table("depots").select("depot_id, name").execute()
                for d in dep_res.data or []:
                    dep_name_clean = str(d.get("name") or "").strip().lower()
                    if dep_name_clean:
                        depot_cache[dep_name_clean] = str(d.get("depot_id"))
            except Exception as e_dep:
                logger.warning(f"Could not prefetch depots for user_depot mapping: {e_dep}")

            # Extract distinct TSMs, ASE-TSM pairs, and user-depot relationships
            tsm_set = set()
            ase_tsm_pairs = set()
            user_depots: Dict[str, set] = {} # user_name -> set of depot_ids

            for row in raw_rows:
                ase_raw = row.get("ase_raw") or ""
                tsm_raw = row.get("asm_tsm_raw") or ""
                depot_raw = str(row.get("depot_raw") or "").strip()
                depot_id = depot_cache.get(depot_raw.lower())

                ase_names = [p.strip() for p in ase_raw.replace(",", "/").split("/") if p.strip()]
                tsm_names = [p.strip() for p in tsm_raw.replace(",", "/").split("/") if p.strip()]

                for tsm in tsm_names:
                    if tsm and tsm.lower() not in ["unassigned", "none", "null", "nan"]:
                        tsm_set.add(tsm)
                        if depot_id:
                            user_depots.setdefault(tsm, set()).add(depot_id)

                first_tsm = tsm_names[0] if tsm_names and tsm_names[0].lower() not in ["unassigned", "none", "null", "nan"] else None
                for ase in ase_names:
                    if ase and ase.lower() not in ["unassigned", "none", "null", "nan"]:
                        ase_tsm_pairs.add((ase, first_tsm))
                        if depot_id:
                            user_depots.setdefault(ase, set()).add(depot_id)

            user_cache: Dict[str, str] = {} # name -> user_id
            user_role_cache: Dict[str, str] = {} # name -> user_role_id

            import random

            def _generate_phone(name: str) -> str:
                # Deterministic random phone starting with 9829 or 9414 (Rajasthan prefixes)
                seed = sum(ord(c) for c in name)
                digits = str(abs(seed * 1234567))[:6].zfill(6)
                return f"+919829{digits}"

            # 2. Upsert TSM users & roles
            for tsm_name in tsm_set:
                parts = tsm_name.split(" ", 1)
                fn = parts[0]
                ln = parts[1] if len(parts) > 1 else ""
                email = f"{fn.lower().replace(' ', '')}.{ln.lower().replace(' ', '')}@rll.com"
                phone = _generate_phone(tsm_name)

                u_id = self._resolve_auth_user_id(client, email, fn, ln) or str(uuid.uuid4())
                client.table("users").upsert({
                    "user_id": u_id,
                    "first_name": fn,
                    "last_name": ln,
                    "email": email,
                    "phone": phone,
                    "is_active": True
                }).execute()
                user_cache[tsm_name] = u_id

                if tsm_role_id:
                    ur_res = client.table("user_roles").upsert({
                        "user_id": u_id,
                        "role_id": tsm_role_id,
                        "is_active": True
                    }, on_conflict="user_id,role_id").execute()
                    if ur_res.data:
                        user_role_cache[tsm_name] = str(ur_res.data[0]["user_role_id"])

                # Insert user_depot records
                for d_id in user_depots.get(tsm_name, set()):
                    try:
                        client.table("user_depot").upsert({"user_id": u_id, "depot_id": d_id}, on_conflict="user_id,depot_id").execute()
                    except Exception as ud_err:
                        logger.warning(f"user_depot mapping error for TSM {tsm_name}: {ud_err}")

            # 3. Upsert ASE users, roles, hierarchy mappings & depot assignments
            mappings_count = 0
            for ase_name, tsm_name in ase_tsm_pairs:
                parts = ase_name.split(" ", 1)
                fn = parts[0]
                ln = parts[1] if len(parts) > 1 else ""
                email = f"{fn.lower().replace(' ', '')}.{ln.lower().replace(' ', '')}@rll.com"
                phone = _generate_phone(ase_name)

                mgr_id = user_cache.get(tsm_name) if tsm_name else None
                u_id = self._resolve_auth_user_id(client, email, fn, ln) or str(uuid.uuid4())

                user_row = {
                    "user_id": u_id,
                    "first_name": fn,
                    "last_name": ln,
                    "email": email,
                    "phone": phone,
                    "is_active": True
                }

                client.table("users").upsert(user_row).execute()
                user_cache[ase_name] = u_id

                ase_ur_id = None
                if ase_role_id:
                    ur_res = client.table("user_roles").upsert({
                        "user_id": u_id,
                        "role_id": ase_role_id,
                        "is_active": True
                    }, on_conflict="user_id,role_id").execute()
                    if ur_res.data:
                        ase_ur_id = str(ur_res.data[0]["user_role_id"])
                        user_role_cache[ase_name] = ase_ur_id

                tsm_ur_id = user_role_cache.get(tsm_name) if tsm_name else None
                if mgr_id:
                    client.table("ase_tsm_mapping").insert({
                        "ase_user_id": u_id,
                        "tsm_user_id": mgr_id,
                        "is_active": True
                    }).execute()
                    mappings_count += 1

                # Insert user_depot records
                for d_id in user_depots.get(ase_name, set()):
                    try:
                        client.table("user_depot").upsert({"user_id": u_id, "depot_id": d_id}, on_conflict="user_id,depot_id").execute()
                    except Exception as ud_err:
                        logger.warning(f"user_depot mapping error for ASE {ase_name}: {ud_err}")

            return {"users": len(user_cache), "mappings": mappings_count}
        except Exception as e:
            logger.error(f"Error populating users and hierarchy from raw: {e}")
            return {"users": 0, "mappings": 0}

    def list_roles(self) -> List[Dict[str, Any]]:
        """
        Fetch available roles from public.roles table.
        Fallback to standard hierarchy roles if database is empty or offline.
        """
        client = get_supabase()
        if client:
            try:
                res = client.table("roles").select("role_id, role_name, description, is_active").execute()
                if res.data and len(res.data) > 0:
                    return [
                        {
                            "role_id": str(r["role_id"]),
                            "role_name": r["role_name"],
                            "description": r.get("description") or f"{r['role_name']} Role",
                            "is_active": r.get("is_active", True)
                        }
                        for r in res.data
                    ]
            except Exception as e:
                logger.warning(f"Error fetching roles from Supabase: {e}")

        return [
            {"role_id": "1", "role_name": "ASE", "description": "Area Sales Executive / Depot Field Sales Executive"},
            {"role_id": "2", "role_name": "TSM", "description": "Territory Sales Manager / Circle Supervisor"},
            {"role_id": "3", "role_name": "Regional Supervisor", "description": "Regional Sales Supervisor"},
            {"role_id": "4", "role_name": "Admin", "description": "System Administrator with full access"}
        ]

    def create_role(self, payload: Dict[str, Any], created_by: Optional[str] = None) -> Dict[str, Any]:
        client = get_supabase()
        if not client:
            raise ValueError("Database connection unavailable")
            
        role_name = payload.get("role_name", "").strip()
        description = payload.get("description", "").strip()
        is_active = payload.get("is_active", True)
        
        if not role_name:
            raise ValueError("Role name is required")
            
        res = client.table("roles").select("role_id").ilike("role_name", role_name).execute()
        if res.data:
            raise ValueError(f"Role '{role_name}' already exists")

        creator_id = created_by or payload.get("created_by") or payload.get("uploaded_by")
        clean_creator_id = str(creator_id) if (creator_id and len(str(creator_id)) == 36 and str(creator_id) != "00000000-0000-0000-0000-000000000001") else None

        role_row = {
            "role_name": role_name,
            "description": description or f"{role_name} Role",
            "is_active": is_active
        }
        if clean_creator_id:
            role_row["created_by"] = clean_creator_id
            role_row["updated_by"] = clean_creator_id
            
        ins = client.table("roles").insert(role_row).execute()
        
        if ins.data:
            r = ins.data[0]
            return {
                "role_id": str(r["role_id"]),
                "role_name": r["role_name"],
                "description": r.get("description"),
                "is_active": r.get("is_active", True)
            }
        return payload

    def update_role(self, role_id: str, payload: Dict[str, Any], updated_by: Optional[str] = None) -> Dict[str, Any]:
        client = get_supabase()
        if not client:
            raise ValueError("Database connection unavailable")
            
        update_data = {}
        if "role_name" in payload:
            update_data["role_name"] = payload["role_name"].strip()
        if "description" in payload:
            update_data["description"] = payload["description"].strip()
        if "is_active" in payload:
            update_data["is_active"] = payload["is_active"]

        updator_id = updated_by or payload.get("updated_by") or payload.get("uploaded_by") or payload.get("created_by")
        clean_updator_id = str(updator_id) if (updator_id and len(str(updator_id)) == 36 and str(updator_id) != "00000000-0000-0000-0000-000000000001") else None
        if clean_updator_id:
            update_data["updated_by"] = clean_updator_id
            
        if not update_data:
            return {"role_id": role_id}
            
        res = client.table("roles").update(update_data).eq("role_id", role_id).execute()
        if res.data:
            r = res.data[0]
            return {
                "role_id": str(r["role_id"]),
                "role_name": r["role_name"],
                "description": r.get("description"),
                "is_active": r.get("is_active", True)
            }
        raise ValueError(f"Failed to update role {role_id}")

    def delete_role(self, role_id: str) -> bool:
        client = get_supabase()
        if not client:
            return False
        try:
            client.table("roles").update({"is_active": False}).eq("role_id", role_id).execute()
        except Exception:
            client.table("roles").delete().eq("role_id", role_id).execute()
        return True

    def get_hierarchy(self) -> List[Dict[str, Any]]:
        """
        Fetch all active personnel hierarchy mappings from public.ase_tsm_mapping
        joined with public.users and public.user_roles.
        """
        client = get_supabase()
        if not client:
            return []

        try:
            res = client.table("ase_tsm_mapping").select("hierarchy_id, ase_user_id, tsm_user_id, is_active").execute()
            mappings = res.data or []
            all_users = {u["id"]: u for u in self.list_users()}
            output = []
            for m in mappings:
                if not m.get("is_active", True):
                    continue
                ase_id = str(m.get("ase_user_id"))
                tsm_id = str(m.get("tsm_user_id"))
                ase_user = all_users.get(ase_id, {})
                tsm_user = all_users.get(tsm_id, {})
                output.append({
                    "hierarchy_id": str(m.get("hierarchy_id")),
                    "ase_user_id": ase_id,
                    "ase_name": ase_user.get("name") or "ASE User",
                    "ase_role": ase_user.get("role") or "ASE",
                    "ase_email": ase_user.get("email") or "",
                    "tsm_user_id": tsm_id,
                    "tsm_name": tsm_user.get("name") or "TSM User",
                    "tsm_role": tsm_user.get("role") or "TSM",
                    "tsm_email": tsm_user.get("email") or "",
                    "is_active": m.get("is_active", True)
                })
            return output
        except Exception as ex:
            logger.error(f"Error querying ase_tsm_mapping hierarchy: {ex}")
            return []


user_service = UserService()

