import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rajasthan Liquor Limited (RLL) Sales Analytics Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Supabase credentials
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://your-supabase-project.supabase.co")
    SUPABASE_KEY: str = os.getenv(
        "SUPABASE_SECRET_KEY", 
        os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_secret_dummy_key")
    )
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY)
    
    # JWT Configuration
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-jwt-key-for-rll-analytics")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
