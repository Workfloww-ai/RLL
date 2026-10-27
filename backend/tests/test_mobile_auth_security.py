import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.core.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    RoleChecker,
    normalize_role_name,
    _LOCAL_USER_PROFILES,
)
from backend.mobile.router import (
    MOBILE_ACCESS_ROLES,
    MOBILE_ADMIN_ROLES,
    mobile_access_checker,
    mobile_admin_checker,
    resolve_user_mobile_roles,
)


@pytest.fixture(autouse=True)
def clean_local_profiles_and_cache():
    """Clear in-memory user profile cache before and after every test."""
    _LOCAL_USER_PROFILES.clear()
    yield
    _LOCAL_USER_PROFILES.clear()


@pytest.fixture
def mock_request():
    """Provide a mock FastAPI Request object with no cookies."""
    req = MagicMock()
    req.cookies = {}
    return req


def make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def create_mock_supabase_for_user(user_rows=None, role_rows=None):
    """Mock Supabase query responses for users and user_roles tables."""
    client = MagicMock()

    users_query = MagicMock()
    users_query.execute.return_value = MagicMock(data=user_rows or [])
    users_select = MagicMock()
    users_select.eq.return_value = users_query
    users_select.ilike.return_value = users_query
    users_select.execute = users_query.execute

    roles_query = MagicMock()
    roles_query.execute.return_value = MagicMock(data=role_rows or [])
    roles_select = MagicMock()
    roles_select.eq.return_value = roles_query
    roles_select.execute = roles_query.execute

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "users":
            mock_t.select.return_value = users_select
        elif table_name == "user_roles":
            mock_t.select.return_value = roles_select
        return mock_t

    client.table.side_effect = table_router
    return client


