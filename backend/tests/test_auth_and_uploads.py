from io import BytesIO
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.security import create_access_token

client = TestClient(app)

def test_admin_only_upload_restriction():
    # 1. Test unauthenticated request -> allowed mock admin in dev or 401
    # 2. Test Sales Rep user token (Non-admin)
    sales_rep_token = create_access_token({"sub": "salesrep@rll.gov.in", "role": "sales_representative"})
    headers = {"Authorization": f"Bearer {sales_rep_token}"}
    
    file_data = BytesIO(b"dummy data")
    response = client.post(
        "/api/v1/uploads/",
        files={"file": ("test.xlsx", file_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers
    )
    assert response.status_code == 403
    assert "Operation not permitted" in response.json()["detail"]

def test_invalid_file_extension():
    admin_token = create_access_token({"sub": "admin@rll.gov.in", "role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    file_data = BytesIO(b"invalid format content")
    response = client.post(
        "/api/v1/uploads/",
        files={"file": ("report.pdf", file_data, "application/pdf")},
        headers=headers
    )
    assert response.status_code == 400
    assert "Invalid file format" in response.json()["detail"]

def test_admin_successful_excel_upload():
    admin_token = create_access_token({"sub": "admin@rll.gov.in", "role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    df = pd.DataFrame({
        "Date": ["2026-07-29"],
        "Depot Code": ["DEP_JPR_01"],
        "License Number": ["LIC-2026-001"],
        "Brand Code": ["ROYAL_STAG"],
        "Packing Size": ["750ml Bottle"],
        "Cases": [10.0],
        "Bottles": [120.0],
        "Bulk Liters": [90.0],
        "Sale Value": [50000.0]
    })
    
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    excel_buffer.seek(0)
    
    response = client.post(
        "/api/v1/uploads/",
        files={"file": ("valid_admin_sales.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers
    )
    assert response.status_code in (200, 202)
    res_data = response.json()
    assert "batch_id" in res_data or "upload_batch_id" in res_data
    assert "uploads/" in res_data["storage_path"]
