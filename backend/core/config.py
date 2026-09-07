from typing import Any
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rajasthan Liquor Limited (RLL) Sales Analytics Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    PAYLOAD_ENCRYPTION_KEY: str = ""
    
    # Supabase credentials
    SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_URL: str = ""
    SUPABASE_PROJECT_URL: str = ""
    
    SUPABASE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    
    # JWT Configuration
    JWT_SECRET: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours
    
    # Dovesoft SMS Gateway Credentials (loaded strictly from .env)
    DOVESOFT_API_KEY: str = ""
    DOVESOFT_SENDER_ID: str = ""
    DOVESOFT_API_URL: str = ""
    DOVESOFT_ENTITY_ID: str = ""
    DOVESOFT_TEMP_ID: str = ""
    DOVESOFT_MESSAGE_TEMPLATE: str = ""
    
    # Redis Cloud Configuration (loaded from .env or environment variables)
    REDIS_URL: str = ""
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes default

    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.SUPABASE_URL:
            self.SUPABASE_URL = self.NEXT_PUBLIC_SUPABASE_URL or self.SUPABASE_PROJECT_URL
        if not self.SUPABASE_KEY:
            self.SUPABASE_KEY = self.SUPABASE_SECRET_KEY or self.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or self.SUPABASE_ANON_KEY or self.NEXT_PUBLIC_SUPABASE_ANON_KEY
        if not self.SUPABASE_SERVICE_ROLE_KEY:
            self.SUPABASE_SERVICE_ROLE_KEY = self.SUPABASE_SECRET_KEY or self.SUPABASE_KEY
        if not self.JWT_SECRET:
            self.JWT_SECRET = self.SUPABASE_SECRET_KEY or self.SUPABASE_KEY or "rll-sales-platform-secret-key-2026-production"

settings = Settings()
