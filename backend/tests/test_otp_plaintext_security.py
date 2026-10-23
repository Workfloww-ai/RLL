import asyncio
import concurrent.futures
import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.core.config import settings
from backend.services.otp_service import (
    generate_6digit_otp,
    sanitize_phone,
    send_otp_sms,
    cleanup_expired_otps,
    store_otp_in_db,
    verify_otp_from_db,
    store_password_reset_code,
    verify_password_reset_code,
    hash_otp,
    verify_otp_hash,
)
from backend.mobile.router import (
    SendOTPRequest,
    VerifyOTPRequest,
    send_mobile_otp,
    verify_mobile_otp,
)
from backend.auth.router import reset_password, ResetPasswordRequest


def run_async(coro):
    """Run an async coroutine synchronously in pytest."""
    return asyncio.run(coro)


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
    return MockDatabase()


class TestOTPPlaintextRemediation:
    """Security verification test suite for Item 10: OTP Stored in Plaintext Remediation."""

    def test_01_normal_otp_stored_as_hmac_hash_never_plaintext(self, mock_db):
        """Verify normal mobile OTP is stored as 64-char HMAC hash, NEVER plaintext."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            phone = "9876543210"
            raw_otp = "482910"

            success = store_otp_in_db(phone, raw_otp)
            assert success is True
            assert len(mock_db.otp_codes) == 1

            stored_record = mock_db.otp_codes[0]
            stored_hash = stored_record["otp_hash"]

            # Must NOT be plaintext
            assert stored_hash != raw_otp, "CRITICAL: Plaintext OTP was stored in database!"
            assert len(stored_hash) == 64, "Stored hash must be 64-hex-char SHA-256 HMAC digest!"
            assert stored_hash == hash_otp(phone, raw_otp), "Stored value must match keyed HMAC!"

    def test_02_password_reset_code_stored_as_hmac_hash_never_plaintext(self, mock_db):
        """Verify password reset recovery code is stored as 64-char HMAC hash, NEVER plaintext."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            email = "analyst@rll.com"
            raw_code = "981273"

            success = store_password_reset_code(email, raw_code)
            assert success is True
            assert len(mock_db.otp_codes) == 1

            stored_record = mock_db.otp_codes[0]
            stored_hash = stored_record["otp_hash"]

            assert stored_hash != raw_code, "CRITICAL: Plaintext reset code was stored in database!"
            assert len(stored_hash) == 64, "Stored hash must be 64-hex-char SHA-256 HMAC digest!"
            assert stored_hash == hash_otp(f"pwd_{email}", raw_code)

    def test_03_correct_otp_verifies_successfully_incorrect_otp_fails(self, mock_db):
        """Verify correct OTP succeeds against HMAC hash and incorrect OTP fails."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            phone = "9876543210"
            correct_otp = "192837"

            store_otp_in_db(phone, correct_otp)

            # Incorrect OTP fails
            assert verify_otp_from_db(phone, "999999") is False
            assert verify_otp_from_db(phone, "192838") is False
            assert verify_otp_from_db(phone, "") is False

            # Correct OTP succeeds
            assert verify_otp_from_db(phone, correct_otp) is True

    def test_04_expired_otp_fails_and_is_purged(self, mock_db):
        """Verify expired OTP record fails verification and is immediately deleted."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            phone = "9876543210"
            otp = "654321"
            past_time = datetime.now(timezone.utc) - timedelta(minutes=10)

            # Insert expired hashed record
            mock_db.otp_codes.append({
                "id": 1,
                "mobile_number": phone,
                "otp_hash": hash_otp(phone, otp),
                "expires_at": past_time.isoformat(),
                "created_at": (past_time - timedelta(minutes=5)).isoformat()
            })

            assert verify_otp_from_db(phone, otp) is False
            assert len(mock_db.otp_codes) == 0, "Expired OTP record must be dropped!"

    def test_05_otp_is_single_use_replay_fails(self, mock_db):
        """Verify single-use consumption: replay attempt fails immediately."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            phone = "9876543210"
            otp = "771122"

            store_otp_in_db(phone, otp)
            assert verify_otp_from_db(phone, otp) is True
            assert len(mock_db.otp_codes) == 0, "Record must be deleted upon successful verification."

            # Replay attempt fails
            assert verify_otp_from_db(phone, otp) is False

    def test_06_concurrent_otp_verification_allows_at_most_one_consumption(self, mock_db):
        """Verify race condition protection: concurrent verification consumes exactly once."""
        phone = "9876543210"
        otp = "334455"

        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            store_otp_in_db(phone, otp)
            assert len(mock_db.otp_codes) == 1

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(verify_otp_from_db, phone, otp) for _ in range(5)]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())

            success_count = sum(1 for r in results if r is True)
            failure_count = sum(1 for r in results if r is False)
            assert success_count == 1, f"Expected exactly 1 success under concurrency, got {success_count}"
            assert failure_count == 4, f"Expected 4 failures under concurrency, got {failure_count}"
            assert len(mock_db.otp_codes) == 0

    def test_07_otps_never_appear_in_logs_or_errors(self, caplog):
        """Verify OTPs are redacted from log messages, error bodies, and tracebacks."""
        caplog.set_level(logging.INFO)
        test_otp = "928374"
        run_async(send_otp_sms("9876543210", test_otp))

        log_messages = [rec.message for rec in caplog.records]
        for msg in log_messages:
            assert f"OTP Code: {test_otp}" not in msg, "Plaintext OTP found in log output!"
            assert f"[{test_otp}]" not in msg, "Plaintext bracketed OTP found in log output!"
            assert f"code={test_otp}" not in msg

    def test_08_missing_hmac_secrets_fail_closed(self, mock_db):
        """Verify fail-closed behavior when HMAC secret is missing or empty."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.OTP_HMAC_SECRET", ""), \
             patch("backend.core.config.settings.JWT_SECRET", ""):

            # Hashing must raise RuntimeError or fail closed
            with pytest.raises(RuntimeError):
                hash_otp("9876543210", "123456")

            # store_otp_in_db must return False
            assert store_otp_in_db("9876543210", "123456") is False

            # verify_otp_hash must return False
            assert verify_otp_hash("9876543210", "123456", "dummyhash") is False

            # verify_otp_from_db must return False
            assert verify_otp_from_db("9876543210", "123456") is False

            # verify_password_reset_code must return False
            assert verify_password_reset_code("user@rll.com", "123456") is False

    def test_09_unavailable_storage_fails_closed(self):
        """Verify verification fails closed when database client is None."""
        with patch("backend.services.otp_service.get_supabase", return_value=None):
            assert verify_otp_from_db("9876543210", "123456") is False
            assert verify_password_reset_code("user@rll.com", "123456") is False
            assert store_otp_in_db("9876543210", "123456") is False

    def test_10_legacy_plaintext_records_in_db_fail_closed(self, mock_db):
        """Verify legacy plaintext OTPs in database (from prior insecure code) are rejected."""
        with patch("backend.services.otp_service.get_supabase", return_value=mock_db):
            phone = "9876543210"
            legacy_plaintext_otp = "123456"

            # Injected legacy record with plaintext in otp_hash column
            mock_db.otp_codes.append({
                "id": 50,
                "mobile_number": phone,
                "otp_hash": legacy_plaintext_otp,  # 6-char plaintext string
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            # Verification must FAIL because HMAC hash comparison fails against plaintext
            assert verify_otp_from_db(phone, legacy_plaintext_otp) is False

    def test_11_cross_identifier_hash_isolation(self):
        """Verify that identical OTP codes produce distinct HMAC hashes for different users/phones."""
        shared_otp = "654321"
        hash_user1 = hash_otp("9876543210", shared_otp)
        hash_user2 = hash_otp("9123456789", shared_otp)
        hash_email = hash_otp("pwd_analyst@rll.com", shared_otp)

        assert hash_user1 != hash_user2, "Hashes must be isolated by identifier!"
        assert hash_user1 != hash_email, "Hashes must be isolated by domain prefix!"

    def test_12_review_login_separate_from_normal_otp_storage(self, mock_db):
        """Verify Google Play / App Store review login does NOT write plaintext records to otp_codes."""
        with patch("backend.mobile.router.get_supabase", return_value=mock_db), \
             patch("backend.services.otp_service.get_supabase", return_value=mock_db), \
             patch("backend.core.config.settings.APP_REVIEW_MODE_ENABLED", True):

            # store_otp_in_db preserves record without adding plaintext row
            stored = store_otp_in_db("9999999999", "123456")
            assert stored is True
            assert len(mock_db.otp_codes) == 0, "Review login must never write plaintext rows to otp_codes!"

            # send_mobile_otp succeeds without writing to otp_codes
            send_res = run_async(send_mobile_otp(SendOTPRequest(phone="9999999999")))
            assert send_res["success"] is True
            assert len(mock_db.otp_codes) == 0

            # verify_mobile_otp succeeds
            verify_res = run_async(verify_mobile_otp(VerifyOTPRequest(phone="9999999999", otp="123456")))
            assert "access_token" in verify_res
            assert verify_res["user"]["phone"] == "+919999999999"
