import logging
import hashlib
from typing import List, Optional, Dict, Any
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

SEED_OFFICES = [
    {"office_id": 1, "office_code": "JAIPUR_HO", "office_name": "Jaipur Head Office", "state": "Rajasthan"}
]

SEED_CIRCLES = [
    {"circle_id": 1, "office_id": 1, "headquarters_id": None, "circle_code": "JPR_CENTRAL", "circle_name": "Jaipur Central Circle"}
]

SEED_DEPOTS = [
    {"depot_id": 1, "circle_id": 1, "depot_code": "DEP_JPR_01", "depot_name": "Jaipur Main Depot", "address": "Jaipur Industrial Area"}
]

SEED_LICENSEES = [
    {"licensee_id": 1, "depot_id": 1, "license_number": "LIC-2026-001", "licensee_name": "Rajasthan Spirits Licensee 1", "status": "active"}
]

SEED_CATEGORIES = [
    {"packaging_category_id": 1, "category_name": "IMFL", "description": "Indian Made Foreign Liquor"},
    {"packaging_category_id": 2, "category_name": "Beer", "description": "Beer Products"}
]

SEED_BRANDS = [
    {"brand_id": 1, "brand_code": "ROYAL_STAG", "brand_name": "Royal Stag Whisky", "packaging_category_id": 1, "is_trade": True, "is_active": True}
]

SEED_PACKING_SIZES = [
    {"packing_size_id": 1, "packing_name": "750ml Bottle", "volume_ml": 750, "bottles_per_case": 12, "packaging_category_id": 1}
]

