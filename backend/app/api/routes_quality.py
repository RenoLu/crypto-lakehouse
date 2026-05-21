from fastapi import APIRouter, Query

from app.data.quality_checks import load_quality_breaks
from app.models.api_models import QualityBreak

router = APIRouter(tags=["quality"])


@router.get("/quality/breaks", response_model=list[QualityBreak])
def get_quality_breaks(
    severity: str | None = Query(None, description="Filter by severity: INFO, WARNING, ERROR, CRITICAL"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(100, ge=1, le=1000),
) -> list[QualityBreak]:
    df = load_quality_breaks()
    if df.is_empty():
        return []

    if severity:
        df = df.filter(pl.col("severity") == severity.upper())
    if symbol:
        df = df.filter(pl.col("symbol") == symbol.upper())

    df = df.sort("detected_at_utc", descending=True).limit(limit)

    breaks = []
    for row in df.iter_rows(named=True):
        breaks.append(QualityBreak(**{k: row.get(k, "") for k in QualityBreak.model_fields}))
    return breaks


import polars as pl  # noqa: E402
