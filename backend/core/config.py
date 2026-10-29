import logging
from typing import Any
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# Explicit development-only fallback signing secret.
# NEVER permitted in production or staging environments.
DEV_DEFAULT_JWT_SECRET = "dev-insecure-jwt-secret-do-not-use-in-production-rll-2026-key"

# Known insecure, default, or leaked secrets strictly forbidden in production.
KNOWN_INSECURE_JWT_SECRETS = {
    DEV_DEFAULT_JWT_SECRET.lower(),
    "rll-sales-platform-secret-key-2026-production",
    "secret",
    "changeme",
    "default",
    "your-secret-key",
    "test-secret",
    "password",
    "admin",
    "12345678",
}

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rajasthan Liquor Limited (RLL) Sales Analytics Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    PAYLOAD_ENCRYPTION_KEY: str = ""
    
    # Supabase credentials (strictly decoupled from application JWT signing)
    SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_URL: str = ""
    SUPABASE_PROJECT_URL: str = ""
    
    SUPABASE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    
    # JWT Configuration (Application Authentication)
    JWT_SECRET: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 # 1 hour short-lived access token
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30   # 30-day rolling inactivity window
    REFRESH_TOKEN_GRACE_SECONDS: int = 30 # Grace period for rotated refresh tokens
    
    # Dovesoft SMS Gateway Credentials (loaded strictly from .env)
    DOVESOFT_API_KEY: str = ""
    DOVESOFT_SENDER_ID: str = ""
    DOVESOFT_API_URL: str = ""
    DOVESOFT_ENTITY_ID: str = ""
    DOVESOFT_TEMP_ID: str = ""
    DOVESOFT_MESSAGE_TEMPLATE: str = ""

    # AI & Chatbot LLM Credentials
    GEMINI_API_KEY: str = ""

    # OTP Cryptographic Keyed-HMAC Configuration
    OTP_HMAC_SECRET: str = ""
    
    # Dedicated App Store & Google Play Review Configuration
    # Explicitly enabled in production only when APP_REVIEW_MODE_ENABLED is set to true
    APP_REVIEW_MODE_ENABLED: bool = True
    APP_REVIEW_PHONE: str = "9999999999"
    APP_REVIEW_OTP: str = "123456"
    APP_REVIEW_USER_ID: str = "00000000-0000-0000-0000-000000000099"
    APP_REVIEW_EMAIL: str = "manish.chum@workfloww.ai"
    APP_REVIEW_DEMO_TENANT_ID: str = "00000000-0000-0000-0000-000000000000"
    APP_REVIEW_TOKEN_EXPIRE_HOURS: int = 2

    # Redis Cloud Configuration (loaded from .env or environment variables)
    REDIS_URL: str = ""
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes default

    # Dedicated Test Redis Isolation Configuration
    # Strictly required to authorize flush_redis_for_testing() in disposable test environments.
    ALLOW_TEST_REDIS_FLUSH: bool = False
    TEST_REDIS_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __repr__(self) -> str:
        """Prevent inadvertent secret leakage in logs, tracebacks, or debug representations."""
        return f"<Settings project='{self.PROJECT_NAME}' env='{self.ENVIRONMENT}'>"

    def model_post_init(self, __context: Any) -> None:
        # Resolve Supabase URL
        if not self.SUPABASE_URL:
            self.SUPABASE_URL = self.NEXT_PUBLIC_SUPABASE_URL or self.SUPABASE_PROJECT_URL

        # Resolve Supabase Data Client Keys
        if not self.SUPABASE_KEY:
            self.SUPABASE_KEY = (
                self.SUPABASE_SECRET_KEY
                or self.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
                or self.SUPABASE_ANON_KEY
                or self.NEXT_PUBLIC_SUPABASE_ANON_KEY
            )
        if not self.SUPABASE_SERVICE_ROLE_KEY:
            self.SUPABASE_SERVICE_ROLE_KEY = self.SUPABASE_SECRET_KEY or self.SUPABASE_KEY

        env_clean = (self.ENVIRONMENT or "development").strip().lower()
        is_production = env_clean in ("production", "prod", "staging")

        # Normalize JWT secret input
        jwt_secret_val = (self.JWT_SECRET or "").strip()

        # -------------------------------------------------------------
        # 1. PRODUCTION / STAGING: Strict Fail-Closed Verification
        # -------------------------------------------------------------
        if is_production:
            if not jwt_secret_val:
                raise RuntimeError(
                    "FATAL: JWT_SECRET environment variable is missing or empty in production. "
                    "Startup aborted to prevent unauthorized token signing."
                )
            if jwt_secret_val.lower() in KNOWN_INSECURE_JWT_SECRETS:
                raise RuntimeError(
                    "FATAL: Insecure, default, or development JWT_SECRET detected in production. "
                    "A unique, cryptographically strong secret must be set via environment variable."
                )
            if len(jwt_secret_val) < 32:
                raise RuntimeError(
                    "FATAL: JWT_SECRET in production must be at least 32 characters long "
                    "for HS256 cryptographic security."
                )
            if not self.SUPABASE_URL:
                raise RuntimeError(
                    "FATAL: SUPABASE_URL environment variable is missing in production. Startup halted."
                )
            if not self.SUPABASE_KEY and not self.SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError(
                    "FATAL: Supabase API key is missing in production. Startup halted."
                )

            self.JWT_SECRET = jwt_secret_val

        # -------------------------------------------------------------
        # 2. DEVELOPMENT / TEST / LOCAL: Deterministic Default Fallback
        # -------------------------------------------------------------
        else:
            if jwt_secret_val:
                # If explicit secret provided in development, reject obvious trivial placeholders
                if jwt_secret_val.lower() in {"secret", "changeme", "default"}:
                    logger.warning(
                        "WARNING: Trivial JWT_SECRET detected in development. Consider setting a stronger local secret."
                    )
                self.JWT_SECRET = jwt_secret_val
            else:
                logger.warning(
                    "NOTICE: JWT_SECRET not configured in environment. "
                    "Using deterministic development default for local multi-worker consistency. "
                    "DO NOT USE IN PRODUCTION."
                )
                self.JWT_SECRET = DEV_DEFAULT_JWT_SECRET

        # -------------------------------------------------------------
        # 3. APP REVIEW MODE: Fail-Closed Production Configuration
        # -------------------------------------------------------------
        if not self.APP_REVIEW_PHONE or not self.APP_REVIEW_OTP:
            self.APP_REVIEW_MODE_ENABLED = False
            logger.warning("App review mode disabled: missing required review phone or OTP configuration.")

        if is_production:
            import os
            env_review_val = os.getenv("APP_REVIEW_MODE_ENABLED", "").strip().lower()
            if env_review_val not in ("true", "1", "yes"):
                self.APP_REVIEW_MODE_ENABLED = False
            else:
                self.APP_REVIEW_MODE_ENABLED = True
                logger.warning(
                    "NOTICE: Dedicated App Review Mode explicitly enabled in %s for review phone %s.",
                    self.ENVIRONMENT,
                    self.APP_REVIEW_PHONE
                )

        # -------------------------------------------------------------
        # 4. OTP HMAC SECRET: Resolve Secret for Cryptographic Hashing
        # -------------------------------------------------------------
        if not self.OTP_HMAC_SECRET:
            self.OTP_HMAC_SECRET = self.JWT_SECRET

        # NOTE: Under NO circumstances should Supabase credentials
        # (SUPABASE_SECRET_KEY, SUPABASE_KEY, etc.) be reused as JWT_SECRET.
        # Application JWT signing and Supabase DB access remain strictly decoupled.

settings = Settings()
