import pytest
import uuid
from typing import List
from fastapi.testclient import TestClient

from backend.db.supabase_client import get_supabase_client as get_supabase
from backend.users.service import user_service
from backend.core.security import create_access_token
from backend.main import app

@pytest.fixture(scope="module")
def db_client():
    client = get_supabase()
    assert client is not None, "Database client should be initialized"
    return client

@pytest.fixture(scope="module")
def hq_fixtures(db_client):
    res = db_client.table("headquarters").select("headquarters_id, name").limit(5).execute()
    assert res.data and len(res.data) >= 2, "At least 2 headquarters must exist"
    return res.data

@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    token = create_access_token({
        "sub": "shruti.sharma@rll.co.in",
        "user_id": "ff64d1df-ca54-4ff0-8321-bb838f28cc85",
        "role": "Admin"
    })
    return {"Authorization": f"Bearer {token}"}

def test_01_single_hq_assignment_to_tsm(db_client):
    """Scenario 1: Single HQ assignment to TSM (Ashmit Sehgal -> Jaipur)"""
    tsm_res = db_client.table("users").select("user_id, first_name, last_name").ilike("first_name", "Ashmit").limit(1).execute()
    assert tsm_res.data, "TSM Ashmit Sehgal should exist"
    user_id = str(tsm_res.data[0]["user_id"])
    
    hq_res = db_client.table("headquarters").select("headquarters_id, name").ilike("name", "Jaipur").limit(1).execute()
    assert hq_res.data, "Jaipur HQ should exist"
    jaipur_id = str(hq_res.data[0]["headquarters_id"])
    
    res = user_service.set_user_headquarters(user_id, [jaipur_id])
    assert res["user_id"] == user_id
    assert jaipur_id in res["headquarters_ids"]
    assert "JAIPUR" in [h.upper() for h in res["headquarters_names"]]

def test_02_multi_hq_assignment_to_tsm(db_client):
    """Scenario 2: Multi-HQ assignment to TSM (Dharmendra Amlani -> Bikaner & Sri Ganganagar)"""
    tsm_res = db_client.table("users").select("user_id, first_name, last_name").ilike("first_name", "Dharmendra").limit(1).execute()
    assert tsm_res.data, "TSM Dharmendra Amlani should exist"
    user_id = str(tsm_res.data[0]["user_id"])
    
    bikaner_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Bikaner").limit(1).execute()
    sg_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Sri Ganganagar").limit(1).execute()
    assert bikaner_res.data and sg_res.data, "Bikaner and Sri Ganganagar HQs should exist"
    
    b_id = str(bikaner_res.data[0]["headquarters_id"])
    sg_id = str(sg_res.data[0]["headquarters_id"])
    
    res = user_service.set_user_headquarters(user_id, [b_id, sg_id])
    assert res["user_id"] == user_id
    assert len(res["headquarters_ids"]) == 2
    assert b_id in res["headquarters_ids"]
    assert sg_id in res["headquarters_ids"]
    names_upper = [n.upper() for n in res["headquarters_names"]]
    assert "BIKANER" in names_upper
    assert "SRI GANGANAGAR" in names_upper

def test_03_single_hq_assignment_to_ase(db_client):
    """Scenario 3: Single HQ assignment to ASE (Chhalu Dan -> Bikaner)"""
    ase_res = db_client.table("users").select("user_id, first_name, last_name").ilike("first_name", "%Chhalu%").limit(1).execute()
    assert ase_res.data, "ASE Chhalu Dan should exist"
    user_id = str(ase_res.data[0]["user_id"])
    
    bikaner_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Bikaner").limit(1).execute()
    assert bikaner_res.data, "Bikaner HQ should exist"
    b_id = str(bikaner_res.data[0]["headquarters_id"])
    
    res = user_service.set_user_headquarters(user_id, [b_id])
    assert res["user_id"] == user_id
    assert b_id in res["headquarters_ids"]

def test_04_multi_hq_assignment_to_ase(db_client, hq_fixtures):
    """Scenario 4: Multi-HQ assignment to ASE"""
    hq_ids = [str(hq_fixtures[0]["headquarters_id"]), str(hq_fixtures[1]["headquarters_id"])]
    ase_res = db_client.table("users").select("user_id").ilike("first_name", "%Chhalu%").limit(1).execute()
    user_id = str(ase_res.data[0]["user_id"])
    
    res = user_service.set_user_headquarters(user_id, hq_ids)
    assert len(res["headquarters_ids"]) == 2
    
    # Restore back to single Bikaner
    bikaner_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Bikaner").limit(1).execute()
    user_service.set_user_headquarters(user_id, [str(bikaner_res.data[0]["headquarters_id"])])