class MasterService:
    def __init__(self):
        self.offices = SEED_OFFICES.copy()
        self.circles = SEED_CIRCLES.copy()
        self.depots = SEED_DEPOTS.copy()
        self.licensees = SEED_LICENSEES.copy()
        self.categories = SEED_CATEGORIES.copy()
        self.brands = SEED_BRANDS.copy()
        self.packing_sizes = SEED_PACKING_SIZES.copy()

        # In-memory lookup caches for ultra-fast lower() matching
        self._depot_cache: Dict[str, int] = {}
        self._licensee_cache: Dict[str, int] = {}
        self._brand_cache: Dict[str, int] = {}
        self._packing_cache: Dict[str, int] = {}

    def get_offices(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("offices").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.offices

    def get_circles(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("circles").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.circles

    def get_depots(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("depots").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.depots

    def get_licensees(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("licensees").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.licensees

    def get_brands(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("brands").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.brands

    def get_packing_sizes(self) -> List[Dict[str, Any]]:
        client = get_supabase()
        if client:
            try:
                res = client.table("packing_sizes").select("*").execute()
                if res.data:
                    return res.data
            except Exception:
                pass
        return self.packing_sizes

    def resolve_depot_id(self, depot_name: str) -> int:
        clean_name = depot_name.strip().lower()
        if clean_name in self._depot_cache:
            return self._depot_cache[clean_name]

        client = get_supabase()
        if client:
            try:
                res = client.table("depots").select("*").execute()
                for d in res.data:
                    if d.get("depot_name", "").strip().lower() == clean_name or d.get("depot_code", "").strip().lower() == clean_name:
                        self._depot_cache[clean_name] = d["depot_id"]
                        return d["depot_id"]
                
                # Insert missing depot to Supabase
                short_code = "DEP_" + hashlib.md5(clean_name.encode()).hexdigest()[:6].upper()
                ins_payload = {
                    "circle_id": 1,
                    "depot_code": short_code,
                    "depot_name": depot_name.strip(),
                    "address": None
                }
                ins_res = client.table("depots").insert(ins_payload).execute()
                if ins_res.data:
                    dep_id = ins_res.data[0]["depot_id"]
                    self._depot_cache[clean_name] = dep_id
                    return dep_id
            except Exception as e:
                logger.warning(f"Supabase depot resolution notice: {e}")

        # Fallback local
        for d in self.depots:
            if d.get("depot_name", "").strip().lower() == clean_name:
                self._depot_cache[clean_name] = d["depot_id"]
                return d["depot_id"]
        
        new_id = len(self.depots) + 1
        self.depots.append({"depot_id": new_id, "circle_id": 1, "depot_code": f"DEP_{new_id}", "depot_name": depot_name.strip()})
        self._depot_cache[clean_name] = new_id
        return new_id

    def resolve_licensee_id(self, licensee_name: str, depot_id: int) -> int:
        clean_name = licensee_name.strip().lower()
        if clean_name in self._licensee_cache:
            return self._licensee_cache[clean_name]

        client = get_supabase()
        if client:
            try:
                res = client.table("licensees").select("*").execute()
                for l in res.data:
                    if l.get("licensee_name", "").strip().lower() == clean_name or l.get("license_number", "").strip().lower() == clean_name:
                        self._licensee_cache[clean_name] = l["licensee_id"]
                        return l["licensee_id"]

                short_lic = "LIC-" + hashlib.md5(clean_name.encode()).hexdigest()[:8].upper()
                ins_payload = {
                    "depot_id": depot_id,
                    "license_number": short_lic,
                    "licensee_name": licensee_name.strip(),
                    "status": "active"
                }
                ins_res = client.table("licensees").insert(ins_payload).execute()
                if ins_res.data:
                    lic_id = ins_res.data[0]["licensee_id"]
                    self._licensee_cache[clean_name] = lic_id
                    return lic_id
            except Exception as e:
                logger.warning(f"Supabase licensee resolution notice: {e}")

        for l in self.licensees:
            if l.get("licensee_name", "").strip().lower() == clean_name:
                self._licensee_cache[clean_name] = l["licensee_id"]
                return l["licensee_id"]

        new_id = len(self.licensees) + 1
        self.licensees.append({"licensee_id": new_id, "depot_id": depot_id, "license_number": f"LIC-{new_id}", "licensee_name": licensee_name.strip()})
        self._licensee_cache[clean_name] = new_id
        return new_id

    def resolve_brand_id(self, brand_name: str) -> int:
        clean_name = brand_name.strip().lower()
        if clean_name in self._brand_cache:
            return self._brand_cache[clean_name]

        client = get_supabase()
        if client:
            try:
                res = client.table("brands").select("*").execute()
                for b in res.data:
                    if b.get("brand_name", "").strip().lower() == clean_name or b.get("brand_code", "").strip().lower() == clean_name:
                        self._brand_cache[clean_name] = b["brand_id"]
                        return b["brand_id"]

                short_code = "BRD_" + hashlib.md5(clean_name.encode()).hexdigest()[:6].upper()
                ins_payload = {
                    "brand_code": short_code,
                    "brand_name": brand_name.strip(),
                    "packaging_category_id": 1,
                    "is_trade": True,
                    "is_active": True
                }
                ins_res = client.table("brands").insert(ins_payload).execute()
                if ins_res.data:
                    brd_id = ins_res.data[0]["brand_id"]
                    self._brand_cache[clean_name] = brd_id
                    return brd_id
            except Exception as e:
                logger.warning(f"Supabase brand resolution notice: {e}")

        for b in self.brands:
            if b.get("brand_name", "").strip().lower() == clean_name:
                self._brand_cache[clean_name] = b["brand_id"]
                return b["brand_id"]

        new_id = len(self.brands) + 1
        self.brands.append({"brand_id": new_id, "brand_code": f"BRD_{new_id}", "brand_name": brand_name.strip()})
        self._brand_cache[clean_name] = new_id
        return new_id

    def resolve_packing_size_id(self, packing_name: str) -> int:
        clean_name = packing_name.strip().lower()
        if clean_name in self._packing_cache:
            return self._packing_cache[clean_name]

        client = get_supabase()
        if client:
            try:
                res = client.table("packing_sizes").select("*").execute()
                for p in res.data:
                    if p.get("packing_name", "").strip().lower() == clean_name:
                        self._packing_cache[clean_name] = p["packing_size_id"]
                        return p["packing_size_id"]

                ins_payload = {
                    "packing_name": packing_name.strip(),
                    "volume_ml": 750,
                    "bottles_per_case": 12,
                    "packaging_category_id": 1
                }
                ins_res = client.table("packing_sizes").insert(ins_payload).execute()
                if ins_res.data:
                    pkg_id = ins_res.data[0]["packing_size_id"]
                    self._packing_cache[clean_name] = pkg_id
                    return pkg_id
            except Exception as e:
                logger.warning(f"Supabase packing size resolution notice: {e}")

        for p in self.packing_sizes:
            if p.get("packing_name", "").strip().lower() == clean_name:
                self._packing_cache[clean_name] = p["packing_size_id"]
                return p["packing_size_id"]

        new_id = len(self.packing_sizes) + 1
        self.packing_sizes.append({"packing_size_id": new_id, "packing_name": packing_name.strip()})
        self._packing_cache[clean_name] = new_id
        return new_id

master_service = MasterService()
