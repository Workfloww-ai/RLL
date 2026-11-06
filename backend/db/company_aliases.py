from typing import Dict, Any, Optional, Set
import logging
import re
import time
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

# Master Company Aliases Map (lowercased raw/alias name -> canonical display name)
COMPANY_ALIASES: Dict[str, str] = {
    # Rajasthan Liquor Limited / RLL conventions
    "rll": "Rajasthan Liquor Limited",
    "r.l.l.": "Rajasthan Liquor Limited",
    "rajasthan liquor limited": "Rajasthan Liquor Limited",
    "rajasthan liquors limited": "Rajasthan Liquor Limited",
    "rajasthan liquor": "Rajasthan Liquor Limited",
    "rajasthan liquors": "Rajasthan Liquor Limited",
    "rajasthan liquor ltd": "Rajasthan Liquor Limited",
    "rajasthan liquor ltd.": "Rajasthan Liquor Limited",
    "rajasthan liquors ltd": "Rajasthan Liquor Limited",
    "rajasthan liquors ltd.": "Rajasthan Liquor Limited",

    # Diageo conventions
    "diageo": "Diageo",
    "diageo india": "Diageo",
    "united spirits": "Diageo",
    "united spirits limited": "Diageo",
    "usl": "Diageo",

    # Inbrew conventions
    "in brew": "Inbrew",
    "inbrew": "Inbrew",
    "in-brew": "Inbrew",
    "in brew beverages": "Inbrew",
    "inbrew beverages": "Inbrew",

    # William Grants conventions
    "willam grants": "William Grants",
    "william grants": "William Grants",
    "william grants & sons": "William Grants",
    "william grant": "William Grants",
    "willam grant": "William Grants",
}


def normalize_company_name(cname: str) -> str:
    """
    Normalizes company names handling typos, acronyms, and aliases.
    E.g. 'rll', 'rajasthan liquors', 'Rajasthan Liquor Limited' -> 'Rajasthan Liquor Limited'
         'Diageo' -> 'Diageo'
         'Inbrew', 'In brew' -> 'Inbrew'
         'willam grants' -> 'William Grants'
    """
    if not cname:
        return ""

    cleaned = cname.strip()
    lowered = cleaned.lower()

    # 1. Direct dictionary match
    if lowered in COMPANY_ALIASES:
        return COMPANY_ALIASES[lowered]

    # 2. Clean punctuation/extra spaces match
    sanitized = re.sub(r'[\s._\-]+', ' ', lowered).strip()
    if sanitized in COMPANY_ALIASES:
        return COMPANY_ALIASES[sanitized]

    # 3. Heuristic / regex fallback checks
    if "rajasthan" in lowered and "liquor" in lowered:
        return "Rajasthan Liquor Limited"
    if lowered in ("rll", "r.l.l."):
        return "Rajasthan Liquor Limited"
    if "diageo" in lowered:
        return "Diageo"
    if "inbrew" in lowered or ("in" in lowered and "brew" in lowered):
        return "Inbrew"
    if "willam" in lowered and "grant" in lowered:
        return "William Grants"

    return cleaned


# In-memory cached set of pinned company identifiers from DB (Rule 3: explicit columns only)
_PINNED_COMPANIES_CACHE: Dict[str, Any] = {"timestamp": 0.0, "pinned_keys": set()}
_PINNED_CACHE_TTL = 60.0  # 60-second TTL allows DB updates to reflect dynamically


def get_pinned_company_keys() -> Set[str]:
    """
    Fetches pinned company IDs, names, and normalized slugs from public.companies (where is_pinned = true).
    Cached in-memory for 60 seconds so DB changes reflect without requiring server redeployment.
    """
    now = time.time()
    if (
        _PINNED_COMPANIES_CACHE["pinned_keys"]
        and (now - _PINNED_COMPANIES_CACHE["timestamp"]) < _PINNED_CACHE_TTL
    ):
        return _PINNED_COMPANIES_CACHE["pinned_keys"]

    client = get_supabase()
    if not client:
        return _PINNED_COMPANIES_CACHE["pinned_keys"]

    try:
        # Rule 3: Explicit columns only (never SELECT *)
        res = client.table("companies").select("company_id, company_name, is_pinned").eq("is_pinned", True).execute()
        keys: Set[str] = set()
        for row in (res.data or []):
            cid = str(row.get("company_id") or "").strip().lower()
            cname = str(row.get("company_name") or "").strip()
            if cid:
                keys.add(cid)
            if cname:
                keys.add(cname.lower())
                norm = normalize_company_name(cname).lower()
                keys.add(norm)
                keys.add(norm.replace(" ", "-").replace("/", "-"))
                keys.add(cname.lower().replace(" ", "-").replace("/", "-"))

        _PINNED_COMPANIES_CACHE["timestamp"] = now
        _PINNED_COMPANIES_CACHE["pinned_keys"] = keys
        return keys
    except Exception as e:
        logger.warning(f"get_pinned_company_keys DB lookup error: {e}")
        return _PINNED_COMPANIES_CACHE["pinned_keys"]


def is_pinned_company(
    company_name: str,
    norm_key: str = "",
    is_pinned_db: Optional[bool] = None
) -> bool:
    """
    Checks if a company is pinned. 100% database-driven.
    - If is_pinned_db is explicitly passed (e.g. from DB row), uses it directly (0ms).
    - Otherwise, verifies against cached pinned companies from public.companies.
    """
    if is_pinned_db is not None:
        return bool(is_pinned_db)

    pinned_keys = get_pinned_company_keys()
    if not pinned_keys:
        return False

    name_lower = (company_name or "").strip().lower()
    key_lower = (norm_key or "").strip().lower()
    norm_lower = normalize_company_name(company_name).lower() if company_name else ""

    return (
        key_lower in pinned_keys
        or name_lower in pinned_keys
        or norm_lower in pinned_keys
    )


def get_company_aliases() -> Dict[str, str]:
    """
    Fetches all company aliases from public.company_aliases.
    Returns a dictionary mapping norm_key -> company_id.
    """
    client = get_supabase()
    if not client:
        return {}

    try:
        res = client.table("company_aliases").select("norm_key, company_id").execute()
        return {
            str(row["norm_key"]): str(row["company_id"])
            for row in (res.data or [])
            if row.get("norm_key") and row.get("company_id")
        }
    except Exception as e:
        logger.warning(f"get_company_aliases error: {e}")
        return {}


def upsert_company_alias(
    raw_name: str,
    norm_key: str,
    company_id: str,
    source: str = "auto"
) -> bool:
    """
    Inserts a company alias into public.company_aliases.
    If norm_key already exists, ignores or updates it.
    """
    client = get_supabase()
    if not client or not norm_key or not company_id:
        return False

    try:
        payload = {
            "raw_name": raw_name,
            "norm_key": norm_key,
            "company_id": company_id,
            "source": source
        }
        client.table("company_aliases").upsert(payload, on_conflict="norm_key").execute()
        return True
    except Exception as e:
        logger.warning(f"upsert_company_alias error for {raw_name} ({norm_key}): {e}")
        return False

