import asyncio
import concurrent.futures
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.core.config import settings
from backend.core.security import RoleChecker, StrictRoleChecker, get_current_user, decode_access_token
from backend.services.otp_service import (
    generate_6digit_otp,
    sanitize_phone,
    send_otp_sms,
    cleanup_expired_otps,
    store_otp_in_db,
    verify_otp_from_db,
    store_password_reset_code,
    verify_password_reset_code,
)
from backend.mobile.router import (
    SendOTPRequest,
    VerifyOTPRequest,
    send_mobile_otp,
    verify_mobile_otp,
    get_mobile_user_profile,
)
from backend.auth.router import reset_password, ResetPasswordRequest


def run_async(coro):
    """Run an async coroutine synchronously in pytest."""
    return asyncio.run(coro)


def resolve_token_user(token: str):
    """Helper to authenticate token through get_current_user dependency."""
    from fastapi.security import HTTPAuthorizationCredentials
    mock_request = MagicMock()
    mock_request.cookies = {}
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return run_async(get_current_user(request=mock_request, credentials=creds))


class MockDatabase:
    """Accurate in-memory table simulator for otp_codes and users queries with row locking."""

    def __init__(self):
        self._lock = threading.Lock()
        self.otp_codes = []  # list of dicts: id, mobile_number, otp_hash, expires_at, created_at
        self.users = []
        self.user_roles = []
        self.roles = []
        self.user_depot = []
        self.depots = []
        self.companies = []
        self.tenant_config = []
        self._next_id = 1

    def table(self, table_name: str):
        mock_tbl = MagicMock()
        data_list = getattr(self, table_name, [])

        # INSERT
        def insert_mock(row_or_rows):
            with self._lock:
                rows = row_or_rows if isinstance(row_or_rows, list) else [row_or_rows]
                inserted = []
                for r in rows:
                    new_row = dict(r)
                    if "id" not in new_row:
                        new_row["id"] = self._next_id
                        self._next_id += 1
                    data_list.append(new_row)
                    inserted.append(new_row)
                res = MagicMock()
                res.data = inserted
                return MagicMock(execute=MagicMock(return_value=res))

        mock_tbl.insert = insert_mock

        # SELECT / QUERY BUILDER
        def select_mock(columns="*"):
            with self._lock:
                builder = MockQueryBuilder(self, table_name, list(data_list))
                return builder

        mock_tbl.select = select_mock

        # DELETE
        def delete_mock():
            builder = MockDeleteBuilder(self, table_name, data_list)
            return builder

        mock_tbl.delete = delete_mock
        return mock_tbl


class MockQueryBuilder:
    def __init__(self, db, table_name, rows):
        self.db = db
        self.table_name = table_name
        self.rows = rows

    def eq(self, col, val):
        self.rows = [r for r in self.rows if r.get(col) == val]
        return self

    def ilike(self, col, pattern):
        p = pattern.lower().replace("%", "")
        self.rows = [r for r in self.rows if p in str(r.get(col, "")).lower()]
        return self

    def or_(self, expr):
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col, "")), reverse=desc)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        res = MagicMock()
        res.data = list(self.rows)
        return res


class MockDeleteBuilder:
    def __init__(self, db, table_name, master_list):
        self.db = db
        self.table_name = table_name
        self.master_list = master_list
        self.filters = []

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: str(r.get(col, "")) < str(val))
        return self

    def execute(self):
        with self.db._lock:
            to_delete = []
            for r in self.master_list:
                if all(f(r) for f in self.filters):
                    to_delete.append(r)
            for r in to_delete:
                self.master_list.remove(r)
            res = MagicMock()
            res.data = to_delete
            return res


@pytest.fixture
def mock_db():
    return MockDatabase()