class TestMobileAuthorizationSecurity:
    """
    Automated security tests for RLL Mobile API authorization, role checking,
    multi-role resolution, tenant isolation, and revocation.
    """

    # 1. Developer with valid authentication accesses /mobile/me and /mobile/sales
    def test_01_developer_accesses_mobile_endpoints(self):
        dev_user = {
            "user_id": "76750131-78b4-4e24-80fe-186b8c98a793",
            "email": "khwaish.gahoi@workfloww.ai",
            "role_name": "developer",
            "roles": ["developer"],
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "company_name": None,
        }
        # Passes /mobile/me and /mobile/sales role check
        assert mobile_access_checker(current_user=dev_user) == dev_user
        # Also passes mobile admin check
        assert mobile_admin_checker(current_user=dev_user) == dev_user

    # 2. Existing roles (ASE, TSM, Leader, Admin, Super Admin, Territory Executive) preserved
    @pytest.mark.parametrize("role", [
        "ase",
        "tsm",
        "leader",
        "admin",
        "super_admin",
        "territory_executive",
    ])
    def test_02_standard_field_and_admin_roles_preserved(self, role):
        user = {
            "user_id": f"u-{role}",
            "email": f"{role}@rll.in",
            "role_name": role,
            "roles": [role],
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
        }
        assert mobile_access_checker(current_user=user) == user

    # 3. Unauthenticated request raises HTTP 401
    def test_03_unauthenticated_request_raises_401(self, mock_request):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(mock_request, credentials=None))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    # 4. User with unauthorized role (e.g., viewer) raises HTTP 403 Forbidden
    def test_04_unauthorized_role_denied(self):
        viewer_user = {
            "user_id": "u-viewer",
            "email": "viewer@rll.in",
            "role_name": "viewer",
            "roles": ["viewer"],
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
        }
        with pytest.raises(HTTPException) as exc_info:
            mobile_access_checker(current_user=viewer_user)
        assert exc_info.value.status_code == 403
        assert "Permission denied" in exc_info.value.detail

    # 5. User with multiple active roles resolves deterministically
    def test_05_multi_role_resolution_deterministic(self):
        client = MagicMock()
        mock_roles_res = MagicMock()
        # User has both 'viewer' and 'developer' in user_roles
        mock_roles_res.data = [
            {"is_active": True, "roles": {"role_name": "viewer"}},
            {"is_active": True, "roles": {"role_name": "developer"}},
        ]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_roles_res

        authoritative_role, active_roles = resolve_user_mobile_roles(client, "u-multi")
        # 'developer' has higher priority than 'viewer'
        assert authoritative_role == "developer"
        assert set(active_roles) == {"viewer", "developer"}

        # RoleChecker evaluates set intersection
        multi_user = {
            "user_id": "u-multi",
            "email": "multi@rll.in",
            "role_name": authoritative_role,
            "roles": active_roles,
        }
        assert mobile_access_checker(current_user=multi_user) == multi_user

    # 6. Inactive developer role assignment does not independently grant access
    def test_06_inactive_role_assignment_ignored(self):
        client = MagicMock()
        mock_roles_res = MagicMock()
        # Developer role is inactive; viewer role is active
        mock_roles_res.data = [
            {"is_active": False, "roles": {"role_name": "developer"}},
            {"is_active": True, "roles": {"role_name": "viewer"}},
        ]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_roles_res

        authoritative_role, active_roles = resolve_user_mobile_roles(client, "u-inactive")
        # Inactive developer role is excluded
        assert authoritative_role == "viewer"
        assert active_roles == ["viewer"]

        # Only active roles reach checker -> access denied
        inactive_dev_user = {
            "user_id": "u-inactive",
            "email": "inactive@rll.in",
            "role_name": authoritative_role,
            "roles": active_roles,
        }
        with pytest.raises(HTTPException) as exc_info:
            mobile_access_checker(current_user=inactive_dev_user)
        assert exc_info.value.status_code == 403

    # 7. Revoked user in Redis denies access immediately (HTTP 401)
    def test_07_revoked_session_denies_access(self, mock_request):
        token = create_access_token({"sub": "dev@rll.in", "user_id": "u-revoked"})
        creds = make_credentials(token)

        with patch("backend.core.security.safe_get", new_callable=AsyncMock) as mock_redis_get:
            # Simulate Redis instant revocation flag
            mock_redis_get.side_effect = lambda key: "1" if "rll:revoked:u-revoked" in key else None

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "Session revoked" in exc_info.value.detail

    # 8. Role name normalization handles irregular capitalization and whitespace
    @pytest.mark.parametrize("raw_role,expected_canonical", [
        ("DEVELOPER", "developer"),
        ("  Developer  ", "developer"),
        ("Super Admin", "super_admin"),
        ("superadmin", "super_admin"),
        ("Territory Executive", "territory_executive"),
        ("territory executive", "territory_executive"),
        ("TSM", "tsm"),
        ("ase", "ase"),
    ])
    def test_08_role_normalization_consistency(self, raw_role, expected_canonical):
        assert normalize_role_name(raw_role) == expected_canonical

        # Normalization allows user to pass mobile_access_checker
        user = {
            "user_id": "u-norm",
            "email": "norm@rll.in",
            "role_name": raw_role,
            "roles": [raw_role],
        }
        assert mobile_access_checker(current_user=user) == user

    # 9. Inactive user account in database rejects authentication (HTTP 401)
    def test_09_inactive_database_account_rejected(self, mock_request):
        token = create_access_token({"sub": "deactivated@rll.in", "user_id": "u-deactivated"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase_for_user(
            user_rows=[{
                "user_id": "u-deactivated",
                "email": "deactivated@rll.in",
                "first_name": "Deact",
                "is_active": False,  # Deactivated
                "tenant_id": "a0000000-0000-0000-0000-000000000001",
            }],
            role_rows=[{"is_active": True, "roles": {"role_name": "developer"}}],
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "deactivated" in exc_info.value.detail.lower()

    # 10. Tenant scoping: Authenticated profile retains verified tenant_id
    def test_10_tenant_scoping_preserved(self, mock_request):
        tenant_uuid = "a0000000-0000-0000-0000-000000000001"
        token = create_access_token({"sub": "dev@rll.in", "user_id": "u-dev-tenant"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase_for_user(
            user_rows=[{
                "user_id": "u-dev-tenant",
                "email": "dev@rll.in",
                "first_name": "Dev",
                "is_active": True,
                "tenant_id": tenant_uuid,
            }],
            role_rows=[{"is_active": True, "roles": {"role_name": "developer"}}],
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["tenant_id"] == tenant_uuid
            assert user["role_name"] == "developer"
            assert "developer" in user["roles"]
