import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.core.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    _LOCAL_USER_PROFILES,
    RoleChecker,
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


class TestAuthFallbackAndPrivilegeEscalation:
    """Automated security regression tests for Item 2: Fail-closed authentication."""

    # 1. Valid JWT and existing active user: authentication succeeds
    def test_01_valid_jwt_and_existing_active_user_succeeds(self, mock_request):
        token = create_access_token({"sub": "alice@rll.in", "user_id": "u-001"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "u-001", "email": "alice@rll.in", "first_name": "Alice", "is_active": True, "tenant_id": "t-1"}]
        )
        mock_client.table("user_roles").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"is_active": True, "roles": {"role_name": "Admin"}}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["email"] == "alice@rll.in"
            assert user["user_id"] == "u-001"
            assert user["role_name"] == "Admin"
            assert user["is_active"] is True

    # 2. Invalid JWT signature: authentication fails
    def test_02_invalid_jwt_signature_fails(self, mock_request):
        import jwt
        forged_token = jwt.encode({"sub": "hacker@evil.com", "user_id": "h-1"}, "wrong-secret-key-that-is-at-least-32-chars-long", algorithm="HS256")
        creds = make_credentials(forged_token)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(mock_request, creds))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    # 3. Expired JWT: authentication fails
    def test_03_expired_jwt_fails(self, mock_request):
        expired_token = create_access_token({"sub": "alice@rll.in", "user_id": "u-001"}, expires_delta=timedelta(seconds=-60))
        creds = make_credentials(expired_token)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(mock_request, creds))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    # 4. Valid JWT referencing a nonexistent user: authentication fails (no synthetic user created)
    def test_04_valid_jwt_nonexistent_user_fails(self, mock_request):
        token = create_access_token({"sub": "ghost@rll.in", "user_id": "ghost-id", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(data=[])

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "User not found" in exc_info.value.detail

    # 5. Database query returns no matching user: authentication fails
    def test_05_db_returns_none_data_fails(self, mock_request):
        token = create_access_token({"sub": "deleted@rll.in", "user_id": "del-id"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(data=None)

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "User not found" in exc_info.value.detail

    # 6. Database query raises an exception: fails without granting access (503 Service Unavailable)
    def test_06_db_query_exception_fails_without_fallback(self, mock_request):
        token = create_access_token({"sub": "attacker@rll.in", "user_id": "att-id", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.side_effect = RuntimeError("Database connection timeout")

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 503
            assert "database lookup failed" in exc_info.value.detail

    # 7. Database client is unavailable (None): fails without granting access
    def test_07_db_client_unavailable_fails_without_fallback(self, mock_request):
        token = create_access_token({"sub": "attacker@rll.in", "user_id": "att-id", "role": "admin"})
        creds = make_credentials(token)

        with patch("backend.core.security.get_supabase", return_value=None), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 503
            assert "database connection could not be established" in exc_info.value.detail

    # 8. User record has a missing role: role is unassigned, privileged access is denied
    def test_08_user_missing_role_assigned_unassigned_and_denied_admin(self, mock_request):
        token = create_access_token({"sub": "norole@rll.in", "user_id": "nr-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "nr-1", "email": "norole@rll.in", "is_active": True}]
        )
        mock_client.table("user_roles").select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "unassigned"
            assert user["role"] == "unassigned"
            assert user["roles"] == []
            assert user["role_name"] != "admin"

    # 9. User record has an invalid or unrecognized role: denied privileged access
    def test_09_user_invalid_role_denied_privileged_access(self, mock_request):
        token = create_access_token({"sub": "contractor@rll.in", "user_id": "c-1"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "c-1", "email": "contractor@rll.in", "is_active": True}]
        )
        mock_client.table("user_roles").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"is_active": True, "roles": {"role_name": "third_party_auditor"}}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "third_party_auditor"
            assert user["role_name"] != "admin"

    # 10. JWT contains role=admin, but DB identifies user as regular user (e.g. TSM): DB role is authoritative
    def test_10_jwt_admin_claim_overridden_by_database_role(self, mock_request):
        token = create_access_token({"sub": "field_tsm@rll.in", "user_id": "tsm-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "tsm-1", "email": "field_tsm@rll.in", "is_active": True}]
        )
        mock_client.table("user_roles").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"is_active": True, "roles": {"role_name": "TSM"}}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            # The database role MUST win; JWT claim must be ignored
            assert user["role_name"] == "TSM"
            assert user["role"] == "TSM"
            assert user["role_name"] != "admin"

    # 11. JWT contains role=admin, but database lookup fails: authentication fails, no admin access
    def test_11_jwt_admin_claim_with_db_failure_fails(self, mock_request):
        token = create_access_token({"sub": "admin_impersonator@rll.in", "user_id": "imp-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.side_effect = Exception("DB Connection Down")

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 503

    # 12. JWT contains administrator claim, but user is inactive or disabled: authentication fails
    def test_12_jwt_admin_with_deactivated_user_fails(self, mock_request):
        token = create_access_token({"sub": "fired_admin@rll.in", "user_id": "ex-admin", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "ex-admin", "email": "fired_admin@rll.in", "is_active": False}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "deactivated" in exc_info.value.detail.lower()

    # 13. Missing required identity claims: authentication fails
    def test_13_missing_sub_identity_claim_fails(self, mock_request):
        token = create_access_token({"role": "admin", "user_id": "orphan-1"})
        creds = make_credentials(token)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(mock_request, creds))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    # 14. An unexpected exception during role lookup: no admin privileges are granted
    def test_14_unexpected_exception_during_role_query_fails_closed(self, mock_request):
        token = create_access_token({"sub": "bob@rll.in", "user_id": "b-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = MagicMock()
        mock_client.table("users").select.return_value.ilike.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "b-1", "email": "bob@rll.in", "is_active": True}]
        )
        mock_client.table("user_roles").select.return_value.eq.return_value.execute.side_effect = Exception("Corrupted relation")

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "unassigned"
            assert user["role"] == "unassigned"
            assert user["role_name"] != "admin"

    # 15. User revocation check in Redis stops access immediately
    def test_15_revoked_user_in_redis_denied_immediately(self, mock_request):
        token = create_access_token({"sub": "alice@rll.in", "user_id": "u-001"})
        creds = make_credentials(token)

        async def mock_redis_safe_get(key):
            if key == "rll:revoked:u-001":
                return "1"  # Revocation flag present
            return None

        with patch("backend.core.security.safe_get", side_effect=mock_redis_safe_get):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail.lower()
