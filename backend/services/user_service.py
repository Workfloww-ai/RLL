import uuid
import logging
import io
from typing import List, Dict, Any, Optional
import pandas as pd
from backend.db.client import get_supabase

from backend.core.security import MOCK_USERS

logger = logging.getLogger(__name__)

# Fallback seed data in case Supabase is offline or empty
FALLBACK_USERS: List[Dict[str, Any]] = []


class UserService:
    def __init__(self):
        self.in_memory_users = list(FALLBACK_USERS)

    def list_users(self) -> List[Dict[str, Any]]:
        """
        Fetch users by joining the 3 main tables:
        1. public.users
        2. public.user_roles + public.roles
        3. public.ase_tsm_mapping (reporting manager mapping)
        plus depots/headquarters if available.
        """
        client = get_supabase()
        if not client:
            return self.in_memory_users

        try:
            # 1. Fetch all users from public.users
            users_res = client.table("users").select("*").execute()
            raw_users = users_res.data if users_res.data is not None else []

            if not raw_users:
                return self.in_memory_users

            # 2. Fetch user roles joined with roles table (public.user_roles + public.roles)
            user_roles_res = client.table("user_roles").select("user_role_id, user_id, role_id, is_active, roles(role_id, role_name)").execute()
            user_roles_data = user_roles_res.data or []

            # Map user_id -> role_name & user_role_id
            role_by_user_id: Dict[str, str] = {}
            user_role_id_by_user: Dict[str, int] = {}
            for ur in user_roles_data:
                u_id = str(ur.get("user_id"))
                ur_id = ur.get("user_role_id")
                role_obj = ur.get("roles") or {}
                role_name = role_obj.get("role_name") or "Territory Executive"
                if ur.get("is_active", True):
                    role_by_user_id[u_id] = role_name
                    if ur_id:
                        user_role_id_by_user[u_id] = ur_id

            # 3. Fetch reporting manager hierarchy from public.ase_tsm_mapping
            mapping_res = client.table("ase_tsm_mapping").select("*").execute()
            mapping_data = mapping_res.data or []

            # Map ase_user_id -> tsm_user_id
            ase_to_tsm: Dict[str, str] = {}
            for m in mapping_data:
                ase_id = str(m.get("ase_user_id"))
                tsm_id = str(m.get("tsm_user_id"))
                ase_to_tsm[ase_id] = tsm_id

            # 4. Fetch depots and user_depot assignments
            depot_by_user: Dict[str, Dict[str, str]] = {}
            try:
                user_depot_res = client.table("user_depot").select("user_id, depot_id, depots(depot_id, name, headquarters(name))").execute()
                for ud in user_depot_res.data or []:
                    u_id = str(ud.get("user_id"))
                    dep_obj = ud.get("depots") or {}
                    dep_name = dep_obj.get("name") or "Unassigned"
                    hq_obj = dep_obj.get("headquarters") or {}
                    hq_name = hq_obj.get("name") or "Unassigned" if isinstance(hq_obj, dict) else "Unassigned"
                    depot_by_user[u_id] = {"depot_name": dep_name, "headquarters": hq_name}
            except Exception as d_err:
                logger.warning(f"Could not fetch user_depot mappings: {d_err}")

            # Map user_id -> user_dict for quick name lookup
            user_dict_by_id = {str(u["user_id"]): u for u in raw_users}

            result = []
            for u in raw_users:
                uid = str(u["user_id"])
                first_name = u.get("first_name") or ""
                last_name = u.get("last_name") or ""
                full_name = f"{first_name} {last_name}".strip() or "Unnamed User"

                # Manager resolution: check manager_id or ase_tsm_mapping
                manager_id = u.get("manager_id") or ase_to_tsm.get(uid)
                manager_name = "Unassigned"
                if manager_id and str(manager_id) in user_dict_by_id:
                    mgr_obj = user_dict_by_id[str(manager_id)]
                    mgr_fn = mgr_obj.get("first_name") or ""
                    mgr_ln = mgr_obj.get("last_name") or ""
                    manager_name = f"{mgr_fn} {mgr_ln}".strip() or "Unassigned"

                depot_info = depot_by_user.get(uid, {"depot_name": "Unassigned", "headquarters": "Unassigned"})

                result.append({
                    "id": uid,
                    "user_id": uid,
                    "first_name": first_name,
                    "last_name": last_name,
                    "name": full_name,
                    "email": u.get("email", ""),
                    "phone": u.get("phone", ""),
                    "phoneNumber": u.get("phone", ""),
                    "role": role_by_user_id.get(uid, "Territory Executive"),
                    "reportingManager": manager_name,
                    "reporting_manager": manager_name,
                    "manager_id": str(manager_id) if manager_id else None,
                    "depotName": depot_info["depot_name"],
                    "depot_name": depot_info["depot_name"],
                    "headquarters": depot_info["headquarters"],
                    "circleName": "Unassigned",
                    "isActive": u.get("is_active", True),
                    "is_active": u.get("is_active", True)
                })

            return result if result else self.in_memory_users
        except Exception as e:
            logger.error(f"Error fetching users from Supabase: {e}")
            return self.in_memory_users

    def _resolve_role_id(self, client: Any, role_name: str) -> int:
        """Resolve role_id from public.roles, inserting if absent."""
        try:
            res = client.table("roles").select("role_id").ilike("role_name", role_name.strip()).limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["role_id"]
            ins = client.table("roles").insert({"role_name": role_name.strip(), "is_active": True}).execute()
            if ins.data:
                return ins.data[0]["role_id"]
        except Exception as e:
            logger.warning(f"Failed to resolve role_id for '{role_name}': {e}")
        return 1

    def _resolve_auth_user_id(self, client: Any, email: str, first_name: str, last_name: str) -> Optional[str]:
        """Find or create user in Supabase auth.users to ensure users_user_id_fkey is satisfied."""
        email_clean = email.strip().lower()

        # 1. Check if user already exists in public.users
        try:
            res = client.table("users").select("user_id").ilike("email", email_clean).limit(1).execute()
            if res.data and len(res.data) > 0:
                return str(res.data[0]["user_id"])
        except Exception as e:
            logger.warning(f"Error checking existing user in public.users: {e}")

        # 2. Try creating user via Supabase Auth Admin API
        try:
            auth_user = client.auth.admin.create_user({
                "email": email_clean,
                "password": "TempPassword123!",
                "email_confirm": True,
                "user_metadata": {"first_name": first_name, "last_name": last_name}
            })
            if auth_user and hasattr(auth_user, 'user') and auth_user.user:
                return str(auth_user.user.id)
            elif isinstance(auth_user, dict) and "id" in auth_user:
                return str(auth_user["id"])
        except Exception as create_err:
            logger.info(f"Auth admin create_user notice for '{email_clean}': {create_err}")

        # 3. If user is already registered in auth.users, search auth.users list
        try:
            users_list = client.auth.admin.list_users()
            user_items = getattr(users_list, 'users', users_list if isinstance(users_list, list) else [])
            for u in user_items:
                u_email = getattr(u, 'email', None) or (u.get('email') if isinstance(u, dict) else '')
                if u_email and u_email.strip().lower() == email_clean:
                    uid = getattr(u, 'id', None) or (u.get('id') if isinstance(u, dict) else None)
                    if uid:
                        return str(uid)
        except Exception as list_err:
            logger.warning(f"Could not list auth.users to find id for '{email_clean}': {list_err}")

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
        manager_user_id = None
        if reporting_manager and reporting_manager != "Unassigned":
            try:
                mgr_first = reporting_manager.split()[0]
                mgr_res = client.table("users").select("user_id").or_(f"email.ilike.{reporting_manager},first_name.ilike.{mgr_first}").limit(1).execute()
                if mgr_res.data:
                    manager_user_id = mgr_res.data[0]["user_id"]
                    user_row["manager_id"] = manager_user_id
            except Exception as e:
                logger.warning(f"Could not resolve manager '{reporting_manager}': {e}")

        try:
            # 1. Upsert into public.users
            client.table("users").upsert(user_row).execute()

            # 2. Insert/Update public.user_roles
            role_id = self._resolve_role_id(client, role_name)
            user_role_id = None
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
                            "tsm_user_role_id": mgr_role_id
                        }).eq("hierarchy_id", h_id).execute()
                    else:
                        client.table("ase_tsm_mapping").insert({
                            "ase_user_id": user_id,
                            "tsm_user_id": manager_user_id,
                            "ase_user_role_id": user_role_id,
                            "tsm_user_role_id": mgr_role_id
                        }).execute()
                except Exception as e:
                    logger.warning(f"Could not update ase_tsm_mapping: {e}")

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
        if reporting_manager and reporting_manager != "Unassigned":
            try:
                mgr_first = reporting_manager.split()[0]
                mgr_res = client.table("users").select("user_id").or_(f"email.ilike.{reporting_manager},first_name.ilike.{mgr_first}").limit(1).execute()
                if mgr_res.data:
                    manager_user_id = mgr_res.data[0]["user_id"]
                    user_update["manager_id"] = manager_user_id
            except Exception as e:
                logger.warning(f"Could not resolve manager '{reporting_manager}': {e}")

        try:
            if user_update:
                client.table("users").update(user_update).eq("user_id", user_id).execute()

            role_name = payload.get("role")
            user_role_id = None
            if role_name:
                role_id = self._resolve_role_id(client, role_name)
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
                sheets_to_try = [pd.read_csv(io.BytesIO(file_content), header=None)]
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


user_service = UserService()

