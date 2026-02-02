"""
Configuration management for Sanctions Screening API
Centralized configuration with environment variable support
"""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation"""
    
    # API Configuration
    API_TITLE: str = "Sanctions Screening API"
    API_VERSION: str = "1.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080
    
    # Yente Service Configuration
    YENTE_BASE_URL: str = "http://127.0.0.1:5000"
    YENTE_TIMEOUT: int = 15  # seconds
    YENTE_CONNECT_TIMEOUT: int = 5  # seconds
    
    # Dataset Configuration
    DATASETS: List[str] = ["us_ofac_sdn", "un_sc_sanctions"]
    
    # Decision Thresholds (carefully calibrated for sanctions screening)
    # These thresholds balance false positives vs regulatory risk
    THRESHOLD_INFO: float = 0.50      # Log only, no action required
    THRESHOLD_REVIEW: float = 0.70    # Manual review required, soft hold
    THRESHOLD_BLOCK: float = 0.85     # High confidence, hard hold
    
    # Response Configuration
    MAX_MATCHES_RETURNED: int = 10    # Top N matches to return
    
    # Audit Logging Configuration
    LOG_BASE_DIR: str = "C:\\SANCTIONS-CHECK\\logs\\api"
    LOG_RETENTION_DAYS: int = 90
    LOG_MAX_SIZE_MB: int = 100
    
    # Data Paths (for reference, not used by API directly)
    DATA_BASE_DIR: str = "D:\\Sanctions-data"
    OFAC_DATA_PATH: str = "D:\\Sanctions-data\\datasets\\raw\\ofac"
    UN_DATA_PATH: str = "D:\\Sanctions-data\\datasets\\raw\\un"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()


def ensure_directories():
    """Ensure required directories exist"""
    log_dir = Path(settings.LOG_BASE_DIR)
    audit_dir = log_dir / "audit"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    return audit_dir


# Initialize directories on import
AUDIT_LOG_DIR = ensure_directories()