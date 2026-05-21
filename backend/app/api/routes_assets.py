from fastapi import APIRouter

from app.core.config import settings
from app.models.api_models import AssetInfo

router = APIRouter(tags=["assets"])

SYMBOL_INFO = {
    "BTCUSDT": {"base_asset": "BTC", "quote_asset": "USDT", "status": "TRADING", "min_price": 0.01, "min_quantity": 1e-05},
    "ETHUSDT": {"base_asset": "ETH", "quote_asset": "USDT", "status": "TRADING", "min_price": 0.01, "min_quantity": 0.0001},
    "SOLUSDT": {"base_asset": "SOL", "quote_asset": "USDT", "status": "TRADING", "min_price": 0.01, "min_quantity": 0.01},
    "CASH": {"base_asset": "USD", "quote_asset": "USD", "status": "ACTIVE", "min_price": 1.0, "min_quantity": 1.0},
}


@router.get("/assets", response_model=list[AssetInfo])
def list_assets() -> list[AssetInfo]:
    assets = []
    for symbol in [*settings.symbols, "CASH"]:
        info = SYMBOL_INFO.get(symbol, {})
        assets.append(AssetInfo(
            symbol=symbol,
            base_asset=info.get("base_asset", symbol.replace("USDT", "")),
            quote_asset=info.get("quote_asset", "USDT"),
            status=info.get("status", "UNKNOWN"),
            min_price=info.get("min_price", 0.01),
            min_quantity=info.get("min_quantity", 0.0001),
        ))
    return assets
