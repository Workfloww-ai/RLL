from typing import Any
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rajasthan Liquor Limited (RLL) Sales Analytics Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Supabase credentials
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    
    # JWT Configuration
    JWT_SECRET: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.SUPABASE_KEY:
            self.SUPABASE_KEY = self.SUPABASE_SECRET_KEY or self.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
        if not self.SUPABASE_SERVICE_ROLE_KEY:
            self.SUPABASE_SERVICE_ROLE_KEY = self.SUPABASE_SECRET_KEY or self.SUPABASE_KEY

settings = Settings()
