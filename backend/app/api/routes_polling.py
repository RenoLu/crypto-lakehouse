from fastapi import APIRouter

from app.core.config import settings
from app.core.polling import run_pipeline_once
from app.models.api_models import HealthResponse

router = APIRouter(tags=["polling"])


@router.get("/polling/status")
def polling_status() -> dict:
    return {
        "enabled": settings.polling_enabled,
        "interval_seconds": settings.polling_interval_seconds,
        "symbols": settings.symbols,
        "intervals": settings.intervals,
    }


@router.post("/polling/trigger")
async def trigger_pipeline() -> dict:
    result = await run_pipeline_once()
    return result
