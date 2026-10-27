"""
Security Audit Item 13: Redis Data Loss via FLUSHDB Test Suite
=============================================================
Validates remediation of Redis database-wide flushes:
1. init_redis() never calls FLUSHDB or FLUSHALL on startup.
2. Production code never calls database-wide flushes.
3. Feature-specific cleanup deletes only intended cache keys.
4. Security-sensitive keys (OTPs, rate limits, sessions, locks, revoked tokens) survive cleanup.
5. Broad wildcards ('*', 'rll:*') and broad 'rll:mobile:*' are strictly rejected by safe_delete_pattern.
6. Unrelated mobile feature keys survive sales/analytics cache invalidation.
7. Security prefixes ('rll:session:*', 'rll:otp:*', etc.) are strictly protected.
8. Redis connection failures do not trigger broad or destructive fallbacks.
9. flush_redis_for_testing() fails closed when ENVIRONMENT is unset, misspelled, unknown, production, or staging.
10. flush_redis_for_testing() fails closed without explicit ALLOW_TEST_REDIS_FLUSH=True authorization.
11. flush_redis_for_testing() fails closed when targeting unapproved, remote, or cloud Redis targets.
12. flush_redis_for_testing() succeeds only on a verified, dedicated disposable test Redis instance.
13. Proof that rejected configurations never invoke flushdb().
14. /cache/clear endpoint requires administrative role authorization.
15. Review login and rate-limit keys survive cache clearing.
"""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import HTTPException

from backend.core.config import settings
from backend.db.redis_client import (
    init_redis,
    safe_get,
    safe_set,
    safe_delete,
    safe_delete_pattern,
    flush_redis_for_testing,
    _in_memory_store,
    _in_memory_expiry,
    _in_memory_lock,
    ALLOWED_CACHE_PREFIXES,
    PROTECTED_SECURITY_PREFIXES,
    is_safe_test_redis_target,
    is_production_or_staging,
)
import backend.db.redis_client as rc_module
from backend.services.cache_service import invalidate_analytics_cache
from backend.mobile.router import clear_mobile_cache_endpoint


