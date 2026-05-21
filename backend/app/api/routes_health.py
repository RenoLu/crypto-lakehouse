from datetime import UTC, datetime

from fastapi import APIRouter

from app.models.api_models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        timestamp=datetime.now(UTC).isoformat(),
    )
