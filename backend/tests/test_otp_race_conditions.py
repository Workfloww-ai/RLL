import pytest
import hmac
import hashlib
import json
import logging
import asyncio
import threading
import concurrent.futures
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from backend.core.config import settings
from backend.services.otp_service import (
    store_otp_in_db,
    verify_otp_from_db,
    store_password_reset_code,
    verify_password_reset_code,
    hash_otp,
    verify_otp_hash,
    cleanup_expired_otps,
    _otp_lock,
    _failed_attempts,
    _consuming_records
)
from backend.auth.router import reset_password, ResetPasswordRequest
from backend.mobile.router import send_mobile_otp, verify_mobile_otp, SendOTPRequest, VerifyOTPRequest
from backend.db.redis_client import (
    safe_get,
    safe_set,
    safe_delete,
    safe_set_nx,
    safe_incr,
    safe_get_and_delete,
    _in_memory_store,
    _in_memory_expiry,
    _in_memory_lock
)


def run_async(coro):
    """Helper to run async coroutines synchronously in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class MockDatabase:
    """Thread-safe in-memory table simulator for otp_codes and users queries."""

    def __init__(self):
        self._lock = threading.Lock()
        self.otp_codes = []  # list of dicts: id, mobile_number, otp_hash, expires_at, created_at
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
    db = MockDatabase()
    with _otp_lock:
        _failed_attempts.clear()
        _consuming_records.clear()
    _in_memory_store.clear()
    _in_memory_expiry.clear()
    return db


class TestOTPRaceConditions:
    """
    Security Audit Item 11: Verification of OTP Race Conditions,
    Atomic Consumption, Rate Limiting, and Concurrency Controls.
    """

    def test_01_concurrent_otp_consumption_allows_at_most_one(self, mock_db):
        """
        Verify that when 10 concurrent requests attempt to consume the same OTP simultaneously,
        exactly ONE succeeds, 9 fail, and the OTP is consumed single-use.
        """
        phone = "9876543210"
        otp = "789012"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_otp_in_db(phone, otp)
            assert len(mock_db.otp_codes) == 1

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(verify_otp_from_db, phone, otp) for _ in range(10)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            assert sum(1 for r in results if r is True) == 1, "Exactly one concurrent verification must succeed"
            assert sum(1 for r in results if r is False) == 9, "All subsequent/concurrent requests must fail"
            assert len(mock_db.otp_codes) == 0, "OTP record must be dropped immediately on consumption"

    def test_02_concurrent_resend_and_verification(self, mock_db):
        """
        Verify that concurrent resend replaces the OTP and invalidates the previous OTP.
        An old OTP cannot be revived or successfully verified once replacement occurs.
        """
        phone = "9876543210"
        old_otp = "111111"
        new_otp = "222222"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_otp_in_db(phone, old_otp)

            # Store new OTP replaces the old one
            store_otp_in_db(phone, new_otp)

            # Old OTP must fail
            assert verify_otp_from_db(phone, old_otp) is False
            # New OTP can be consumed
            assert verify_otp_from_db(phone, new_otp) is True
            # Second attempt with new OTP fails (single use)
            assert verify_otp_from_db(phone, new_otp) is False

    def test_03_concurrent_incorrect_attempts_enforce_lockout_rate_limit(self, mock_db):
        """
        Verify that concurrent incorrect attempts increment the failed-attempt counter atomically.
        Once 5 failed attempts are reached, lockout is triggered and the OTP record is purged.
        """
        phone = "9876543210"
        valid_otp = "654321"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_otp_in_db(phone, valid_otp)
            assert len(mock_db.otp_codes) == 1

            # Submit 10 concurrent bad guesses
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(verify_otp_from_db, phone, f"99999{i}") for i in range(10)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            # All bad guesses must fail
            assert all(r is False for r in results)
            # The record must have been purged from the database due to lockout
            assert len(mock_db.otp_codes) == 0, "Record must be dropped from database upon lockout"

            # Even with the correct OTP now, verification must fail
            assert verify_otp_from_db(phone, valid_otp) is False

    def test_04_concurrent_password_reset_verification_single_use(self, mock_db):
        """
        Verify that concurrent calls to verify_password_reset_code permit at most ONE consumption.
        """
        email = "analyst@rll.com"
        code = "456789"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_password_reset_code(email, code)
            assert len(mock_db.otp_codes) == 1

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(verify_password_reset_code, email, code) for _ in range(6)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            assert sum(1 for r in results if r is True) == 1
            assert sum(1 for r in results if r is False) == 5
            assert len(mock_db.otp_codes) == 0

    def test_05_concurrent_password_reset_endpoint_single_consumption(self, mock_db):
        """
        Verify that concurrent requests to /api/v1/auth/reset-password with the valid OTP
        permit exactly ONE password reset. The second request is rejected due to single-use consumption.
        """
        email = "executive@rll.com"
        otp = "333444"
        hashed = hashlib.sha256(otp.encode()).hexdigest()

        # Seed Redis with valid OTP record
        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        mock_user = {
            "user_id": "88888888-4444-4444-4444-888888888888",
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
            new_password="NewSecurePassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=client):
            # First reset request succeeds
            res1 = run_async(reset_password(req))
            assert res1["success"] is True
            assert auth_admin.update_user_by_id.call_count == 1

            # Second request with same OTP immediately fails (already consumed)
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 400
            assert "Invalid or expired OTP code" in exc.value.detail or "already in progress" in exc.value.detail

    def test_06_concurrent_password_reset_lockout_enforcement(self, mock_db):
        """
        Verify that concurrent incorrect password-reset requests enforce the 3-attempt lockout.
        Subsequent attempts are blocked and the OTP is purged.
        """
        email = "locked@rll.com"
        valid_otp = "123456"
        hashed = hashlib.sha256(valid_otp.encode()).hexdigest()

        run_async(safe_set(f"rll:otp:{email}", json.dumps({"hash": hashed, "attempts": 0}), ttl=600))

        req_wrong = ResetPasswordRequest(
            email=email,
            otp="999999",
            new_password="NewPassword123!"
        )

        with patch("backend.auth.router.get_supabase", return_value=mock_db):
            # Attempt 1: fails
            with pytest.raises(HTTPException) as exc1:
                run_async(reset_password(req_wrong))
            assert exc1.value.status_code == 400
            assert "Incorrect OTP" in exc1.value.detail

            # Attempt 2: fails
            with pytest.raises(HTTPException) as exc2:
                run_async(reset_password(req_wrong))
            assert exc2.value.status_code == 400

            # Attempt 3: fails
            with pytest.raises(HTTPException) as exc3:
                run_async(reset_password(req_wrong))
            assert exc3.value.status_code == 400

            # Attempt 4: Lockout exceeded
            with pytest.raises(HTTPException) as exc4:
                run_async(reset_password(req_wrong))
            assert exc4.value.status_code == 400
            assert "Maximum OTP verification attempts exceeded" in exc4.value.detail

            # OTP must be purged from Redis
            assert run_async(safe_get(f"rll:otp:{email}")) is None

    def test_07_expired_and_consumed_otps_cannot_be_reused(self, mock_db):
        """
        Verify expired OTPs fail closed and are purged from database, and consumed OTPs cannot be replayed.
        """
        phone = "9876543210"
        otp = "112233"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            # Inject expired OTP record
            expired_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            mock_db.otp_codes.append({
                "id": 1,
                "mobile_number": phone,
                "otp_hash": hash_otp(phone, otp),
                "expires_at": expired_time,
                "created_at": expired_time
            })

            # Expired OTP verification must return False and drop record
            assert verify_otp_from_db(phone, otp) is False
            assert len(mock_db.otp_codes) == 0

            # Store fresh OTP
            store_otp_in_db(phone, "445566")
            assert verify_otp_from_db(phone, "445566") is True
            # Replay attempt fails immediately
            assert verify_otp_from_db(phone, "445566") is False

    def test_08_database_and_redis_failures_fail_closed(self, mock_db):
        """
        Verify that database and Redis failures fail closed for all security-sensitive verification paths.
        """
        # 1. DB Client is None
        with patch("backend.services.otp_service.get_supabase", return_value=None):
            assert verify_otp_from_db("9876543210", "123456") is False
            assert verify_password_reset_code("user@rll.com", "123456") is False
            assert store_otp_in_db("9876543210", "123456") is False

        # 2. DB Query throws exception
        faulty_db = MagicMock()
        faulty_db.table.side_effect = RuntimeError("Database connection timed out")
        with patch("backend.services.otp_service.get_supabase", return_value=faulty_db):
            assert verify_otp_from_db("9876543210", "123456") is False
            assert verify_password_reset_code("user@rll.com", "123456") is False

        # 3. Redis missing in reset_password
        req = ResetPasswordRequest(
            email="failclosed@rll.com",
            otp="123456",
            new_password="Password123!"
        )
        with patch("backend.db.redis_client.safe_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc:
                run_async(reset_password(req))
            assert exc.value.status_code == 400

    def test_09_review_login_gating_and_isolation_under_concurrency(self, mock_db):
        """
        Verify that review login (9999999999 + 123456):
        1. Works under concurrency when APP_REVIEW_MODE_ENABLED=True.
        2. Never writes plaintext or hashed rows to otp_codes table.
        3. Fails when invalid OTP is provided.
        4. Fails closed when APP_REVIEW_MODE_ENABLED=False.
        """
        review_phone = "9999999999"
        review_otp = "123456"

        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.mobile.router.get_supabase", return_value=mock_db):

            # 1. Concurrent review login attempts all succeed without DB writes
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(verify_otp_from_db, review_phone, review_otp) for _ in range(5)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            assert all(r is True for r in results)
            assert len(mock_db.otp_codes) == 0, "Review login must never write rows to otp_codes table"

            # 2. Invalid OTP on review phone fails
            assert verify_otp_from_db(review_phone, "000000") is False

        # 3. Review login fails closed when disabled
        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", False), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            assert verify_otp_from_db(review_phone, review_otp) is False

    def test_10_resend_cooldown_blocks_rapid_duplicate_requests(self, mock_db):
        """
        Verify that send_mobile_otp enforces a resend cooldown (30s) and blocks rapid duplicate requests.
        """
        mock_user = {
            "user_id": "11111111-2222-3333-4444-555555555555",
            "email": "field.tsm@rll.com",
            "phone": "+919876543210",
            "is_active": True,
            "tenant_id": "tenant-real-12345",
            "company_name": "Rajasthan Liquor Limited"
        }
        mock_db.users.append(mock_user)

        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.mobile.router.send_otp_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = True

            req = SendOTPRequest(phone="9876543210", email=None)

            # First send succeeds
            res1 = run_async(send_mobile_otp(req))
            assert res1["success"] is True

            # Rapid duplicate send immediately hits cooldown
            with pytest.raises(HTTPException) as exc:
                run_async(send_mobile_otp(req))
            assert exc.value.status_code == 429
            assert "Please wait 30 seconds" in exc.value.detail

    def test_11_redis_outage_fails_closed_in_production_for_rate_limits(self, mock_db):
        """
        Verify that in production/staging environments, a Redis outage causes
        security-sensitive endpoints (verify-otp, reset-password, send-otp) to FAIL CLOSED (HTTP 503)
        rather than falling back to per-process in-memory counters that would bypass distributed rate limits.
        """
        phone = "9876543210"
        email = "production_victim@rll.com"

        mock_user = {
            "user_id": "99999999-5555-5555-5555-999999999999",
            "email": email,
            "phone": f"+91{phone}",
            "is_active": True,
            "tenant_id": "tenant-prod-12345",
            "company_name": "Rajasthan Liquor Limited"
        }
        mock_db.users.append(mock_user)

        with patch("backend.core.config.settings.ENVIRONMENT", "production"), \
             patch("backend.db.redis_client.get_redis", return_value=None), \
             patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.auth.router.get_supabase", return_value=mock_db):

            # 1. verify_mobile_otp must fail closed (HTTP 503)
            with pytest.raises(HTTPException) as exc_v:
                run_async(verify_mobile_otp(VerifyOTPRequest(phone=phone, otp="123456")))
            assert exc_v.value.status_code == 503
            assert "temporarily unavailable" in exc_v.value.detail

            # 2. reset_password must fail closed (HTTP 503)
            with pytest.raises(HTTPException) as exc_r:
                run_async(reset_password(ResetPasswordRequest(
                    email=email,
                    otp="123456",
                    new_password="NewSecurePassword123!"
                )))
            assert exc_r.value.status_code == 503
            assert "temporarily unavailable" in exc_r.value.detail

            # 3. send_mobile_otp must fail closed (HTTP 503) because distributed cooldown cannot be established
            with pytest.raises(HTTPException) as exc_s:
                run_async(send_mobile_otp(SendOTPRequest(phone=phone, email=None)))
            assert exc_s.value.status_code == 503
            assert "temporarily unavailable" in exc_s.value.detail

    def test_12_non_security_cache_degrades_gracefully_during_redis_outage(self):
        """
        Verify that non-security cache operations degrade gracefully (do not raise 503)
        when Redis is unavailable in production.
        """
        with patch("backend.core.config.settings.ENVIRONMENT", "production"), \
             patch("backend.db.redis_client.get_redis", return_value=None):

            # Non-security safe_get returns in-memory or None without crashing
            res_get = run_async(safe_get("rll:cache:analytics:summary", security_sensitive=False))
            assert res_get is None

            # Non-security safe_set returns True without crashing
            res_set = run_async(safe_set("rll:cache:analytics:summary", "cached_data", ttl=60, security_sensitive=False))
            assert res_set is True

    def test_13_new_otp_resend_cannot_reset_failed_attempt_counter_or_bypass_lockout(self, mock_db):
        """
        Verify that requesting a new OTP (or calling store_otp_in_db) DOES NOT reset
        the accumulated failed-attempt counter. This prevents an attacker from obtaining
        unlimited guesses by alternating between guessing and resending.
        """
        phone = "9876543210"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            # Store initial OTP
            store_otp_in_db(phone, "111111")

            # Make 4 incorrect attempts
            for i in range(4):
                assert verify_otp_from_db(phone, f"99999{i}") is False

            # Verify 4 failed attempts are recorded
            with _otp_lock:
                assert _failed_attempts[phone]["count"] == 4

            # Attacker triggers a resend / new OTP generation
            store_otp_in_db(phone, "222222")

            # Crucial: Failed attempts counter must NOT have been wiped to 0
            with _otp_lock:
                assert _failed_attempts[phone]["count"] == 4, "Resend must not reset failed attempt counter!"

            # 5th attempt (even on the new OTP) triggers lockout
            assert verify_otp_from_db(phone, "888888") is False
            with _otp_lock:
                assert _failed_attempts[phone]["count"] >= 5

            # Subsequent attempts are locked out immediately, even with the correct new OTP!
            assert verify_otp_from_db(phone, "222222") is False

    def test_14_locked_out_account_cannot_request_new_otp(self, mock_db):
        """
        Verify that once an account is locked out from 5 failed attempts,
        calling send_mobile_otp or store_otp_in_db is rejected.
        """
        phone = "9876543210"
        email = "victim.locked@rll.com"

        mock_user = {
            "user_id": "33333333-3333-3333-3333-333333333333",
            "email": email,
            "phone": f"+91{phone}",
            "is_active": True,
            "tenant_id": "tenant-test-12345",
            "company_name": "Rajasthan Liquor Limited"
        }
        mock_db.users.append(mock_user)

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.mobile.router.get_supabase", return_value=mock_db):

            # Simulate 5 failed attempts recorded in attempt tracking
            with _otp_lock:
                _failed_attempts[phone] = {
                    "count": 5,
                    "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
                }
            run_async(safe_set(f"rll:mobile_otp_attempts:{phone}", "5", ttl=300))

            # 1. store_otp_in_db must reject
            assert store_otp_in_db(phone, "123456") is False

            # 2. send_mobile_otp must raise HTTP 429 Lockout
            with pytest.raises(HTTPException) as exc:
                run_async(send_mobile_otp(SendOTPRequest(phone=phone, email=None)))
            assert exc.value.status_code == 429
            assert "temporarily locked out" in exc.value.detail

    def test_15_atomic_incr_lua_script_ttl_establishment(self):
        """
        Verify safe_incr establishes TTL atomically on initial key creation (current == 1)
        and subsequent increments do not reset or extend the TTL.
        """
        key = "rll:test:atomic_counter"
        run_async(safe_delete(key))

        # First increment creates key and sets TTL
        val1 = run_async(safe_incr(key, ttl=300))
        assert val1 == 1
        with _in_memory_lock:
            assert key in _in_memory_expiry
            initial_exp = _in_memory_expiry[key]

        # Second increment increments counter without altering initial TTL
        val2 = run_async(safe_incr(key, ttl=300))
        assert val2 == 2
        with _in_memory_lock:
            assert _in_memory_expiry[key] == initial_exp, "Subsequent increments must not extend TTL!"

        # Third increment
        val3 = run_async(safe_incr(key, ttl=300))
        assert val3 == 3
        with _in_memory_lock:
            assert _in_memory_expiry[key] == initial_exp

        run_async(safe_delete(key))

    def test_16_review_login_identity_strictly_isolated_from_privileged_and_tenant_data(self, mock_db):
        """
        Verify that review credentials (9999999999 + 123456) produce an isolated demo session
        that cannot access administrative endpoints or real tenant data.
        """
        from backend.core.security import decode_access_token

        with patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True), \
             patch("backend.mobile.router.get_supabase", return_value=mock_db):

            res = run_async(verify_mobile_otp(VerifyOTPRequest(phone="9999999999", otp="123456")))
            assert "access_token" in res

            token_payload = decode_access_token(res["access_token"])
            assert token_payload is not None
            assert token_payload.get("is_review_user") is True
            assert token_payload.get("tenant_id") == settings.APP_REVIEW_DEMO_TENANT_ID
            assert token_payload.get("tenant_id") != "real-tenant-production"

