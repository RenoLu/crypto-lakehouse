import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response, PlainTextResponse

from mangum import Mangum

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

API_PREFIXES = (
    "/health",
    "/assets",
    "/market",
    "/analytics",
    "/portfolio",
    "/quality",
    "/assistant",
    "/polling",
    "/docs",
    "/openapi.json",
    "/redoc",
)


@app.get("/__debug__", include_in_schema=False)
async def debug():
    return {
        "frontend_dist": str(FRONTEND_DIST),
        "frontend_dist_exists": FRONTEND_DIST.exists(),
        "index_exists": (FRONTEND_DIST / "index.html").exists(),
        "contents": [str(p) for p in FRONTEND_DIST.rglob("*")] if FRONTEND_DIST.exists() else [],
        "cwd": str(Path.cwd()),
    }


class FrontendMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith(API_PREFIXES):
            return await call_next(request)

        if path == "/" or path == "/index.html":
            index = FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(str(index))

        asset_path = FRONTEND_DIST / path.lstrip("/")
        if asset_path.is_file():
            return FileResponse(str(asset_path))

        if path.startswith("/assets/"):
            return Response("Asset not found: " + path, status_code=404)

        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))

        return Response("Frontend not built: " + str(FRONTEND_DIST), status_code=404)


app.add_middleware(FrontendMiddleware)

handler = Mangum(app)
