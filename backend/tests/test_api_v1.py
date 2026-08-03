from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"

def test_auth_login():
    response = client.post("/api/v1/auth/login", json={"email": "admin@rll.gov.in", "password": "anypassword"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role_name"] == "admin"

def test_master_data_endpoints():
    response = client.get("/api/v1/master-data/offices")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = client.get("/api/v1/master-data/brands")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_dashboard_overview():
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert "kpis" in data
    assert "trends" in data
    assert "top_brands" in data
    assert "top_depots" in data

def test_analytics_trends():
    response = client.get("/api/v1/analytics/trends")
    assert response.status_code == 200
    assert "trends" in response.json()
