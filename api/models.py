"""
Pydantic models for API request/response validation
"""
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class PersonScreeningRequest(BaseModel):
    """Request model for person screening"""
    
    full_name: str = Field(
        ..., 
        min_length=2,
        description="Full name of person to screen"
    )
    country: Optional[str] = Field(
        None,
        description="Country code (ISO 2-letter, e.g., 'US', 'LB', 'IN')"
    )
    date_of_birth: Optional[str] = Field(
        None,
        description="Date of birth in YYYY-MM-DD format"
    )
    passport_number: Optional[str] = Field(
        None,
        description="Passport number if available"
    )
    national_id: Optional[str] = Field(
        None,
        description="National ID or other government ID"
    )
    request_id: Optional[str] = Field(
        None,
        description="External request ID for tracking (auto-generated if not provided)"
    )
    user_id: Optional[str] = Field(
        None,
        description="Internal user ID from betting platform"
    )
    transaction_context: Optional[str] = Field(
        None,
        description="Context: 'withdrawal', 'registration', 'high_deposit', etc."
    )
    
    @field_validator('country')
    @classmethod
    def validate_country(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.upper().strip()
        return v
    
    @field_validator('full_name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()


class MatchedEntity(BaseModel):
    """Matched sanctions entity information"""
    
    entity_id: str = Field(..., description="Unique entity ID from dataset")
    dataset: str = Field(..., description="Source dataset (OFAC or UN)")
    caption: str = Field(..., description="Entity display name/caption")
    score: float = Field(..., description="Match confidence score (0.0 to 1.0)")
    match: bool = Field(..., description="Whether Yente considers this a match")
    
    # Essential properties
    names: List[str] = Field(default_factory=list, description="All known names/aliases")
    countries: List[str] = Field(default_factory=list, description="Associated countries")
    birth_dates: List[str] = Field(default_factory=list, description="Known birth dates")
    programs: List[str] = Field(default_factory=list, description="Sanctions programs")
    source_urls: List[str] = Field(default_factory=list, description="Reference URLs")


class ScreeningResponse(BaseModel):
    """Response model for screening results"""
    
    request_id: str = Field(..., description="Unique request identifier")
    timestamp: datetime = Field(..., description="Screening timestamp (UTC)")
    
    decision: Literal["clear", "review", "block"] = Field(
        ...,
        description="Decision outcome based on thresholds"
    )
    
    risk_level: Literal["none", "low", "medium", "high", "critical"] = Field(
        ...,
        description="Risk categorization"
    )
    
    top_score: float = Field(
        ...,
        description="Highest match score across all datasets"
    )
    
    matches: List[MatchedEntity] = Field(
        default_factory=list,
        description="Matched entities (top N by score)"
    )
    
    reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable decision reasoning"
    )
    
    datasets_checked: List[str] = Field(
        default_factory=list,
        description="Datasets queried during screening"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for audit"
    )


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    yente_status: str
    datasets_available: List[str]
    timestamp: datetime