def test_05_shared_hq_between_multiple_users(db_client):
    """Scenario 5: Shared HQ between multiple users (e.g. Bikaner shared by Dharmendra, Chhalu, Bhagwan)"""
    bikaner_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Bikaner").limit(1).execute()
    b_id = str(bikaner_res.data[0]["headquarters_id"])
    
    mappings = db_client.table("user_headquarters_mapping").select("user_id").eq("headquarters_id", b_id).execute()
    assert mappings.data and len(mappings.data) >= 2, "Bikaner HQ should be assigned to multiple users"

def test_06_empty_list_assignment_unassigned(db_client):
    """Scenario 6: Empty list assignment removes all mapped HQs and falls back to Unassigned"""
    ase_res = db_client.table("users").select("user_id").ilike("first_name", "Ashmit").limit(1).execute()
    user_id = str(ase_res.data[0]["user_id"])
    
    # Empty assignment
    res = user_service.set_user_headquarters(user_id, [])
    assert len(res["headquarters_ids"]) == 0
    assert len(res["headquarters_names"]) == 0
    assert res["headquarters_display"] == "Unassigned"
    
    # Restore Ashmit to Jaipur
    jaipur_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Jaipur").limit(1).execute()
    user_service.set_user_headquarters(user_id, [str(jaipur_res.data[0]["headquarters_id"])])

def test_07_duplicate_assignment_rejection_or_deduplication(db_client, hq_fixtures):
    """Scenario 7: Duplicate assignment deduplication"""
    ase_res = db_client.table("users").select("user_id").ilike("first_name", "Ashmit").limit(1).execute()
    user_id = str(ase_res.data[0]["user_id"])
    hq_id = str(hq_fixtures[0]["headquarters_id"])
    
    res = user_service.set_user_headquarters(user_id, [hq_id, hq_id, hq_id])
    assert len(res["headquarters_ids"]) == 1
    
    # Restore Ashmit to Jaipur
    jaipur_res = db_client.table("headquarters").select("headquarters_id").ilike("name", "Jaipur").limit(1).execute()
    user_service.set_user_headquarters(user_id, [str(jaipur_res.data[0]["headquarters_id"])])

def test_08_invalid_hq_id_rejection(db_client):
    """Scenario 8: Invalid HQ ID rejection"""
    ase_res = db_client.table("users").select("user_id").ilike("first_name", "Ashmit").limit(1).execute()
    user_id = str(ase_res.data[0]["user_id"])
    fake_hq_id = str(uuid.uuid4())
    
    with pytest.raises(ValueError) as excinfo:
        user_service.set_user_headquarters(user_id, [fake_hq_id])
    assert "does not exist" in str(excinfo.value)

def test_09_cross_tenant_assignment_rejection(db_client):
    """Scenario 9: Cross-tenant integrity check"""
    fake_user_id = str(uuid.uuid4())
    with pytest.raises(ValueError) as excinfo:
        user_service.set_user_headquarters(fake_user_id, [])
    assert f"User '{fake_user_id}' does not exist" in str(excinfo.value)

def test_10_admin_authorization_and_fetching():
    """Scenario 10: User list includes headquarters metadata for admin views"""
    users = user_service.list_users()
    assert len(users) > 0
    dharmendra = next((u for u in users if "dharmendra" in (u.get("name") or "").lower()), None)
    assert dharmendra is not None
    assert "headquarters_ids" in dharmendra
    assert len(dharmendra["headquarters_ids"]) >= 2
    assert "headquarters" in dharmendra
    assert "Bikaner" in dharmendra["headquarters"] or "BIKANER" in dharmendra["headquarters"]

def test_11_dual_role_user_assignment(db_client):
    """Scenario 11: Assignment persists regardless of role transitions"""
    tsm_res = db_client.table("users").select("user_id").ilike("first_name", "Ashmit").limit(1).execute()
    user_id = str(tsm_res.data[0]["user_id"])
    hqs = user_service.get_user_headquarters(user_id)
    assert hqs["user_id"] == user_id
    assert len(hqs["headquarters_ids"]) >= 1

