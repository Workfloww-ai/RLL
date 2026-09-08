from typing import Dict, Any, Optional
import logging
import re
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

    # Diageo / Inbrew conventions
    "diageo/in brew": "Diageo/In brew",
    "diageo/inbrew": "Diageo/In brew",
    "diageo / inbrew": "Diageo/In brew",
    "diageo / in brew": "Diageo/In brew",
    "diageo inbrew": "Diageo/In brew",
    "diageo in brew": "Diageo/In brew",
    "diageo": "Diageo/In brew",
    "in brew": "Diageo/In brew",
    "inbrew": "Diageo/In brew",
    "in-brew": "Diageo/In brew",
    "diageo-inbrew": "Diageo/In brew",
    "diageo-in-brew": "Diageo/In brew",

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
         'Diageo', 'In brew', 'Diageo/In brew' -> 'Diageo/In brew'
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
    if "diageo" in lowered or "inbrew" in lowered or ("in" in lowered and "brew" in lowered):
        return "Diageo/In brew"
    if "willam" in lowered and "grant" in lowered:
        return "William Grants"

    return cleaned


def is_pinned_company(company_name: str, norm_key: str = "") -> bool:
    """
    Checks if a company should be pinned to top in lists (RLL & Diageo/In brew).
    """
    name_upper = (company_name or "").strip().upper()
    key_lower = (norm_key or "").strip().lower()

    pinned_keys = {
        "rll", "rajasthan-liquor-limited", "rajasthan-liquors",
        "diageo-inbrew", "diageo-in-brew", "diageo/in-brew", "diageo/inbrew"
    }
    pinned_names = {
        "RLL", "RAJASTHAN LIQUOR LIMITED", "RAJASTHAN LIQUORS",
        "DIAGEO/IN BREW", "DIAGEO/INBREW", "DIAGEO", "INBREW", "IN BREW"
    }

    return (
        key_lower in pinned_keys
        or name_upper in pinned_names
        or "RAJASTHAN" in name_upper
        or "DIAGEO" in name_upper
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

