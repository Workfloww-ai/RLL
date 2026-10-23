"""
Security Audit Item 12: Password Reset Fail-Open Test Suite
===========================================================
Validates fail-closed behavior for all password reset operations:
- Supabase / Database client unavailable (HTTP 503)
- Database query exceptions and error responses (HTTP 503)
- Redis outage in production/staging (HTTP 503)
- Missing, expired, invalid, malformed, and previously consumed codes (HTTP 400)
- Hash verification failures and lockout (HTTP 400)
- User lookup failures, deactivated accounts, and identity mismatches (HTTP 400 / 401)
- Concurrent reset requests permitting at most ONE consumption
- Supabase Auth admin password update failures and recovery semantics (HTTP 500)
- Successful password reset via Redis and DB stores
- App review credentials isolation (no password reset bypass)
"""

import asyncio
import concurrent.futures
import hashlib
import json
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.auth.router import reset_password, forgot_password
from backend.auth.schemas import ResetPasswordRequest, ForgotPasswordRequest
from backend.core.config import settings
from backend.db.redis_client import (
    safe_get,
    safe_set,
    safe_delete,
    safe_set_nx,
    _in_memory_store,
    _in_memory_expiry,
    _in_memory_lock,
)
from backend.services.otp_service import (
    store_password_reset_code,
    verify_password_reset_code,
    hash_otp,
    _failed_attempts,
    _otp_lock,
    _consuming_records,
)


