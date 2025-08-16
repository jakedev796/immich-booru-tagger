"""
Configuration management for the Immich Auto-Tagger service.
"""

import os
from typing import Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation."""
    
    # Immich Configuration
    immich_base_url: str = Field(..., env="IMMICH_BASE_URL")
    immich_api_key: str = Field(..., env="IMMICH_API_KEY")
    
    # Processing Configuration
    confidence_threshold: float = Field(default=0.35, env="CONFIDENCE_THRESHOLD", ge=0.0, le=1.0)
    batch_size: int = Field(default=25, env="BATCH_SIZE", gt=0, le=500)
    processed_tag_name: str = Field(default="auto:processed", env="PROCESSED_TAG_NAME")
    
    # Model Configuration
    tagging_model: str = Field(default="wd14", env="TAGGING_MODEL")
    model_cache_dir: str = Field(default="/app/models", env="MODEL_CACHE_DIR")
    
    # Performance Configuration
    max_retries: int = Field(default=3, env="MAX_RETRIES", gt=0)
    retry_delay: float = Field(default=1.0, env="RETRY_DELAY", gt=0.0)
    request_timeout: float = Field(default=30.0, env="REQUEST_TIMEOUT", gt=0.0)
    tag_cache_ttl: int = Field(default=300, env="TAG_CACHE_TTL", gt=0)  # Tag cache TTL in seconds
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Health endpoint
    health_port: int = Field(default=8000, env="HEALTH_PORT")
    
    # Scheduling Configuration
    enable_scheduler: bool = Field(default=True, env="ENABLE_SCHEDULER")
    cron_schedule: str = Field(default="0 2 * * *", env="CRON_SCHEDULE")  # Daily at 2 AM
    timezone: str = Field(default="UTC", env="TIMEZONE")
    
    @validator("immich_base_url")
    def validate_immich_url(cls, v):
        """Ensure the Immich URL is properly formatted."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("IMMICH_BASE_URL must start with http:// or https://")
        return v.rstrip("/")
    
    @validator("tagging_model")
    def validate_tagging_model(cls, v):
        """Ensure the tagging model is supported."""
        supported_models = ["wd14", "deepdanbooru"]
        if v.lower() not in supported_models:
            raise ValueError(f"TAGGING_MODEL must be one of: {supported_models}")
        return v.lower()
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Ensure the log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {valid_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
