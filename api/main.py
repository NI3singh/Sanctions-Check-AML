"""
Sanctions Screening API
FastAPI application for PEP and sanctions screening
"""
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from config import settings
from models import (
    PersonScreeningRequest,
    ScreeningResponse,
    HealthCheckResponse
)
from services.yente_client import yente_client
from services.decision_engine import decision_engine
from utils.audit_logger import audit_logger


# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Sanctions screening API for i-betting platform compliance",
    docs_url="/docs",
    redoc_url="/redoc"
)


@app.on_event("startup")
async def startup_event():
    """Startup checks"""
    print(f"\n{'='*60}")
    print(f"Starting {settings.API_TITLE} v{settings.API_VERSION}")
    print(f"{'='*60}")
    print(f"Yente URL: {settings.YENTE_BASE_URL}")
    print(f"Datasets: {', '.join(settings.DATASETS)}")
    print(f"Thresholds: Review={settings.THRESHOLD_REVIEW}, Block={settings.THRESHOLD_BLOCK}")
    print(f"Audit logs: {settings.LOG_BASE_DIR}")
    print(f"{'='*60}\n")
    
    # Check Yente connectivity
    is_healthy, message = await yente_client.check_health()
    if not is_healthy:
        print(f"WARNING: Yente health check failed: {message}")
        print("API will start but screening requests will fail until Yente is available.\n")
    else:
        print(f"Yente status: {message}\n")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "screen_person": "POST /v1/sanctions/screen/person",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint
    Verifies API and Yente service availability
    """
    yente_healthy, yente_message = await yente_client.check_health()
    
    return HealthCheckResponse(
        status="healthy" if yente_healthy else "degraded",
        yente_status=yente_message,
        datasets_available=settings.DATASETS,
        timestamp=datetime.utcnow()
    )


@app.post(
    "/v1/sanctions/screen/person",
    response_model=ScreeningResponse,
    status_code=status.HTTP_200_OK
)
async def screen_person(request: PersonScreeningRequest):
    """
    Screen a person against sanctions lists
    
    This endpoint performs the following:
    1. Validates input data
    2. Queries OFAC and UN sanctions datasets via Yente
    3. Applies fuzzy matching and scoring
    4. Determines decision (clear/review/block) based on thresholds
    5. Returns detailed results and reasoning
    6. Logs complete audit trail
    
    Use this endpoint:
    - Before processing withdrawals (primary use case)
    - During registration (soft screening)
    - For periodic rescans of existing users
    
    Decisions:
    - CLEAR: No significant match, proceed with transaction
    - REVIEW: Possible match, manual review required, soft hold
    - BLOCK: High confidence match, hard hold, compliance escalation
    """
    
    # Generate request ID if not provided
    request_id = request.request_id or str(uuid.uuid4())
    
    # Log incoming request
    audit_logger.log_screening_request(
        request_id=request_id,
        request_data=request.model_dump(),
        user_id=request.user_id,
        context=request.transaction_context
    )
    
    try:
        # Check Yente availability
        yente_healthy, yente_message = await yente_client.check_health()
        if not yente_healthy:
            audit_logger.log_error(
                request_id=request_id,
                error_type="yente_unavailable",
                error_message=yente_message
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Sanctions screening service unavailable: {yente_message}"
            )
        
        # Screen against all datasets
        all_matches = await yente_client.screen_all_datasets(
            request=request,
            request_id=request_id
        )
        
        # Apply decision engine
        decision, risk_level, top_score, reasons = decision_engine.make_decision(all_matches)
        
        # Limit matches returned (keep top N)
        top_matches = all_matches[:settings.MAX_MATCHES_RETURNED]
        
        # Build metadata
        metadata: Dict[str, Any] = {
            "total_matches_found": len(all_matches),
            "matches_returned": len(top_matches),
            "thresholds": {
                "info": settings.THRESHOLD_INFO,
                "review": settings.THRESHOLD_REVIEW,
                "block": settings.THRESHOLD_BLOCK
            },
            "input_fields_provided": {
                "name": True,
                "country": bool(request.country),
                "dob": bool(request.date_of_birth),
                "passport": bool(request.passport_number),
                "national_id": bool(request.national_id)
            }
        }
        
        # Log decision
        audit_logger.log_decision(
            request_id=request_id,
            decision=decision,
            risk_level=risk_level,
            top_score=top_score,
            total_matches=len(all_matches),
            reasons=reasons,
            user_id=request.user_id,
            context=request.transaction_context
        )
        
        # Build response
        response = ScreeningResponse(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            decision=decision,
            risk_level=risk_level,
            top_score=top_score,
            matches=top_matches,
            reasons=reasons,
            datasets_checked=settings.DATASETS,
            metadata=metadata
        )
        
        return response
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 503)
        raise
    
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_error(
            request_id=request_id,
            error_type="unexpected_error",
            error_message=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal screening error: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level="info"
    )