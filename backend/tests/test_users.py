import pytest
import io
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.user_service import user_service

client = TestClient(app)

def test_list_users_api():
    response = client.get("/api/v1/users/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "role" in data[0]
    assert "reportingManager" in data[0]

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
