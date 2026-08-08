import pytest
import io
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.user_service import user_service

client = TestClient(app)

def test_list_users_api():
    created = user_service.create_user({
        "first_name": "Test",
        "last_name": "User",
        "email": "test.user@rll.com",
        "role": "Territory Executive",
        "is_active": True
    })
    try:
        response = client.get("/api/v1/users/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "role" in data[0]
        assert "reportingManager" in data[0]
    finally:
        u_id = created.get("user_id") or created.get("id")
        if u_id:
            user_service.delete_user(u_id)

def test_create_and_delete_user():
    new_user_payload = {
        "first_name": "Amit",
        "last_name": "Kumar",
        "email": "amit.kumar@rll.com",
        "phone": "+91 9988776655",
        "role": "Area Sales Manager",
        "reporting_manager": "Rahul Sharma",
        "depot_name": "Jaipur Main Depot",
        "is_active": True
    }
    create_res = client.post("/api/v1/users/", json=new_user_payload)
    assert create_res.status_code == 200
    created_user = create_res.json()
    assert created_user["email"] == "amit.kumar@rll.com"
    user_id = created_user["id"]

    # Delete created user
    del_res = client.delete(f"/api/v1/users/{user_id}")
    assert del_res.status_code == 200

def test_upload_excel_roster():
    # Create sample in-memory Excel file
    df = pd.DataFrame([
        {
            "First Name": "Rohan",
            "Last Name": "Mehta",
            "Email": "rohan.mehta@rll.com",
            "Phone": "+91 9123456789",
            "Role": "Territory Executive",
            "Reporting Manager": "Rahul Sharma",
            "Depot": "Mansarovar",
            "HQ": "Jaipur North"
        },
        {
            "First Name": "Suresh",
            "Last Name": "Verma",
            "Email": "suresh.verma@rll.com",
            "Phone": "+91 9876123456",
            "Role": "Area Sales Manager",
            "Reporting Manager": "Arun K. Verma",
            "Depot": "Pal Road",
            "HQ": "Jodhpur West"
        }
    ])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    response = client.post(
        "/api/v1/users/upload-roster",
        files={"file": ("roster_test.xlsx", output, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "success"
    assert result["imported_count"] == 2
    assert "users, user_roles, and ase_tsm_mapping" in result["message"]

    # Cleanup test roster users from DB
    try:
        all_u = user_service.list_users()
        for u in all_u:
            if u.get("email") in ("rohan.mehta@rll.com", "suresh.verma@rll.com"):
                user_service.delete_user(u["id"])
    except Exception:
        pass

def test_list_roles_api():
    response = client.get("/api/v1/users/roles")
    assert response.status_code == 200
    roles = response.json()
    assert isinstance(roles, list)
    assert len(roles) >= 3
    role_names = [r.get("role_name") for r in roles]
    assert any(rn in role_names for rn in ["ASE", "TSM", "Area Sales Executive", "Territory Sales Manager"])

def test_user_hierarchy_api():
    response = client.get("/api/v1/users/hierarchy")
    assert response.status_code == 200
    hierarchy = response.json()
    assert isinstance(hierarchy, list)

def test_user_roles_and_ase_tsm_mapping_connection():
    # 1. Create TSM User
    tsm_user = user_service.create_user({
        "first_name": "Rajesh",
        "last_name": "Sharma",
        "email": "rajesh.tsm@rll.com",
        "phone": "+91 9811122233",
        "role": "TSM",
        "is_active": True
    })
    tsm_id = tsm_user.get("user_id") or tsm_user.get("id")

    # 2. Create ASE User assigned to TSM
    ase_user = user_service.create_user({
        "first_name": "Vikas",
        "last_name": "Singh",
        "email": "vikas.ase@rll.com",
        "phone": "+91 9844455566",
        "role": "ASE",
        "reporting_manager": "Rajesh Sharma",
        "is_active": True
    })
    ase_id = ase_user.get("user_id") or ase_user.get("id")

    try:
        users = user_service.list_users()
        created_ase = next((u for u in users if u["id"] == ase_id), None)
        assert created_ase is not None
        assert created_ase["reportingManager"] == "Rajesh Sharma"
        assert created_ase["role"] == "ASE"

        # Check hierarchy
        hierarchy = user_service.get_hierarchy()
        if hierarchy:
            matched = [h for h in hierarchy if h.get("ase_user_id") == ase_id or h.get("ase_name") == "Vikas Singh"]
            if matched:
                assert matched[0]["tsm_name"] in ("Rajesh Sharma", "TSM User")

    finally:
        if ase_id:
            user_service.delete_user(ase_id)
        if tsm_id:
            user_service.delete_user(tsm_id)

