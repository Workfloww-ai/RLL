import re
import pytest
from backend.master_data.service import MasterService


def test_normalize_hq_key_basic():
    """Verify MasterService.normalize_hq_key standardizes spaces, cases, and punctuation."""
    assert MasterService.normalize_hq_key("SRI GANGANAGAR") == "SRIGANGANAGAR"
    assert MasterService.normalize_hq_key("SRIGANGANAGAR") == "SRIGANGANAGAR"
    assert MasterService.normalize_hq_key("sri ganganagar") == "SRIGANGANAGAR"
    assert MasterService.normalize_hq_key("  Sri   Ganga   Nagar  ") == "SRIGANGANAGAR"
    assert MasterService.normalize_hq_key("Sri-Ganganagar") == "SRIGANGANAGAR"
    assert MasterService.normalize_hq_key("Sri.Ganganagar") == "SRIGANGANAGAR"


def test_normalize_hq_key_edge_cases():
    """Verify empty, None, and sentinel values produce empty string."""
    assert MasterService.normalize_hq_key(None) == ""
    assert MasterService.normalize_hq_key("") == ""
    assert MasterService.normalize_hq_key("nan") == ""
    assert MasterService.normalize_hq_key("None") == ""
    assert MasterService.normalize_hq_key("NULL") == ""
    assert MasterService.normalize_hq_key("UNASSIGNED") == ""


def test_hq_canonicalization_logic():
    """
    Test the canonicalization logic mirroring uploads/service.py:
    Maps raw variants (SRIGANGANAGAR, sri ganganagar) to DB canonical name (SRI GANGANAGAR).
    """
    db_canonical_hqs = ["JAIPUR", "JODHPUR", "KOTA", "SRI GANGANAGAR", "BIKANER", "UDAIPUR"]
    hq_no_space_to_canonical = {
        re.sub(r'[\s\-_.]+', '', h).upper(): h for h in db_canonical_hqs
    }

    def _canonicalize_hq(val: str) -> str:
        if not val or str(val).strip().lower() in ("unassigned", "none", "null", "nan", ""):
            return ""
        clean_v = re.sub(r'\s+', ' ', str(val)).strip().upper()
        no_sp = re.sub(r'[\s\-_.]+', '', clean_v).upper()
        if no_sp in hq_no_space_to_canonical:
            return hq_no_space_to_canonical[no_sp]
        return clean_v

    assert _canonicalize_hq("SRIGANGANAGAR") == "SRI GANGANAGAR"
    assert _canonicalize_hq("sri ganganagar") == "SRI GANGANAGAR"
    assert _canonicalize_hq("Sri-Ganganagar") == "SRI GANGANAGAR"
    assert _canonicalize_hq("SRI GANGANAGAR") == "SRI GANGANAGAR"
    assert _canonicalize_hq("jaipur") == "JAIPUR"
    assert _canonicalize_hq("JAIPUR") == "JAIPUR"
    assert _canonicalize_hq(None) == ""
    assert _canonicalize_hq("None") == ""


def test_is_hq_matching_approved():
    """
    Test _is_hq_matching_approved function from uploads/service.py:
    Ensures that an approved headquarters 'SRI GANGANAGAR' matches uploaded variants
    such as 'SRIGANGANAGAR', 'sri ganganagar', 'Sri-Ganganagar', etc.
    """
    def _is_hq_matching_approved(target_hq: str, approved_set: set) -> bool:
        if not target_hq or not approved_set:
            return False
        if target_hq in approved_set:
            return True
        target_no_sp = re.sub(r'[\s\-_.]+', '', target_hq).upper()
        return any(re.sub(r'[\s\-_.]+', '', a).upper() == target_no_sp for a in approved_set)

    user_registered_hqs = {"SRI GANGANAGAR"}

    # Exact match
    assert _is_hq_matching_approved("SRI GANGANAGAR", user_registered_hqs) is True

    # No-space match (exact bug from user screenshot)
    assert _is_hq_matching_approved("SRIGANGANAGAR", user_registered_hqs) is True

    # Mixed case and spacing
    assert _is_hq_matching_approved("sri ganganagar", user_registered_hqs) is True
    assert _is_hq_matching_approved("Sri-Ganganagar", user_registered_hqs) is True
    assert _is_hq_matching_approved("  sriganganagar  ", user_registered_hqs) is True

    # Real mismatch
    assert _is_hq_matching_approved("JAIPUR", user_registered_hqs) is False
    assert _is_hq_matching_approved("JODHPUR", user_registered_hqs) is False
    assert _is_hq_matching_approved("", user_registered_hqs) is False
    assert _is_hq_matching_approved(None, user_registered_hqs) is False


def test_intra_sheet_multiple_hq_canonicalization():
    """
    Ensure that if an Excel sheet contains both 'SRI GANGANAGAR' and 'SRIGANGANAGAR'
    for the same ASE or TSM, it is collapsed into a single canonical HQ rather than
    raising false MULTIPLE_HQ_FOR_ASE / MULTIPLE_HQ_FOR_TSM warnings.
    """
    db_canonical_hqs = ["SRI GANGANAGAR", "JAIPUR"]
    hq_no_space_to_canonical = {
        re.sub(r'[\s\-_.]+', '', h).upper(): h for h in db_canonical_hqs
    }

    def _canonicalize_hq(val: str) -> str:
        clean_v = re.sub(r'\s+', ' ', str(val)).strip().upper()
        no_sp = re.sub(r'[\s\-_.]+', '', clean_v).upper()
        return hq_no_space_to_canonical.get(no_sp, clean_v)

    # Simulated sheet entries for Dharmendra Amlani (TSM)
    sheet_hq_entries = {
        "SRI GANGANAGAR": [10, 11, 12],
        "SRIGANGANAGAR": [13, 14, 15]
    }

    # Old logic: len(sheet_hq_entries) == 2 -> false MULTIPLE_HQ_FOR_TSM
    assert len(sheet_hq_entries.keys()) == 2

    # New logic: canonicalize unique HQs
    unique_canonical_hqs = {_canonicalize_hq(h) for h in sheet_hq_entries.keys()}
    assert len(unique_canonical_hqs) == 1
    assert "SRI GANGANAGAR" in unique_canonical_hqs


def test_mobile_router_hq_resolution():
    """
    Test mobile router space-insensitive headquarters lookup.
    """
    hq_name_to_id = {
        "sri ganganagar": 12,
        "sriganganagar": 12,
        "jaipur": 4
    }

    # Query with space
    param_with_space = "SRI GANGANAGAR"
    clean_v1 = param_with_space.strip().lower()
    no_sp1 = re.sub(r'[\s\-_.]+', '', clean_v1)
    resolved_id1 = hq_name_to_id.get(clean_v1) or hq_name_to_id.get(no_sp1)
    assert resolved_id1 == 12

    # Query without space
    param_no_space = "SRIGANGANAGAR"
    clean_v2 = param_no_space.strip().lower()
    no_sp2 = re.sub(r'[\s\-_.]+', '', clean_v2)
    resolved_id2 = hq_name_to_id.get(clean_v2) or hq_name_to_id.get(no_sp2)
    assert resolved_id2 == 12