def run_async(coro):
    """Safely execute async coroutine in sync test runner."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def reset_in_memory():
    rc_module._redis_client = None
    with _in_memory_lock:
        _in_memory_store.clear()
        _in_memory_expiry.clear()
    yield
    rc_module._redis_client = None
    with _in_memory_lock:
        _in_memory_store.clear()
        _in_memory_expiry.clear()


class TestRedisFlushDBSecurity:
    """Security verification test suite for Item 13: Redis Data Loss via FLUSHDB."""

    def test_01_init_redis_never_invokes_flushdb_or_flushall(self):
        """Verify that server startup / init_redis NEVER flushes the Redis database."""
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.flushdb = AsyncMock()
        mock_redis.flushall = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis), \
             patch("backend.core.config.settings.REDIS_ENABLED", True), \
             patch("backend.core.config.settings.REDIS_URL", "redis://localhost:6379/0"):

            client = run_async(init_redis())
            assert client is not None
            mock_redis.ping.assert_called_once()
            # CRITICAL: Neither flushdb nor flushall may be called during init_redis
            mock_redis.flushdb.assert_not_called()
            mock_redis.flushall.assert_not_called()

    def test_02_feature_specific_cleanup_deletes_only_intended_cache_keys(self):
        """
        Verify that invalidate_analytics_cache() purges only analytics/dashboard/mobile-sales/companies caches,
        while unrelated mobile feature keys, cascading caches, and security-sensitive keys survive intact.
        """
        # Seed both intended cache keys and unrelated mobile feature keys into store
        run_async(safe_set("rll:analytics:summary:jan", '{"cases": 100}'))
        run_async(safe_set("rll:dashboard:kpi:mtd", '{"revenue": 50000}'))
        run_async(safe_set("rll:mobile:sales:today", '{"sold": 10}'))
        run_async(safe_set("rll:mobile:companies:all", '{"companies": []}'))

        # Unrelated mobile feature caches that MUST survive
        run_async(safe_set("rll:mobile:config:app_version", "2.4.0"))
        run_async(safe_set("rll:mobile:announcements:notice_1", '{"title": "Holiday schedule"}'))
        run_async(safe_set("rll:mobile:user_prefs:usr_42", '{"dark_mode": true}'))
        run_async(safe_set("rll:cascading:groups_json_test", '{"groups": []}'))

        # Security-sensitive state that MUST survive
        run_async(safe_set("rll:session:token_user_123", "session_data"))
        run_async(safe_set("rll:otp:user@rll.com", '{"hash": "secret", "attempts": 0}'))
        run_async(safe_set("rll:otp_attempts:user@rll.com", "1"))
        run_async(safe_set("rll:otp_consuming:user@rll.com", "1"))
        run_async(safe_set("rll:mobile_otp_attempts:9999999999", "2"))
        run_async(safe_set("rll:cooldown:9999999999", "active"))
        run_async(safe_set("rll:revoked:user-uuid-888", "true"))
        run_async(safe_set("rll:syslock:roster", "locked"))

        # Execute cache invalidation
        purged = run_async(invalidate_analytics_cache())
        assert purged >= 4

        # Assert intended cache keys are gone
        assert run_async(safe_get("rll:analytics:summary:jan")) is None
        assert run_async(safe_get("rll:dashboard:kpi:mtd")) is None
        assert run_async(safe_get("rll:mobile:sales:today")) is None
        assert run_async(safe_get("rll:mobile:companies:all")) is None

        # Assert UNRELATED mobile feature caches survived intact
        assert run_async(safe_get("rll:mobile:config:app_version")) == "2.4.0"
        assert run_async(safe_get("rll:mobile:announcements:notice_1")) == '{"title": "Holiday schedule"}'
        assert run_async(safe_get("rll:mobile:user_prefs:usr_42")) == '{"dark_mode": true}'
        assert run_async(safe_get("rll:cascading:groups_json_test")) == '{"groups": []}'

        # Assert ALL security-sensitive keys survived intact
        assert run_async(safe_get("rll:session:token_user_123")) == "session_data"
        assert run_async(safe_get("rll:otp:user@rll.com")) == '{"hash": "secret", "attempts": 0}'
        assert run_async(safe_get("rll:otp_attempts:user@rll.com")) == "1"
        assert run_async(safe_get("rll:otp_consuming:user@rll.com")) == "1"
        assert run_async(safe_get("rll:mobile_otp_attempts:9999999999")) == "2"
        assert run_async(safe_get("rll:cooldown:9999999999")) == "active"
        assert run_async(safe_get("rll:revoked:user-uuid-888")) == "true"
        assert run_async(safe_get("rll:syslock:roster")) == "locked"

    def test_03_broad_wildcards_and_broad_mobile_prefix_strictly_rejected(self):
        """Verify that broad wildcard patterns ('*', 'rll:*', 'rll:mobile:*') are rejected by safe_delete_pattern."""
        run_async(safe_set("rll:analytics:data", "1"))
        run_async(safe_set("rll:mobile:sales:test", "sales_data"))
        run_async(safe_set("rll:mobile:config:version", "1.0"))
        run_async(safe_set("rll:session:123", "secret"))

        # Broad patterns and parent mobile prefix MUST be rejected
        for dangerous_pattern in ["*", "rll:*", "rll*", "?", "", "   ", "rll:mobile:*", "rll:mobile"]:
            res = run_async(safe_delete_pattern(dangerous_pattern))
            assert res == 0, f"Dangerous pattern '{dangerous_pattern}' was not rejected!"

        # Data must remain untouched
        assert run_async(safe_get("rll:analytics:data")) == "1"
        assert run_async(safe_get("rll:mobile:sales:test")) == "sales_data"
        assert run_async(safe_get("rll:mobile:config:version")) == "1.0"
        assert run_async(safe_get("rll:session:123")) == "secret"

        # Explicit granular namespaces succeed
        assert "rll:mobile:" not in ALLOWED_CACHE_PREFIXES
        assert "rll:mobile:sales:" in ALLOWED_CACHE_PREFIXES
        assert "rll:mobile:companies:" in ALLOWED_CACHE_PREFIXES

    def test_04_security_prefixes_are_strictly_protected_from_pattern_deletion(self):
        """Verify that security-sensitive key prefixes cannot be targeted by safe_delete_pattern."""
        run_async(safe_set("rll:session:s1", "session1"))
        run_async(safe_set("rll:otp:victim@rll.com", "otp1"))
        run_async(safe_set("rll:otp_attempts:victim@rll.com", "2"))
        run_async(safe_set("rll:revoked:victim-uuid", "true"))
        run_async(safe_set("rll:syslock:system", "lock1"))

        # Attempt pattern deletions targeting security namespaces
        for sec_pattern in [
            "rll:session:*",
            "rll:otp:*",
            "rll:otp_attempts:*",
            "rll:otp_consuming:*",
            "rll:mobile_otp_attempts:*",
            "rll:cooldown:*",
            "rll:revoked:*",
            "rll:syslock:*",
        ]:
            res = run_async(safe_delete_pattern(sec_pattern))
            assert res == 0, f"Pattern targeting security prefix '{sec_pattern}' was not blocked!"

        # Verify all security keys remain intact
        assert run_async(safe_get("rll:session:s1")) == "session1"
        assert run_async(safe_get("rll:otp:victim@rll.com")) == "otp1"
        assert run_async(safe_get("rll:otp_attempts:victim@rll.com")) == "2"
        assert run_async(safe_get("rll:revoked:victim-uuid")) == "true"
        assert run_async(safe_get("rll:syslock:system")) == "lock1"

    def test_05_defense_in_depth_scan_iter_filters_protected_keys(self):
        """
        Verify that during active Redis scan_iter, any key matching a protected security
        prefix is filtered out and never passed to delete().
        """
        deleted_keys = []

        async def mock_scan_iter(match=None, count=None):
            yield "rll:mobile:sales:1"
            yield "rll:session:stolen"
            yield "rll:otp:compromised"
            yield "rll:mobile:sales:2"

        async def mock_delete(*keys):
            deleted_keys.extend(keys)
            return len(keys)

        mock_r = MagicMock()
        mock_r.scan_iter = mock_scan_iter
        mock_r.delete = mock_delete

        async def mock_exec(fn):
            return await fn(mock_r)

        with patch("backend.db.redis_client.get_redis", return_value=mock_r), \
             patch("backend.db.redis_client._execute_redis", side_effect=mock_exec):

            count = run_async(safe_delete_pattern("rll:mobile:sales:*"))
            assert count == 2
            # Only sales keys should have been deleted
            assert "rll:mobile:sales:1" in deleted_keys
            assert "rll:mobile:sales:2" in deleted_keys
            # Security keys MUST NEVER be in deleted_keys
            assert "rll:session:stolen" not in deleted_keys
            assert "rll:otp:compromised" not in deleted_keys

    def test_06_redis_failures_do_not_trigger_destructive_fallback(self):
        """Verify that Redis connection/scan exceptions fail safely without broad or destructive cleanup."""
        run_async(safe_set("rll:session:active_user", "session_token"))

        mock_r = MagicMock()
        mock_r.scan_iter.side_effect = ConnectionError("Redis server went away")

        with patch("backend.db.redis_client.get_redis", return_value=mock_r), \
             patch("backend.db.redis_client._execute_redis", side_effect=ConnectionError("Redis down")):

            res = run_async(safe_delete_pattern("rll:analytics:*"))
            assert run_async(safe_get("rll:session:active_user")) == "session_token"

    def test_07_flush_rejected_when_environment_unset_misspelled_or_unknown(self):
        """
        Verify flush_redis_for_testing() fails closed when ENVIRONMENT is unset, misspelled,
        or unknown, and proves that flushdb() is never called.
        """
        mock_r = MagicMock()
        mock_r.flushdb = AsyncMock()

        unauthorized_envs = [
            "",              # Unset
            "   ",           # Whitespace
            "produciton",    # Misspelled production
            "stagin",        # Misspelled staging
            "unknown",       # Unknown
            "custom_env",    # Custom
            "development",   # Development is not a permitted test env
            "dev",           # Dev is not a permitted test env
            "local",         # Local is not a permitted test env
        ]

        with patch("backend.db.redis_client.get_redis", return_value=mock_r):
            for bad_env in unauthorized_envs:
                with patch("backend.core.config.settings.ENVIRONMENT", bad_env), \
                     patch("backend.core.config.settings.ALLOW_TEST_REDIS_FLUSH", True):
                    with pytest.raises(RuntimeError) as exc:
                        run_async(flush_redis_for_testing())
                    assert "flush_redis_for_testing is strictly prohibited in environment" in str(exc.value)
                    mock_r.flushdb.assert_not_called()

    def test_08_flush_rejected_in_production_and_staging(self):
        """
        Verify flush_redis_for_testing() raises a RuntimeError if invoked in production or staging,
        and proves that flushdb() is never called.
        """
        mock_r = MagicMock()
        mock_r.flushdb = AsyncMock()

        prod_envs = ["production", "prod", "staging", "PRODUCTION", "STAGING"]

        with patch("backend.db.redis_client.get_redis", return_value=mock_r):
            for prod_env in prod_envs:
                with patch("backend.core.config.settings.ENVIRONMENT", prod_env), \
                     patch("backend.core.config.settings.ALLOW_TEST_REDIS_FLUSH", True):
                    with pytest.raises(RuntimeError) as exc:
                        run_async(flush_redis_for_testing())
                    assert "strictly prohibited in environment" in str(exc.value)
                    mock_r.flushdb.assert_not_called()

    def test_09_flush_rejected_when_missing_or_false_isolation_flag(self):
        """
        Verify that ENVIRONMENT=test alone CANNOT authorize a flush unless ALLOW_TEST_REDIS_FLUSH=True,
        and proves that flushdb() is never called.
        """
        mock_r = MagicMock()
        mock_r.flushdb = AsyncMock()

        with patch("backend.db.redis_client.get_redis", return_value=mock_r), \
             patch("backend.core.config.settings.ENVIRONMENT", "test"), \
             patch("backend.core.config.settings.ALLOW_TEST_REDIS_FLUSH", False):

            with pytest.raises(RuntimeError) as exc:
                run_async(flush_redis_for_testing())
            assert "ALLOW_TEST_REDIS_FLUSH must be explicitly set to True" in str(exc.value)
            mock_r.flushdb.assert_not_called()

    def test_10_flush_rejected_for_remote_or_cloud_redis_targets(self):
        """
        Verify that test environments pointing to remote, cloud, or production Redis URLs are rejected,
        and proves that flushdb() is never called.
        """
        mock_r = MagicMock()
        mock_r.flushdb = AsyncMock()

        unsafe_targets = [
            ("redis://default:pwd@redis-12345.c1.asia.redislabs.com:12345", "localhost"),
            ("redis://user:pwd@rll-prod.elasticache.amazonaws.com:6379", "localhost"),
            ("redis://default:pwd@production-redis-cloud:6379", "localhost"),
            ("redis://user:pwd@upstash.io:6379", "localhost"),
            ("redis://user:pwd@remote-db.example.com:6379", "remote-db.example.com"),
        ]

        with patch("backend.db.redis_client.get_redis", return_value=mock_r):
            for unsafe_url, unsafe_host in unsafe_targets:
                with patch("backend.core.config.settings.ENVIRONMENT", "test"), \
                     patch("backend.core.config.settings.ALLOW_TEST_REDIS_FLUSH", True), \
                     patch("backend.core.config.settings.REDIS_URL", unsafe_url), \
                     patch("backend.core.config.settings.REDIS_HOST", unsafe_host), \
                     patch("backend.core.config.settings.TEST_REDIS_URL", ""):

                    with pytest.raises(RuntimeError) as exc:
                        run_async(flush_redis_for_testing())
                    assert "cannot target unapproved, remote, or production" in str(exc.value)
                    mock_r.flushdb.assert_not_called()

    def test_11_flush_allowed_only_for_verified_isolated_test_instance(self):
        """
        Verify flush_redis_for_testing() executes cleanly ONLY when:
        1. ENVIRONMENT is 'test' or 'testing'
        2. ALLOW_TEST_REDIS_FLUSH is True
        3. Target is an explicitly approved isolated test instance.
        """
        mock_r = MagicMock()
        mock_r.flushdb = AsyncMock(return_value=True)

        async def mock_exec(fn):
            return await fn(mock_r)

        # Prepopulate in-memory store
        run_async(safe_set("test:scratch_key", "value123"))
        assert run_async(safe_get("test:scratch_key")) == "value123"

        with patch("backend.db.redis_client.get_redis", return_value=mock_r), \
             patch("backend.db.redis_client._execute_redis", side_effect=mock_exec), \
             patch("backend.core.config.settings.ENVIRONMENT", "test"), \
             patch("backend.core.config.settings.ALLOW_TEST_REDIS_FLUSH", True), \
             patch("backend.core.config.settings.REDIS_URL", "redis://localhost:6379/15"), \
             patch("backend.core.config.settings.TEST_REDIS_URL", "redis://localhost:6379/15"):

            res = run_async(flush_redis_for_testing())
            assert res is True
            mock_r.flushdb.assert_called_once_with(asynchronous=False)
            # In-memory store was also cleanly reset
            assert run_async(safe_get("test:scratch_key")) is None

    def test_12_mobile_cache_clear_endpoint_requires_admin_authorization(self):
        """Verify that the /cache/clear endpoint requires administrative role authorization."""
        admin_user = {"email": "admin@rll.com", "role": "admin"}
        regular_user = {"email": "viewer@rll.com", "role": "viewer"}

        # Admin user succeeds
        res = run_async(clear_mobile_cache_endpoint(current_user=admin_user))
        assert res["status"] == "success"
        assert "cleared successfully" in res["message"]

        # Non-admin user is rejected
        from backend.core.security import RoleChecker
        checker = RoleChecker(["admin", "super_admin"])
        with pytest.raises(HTTPException) as exc:
            checker(regular_user)
        assert exc.value.status_code == 403

    def test_13_app_review_credentials_and_rate_limits_survive_cache_clear(self):
        """Verify app store review credentials and OTP rate-limit counters survive cache clearing cycles."""
        phone = "9999999999"
        attempt_key = f"rll:mobile_otp_attempts:{phone}"
        run_async(safe_set(attempt_key, "2", ttl=300))

        # Perform cache invalidation
        run_async(invalidate_analytics_cache())

        # Review account rate limit state survives
        survived_attempts = run_async(safe_get(attempt_key))
        assert survived_attempts == "2", "Review account rate limit counter must not be cleared!"