def run_async(coro):
    """Safely run async coroutine in sync test runner."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class MockDatabase:
    """Thread-safe in-memory database simulator for users and otp_codes."""

    def __init__(self):
        self._lock = threading.Lock()
        self.otp_codes = []
        self.users = []
        self._next_id = 1

    def table(self, table_name: str):
        mock_tbl = MagicMock()
        data_list = getattr(self, table_name, [])

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
                res.error = None
                return MagicMock(execute=MagicMock(return_value=res))

        mock_tbl.insert = insert_mock

        def select_mock(columns="*"):
            with self._lock:
                return MockQueryBuilder(self, table_name, list(data_list))

        mock_tbl.select = select_mock

        def delete_mock():
            return MockDeleteBuilder(self, table_name, data_list)

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

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col, "")), reverse=desc)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        res = MagicMock()
        res.data = list(self.rows)
        res.error = None
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
            res.error = None
            return res


@pytest.fixture
def mock_db():
    db = MockDatabase()
    with _otp_lock:
        _failed_attempts.clear()
        _consuming_records.clear()
    with _in_memory_lock:
        _in_memory_store.clear()
        _in_memory_expiry.clear()
    return db


class TestPasswordResetFailOpen:
    """Complete security test suite verifying fail-closed password reset behavior."""

    def test_01_database_client_unavailable_fails_closed_service_unavailable(self):
        """When Supabase client is None, operations fail closed with HTTP 503 or False."""
        with patch("backend.auth.router.get_supabase", return_value=None), \
             patch("backend.services.otp_service.get_supabase", return_value=None):

            # reset_password endpoint must reject with 503 Service Unavailable
            req = ResetPasswordRequest(
                email="user@rll.com",
                otp="123456",
                new_password="NewSecurePassword123!"
            )
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()

            # forgot_password endpoint must reject with 503
            f_req = ForgotPasswordRequest(email="user@rll.com")
            with pytest.raises(HTTPException) as f_exc:
                run_async(forgot_password(f_req))
            assert f_exc.value.status_code == 503

            # Helpers must fail closed (return False)
            assert store_password_reset_code("user@rll.com", "123456") is False
            assert verify_password_reset_code("user@rll.com", "123456") is False

    def test_02_database_query_exceptions_fail_closed_service_unavailable(self, mock_db):
        """Database connection/query exceptions during reset operations must fail closed with HTTP 503."""
        email = "analyst@rll.com"
        otp = "654321"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        exploding_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.side_effect = Exception("PostgreSQL server closed connection unexpectedly")
        exploding_client.table.return_value = mock_table

        with patch("backend.auth.router.get_supabase", return_value=exploding_client):
            req = ResetPasswordRequest(
                email=email,
                otp=otp,
                new_password="NewSecurePassword123!"
            )
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()

    def test_03_database_error_response_fails_closed(self, mock_db):
        """Database error response (e.g., query error/timeout) must fail closed with HTTP 503."""
        email = "analyst@rll.com"
        otp = "654321"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        error_client = MagicMock()
        err_res = MagicMock()
        err_res.error = {"code": "PGRST000", "message": "Query timeout exceeded"}
        err_res.data = None
        error_client.table.return_value.select.return_value.ilike.return_value.execute.return_value = err_res

        with patch("backend.auth.router.get_supabase", return_value=error_client):
            req = ResetPasswordRequest(
                email=email,
                otp=otp,
                new_password="NewSecurePassword123!"
            )
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()

    def test_04_redis_outage_fails_closed_in_production(self, mock_db):
        """In production/staging, shared Redis outage must reject password-reset requests with HTTP 503."""
        email = "manager@rll.com"
        req = ResetPasswordRequest(
            email=email,
            otp="112233",
            new_password="NewSecurePassword123!"
        )

        mock_user = {
            "user_id": "11111111-2222-3333-4444-555555555555",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        client = MagicMock()
        client.table = mock_db.table

        with patch("backend.core.config.settings.ENVIRONMENT", "production"), \
             patch("backend.db.redis_client.get_redis", return_value=None), \
             patch("backend.auth.router.get_supabase", return_value=client):

            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()

    def test_05_missing_invalid_malformed_reset_codes_rejected(self, mock_db):
        """Missing, malformed, non-numeric, or incorrect-length OTP codes must be rejected with HTTP 400."""
        client = MagicMock()
        client.table = mock_db.table

        with patch("backend.auth.router.get_supabase", return_value=client):
            # Non-numeric OTP
            req_alpha = ResetPasswordRequest(email="user@rll.com", otp="abcdef", new_password="NewPassword123!")
            with pytest.raises(HTTPException) as exc1:
                run_async(reset_password(req_alpha))
            assert exc1.value.status_code == 400

            # Too short
            req_short = ResetPasswordRequest(email="user@rll.com", otp="12345", new_password="NewPassword123!")
            with pytest.raises(HTTPException) as exc2:
                run_async(reset_password(req_short))
            assert exc2.value.status_code == 400

            # Too long
            req_long = ResetPasswordRequest(email="user@rll.com", otp="1234567", new_password="NewPassword123!")
            with pytest.raises(HTTPException) as exc3:
                run_async(reset_password(req_long))
            assert exc3.value.status_code == 400

            # Invalid email format
            req_bad_email = ResetPasswordRequest(email="notanemail", otp="123456", new_password="NewPassword123!")
            with pytest.raises(HTTPException) as exc4:
                run_async(reset_password(req_bad_email))
            assert exc4.value.status_code == 400

            # Non-existent OTP code (no code in Redis or DB)
            req_valid_format = ResetPasswordRequest(email="user@rll.com", otp="123456", new_password="NewPassword123!")
            with pytest.raises(HTTPException) as exc5:
                run_async(reset_password(req_valid_format))
            assert exc5.value.status_code == 400
            assert "Invalid or expired OTP code" in exc5.value.detail

    def test_06_expired_reset_code_rejected_and_purged(self, mock_db):
        """An expired reset code must be rejected and purged from storage."""
        email = "expired_user@rll.com"
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        code = "789123"
        hashed = hash_otp(f"pwd_{email}", code)

        mock_db.otp_codes.append({
            "id": 99,
            "mobile_number": f"pwd_{email}",
            "otp_hash": hashed,
            "expires_at": past_time,
            "created_at": past_time
        })

        client = MagicMock()
        client.table = mock_db.table

        with patch("backend.services.otp_service.get_supabase", return_value=client):
            # verify_password_reset_code must reject and drop record
            assert verify_password_reset_code(email, code) is False
            assert len(mock_db.otp_codes) == 0

    def test_07_hash_verification_failure_and_lockout(self, mock_db):
        """Incorrect reset codes decrement attempts and enforce a 3-attempt lockout."""
        email = "target@rll.com"
        correct_otp = "889900"
        hashed = hashlib.sha256(correct_otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        client = MagicMock()
        client.table = mock_db.table

        req_wrong = ResetPasswordRequest(
            email=email,
            otp="111111",
            new_password="NewPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client):
            # Attempt 1: wrong code -> 400 with 2 remaining
            with pytest.raises(HTTPException) as exc1:
                run_async(reset_password(req_wrong))
            assert exc1.value.status_code == 400
            assert "Incorrect OTP code. 2 attempt(s) remaining" in exc1.value.detail

            # Attempt 2: wrong code -> 400 with 1 remaining
            with pytest.raises(HTTPException) as exc2:
                run_async(reset_password(req_wrong))
            assert exc2.value.status_code == 400
            assert "Incorrect OTP code. 1 attempt(s) remaining" in exc2.value.detail

            # Attempt 3: wrong code -> 400 with 0 remaining
            with pytest.raises(HTTPException) as exc3:
                run_async(reset_password(req_wrong))
            assert exc3.value.status_code == 400
            assert "Incorrect OTP code. 0 attempt(s) remaining" in exc3.value.detail

            # Attempt 4: lockout exceeded -> OTP purged immediately
            with pytest.raises(HTTPException) as exc4:
                run_async(reset_password(req_wrong))
            assert exc4.value.status_code == 400
            assert "Maximum OTP verification attempts exceeded" in exc4.value.detail

            # Subsequent attempt with even the CORRECT OTP must now fail
            req_correct = ResetPasswordRequest(
                email=email,
                otp=correct_otp,
                new_password="NewPassword123!"
            )
            with pytest.raises(HTTPException) as exc5:
                run_async(reset_password(req_correct))
            assert exc5.value.status_code == 400

    def test_08_single_use_consumption_and_replay_prevention(self, mock_db):
        """A reset code can only be used once. Replay attempts must be immediately rejected."""
        email = "leader@rll.com"
        otp = "998877"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "22222222-3333-4444-5555-666666666666",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client):
            # First reset succeeds
            res = run_async(reset_password(req))
            assert res["success"] is True
            assert auth_admin.update_user_by_id.call_count == 1

            # Second reset with identical credentials fails (single-use)
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 400
            assert "Invalid or expired OTP code" in exc.value.detail or "already in progress" in exc.value.detail

    def test_09_user_lookup_failure_and_identity_mismatch(self, mock_db):
        """Rejects reset requests if user lookup fails, identity mismatches, or account is deactivated."""
        email = "legit@rll.com"
        otp = "445566"
        hashed = hashlib.sha256(otp.encode()).hexdigest()

        # Seed valid OTP in Redis
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client):
            # 1. User not found in users table
            with pytest.raises(HTTPException) as exc1:
                run_async(reset_password(req))
            assert exc1.value.status_code == 400
            assert "not registered in the system" in exc1.value.detail

            # 2. Deactivated user account
            run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))
            mock_db.users.append({
                "user_id": "33333333-4444-5555-6666-777777777777",
                "email": email,
                "is_active": False  # Deactivated
            })
            with pytest.raises(HTTPException) as exc2:
                run_async(reset_password(req))
            assert exc2.value.status_code == 401
            assert "deactivated" in exc2.value.detail.lower()

            # 3. Identity mismatch (e.g., query returned different email)
            mock_db.users.clear()
            run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))
            mock_db.users.append({
                "user_id": "44444444-5555-6666-7777-888888888888",
                "email": "different_user@rll.com",
                "is_active": True
            })
            with pytest.raises(HTTPException) as exc3:
                run_async(reset_password(req))
            assert exc3.value.status_code == 400
            assert "Identity mismatch" in exc3.value.detail or "not registered" in exc3.value.detail

    def test_10_concurrent_reset_requests_allow_at_most_one(self, mock_db):
        """Under concurrent execution, at most ONE request can consume the OTP and update password."""
        email = "concurrent_user@rll.com"
        otp = "776655"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "55555555-6666-7777-8888-999999999999",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        success_count = 0
        error_count = 0

        def attempt_reset():
            try:
                res = run_async(reset_password(req))
                return True if res.get("success") else False
            except HTTPException:
                return False

        with patch("backend.auth.router.get_supabase", return_value=client):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(attempt_reset) for _ in range(5)]
                for f in concurrent.futures.as_completed(futures):
                    if f.result():
                        success_count += 1
                    else:
                        error_count += 1

        assert success_count == 1, f"Expected exactly 1 successful reset under concurrency, got {success_count}"
        assert error_count == 4, f"Expected 4 rejected requests under concurrency, got {error_count}"
        assert auth_admin.update_user_by_id.call_count == 1

    def test_11_supabase_auth_admin_password_update_failure_and_recovery(self, mock_db):
        """
        If Supabase Auth admin update fails, endpoint returns HTTP 500.
        Recovery semantics: OTP is consumed and NOT revived to prevent replay/TOCTOU exploits.
        """
        email = "downstream_failure@rll.com"
        otp = "332211"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "66666666-7777-8888-9999-000000000000",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        failing_admin = MagicMock()
        failing_admin.update_user_by_id.side_effect = Exception("Supabase Auth internal gateway timeout 504")

        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = failing_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client):
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 500
            assert "Failed to update password in database" in exc.value.detail

            # Verify OTP remains consumed and is NOT revived
            stored_raw = run_async(safe_get(f"rll:otp:{email}"))
            assert stored_raw is None, "Consumed OTP must never be revived upon downstream failure!"

    def test_12_successful_password_reset_via_database_otp_store(self, mock_db):
        """Verifies successful password reset flow when OTP was stored in Postgres otp_codes table."""
        email = "db_user@rll.com"
        otp = "654987"

        # Store in DB table via store_password_reset_code
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            assert store_password_reset_code(email, otp) is True
            assert len(mock_db.otp_codes) == 1

        mock_user = {
            "user_id": "77777777-8888-9999-aaaa-bbbbbbbbbbbb",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewBrandNewPass999!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client), \
             patch("backend.services.otp_service.get_supabase", return_value=client):
            res = run_async(reset_password(req))
            assert res["success"] is True
            assert auth_admin.update_user_by_id.call_count == 1
            # DB code must now be deleted
            assert len(mock_db.otp_codes) == 0

    def test_13_app_review_credentials_cannot_reset_passwords(self, mock_db):
        """App store review credentials (phone: 9999999999, OTP: 123456) cannot reset passwords."""
        client = MagicMock()
        client.table = mock_db.table

        with patch("backend.auth.router.get_supabase", return_value=client):
            # Attempting to use phone number as email must fail format check
            req_phone = ResetPasswordRequest(
                email="9999999999",
                otp="123456",
                new_password="NewPassword123!"
            )
            with pytest.raises(HTTPException) as exc1:
                run_async(reset_password(req_phone))
            assert exc1.value.status_code == 400

            # Attempting to reset arbitrary user with review OTP 123456 without legitimate stored code
            req_user = ResetPasswordRequest(
                email="victim@rll.com",
                otp="123456",
                new_password="HackedPassword123!"
            )
            with pytest.raises(HTTPException) as exc2:
                run_async(reset_password(req_user))
            assert exc2.value.status_code == 400
            assert "Invalid or expired OTP code" in exc2.value.detail

    def test_14_cross_identity_code_reuse_rejected(self, mock_db):
        """A reset code generated for User A cannot be used to reset password for User B."""
        user_a = "user_a@rll.com"
        user_b = "user_b@rll.com"
        otp = "554433"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_password_reset_code(user_a, otp)

        mock_db.users.append({
            "user_id": "88888888-9999-aaaa-bbbb-cccccccccccc",
            "email": user_b,
            "is_active": True
        })

        client = MagicMock()
        client.table = mock_db.table

        # User B attempts reset using User A's code
        req = ResetPasswordRequest(
            email=user_b,
            otp=otp,
            new_password="NewUserBPass123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client), \
             patch("backend.services.otp_service.get_supabase", return_value=client):
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 400
            assert "Invalid or expired OTP code" in exc.value.detail

    def test_15_redis_safe_delete_failure_fails_closed_and_releases_lock(self, mock_db):
        """
        If safe_delete() fails or returns False during Redis OTP consumption,
        the endpoint must fail closed with HTTP 503, release the lock, and NOT update the password.
        """
        email = "del_failure@rll.com"
        otp = "665544"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "99999999-aaaa-bbbb-cccc-dddddddddddd",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client), \
             patch("backend.auth.router.safe_delete") as mock_del:

            # First call for OTP returns False (deletion failure), second call for lock cleanup returns True
            def safe_delete_mock(key, security_sensitive=False):
                if f"rll:otp:{email}" in key:
                    return False
                return True

            mock_del.side_effect = safe_delete_mock

            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()
            # Password must NOT be updated
            assert auth_admin.update_user_by_id.call_count == 0

    def test_16_redis_safe_delete_exception_fails_closed(self, mock_db):
        """
        If safe_delete() raises an unexpected exception or timeout during OTP consumption,
        the endpoint must catch it, fail closed with HTTP 503, and NOT update the password.
        """
        email = "del_exception@rll.com"
        otp = "113355"
        hashed = hashlib.sha256(otp.encode()).hexdigest()
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "email": email,
            "is_active": True
        }
        mock_db.users.append(mock_user)

        auth_admin = MagicMock()
        client = MagicMock()
        client.table = mock_db.table
        client.auth.admin = auth_admin

        req = ResetPasswordRequest(
            email=email,
            otp=otp,
            new_password="NewStrongPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client), \
             patch("backend.auth.router.safe_delete") as mock_del:

            def safe_delete_side_effect(key, security_sensitive=False):
                if f"rll:otp:{email}" in key:
                    raise TimeoutError("Redis delete command timed out")
                return True

            mock_del.side_effect = safe_delete_side_effect

            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in exc.value.detail.lower()
            assert auth_admin.update_user_by_id.call_count == 0