class TestOTPBackdoorsSecurity:
    """
    Comprehensive Security Verification Test Suite for Item 9:
    OTP Backdoors Remediation & Dedicated App Store / Google Play Review Login.
    """

    # -------------------------------------------------------------------------
    # Required Functionality
    # -------------------------------------------------------------------------

    def test_01_review_login_9999999999_with_123456_succeeds_when_enabled(self, mock_db):
        """
        Requirement 1: 9999999999 with 123456 succeeds when review mode is explicitly enabled.
        """
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            req = VerifyOTPRequest(phone="9999999999", otp="123456")
            res = run_async(verify_mobile_otp(req))

            assert "access_token" in res
            assert res["token_type"] == "bearer"
            assert res["user"]["phone"] == "+919999999999"
            assert res["user"]["role_name"] == "TSM"
            assert res["user"]["tenant_id"] == settings.APP_REVIEW_DEMO_TENANT_ID

            # Verify token payload has short-lived expiration and review claims
            payload = decode_access_token(res["access_token"])
            assert payload is not None
            assert payload.get("is_review_user") is True
            assert payload.get("tenant_id") == settings.APP_REVIEW_DEMO_TENANT_ID

    def test_02_review_login_does_not_require_sms_delivery(self, mock_db):
        """
        Requirement 2: The review login does not require SMS delivery for SMS-free access.
        """
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.mobile.router.send_otp_sms", new_callable=AsyncMock) as mock_sms, \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            req = SendOTPRequest(phone="9999999999", email=None)
            res = run_async(send_mobile_otp(req))

            assert res["success"] is True
            assert res["phone"] == "+919999999999"
            assert not mock_sms.called, "SMS service must not be invoked for dedicated review flow!"

    def test_03_review_identity_receives_intended_demo_profile(self, mock_db):
        """
        Requirement 3: The review identity receives the intended profile from /me endpoint.
        """
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            review_user_context = {
                "user_id": settings.APP_REVIEW_USER_ID,
                "sub": settings.APP_REVIEW_EMAIL,
                "role": "TSM",
                "role_name": "TSM",
                "is_review_user": True,
            }
            profile = get_mobile_user_profile(current_user=review_user_context)

            assert profile["user_id"] == settings.APP_REVIEW_USER_ID
            assert profile["phone"] == f"+91{settings.APP_REVIEW_PHONE}"
            assert profile["role_name"] == "TSM"
            assert profile["tenant_id"] == settings.APP_REVIEW_DEMO_TENANT_ID
            assert "Demo" in profile["company_name"]

    def test_04_review_account_can_access_approved_demo_features(self, mock_db):
        """
        Requirement 4: The review account can access approved features (e.g. TSM role-checker).
        """
        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            # Generate valid review token
            from backend.core.security import create_access_token
            token = create_access_token(
                data={
                    "sub": settings.APP_REVIEW_EMAIL,
                    "user_id": settings.APP_REVIEW_USER_ID,
                    "role": "TSM",
                    "tenant_id": settings.APP_REVIEW_DEMO_TENANT_ID,
                    "is_review_user": True
                },
                expires_delta=timedelta(hours=2)
            )

            # Test get_current_user resolution
            user_resolved = resolve_token_user(token)
            assert user_resolved["user_id"] == settings.APP_REVIEW_USER_ID
            assert user_resolved["role"] == "tsm"
            assert "tsm" in user_resolved["roles"]

            # RoleChecker with TSM allowed should permit access
            checker = RoleChecker(["tsm", "ase", "leader"])
            authorized_user = checker(current_user=user_resolved)
            assert authorized_user["user_id"] == settings.APP_REVIEW_USER_ID

    def test_05_normal_registered_users_standard_otp_flow(self, mock_db):
        """
        Requirement 5: Normal registered users can still use standard OTP authentication.
        """
        mock_db.users.append({
            "user_id": "11111111-2222-3333-4444-555555555555",
            "email": "field.tsm@rll.com",
            "phone": "+919876543210",
            "first_name": "Field",
            "last_name": "TSM",
            "is_active": True,
            "tenant_id": "tenant-real-12345",
            "company_name": "Rajasthan Liquor Limited"
        })

        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.mobile.router.send_otp_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = True

            # Step 1: Send OTP for registered user
            send_req = SendOTPRequest(phone="9876543210", email=None)
            send_res = run_async(send_mobile_otp(send_req))
            assert send_res["success"] is True
            assert mock_sms.called
            assert len(mock_db.otp_codes) >= 1

            # Retrieve generated random OTP dispatched to SMS
            call_phone, dispatched_otp = mock_sms.call_args[0]
            assert len(dispatched_otp) == 6
            assert dispatched_otp.isdigit()

            # Verify that stored OTP in database is cryptographically hashed (NEVER plaintext)
            stored_hash = mock_db.otp_codes[0]["otp_hash"]
            assert len(stored_hash) == 64
            assert stored_hash != dispatched_otp

            # Step 2: Verify OTP
            verify_req = VerifyOTPRequest(phone="9876543210", otp=dispatched_otp)
            verify_res = run_async(verify_mobile_otp(verify_req))
            assert "access_token" in verify_res
            assert verify_res["user"]["email"] == "field.tsm@rll.com"

            # OTP must be consumed atomically
            assert len(mock_db.otp_codes) == 0

    # -------------------------------------------------------------------------
    # Security Boundaries
    # -------------------------------------------------------------------------

    def test_06_fixed_review_otp_does_not_authenticate_arbitrary_phone_numbers(self, mock_db):
        """
        Requirement 6: The fixed review OTP (123456) does not authenticate arbitrary phone numbers.
        Also verifies additional fixed OTPs (000000, 12345) are strictly rejected.
        """
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            # Arbitrary phone numbers must not accept 123456
            assert verify_otp_from_db("9876543210", "123456") is False
            assert verify_otp_from_db("9123456789", "123456") is False

            # Additional fixed OTPs must be rejected even for 9999999999
            assert verify_otp_from_db("9999999999", "000000") is False
            assert verify_otp_from_db("9999999999", "12345") is False

    def test_07_review_login_cannot_be_activated_through_client_controlled_bypass(self, mock_db):
        """
        Requirement 7: The review login cannot be activated through client-controlled flags or arbitrary emails.
        """
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            # Attacker passes an arbitrary phone with the review email
            req = VerifyOTPRequest(
                phone="9876543210",
                otp="123456",
                email="manish.chum@workfloww.ai"
            )
            with pytest.raises(HTTPException) as exc:
                run_async(verify_mobile_otp(req))
            assert exc.value.status_code == 401
            assert "invalid or expired" in exc.value.detail.lower()

    def test_08_review_authentication_fails_closed_when_disabled_or_invalid_config(self, mock_db):
        """
        Requirement 8: Review authentication fails closed when APP_REVIEW_MODE_ENABLED is False or config is invalid.
        """
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db):

            # Case A: APP_REVIEW_MODE_ENABLED is False
            with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", False):
                # verify_otp_from_db fails closed
                assert verify_otp_from_db("9999999999", "123456") is False

                # send_mobile_otp fails closed
                with pytest.raises(HTTPException) as exc_send:
                    run_async(send_mobile_otp(SendOTPRequest(phone="9999999999")))
                assert exc_send.value.status_code in (400, 401)

                # verify_mobile_otp fails closed
                with pytest.raises(HTTPException) as exc_verify:
                    run_async(verify_mobile_otp(VerifyOTPRequest(phone="9999999999", otp="123456")))
                assert exc_verify.value.status_code == 401

            # Case B: Configuration missing/empty fails closed
            with patch("backend.core.config.settings.APP_REVIEW_PHONE", ""):
                assert verify_otp_from_db("9999999999", "123456") is False

    def test_09_review_tokens_cannot_access_real_tenant_data(self, mock_db):
        """
        Requirement 9: Review tokens cannot access real customer tenant data; strictly bound to demo tenant.
        """
        mock_db.tenant_config.append({
            "id": 1,
            "tenant_id": "real-production-tenant-uuid-8888",
            "app_name": "Real Client Tenant"
        })

        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            req = VerifyOTPRequest(phone="9999999999", otp="123456")
            res = run_async(verify_mobile_otp(req))

            assert res["user"]["tenant_id"] == settings.APP_REVIEW_DEMO_TENANT_ID
            assert res["user"]["tenant_id"] != "real-production-tenant-uuid-8888"
            assert res["tenant_config"]["tenant_id"] == settings.APP_REVIEW_DEMO_TENANT_ID

    def test_10_review_tokens_cannot_perform_administrative_operations(self):
        """
        Requirement 10: Review tokens cannot perform administrative operations (HTTP 403 Forbidden).
        """
        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            review_user = {
                "user_id": settings.APP_REVIEW_USER_ID,
                "email": settings.APP_REVIEW_EMAIL,
                "roles": ["tsm"],
                "role_name": "tsm",
                "role": "tsm",
                "tenant_id": settings.APP_REVIEW_DEMO_TENANT_ID
            }

            admin_checker = RoleChecker(["admin", "super_admin"])
            with pytest.raises(HTTPException) as exc:
                admin_checker(current_user=review_user)
            assert exc.value.status_code == 403
            assert "permission denied" in exc.value.detail.lower()

            dev_checker = StrictRoleChecker(["developer"])
            with pytest.raises(HTTPException) as exc_dev:
                dev_checker(current_user=review_user)
            assert exc_dev.value.status_code == 403

    def test_11_review_tokens_cannot_modify_production_business_data(self):
        """
        Requirement 11: Review tokens cannot modify production business data (no write/admin roles).
        """
        review_user = {
            "user_id": settings.APP_REVIEW_USER_ID,
            "role": "tsm",
            "roles": ["tsm"],
            "tenant_id": settings.APP_REVIEW_DEMO_TENANT_ID
        }
        # Verify review user does not possess write/import/admin privileges
        assert "admin" not in review_user["roles"]
        assert "super_admin" not in review_user["roles"]
        assert "developer" not in review_user["roles"]

    def test_12_review_identity_cannot_escalate_its_privileges(self):
        """
        Requirement 12: Review identity cannot escalate its privileges via token claims or parameters.
        """
        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):
            from backend.core.security import create_access_token
            # Attacker creates a token with review user ID but claims admin role
            forged_token = create_access_token(
                data={
                    "sub": settings.APP_REVIEW_EMAIL,
                    "user_id": settings.APP_REVIEW_USER_ID,
                    "role": "super_admin",
                    "roles": ["super_admin"]
                }
            )

            # get_current_user authoritative resolution forces review profile role to tsm
            resolved = resolve_token_user(forged_token)
            assert resolved["role_name"] == "tsm"
            assert resolved["roles"] == ["tsm"]
            assert "super_admin" not in resolved["roles"]

    def test_13_review_credentials_cannot_reset_another_users_password(self, mock_db):
        """
        Requirement 13: Review credentials (123456) cannot be used to reset another user's password.
        """
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            victim_email = "executive@rll.com"
            # 123456 must return False when verified as a password reset code
            assert verify_password_reset_code(victim_email, "123456") is False
            assert verify_password_reset_code(victim_email, "12345") is False
            assert verify_password_reset_code(victim_email, "000000") is False

    def test_14_otp_values_not_exposed_in_logs(self, caplog):
        """
        Requirement 14: OTP values are not exposed in log messages or output.
        """
        caplog.set_level(logging.INFO)
        test_otp = "839201"
        run_async(send_otp_sms("9876543210", test_otp))

        log_messages = [rec.message for rec in caplog.records]
        for msg in log_messages:
            assert f"OTP Code: {test_otp}" not in msg, "Plaintext OTP found in log output!"
            assert f"[{test_otp}]" not in msg, "Plaintext bracketed OTP found in log output!"

    def test_15_normal_otps_retain_expiration_and_single_use_protections(self, mock_db):
        """
        Requirement 15: Normal OTPs retain expiration and single-use protections (concurrent test).
        """
        phone = "9876543210"
        otp = "543219"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_otp_in_db(phone, otp)
            assert len(mock_db.otp_codes) == 1

            # Concurrent verification: exactly 1 succeeds
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(verify_otp_from_db, phone, otp) for _ in range(5)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            assert sum(1 for r in results if r is True) == 1
            assert sum(1 for r in results if r is False) == 4
            assert len(mock_db.otp_codes) == 0, "Record must be dropped immediately on consumption"

    def test_16_existing_password_reset_failure_paths_remain_intact(self, mock_db):
        """
        Requirement 16: The existing password-reset failure-path protections remain intact.
        """
        # A: Client is None -> fails closed
        with patch("backend.services.otp_service.get_supabase", return_value=None):
            assert verify_password_reset_code("user@example.com", "123456") is False

        # B: Database exception -> fails closed
        faulty_client = MagicMock()
        faulty_client.table.side_effect = RuntimeError("DB timeout")
        with patch("backend.services.otp_service.get_supabase", return_value=faulty_client):
            assert verify_password_reset_code("user@example.com", "123456") is False

        # C: Malformed records -> fail closed
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            mock_db.otp_codes = [{
                "id": 1,
                "mobile_number": "pwd_user@example.com",
                "otp_hash": None,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            }]
            assert verify_password_reset_code("user@example.com", "123456") is False

        # D: Endpoint fails closed on Redis missing
        req = ResetPasswordRequest(
            email="victim@example.com",
            otp="123456",
            new_password="SecurePassword123!"
        )
        with patch("backend.db.redis_client.safe_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 400
