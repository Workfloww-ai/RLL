import os
import time
from datetime import timedelta
import pytest
import jwt
from fastapi import HTTPException

from backend.core.config import (
    Settings,
    DEV_DEFAULT_JWT_SECRET,
    KNOWN_INSECURE_JWT_SECRETS,
)
from backend.core.security import create_access_token, decode_access_token


class TestJWTSecurityConfiguration:
    """Automated regression suite for JWT secret configuration and validation."""

    def test_missing_production_jwt_secret_fails(self):
        """Production must fail fast if JWT_SECRET is missing or empty."""
        with pytest.raises(RuntimeError, match="JWT_SECRET environment variable is missing or empty in production"):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET="",
                SUPABASE_URL="https://example.supabase.co",
                SUPABASE_KEY="service-key-placeholder",
            )

    def test_whitespace_production_jwt_secret_fails(self):
        """Production must fail fast if JWT_SECRET contains only whitespace."""
        with pytest.raises(RuntimeError, match="JWT_SECRET environment variable is missing or empty in production"):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET="   ",
                SUPABASE_URL="https://example.supabase.co",
                SUPABASE_KEY="service-key-placeholder",
            )

    @pytest.mark.parametrize("insecure_secret", [
        DEV_DEFAULT_JWT_SECRET,
        "rll-sales-platform-secret-key-2026-production",
        "secret",
        "changeme",
        "default",
        "your-secret-key",
        "test-secret",
        "password",
        "admin",
    ])
    def test_known_insecure_secrets_rejected_in_production(self, insecure_secret):
        """Known default or leaked secrets must be strictly rejected in production."""
        with pytest.raises(RuntimeError, match="Insecure, default, or development JWT_SECRET detected in production"):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET=insecure_secret,
                SUPABASE_URL="https://example.supabase.co",
                SUPABASE_KEY="service-key-placeholder",
            )

    def test_short_production_jwt_secret_fails(self):
        """Production JWT_SECRET must have at least 32 characters for 256-bit HS256 security."""
        with pytest.raises(RuntimeError, match="must be at least 32 characters long"):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET="short-secret-under-32-chars!",
                SUPABASE_URL="https://example.supabase.co",
                SUPABASE_KEY="service-key-placeholder",
            )

    def test_valid_production_configuration_succeeds(self):
        """A valid production configuration with a strong 32+ char secret succeeds."""
        valid_secret = "a-very-strong-cryptographic-secret-key-32-chars-minimum!"
        settings = Settings(
            ENVIRONMENT="production",
            JWT_SECRET=valid_secret,
            SUPABASE_URL="https://prod.supabase.co",
            SUPABASE_KEY="prod-service-role-key-xyz",
        )
        assert settings.JWT_SECRET == valid_secret
        assert settings.ENVIRONMENT == "production"

    def test_no_supabase_credential_reuse_as_jwt_secret(self):
        """Supabase credentials (SUPABASE_SECRET_KEY) must NEVER be reused as application JWT_SECRET."""
        supabase_secret = "sb_secret_super_privileged_key_12345"
        settings = Settings(
            ENVIRONMENT="development",
            JWT_SECRET="",
            SUPABASE_SECRET_KEY=supabase_secret,
        )
        # Should NOT copy SUPABASE_SECRET_KEY to JWT_SECRET
        assert settings.JWT_SECRET != supabase_secret
        assert settings.JWT_SECRET == DEV_DEFAULT_JWT_SECRET

    def test_deterministic_development_secret_fallback(self):
        """Development fallback must be deterministic across workers and restarts."""
        worker1_settings = Settings(ENVIRONMENT="development", JWT_SECRET="")
        worker2_settings = Settings(ENVIRONMENT="development", JWT_SECRET="")
        assert worker1_settings.JWT_SECRET == DEV_DEFAULT_JWT_SECRET
        assert worker2_settings.JWT_SECRET == DEV_DEFAULT_JWT_SECRET
        assert worker1_settings.JWT_SECRET == worker2_settings.JWT_SECRET

    def test_settings_repr_does_not_expose_secrets(self):
        """repr(settings) must not expose sensitive signing keys or database credentials."""
        secret_value = "super-secret-key-that-must-never-be-printed"
        settings = Settings(ENVIRONMENT="development", JWT_SECRET=secret_value)
        repr_str = repr(settings)
        assert secret_value not in repr_str
        assert "Settings" in repr_str


class TestJWTTokenIssuanceAndVerification:
    """Automated tests for token issuance, expiration, signature verification, and claims."""

    def test_valid_token_encode_and_decode(self):
        """Tokens created via create_access_token must decode correctly with matching claims."""
        token_data = {"sub": "user@rll.in", "role": "admin", "user_id": "usr-123"}
        token = create_access_token(token_data, expires_delta=timedelta(minutes=15))
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user@rll.in"
        assert payload["role"] == "admin"
        assert payload["user_id"] == "usr-123"
        assert "exp" in payload

    def test_invalid_signature_rejected(self):
        """Tokens signed with a different key must fail verification."""
        forged_token = jwt.encode(
            {"sub": "attacker@evil.com", "role": "admin"},
            "attacker-different-secret-key-12345",
            algorithm="HS256"
        )
        assert decode_access_token(forged_token) is None

    def test_expired_token_rejected(self):
        """Expired tokens must fail verification."""
        token_data = {"sub": "user@rll.in", "role": "viewer"}
        expired_token = create_access_token(token_data, expires_delta=timedelta(seconds=-10))
        assert decode_access_token(expired_token) is None

    def test_unsupported_algorithm_rejected(self):
        """Tokens using an unapproved algorithm (e.g., 'none') must fail verification."""
        # Unsigned/none algorithm token
        unsupported_token = jwt.encode(
            {"sub": "admin@rll.in", "role": "admin"},
            key="",
            algorithm="none"
        )
        assert decode_access_token(unsupported_token) is None

    def test_multi_worker_consistency(self):
        """Tokens signed by worker process A must decode cleanly by worker process B sharing config."""
        worker_a = Settings(ENVIRONMENT="development", JWT_SECRET="")
        worker_b = Settings(ENVIRONMENT="development", JWT_SECRET="")

        token = jwt.encode(
            {"sub": "worker_test@rll.in", "role": "admin", "exp": int(time.time()) + 3600},
            worker_a.JWT_SECRET,
            algorithm=worker_a.ALGORITHM
        )

        decoded_by_b = jwt.decode(
            token,
            worker_b.JWT_SECRET,
            algorithms=[worker_b.ALGORITHM]
        )
        assert decoded_by_b["sub"] == "worker_test@rll.in"
