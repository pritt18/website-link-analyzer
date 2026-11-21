import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration."""
    
    # Service Information
    APP_NAME: str = "AI-Powered Website Link Analysis API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 4000
    
    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # "gemini", "openai", or "mock"
    
    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Crawler & Extractor Settings
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    MAX_REDIRECTS: int = 3
    MAX_CONTENT_CHARS: int = 15000
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 LinkIntelBot/1.0"
    )
    
    # Security / SSRF
    BLOCK_PRIVATE_NETWORKS: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
