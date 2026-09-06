import uuid
import logging
import io
from typing import List, Dict, Any, Optional
import pandas as pd
from backend.db.client import get_supabase


logger = logging.getLogger(__name__)

# Fallback seed data in case Supabase is offline or empty
FALLBACK_USERS: List[Dict[str, Any]] = []


class UserService:
    def __init__(self):
        self.in_memory_users = list(FALLBACK_USERS)

    def list_users(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if not client:
            return self.in_memory_users

        try:
            # 1. Fetch users
            users_res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active, created_at").execute()
            raw_users = users_res.data if users_res.data is not None else []

            if not raw_users:
                return self.in_memory_users

            # 2. Fetch roles map
            roles_res = client.table("roles").select("role_id, role_name").execute()
            roles_map = {str(r["role_id"]): r.get("role_name", "ASE") for r in (roles_res.data or []) if r.get("role_id")}

            # 3. Fetch user_roles
            user_roles_res = client.table("user_roles").select("user_id, role_id, is_active").execute()
            role_by_user_id: Dict[str, str] = {}
            for ur in (user_roles_res.data or []):
                if ur.get("is_active", True):
                    uid = str(ur["user_id"])
                    rid = str(ur.get("role_id") or "")
                    role_by_user_id[uid] = roles_map.get(rid, "ASE")

            # 4. Fetch depots & headquarters map
            depots_res = client.table("depots").select("depot_id, name, headquarters_id").execute()
            depots_map = {str(d["depot_id"]): d for d in (depots_res.data or []) if d.get("depot_id")}

            hq_res = client.table("headquarters").select("headquarters_id, name").execute()
            hq_map = {str(h["headquarters_id"]): h.get("name", "Unassigned") for h in (hq_res.data or []) if h.get("headquarters_id")}

            # 5. Fetch user_depot mapping
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

            # 6. Build final list
            user_dict_by_id = {str(u["user_id"]): u for u in raw_users}
            result = []
            for u in raw_users:
                uid = str(u["user_id"])
                first_name = u.get("first_name") or ""
                last_name = u.get("last_name") or ""
                full_name = f"{first_name} {last_name}".strip() or u.get("email") or "Unnamed User"

                manager_id = u.get("manager_id")
                manager_name = "Unassigned"
                if manager_id and str(manager_id) in user_dict_by_id:
                    mgr_obj = user_dict_by_id[str(manager_id)]
                    mgr_fn = mgr_obj.get("first_name") or ""
                    mgr_ln = mgr_obj.get("last_name") or ""
                    manager_name = f"{mgr_fn} {mgr_ln}".strip() or "Unassigned"

                ud_data = user_depot_info.get(uid, {})
                depot_name = ud_data.get("depot_name", "Unassigned")
                headquarters = ud_data.get("headquarters", "Unassigned")
                circle_name = ud_data.get("circle_name", "Unassigned")

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
                    "headquarters": headquarters,
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
        """Resolve role_id (UUID) from public.roles, restricting automatic creation."""
        try:
            res = client.table("roles").select("role_id").ilike("role_name", role_name.strip()).limit(1).execute()
            if res.data and len(res.data) > 0:
                return str(res.data[0]["role_id"])
            logger.warning(f"Role '{role_name}' does not exist in the database. Rejecting automatic creation.")
            return None
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

        return None

    def _resolve_manager_user_id(self, client: Any, mgr_str: str) -> Optional[str]:
        """Resolve manager user_id (UUID) from public.users by UUID, email, full name, or first name."""
        if not mgr_str or str(mgr_str).strip().lower() in ("unassigned", "none", "null", ""):
            return None
        mgr_clean = str(mgr_str).strip()

        # 1. Check if UUID
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

        # 3. Check by name (First/Last or First name)
        try:
            parts = mgr_clean.split()
            first = parts[0]
            if len(parts) > 1:
                last = parts[1]
                res = client.table("users").select("user_id").ilike("first_name", first).ilike("last_name", last).limit(1).execute()
                if res.data:
                    return str(res.data[0]["user_id"])

            res = client.table("users").select("user_id").ilike("first_name", first).limit(1).execute()
            if res.data:
                return str(res.data[0]["user_id"])
        except Exception as e:
            logger.warning(f"Failed to resolve manager '{mgr_clean}': {e}")

        return None

    def create_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        client = get_supabase()

        first_name = payload.get("first_name") or payload.get("firstName") or ""
        last_name = payload.get("last_name") or payload.get("lastName") or ""
        if not first_name and payload.get("name"):
            parts = payload["name"].split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        email = payload.get("email") or f"{first_name.lower().replace(' ', '')}.{last_name.lower().replace(' ', '')}@rll.com"
        phone = payload.get("phone") or payload.get("phoneNumber") or ""
        role_name = payload.get("role") or "Territory Executive"
        reporting_manager = payload.get("reportingManager") or payload.get("reporting_manager") or ""
        depot_name = payload.get("depotName") or payload.get("depot_name") or "Unassigned"
        headquarters = payload.get("headquarters") or "Unassigned"
        is_active = payload.get("is_active", payload.get("isActive", True))

        full_name = f"{first_name} {last_name}".strip()

        # Resolve real user_id from auth.users or public.users if client is available
        user_id = None
        if client:
            user_id = self._resolve_auth_user_id(client, email, first_name, last_name)

        if not user_id:
            user_id = payload.get("id") or payload.get("user_id") or str(uuid.uuid4())

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
            "is_active": is_active
        }

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

        # Resolve manager user_id if reporting_manager provided
        manager_user_id = self._resolve_manager_user_id(client, reporting_manager)
        if manager_user_id:
            user_row["manager_id"] = manager_user_id

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

            # 3. If manager exists and is not self, insert/update public.ase_tsm_mapping
            if manager_user_id and str(manager_user_id) != str(user_id):
                try:
                    mgr_ur_res = client.table("user_roles").select("user_role_id").eq("user_id", manager_user_id).limit(1).execute()
                    mgr_role_id = mgr_ur_res.data[0]["user_role_id"] if mgr_ur_res.data else None

                    existing_map = client.table("ase_tsm_mapping").select("hierarchy_id").eq("ase_user_id", user_id).limit(1).execute()
                    if existing_map.data and len(existing_map.data) > 0:
                        h_id = existing_map.data[0]["hierarchy_id"]
                        client.table("ase_tsm_mapping").update({
                            "tsm_user_id": manager_user_id,
                            "ase_user_role_id": user_role_id,
                            "tsm_user_role_id": mgr_role_id,
                            "is_active": True
                        }).eq("hierarchy_id", h_id).execute()
                    else:
                        client.table("ase_tsm_mapping").insert({
                            "ase_user_id": user_id,
                            "tsm_user_id": manager_user_id,
                            "ase_user_role_id": user_role_id,
                            "tsm_user_role_id": mgr_role_id,
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

        except Exception as e:
            logger.error(f"Error creating user in Supabase: {e}")

        user_record["id"] = user_id
        user_record["user_id"] = user_id
        self.in_memory_users.insert(0, user_record)
        return user_record

    def update_user(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        client = get_supabase()

        first_name = payload.get("first_name") or payload.get("firstName")
        last_name = payload.get("last_name") or payload.get("lastName")
        if not first_name and payload.get("name"):
            parts = payload["name"].split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

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
        if "is_active" in payload or "isActive" in payload:
            user_update["is_active"] = payload.get("is_active", payload.get("isActive"))

        reporting_manager = payload.get("reportingManager") or payload.get("reporting_manager")
        manager_user_id = None
        if reporting_manager:
            if str(reporting_manager).strip().lower() in ("unassigned", "none", "null", ""):
                user_update["manager_id"] = None
            else:
                manager_user_id = self._resolve_manager_user_id(client, reporting_manager)
                if manager_user_id:
                    user_update["manager_id"] = manager_user_id

        try:
            if user_update:
                client.table("users").update(user_update).eq("user_id", user_id).execute()

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

            # Upsert into public.ase_tsm_mapping if manager resolved
            if manager_user_id and str(manager_user_id) != str(user_id):
                try:
                    if not user_role_id:
                        ur_res = client.table("user_roles").select("user_role_id").eq("user_id", user_id).limit(1).execute()
                        user_role_id = ur_res.data[0]["user_role_id"] if ur_res.data else None

                    mgr_ur_res = client.table("user_roles").select("user_role_id").eq("user_id", manager_user_id).limit(1).execute()
                    mgr_ur_id = mgr_ur_res.data[0]["user_role_id"] if mgr_ur_res.data else None

                    existing_map = client.table("ase_tsm_mapping").select("hierarchy_id").eq("ase_user_id", user_id).limit(1).execute()
                    if existing_map.data and len(existing_map.data) > 0:
                        h_id = existing_map.data[0]["hierarchy_id"]
                        client.table("ase_tsm_mapping").update({
                            "tsm_user_id": manager_user_id,
                            "ase_user_role_id": user_role_id,
                            "tsm_user_role_id": mgr_ur_id
                        }).eq("hierarchy_id", h_id).execute()
                    else:
                        client.table("ase_tsm_mapping").insert({
                            "ase_user_id": user_id,
                            "tsm_user_id": manager_user_id,
                            "ase_user_role_id": user_role_id,
                            "tsm_user_role_id": mgr_ur_id
                        }).execute()
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

        except Exception as e:
            logger.error(f"Error updating user {user_id} in Supabase: {e}")

        # Return refreshed user record
        all_users = self.list_users()
        for u in all_users:
            if u.get("id") == user_id or u.get("user_id") == user_id:
                return u
        return payload

    def delete_user(self, user_id: str) -> bool:
        client = get_supabase()
        
        # Always remove from in-memory cache
        self.in_memory_users = [u for u in self.in_memory_users if u.get("id") != user_id and u.get("user_id") != user_id]

        if not client:
            return True

        try:
            try:
                client.table("ase_tsm_mapping").delete().or_(f"ase_user_id.eq.{user_id},tsm_user_id.eq.{user_id}").execute()
            except Exception as e:
                logger.warning(f"Could not delete ase_tsm_mapping for {user_id}: {e}")

            try:
                client.table("user_roles").delete().eq("user_id", user_id).execute()
            except Exception as e:
                logger.warning(f"Could not delete user_roles for {user_id}: {e}")

            try:
                client.table("users").update({"is_active": False}).eq("user_id", user_id).execute()
            except Exception as e:
                client.table("users").delete().eq("user_id", user_id).execute()

            return True
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return True

    def process_excel_roster(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Parses uploaded Excel roster and maps data using a 2-pass pipeline:
        Pass 1: Insert/Upsert users into public.users and public.user_roles
        Pass 2: Resolve reporting managers and map hierarchy into public.ase_tsm_mapping
        """
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
                    parts = raw_name.split(" ", 1)
                    fn = parts[0]
                    ln = parts[1] if len(parts) > 1 else ""

            if not fn or fn.lower() in ("nan", "none", "null", ""):
                continue

            email_val = str(row[email_col]).strip() if email_col and pd.notna(row[email_col]) else f"{fn.lower().replace(' ', '')}.{ln.lower().replace(' ', '')}@rll.com"
            
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

            role_val = str(row[role_col]).strip() if role_col and pd.notna(row[role_col]) else "Territory Executive"
            manager_val = str(row[manager_col]).strip() if manager_col and pd.notna(row[manager_col]) else "Unassigned"
            depot_val = str(row[depot_col]).strip() if depot_col and pd.notna(row[depot_col]) else "Unassigned"
            hq_val = str(row[hq_col]).strip() if hq_col and pd.notna(row[hq_col]) else "Unassigned"

            payload = {
                "first_name": fn,
                "last_name": ln,
                "email": email_val,
                "phone": phone_val,
                "role": role_val,
                "reporting_manager": "Unassigned",  # Will map in Pass 2
                "depot_name": depot_val,
                "headquarters": hq_val,
                "is_active": True
            }

            res = self.create_user(payload)
            if res:
                imported_count += 1
                pass1_records.append({
                    "user": res,
                    "target_manager": manager_val
                })

        # PASS 2: Establish Hierarchy Mappings in public.ase_tsm_mapping and update manager_id
        for rec in pass1_records:
            mgr_target = rec["target_manager"]
            if not mgr_target or mgr_target.lower() in ("unassigned", "none", "", "nan"):
                continue

            user_obj = rec["user"]
            u_id = user_obj.get("user_id") or user_obj.get("id")

            # Update manager hierarchy and trigger public.ase_tsm_mapping update
            self.update_user(u_id, {"reporting_manager": mgr_target})

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
                        "ase_user_role_id": ase_ur_id,
                        "tsm_user_role_id": tsm_ur_id
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

    def create_role(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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
            
        ins = client.table("roles").insert({
            "role_name": role_name,
            "description": description or f"{role_name} Role",
            "is_active": is_active
        }).execute()
        
        if ins.data:
            r = ins.data[0]
            return {
                "role_id": str(r["role_id"]),
                "role_name": r["role_name"],
                "description": r.get("description"),
                "is_active": r.get("is_active", True)
            }
        return payload

    def update_role(self, role_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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

