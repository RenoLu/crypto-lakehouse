import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from mangum import Mangum
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from app.main import app
from app.core.config import settings

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

for d in [
    settings.bronze_path,
    settings.silver_path / "market_candles",
    settings.gold_path / "asset_daily_metrics",
    settings.gold_path / "asset_intraday_metrics",
    settings.gold_path / "portfolio_positions",
    settings.gold_path / "portfolio_exposures",
    settings.gold_path / "data_quality_breaks",
    settings.duckdb_db_path.parent,
]:
    d.mkdir(parents=True, exist_ok=True)

API_PREFIXES = ("/health", "/assets", "/market", "/analytics", "/portfolio", "/quality", "/assistant", "/polling", "/docs", "/openapi.json", "/redoc")


class StaticFileMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path == "/" or (not path.startswith(API_PREFIXES) and not path.startswith("/api/")):
            if path == "/" or path == "/index.html":
                index = FRONTEND_DIST / "index.html"
                if index.exists():
                    return FileResponse(str(index))

            if not path.startswith("/"):
                path = "/" + path

            file_path = FRONTEND_DIST / path.lstrip("/")
            if file_path.is_file():
                return FileResponse(str(file_path))

            index = FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(str(index))

            return Response("Frontend not built", status_code=404)

        return await call_next(request)


app.add_middleware(StaticFileMiddleware)

handler = Mangum(app)
