from fastapi import APIRouter

from app.core.config import settings
from app.core.polling import run_pipeline_once
from app.data.retention import cleanup_old_data, get_dir_size_mb
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


@router.get("/polling/storage")
def storage_status() -> dict:
    size_mb = get_dir_size_mb(settings.lakehouse_path)
    return {
        "size_mb": round(size_mb, 1),
        "limit_mb": 500,
        "usage_pct": round(size_mb / 500 * 100, 1),
    }


@router.post("/polling/cleanup")
def trigger_cleanup(max_size_mb: float = 400.0) -> dict:
    return cleanup_old_data(max_size_mb=max_size_mb)