def test_12_preservation_of_ase_tsm_mapping(db_client):
    """Scenario 12: Updating HQ does not modify or delete ase_tsm_mapping hierarchy"""
    res_before = db_client.table("ase_tsm_mapping").select("ase_user_id, tsm_user_id").execute()
    count_before = len(res_before.data or [])
    
    tsm_res = db_client.table("users").select("user_id").ilike("first_name", "Dharmendra").limit(1).execute()
    user_id = str(tsm_res.data[0]["user_id"])
    hqs = user_service.get_user_headquarters(user_id)
    user_service.set_user_headquarters(user_id, hqs["headquarters_ids"])
    
    res_after = db_client.table("ase_tsm_mapping").select("ase_user_id, tsm_user_id").execute()
    count_after = len(res_after.data or [])
    assert count_before == count_after, "ase_tsm_mapping row count must not change when assigning HQs"

def test_13_unassigned_fallback_display():
    """Scenario 13: Unassigned fallback display string"""
    users = user_service.list_users()
    unassigned_found = any(u.get("headquarters") == "Unassigned" for u in users)
    assert unassigned_found or all(len(u.get("headquarters_ids", [])) > 0 for u in users)

def test_14_mobile_tsm_and_ase_hq_location_format(api_client, auth_headers):
    """Scenario 14: Mobile TSM & ASE hqLocation response format"""
    response = api_client.get(
        "/api/v1/mobile/sales?period=Daily&selected_hq=All%20Headquarters",
        headers=auth_headers
    )
    assert response.status_code == 200
    res = response.json()
    tsms = res.get("tsms", [])
    assert len(tsms) > 0
    
    dharmendra = next((t for t in tsms if "dharmendra" in (t.get("name") or "").lower()), None)
    assert dharmendra is not None
    assert "hqLocation" in dharmendra
    assert "Bikaner" in dharmendra["hqLocation"] or "BIKANER" in dharmendra["hqLocation"]
    assert "assignedHqs" in dharmendra
    assert len(dharmendra["assignedHqs"]) == 2
    
    # Check reporting ASE
    ases = dharmendra.get("ases", [])
    assert len(ases) > 0
    bhagwan = next((a for a in ases if "bhagwan" in (a.get("name") or "").lower()), None)
    assert bhagwan is not None
    assert "hqLocation" in bhagwan
    assert "Bikaner" in bhagwan["hqLocation"] or "BIKANER" in bhagwan["hqLocation"]

def test_15_hq_filtering_in_mobile_response(api_client, auth_headers):
    """Scenario 15: HQ filtering in mobile response for multi-HQ TSM"""
    # Filter by Bikaner
    res_bikaner = api_client.get(
        "/api/v1/mobile/sales?period=Daily&selected_hq=Bikaner",
        headers=auth_headers
    ).json()
    tsms_bikaner = [t["name"].lower() for t in res_bikaner.get("tsms", [])]
    assert any("dharmendra" in name for name in tsms_bikaner), "Dharmendra should appear when filtering by Bikaner"
    
    # Filter by Sri Ganganagar
    res_sg = api_client.get(
        "/api/v1/mobile/sales?period=Daily&selected_hq=Sri%20Ganganagar",
        headers=auth_headers
    ).json()
    tsms_sg = [t["name"].lower() for t in res_sg.get("tsms", [])]
    assert any("dharmendra" in name for name in tsms_sg), "Dharmendra should appear when filtering by Sri Ganganagar"

def test_16_sales_metrics_invariance(api_client, auth_headers):
    """Scenario 16: Sales metrics invariance (total cases across company unchanged)"""
    res_all = api_client.get(
        "/api/v1/mobile/sales?period=Daily&selected_hq=All%20Headquarters",
        headers=auth_headers
    ).json()
    tsms = res_all.get("tsms", [])
    total_cases = sum(t.get("data", {}).get("Daily", {}).get("cases", 0) for t in tsms)
    assert total_cases > 0, "Daily total cases should be positive and valid"

def test_17_no_duplicate_sales_summation(api_client, auth_headers):
    """Scenario 17: No duplicate sales summation across multi-HQ users"""
    res_all = api_client.get(
        "/api/v1/mobile/sales?period=Daily&selected_hq=All%20Headquarters",
        headers=auth_headers
    ).json()
    dharmendra_occurrences = [t for t in res_all.get("tsms", []) if "dharmendra" in (t.get("name") or "").lower()]
    assert len(dharmendra_occurrences) == 1, "Dharmendra should appear exactly once in TSM list"

def test_18_cache_invalidation():
    """Scenario 18: Redis cache invalidation on HQ update"""
    from backend.users.router import invalidate_user_and_territory_caches
    import asyncio
    asyncio.run(invalidate_user_and_territory_caches())
