from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class AssetInfo(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    min_price: float
    min_quantity: float


class CandleResponse(BaseModel):
    symbol: str
    interval: str
    count: int
    data: list[dict]


class DailyMetricsResponse(BaseModel):
    symbol: str
    count: int
    data: list[dict]


class PortfolioExposure(BaseModel):
    symbol: str
    asset_name: str
    quantity: float
    market_value: float
    allocation_pct: float
    daily_pnl: float
    total_nav: float


class QualityBreak(BaseModel):
    check_name: str
    severity: str
    dataset: str
    symbol: str
    interval: str
    event_time_utc: str
    description: str
    detected_at_utc: str
    suggested_action: str


class PredictionResponse(BaseModel):
    symbol: str
    interval: str
    mode: str
    lookback: int
    count: int
    generated_at_utc: str | None
    data: list[dict]


class AssistantRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class AssistantResponse(BaseModel):
    question: str
    answer: str
    query_used: str
    rows: list[dict]
    warnings: list[str]


class BacktestReplayResponse(BaseModel):
    symbol: str
    interval: str
    supported: bool
    anchors: list[dict]


class BacktestMetricsResponse(BaseModel):
    symbol: str
    interval: str
    supported: bool
    n_anchors: int
    directional_pct: float
    mape: float
    band_coverage: float
    band_nominal: float
    horizon: list[dict]
