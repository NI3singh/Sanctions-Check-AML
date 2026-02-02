"""
Audit logging system for sanctions screening
Maintains immutable audit trail for regulatory compliance
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from logging.handlers import RotatingFileHandler

from config import settings, AUDIT_LOG_DIR


class AuditLogger:
    """Structured audit logger for screening events"""
    
    def __init__(self):
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """Configure audit logger with rotation"""
        logger = logging.getLogger("sanctions_audit")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Daily rotating file handler
        log_file = AUDIT_LOG_DIR / f"screening_{datetime.utcnow().strftime('%Y%m%d')}.log"
        
        handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=settings.LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=settings.LOG_RETENTION_DAYS,
            encoding='utf-8'
        )
        
        # JSON formatter for structured logs
        formatter = logging.Formatter(
            '%(message)s'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
        return logger
    
    def log_screening_request(
        self,
        request_id: str,
        request_data: Dict[str, Any],
        user_id: Optional[str] = None,
        context: Optional[str] = None
    ):
        """Log incoming screening request"""
        log_entry = {
            "event_type": "screening_request",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "user_id": user_id,
            "context": context,
            "request_data": {
                "full_name": request_data.get("full_name"),
                "country": request_data.get("country"),
                "has_dob": bool(request_data.get("date_of_birth")),
                "has_passport": bool(request_data.get("passport_number")),
                "has_national_id": bool(request_data.get("national_id"))
            }
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_yente_query(
        self,
        request_id: str,
        dataset: str,
        query_payload: Dict[str, Any],
        response_status: int,
        response_time_ms: float
    ):
        """Log Yente API interaction"""
        log_entry = {
            "event_type": "yente_query",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "dataset": dataset,
            "query_fields": list(query_payload.get("queries", {}).get("q1", {}).get("properties", {}).keys()),
            "response_status": response_status,
            "response_time_ms": round(response_time_ms, 2)
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_matches_found(
        self,
        request_id: str,
        dataset: str,
        match_count: int,
        top_score: float,
        top_entity_id: Optional[str] = None
    ):
        """Log match results from Yente"""
        log_entry = {
            "event_type": "matches_found",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "dataset": dataset,
            "match_count": match_count,
            "top_score": round(top_score, 4) if match_count > 0 else 0.0,
            "top_entity_id": top_entity_id
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_decision(
        self,
        request_id: str,
        decision: str,
        risk_level: str,
        top_score: float,
        total_matches: int,
        reasons: list,
        user_id: Optional[str] = None,
        context: Optional[str] = None
    ):
        """Log final screening decision"""
        log_entry = {
            "event_type": "screening_decision",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "user_id": user_id,
            "context": context,
            "decision": decision,
            "risk_level": risk_level,
            "top_score": round(top_score, 4),
            "total_matches": total_matches,
            "reasons": reasons
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_error(
        self,
        request_id: str,
        error_type: str,
        error_message: str,
        dataset: Optional[str] = None
    ):
        """Log error events"""
        log_entry = {
            "event_type": "screening_error",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "error_type": error_type,
            "error_message": error_message,
            "dataset": dataset
        }
        
        self.logger.error(json.dumps(log_entry, ensure_ascii=False))


# Global audit logger instance
audit_logger = AuditLogger()