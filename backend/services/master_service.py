import logging
import hashlib
from typing import List, Optional, Dict, Any
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

SEED_DEPOTS = [{"depot_id": 1, "name": "Jaipur Main Depot"}]
SEED_LICENSEES = [{"licensee_id": 1, "licensee_name": "Rajasthan Spirits Licensee 1"}]
SEED_BRANDS = [{"brand_id": 1, "brand_name": "Royal Stag Whisky"}]
SEED_PACKAGINGS = [{"packaging_id": 1, "packing_raw": "750ml Bottle"}]

class MasterService:
    def __init__(self):
        self.depots = SEED_DEPOTS.copy()
        self.licensees = SEED_LICENSEES.copy()
        self.brands = SEED_BRANDS.copy()
        self.packagings = SEED_PACKAGINGS.copy()

        # In-memory lookup caches for ultra-fast lower() matching across 550k+ rows
        self._depot_cache: Dict[str, int] = {}
        self._licensee_cache: Dict[str, int] = {}
        self._brand_cache: Dict[str, int] = {}
        self._packaging_cache: Dict[str, int] = {}

    def resolve_depot_id(self, depot_name: str) -> int:
        clean_name = depot_name.strip()
        lower_key = clean_name.lower()
        if lower_key in self._depot_cache:
            return self._depot_cache[lower_key]

        client = get_supabase()
        if client:
            try:
                # Query exact name to bypass 1,000 PostgREST row limits
                res = client.table("depots").select("depot_id").ilike("name", clean_name).limit(1).execute()
                if res.data and len(res.data) > 0:
                    dep_id = res.data[0]["depot_id"]
                    self._depot_cache[lower_key] = dep_id
                    return dep_id
                
                ins_payload = {
                    "name": clean_name,
                    "is_active": True
                }
                ins_res = client.table("depots").insert(ins_payload).execute()
                if ins_res.data:
                    dep_id = ins_res.data[0]["depot_id"]
                    self._depot_cache[lower_key] = dep_id
                    return dep_id
            except Exception as e:
                pass

        # Local fallback
        for d in self.depots:
            if d.get("name", "").strip().lower() == lower_key:
                self._depot_cache[lower_key] = d["depot_id"]
                return d["depot_id"]
        
        new_id = len(self.depots) + 1
        self.depots.append({"depot_id": new_id, "name": clean_name})
        self._depot_cache[lower_key] = new_id
        return new_id

    def resolve_licensee_id(self, licensee_name: str, depot_id: int = 1) -> int:
        clean_name = licensee_name.strip()
        lower_key = clean_name.lower()
        if lower_key in self._licensee_cache:
            return self._licensee_cache[lower_key]

        client = get_supabase()
        if client:
            try:
                # Query exact licensee_name via ilike to bypass 1,000 PostgREST limit and prevent duplicate key errors
                res = client.table("licensees").select("licensee_id").ilike("licensee_name", clean_name).limit(1).execute()
                if res.data and len(res.data) > 0:
                    lic_id = res.data[0]["licensee_id"]
                    self._licensee_cache[lower_key] = lic_id
                    return lic_id

                ins_payload = {
                    "licensee_name": clean_name,
                    "trade_type": "Off",
                    "group_name": "Indivisual",
                    "is_active": True
                }
                ins_res = client.table("licensees").insert(ins_payload).execute()
                if ins_res.data:
                    lic_id = ins_res.data[0]["licensee_id"]
                    self._licensee_cache[lower_key] = lic_id
                    return lic_id
            except Exception as e:
                pass

        for l in self.licensees:
            if l.get("licensee_name", "").strip().lower() == lower_key:
                self._licensee_cache[lower_key] = l["licensee_id"]
                return l["licensee_id"]

        new_id = len(self.licensees) + 1
        self.licensees.append({"licensee_id": new_id, "licensee_name": clean_name})
        self._licensee_cache[lower_key] = new_id
        return new_id

    def resolve_brand_id(self, brand_name: str) -> int:
        clean_name = brand_name.strip()
        lower_key = clean_name.lower()
        if lower_key in self._brand_cache:
            return self._brand_cache[lower_key]

        client = get_supabase()
        if client:
            try:
                res = client.table("brands").select("brand_id").ilike("brand_name", clean_name).limit(1).execute()
                if res.data and len(res.data) > 0:
                    brd_id = res.data[0]["brand_id"]
                    self._brand_cache[lower_key] = brd_id
                    return brd_id

                ins_payload = {
                    "brand_name": clean_name,
                    "is_active": True
                }
                ins_res = client.table("brands").insert(ins_payload).execute()
                if ins_res.data:
                    brd_id = ins_res.data[0]["brand_id"]
                    self._brand_cache[lower_key] = brd_id
                    return brd_id
            except Exception as e:
                pass

        for b in self.brands:
            if b.get("brand_name", "").strip().lower() == lower_key:
                self._brand_cache[lower_key] = b["brand_id"]
                return b["brand_id"]

        new_id = len(self.brands) + 1
        self.brands.append({"brand_id": new_id, "brand_name": clean_name})
        self._brand_cache[lower_key] = new_id
        return new_id

    def resolve_packaging_id(self, packing_name: str) -> int:
        clean_name = packing_name.strip()
        lower_key = clean_name.lower()
        if lower_key in self._packaging_cache:
            return self._packaging_cache[lower_key]

        client = get_supabase()
        if client:
            try:
                res = client.table("packagings").select("packaging_id").ilike("packing_raw", clean_name).limit(1).execute()
                if res.data and len(res.data) > 0:
                    pkg_id = res.data[0]["packaging_id"]
                    self._packaging_cache[lower_key] = pkg_id
                    return pkg_id

                ins_payload = {
                    "packing_raw": clean_name,
                    "bottle_size_ml": 750,
                    "units_per_case": 12,
                    "is_active": True
                }
                ins_res = client.table("packagings").insert(ins_payload).execute()
                if ins_res.data:
                    pkg_id = ins_res.data[0]["packaging_id"]
                    self._packaging_cache[lower_key] = pkg_id
                    return pkg_id
            except Exception as e:
                pass

        for p in self.packagings:
            if p.get("packing_raw", "").strip().lower() == lower_key:
                self._packaging_cache[lower_key] = p["packaging_id"]
                return p["packaging_id"]

        new_id = len(self.packagings) + 1
        self.packagings.append({"packaging_id": new_id, "packing_raw": clean_name})
        self._packaging_cache[lower_key] = new_id
        return new_id

    def get_headquarters(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("headquarters").select("*").limit(5000).execute()
                if res.data:
                    return res.data
            except Exception as e:
                logger.warning(f"Error fetching headquarters: {e}")
        return [
            {"headquarters_id": 1, "name": "Jaipur North", "is_active": True},
            {"headquarters_id": 2, "name": "Jodhpur West", "is_active": True},
            {"headquarters_id": 3, "name": "Udaipur Central", "is_active": True}
        ]

    def get_depots_with_hq(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                depots_res = client.table("depots").select("*").order("depot_id", desc=False).limit(5000).execute()
                hq_res = client.table("headquarters").select("*").limit(5000).execute()
                
                hq_map = {h["headquarters_id"]: h["name"] for h in (hq_res.data or [])}
                
                result = []
                for d in (depots_res.data or []):
                    d_copy = d.copy()
                    hq_id = d.get("headquarters_id")
                    d_copy["headquarters_name"] = hq_map.get(hq_id, "Unassigned")
                    result.append(d_copy)
                return result
            except Exception as e:
                logger.warning(f"Error fetching depots with HQ: {e}")

        return [
            {"depot_id": 1, "name": "Mansarovar", "headquarters_id": 1, "headquarters_name": "Jaipur North", "is_active": True},
            {"depot_id": 2, "name": "Pal Road", "headquarters_id": 2, "headquarters_name": "Jodhpur West", "is_active": False},
            {"depot_id": 3, "name": "Pratapnagar", "headquarters_id": 3, "headquarters_name": "Udaipur Central", "is_active": True}
        ]

    def update_depot(self, depot_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        client = get_supabase()
        clean_updates = {k: v for k, v in updates.items() if v is not None}
        
        if client:
            try:
                res = client.table("depots").update(clean_updates).eq("depot_id", depot_id).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
            except Exception as e:
                logger.warning(f"Error updating depot {depot_id}: {e}")
        return {"depot_id": depot_id, **clean_updates}

    def delete_depot(self, depot_id: int) -> bool:
        client = get_supabase()
        if client:
            try:
                client.table("depots").delete().eq("depot_id", depot_id).execute()
                return True
            except Exception as e:
                logger.warning(f"Error deleting depot {depot_id}: {e}")
        return True

    def resolve_packing_size_id(self, packing_name: str) -> int:
        return self.resolve_packaging_id(packing_name)

master_service = MasterService()
