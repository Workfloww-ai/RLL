import asyncio
import logging
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


def create_mock_supabase(user_rows=None, role_rows=None, users_side_effect=None, roles_side_effect=None):
    """Helper to mock Supabase queries cleanly for both user_id (eq) and email (ilike)."""
    client = MagicMock()

    # Users table mock
    users_query = MagicMock()
    if users_side_effect:
        users_query.execute.side_effect = users_side_effect
    else:
        users_query.execute.return_value = MagicMock(data=user_rows)

    users_select = MagicMock()
    users_select.eq.return_value = users_query
    users_select.ilike.return_value = users_query
    users_select.execute = users_query.execute

    # Roles table mock
    roles_query = MagicMock()
    if roles_side_effect:
        roles_query.execute.side_effect = roles_side_effect
    else:
        roles_query.execute.return_value = MagicMock(data=role_rows)

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


class TestAuthFallbackAndPrivilegeEscalation:
    """Automated security regression tests for Item 2: Fail-closed authentication & role verification."""

    # 1. Valid JWT and existing active user: authentication succeeds
    def test_01_valid_jwt_and_existing_active_user_succeeds(self, mock_request):
        token = create_access_token({"sub": "alice@rll.in", "user_id": "u-001"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "u-001", "email": "alice@rll.in", "first_name": "Alice", "is_active": True, "tenant_id": "t-1"}],
            role_rows=[{"is_active": True, "roles": {"role_name": "Admin"}}]
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
        forged_token = jwt.encode(
            {"sub": "hacker@evil.com", "user_id": "h-1"},
            "wrong-secret-key-that-is-at-least-32-chars-long",
            algorithm="HS256"
        )
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

        mock_client = create_mock_supabase(user_rows=[])

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

        mock_client = create_mock_supabase(user_rows=None)

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

        mock_client = create_mock_supabase(users_side_effect=RuntimeError("Database connection timeout"))

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

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "nr-1", "email": "norole@rll.in", "is_active": True}],
            role_rows=[]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "unassigned"
            assert user["role"] == "unassigned"
            assert user["roles"] == []
            assert user["role_name"] != "admin"

            # Check that RoleChecker(["admin"]) strictly blocks this user
            admin_check = RoleChecker(["admin"])
            with pytest.raises(HTTPException) as exc_info:
                admin_check(current_user=user)
            assert exc_info.value.status_code == 403

    # 9. User record has an invalid or unrecognized role: denied privileged access
    def test_09_user_invalid_role_denied_privileged_access(self, mock_request):
        token = create_access_token({"sub": "contractor@rll.in", "user_id": "c-1"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "c-1", "email": "contractor@rll.in", "is_active": True}],
            role_rows=[{"is_active": True, "roles": {"role_name": "third_party_auditor"}}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "third_party_auditor"
            assert user["role_name"] != "admin"

            admin_check = RoleChecker(["admin"])
            with pytest.raises(HTTPException) as exc_info:
                admin_check(current_user=user)
            assert exc_info.value.status_code == 403

    # 10. JWT contains role=admin, but DB identifies user as regular user (e.g. TSM): DB role is authoritative
    def test_10_jwt_admin_claim_overridden_by_database_role(self, mock_request):
        token = create_access_token({"sub": "field_tsm@rll.in", "user_id": "tsm-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "tsm-1", "email": "field_tsm@rll.in", "is_active": True}],
            role_rows=[{"is_active": True, "roles": {"role_name": "TSM"}}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert user["role_name"] == "TSM"
            assert user["role"] == "TSM"
            assert user["role_name"] != "admin"

            admin_check = RoleChecker(["admin"])
            with pytest.raises(HTTPException) as exc_info:
                admin_check(current_user=user)
            assert exc_info.value.status_code == 403

    # 11. JWT contains role=admin, but database lookup fails: authentication fails, no admin access
    def test_11_jwt_admin_claim_with_db_failure_fails(self, mock_request):
        token = create_access_token({"sub": "admin_impersonator@rll.in", "user_id": "imp-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(users_side_effect=Exception("DB Connection Down"))

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 503

    # 12. JWT contains administrator claim, but user is inactive or disabled: authentication fails
    def test_12_jwt_admin_with_deactivated_user_fails(self, mock_request):
        token = create_access_token({"sub": "fired_admin@rll.in", "user_id": "ex-admin", "role": "admin"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "ex-admin", "email": "fired_admin@rll.in", "is_active": False}]
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

    # 14. Role database query failure: fails closed with HTTP 503
    def test_14_role_query_failure_fails_closed_with_503(self, mock_request):
        token = create_access_token({"sub": "bob@rll.in", "user_id": "b-1", "role": "admin"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "b-1", "email": "bob@rll.in", "is_active": True}],
            roles_side_effect=RuntimeError("user_roles relation lock failure")
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 503
            assert "role verification failed" in exc_info.value.detail

    # 15. Missing or malformed is_active status: fails closed (must be explicit True)
    @pytest.mark.parametrize("invalid_is_active", [None, "true", "True", 1, 0, "", False])
    def test_15_missing_or_malformed_is_active_rejected(self, mock_request, invalid_is_active):
        token = create_access_token({"sub": "user@rll.in", "user_id": "u-test"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "u-test", "email": "user@rll.in", "is_active": invalid_is_active}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "deactivated or invalid" in exc_info.value.detail

    # 16. Duplicate or ambiguous user identity: fails closed
    def test_16_duplicate_ambiguous_user_identity_fails(self, mock_request):
        # When token does not provide user_id, it queries by email
        token = create_access_token({"sub": "ambiguous@rll.in"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[
                {"user_id": "u-1", "email": "ambiguous@rll.in", "is_active": True},
                {"user_id": "u-2", "email": "ambiguous@rll.in", "is_active": True},
            ]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "multiple user accounts matched" in exc_info.value.detail

    # 17. Identity claim mismatch: token sub does not match database user email
    def test_17_identity_claim_mismatch_fails(self, mock_request):
        token = create_access_token({"sub": "impostor@rll.in", "user_id": "u-target"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "u-target", "email": "legit@rll.in", "is_active": True}]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "Identity claim mismatch" in exc_info.value.detail

    # 18. Multiple assigned roles: user preserves all roles and authorization matches correctly
    def test_18_multiple_assigned_roles_preserved_and_authorized(self, mock_request):
        token = create_access_token({"sub": "field_lead@rll.in", "user_id": "fl-1"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(
            user_rows=[{"user_id": "fl-1", "email": "field_lead@rll.in", "is_active": True}],
            role_rows=[
                {"is_active": True, "roles": {"role_name": "TSM"}},
                {"is_active": True, "roles": {"role_name": "ASE"}},
            ]
        )

        with patch("backend.core.security.get_supabase", return_value=mock_client), \
             patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.db.redis_client.safe_set", new_callable=AsyncMock, return_value=True):
            user = asyncio.run(get_current_user(mock_request, creds))
            assert "TSM" in user["roles"]
            assert "ASE" in user["roles"]

            # RoleChecker for ASE passes
            ase_check = RoleChecker(["ASE"])
            assert ase_check(current_user=user) == user

            # RoleChecker for TSM passes
            tsm_check = RoleChecker(["TSM"])
            assert tsm_check(current_user=user) == user

            # RoleChecker for Admin is blocked
            admin_check = RoleChecker(["Admin"])
            with pytest.raises(HTTPException) as exc_info:
                admin_check(current_user=user)
            assert exc_info.value.status_code == 403

    # 19. User revocation check in Redis stops access immediately
    def test_19_revoked_user_in_redis_denied_immediately(self, mock_request):
        token = create_access_token({"sub": "alice@rll.in", "user_id": "u-001"})
        creds = make_credentials(token)

        async def mock_redis_safe_get(key):
            if key == "rll:revoked:u-001":
                return "1"
            return None

        with patch("backend.core.security.safe_get", side_effect=mock_redis_safe_get):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request, creds))
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail.lower()

    # 20. Sensitive information not exposed in authentication logs
    def test_20_sensitive_info_not_exposed_in_logs(self, mock_request, caplog):
        token = create_access_token({"sub": "user@rll.in", "user_id": "u-001"})
        creds = make_credentials(token)

        mock_client = create_mock_supabase(users_side_effect=RuntimeError("internal_db_error_with_details"))

        with caplog.at_level(logging.DEBUG):
            with patch("backend.core.security.get_supabase", return_value=mock_client), \
                 patch("backend.core.security.safe_get", new_callable=AsyncMock, return_value=None):
                with pytest.raises(HTTPException):
                    asyncio.run(get_current_user(mock_request, creds))

        # Ensure raw token string and passwords never appear in log records
        for record in caplog.records:
            assert token not in record.message
            assert "secret" not in record.message.lower()
            assert "bearer" not in record.message.lower()
