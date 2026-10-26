import pytest
import uuid
from typing import List

from backend.db.supabase_client import get_supabase_client as get_supabase
from backend.users.service import user_service


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
def temp_test_user(db_client):
    """
    Creates an isolated ephemeral test user so real users in the database
    (such as Chhalu Dan Charan, Dharmendra Amlani, etc.) are NEVER mutated by tests.
    """
    user_id = str(uuid.uuid4())
    temp_email = f"test.hq.ephemeral.{uuid.uuid4().hex[:8]}@rll.test"
    db_client.table("users").insert({
        "user_id": user_id,
        "email": temp_email,
        "first_name": "TestHQ",
        "last_name": "MockUser",
        "is_active": True,
        "tenant_id": "a0000000-0000-0000-0000-000000000001"
    }).execute()

    # Assign role ASE
    try:
        r_res = db_client.table("roles").select("role_id").eq("role_name", "ASE").limit(1).execute()
        if r_res.data:
            db_client.table("user_roles").insert({
                "user_id": user_id,
                "role_id": r_res.data[0]["role_id"],
                "is_active": True
            }).execute()
    except Exception:
        pass

    yield user_id

    # Cleanup after test module completes
    try:
        db_client.table("user_headquarters_mapping").delete().eq("user_id", user_id).execute()
        db_client.table("user_roles").delete().eq("user_id", user_id).execute()
        db_client.table("users").delete().eq("user_id", user_id).execute()
    except Exception:
        pass


def test_01_single_hq_assignment(temp_test_user, hq_fixtures):
    """Scenario 1: Single HQ assignment to user"""
    hq_id = str(hq_fixtures[0]["headquarters_id"])
    res = user_service.set_user_headquarters(temp_test_user, [hq_id])
    assert res["user_id"] == temp_test_user
    assert res["headquarters_ids"] == [hq_id]


def test_02_enforce_strictly_one_hq_for_ase_tsm(temp_test_user, hq_fixtures):
    """
    Scenario 2: Strict business rule - ASE and TSM must have at most 1 HQ.
    When multiple HQs are provided, the service enforces strictly 1 HQ.
    """
    hq1 = str(hq_fixtures[0]["headquarters_id"])
    hq2 = str(hq_fixtures[1]["headquarters_id"])
    res = user_service.set_user_headquarters(temp_test_user, [hq1, hq2])
    assert res["user_id"] == temp_test_user
    assert len(res["headquarters_ids"]) == 1
    assert res["headquarters_ids"] == [hq2]


def test_03_empty_list_assignment_unassigned(temp_test_user):
    """Scenario 3: Empty list assignment clears HQs and returns Unassigned"""
    res = user_service.set_user_headquarters(temp_test_user, [])
    assert len(res["headquarters_ids"]) == 0
    assert len(res["headquarters_names"]) == 0
    assert res["headquarters_display"] == "Unassigned"


def test_04_duplicate_assignment_deduplication(temp_test_user, hq_fixtures):
    """Scenario 4: Duplicate assignment deduplication"""
    hq_id = str(hq_fixtures[0]["headquarters_id"])
    res = user_service.set_user_headquarters(temp_test_user, [hq_id, hq_id, hq_id])
    assert len(res["headquarters_ids"]) == 1
    assert res["headquarters_ids"] == [hq_id]


def test_05_invalid_hq_id_rejection(temp_test_user):
    """Scenario 5: Invalid HQ ID rejection"""
    fake_hq_id = str(uuid.uuid4())
    with pytest.raises(ValueError) as excinfo:
        user_service.set_user_headquarters(temp_test_user, [fake_hq_id])
    assert "does not exist" in str(excinfo.value)


def test_06_nonexistent_user_rejection():
    """Scenario 6: Nonexistent user rejection"""
    fake_user_id = str(uuid.uuid4())
    with pytest.raises(ValueError) as excinfo:
        user_service.set_user_headquarters(fake_user_id, [])
    assert f"User '{fake_user_id}' does not exist" in str(excinfo.value)
