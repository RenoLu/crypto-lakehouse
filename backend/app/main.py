from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analytics import router as analytics_router
from app.api.routes_assets import router as assets_router
from app.api.routes_assistant import router as assistant_router
from app.api.routes_health import router as health_router
from app.api.routes_market_data import router as market_data_router
from app.api.routes_polling import router as polling_router
from app.api.routes_portfolio import router as portfolio_router
from app.api.routes_quality import router as quality_router
from app.core.config import settings
from app.core.logging import logger
from app.core.polling import polling_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Crypto Lakehouse API")

    poll_task = None
    if settings.polling_enabled:
        logger.info(f"Background polling enabled (interval={settings.polling_interval_seconds}s)")
        poll_task = asyncio.create_task(polling_loop(settings.polling_interval_seconds))

    yield

    if poll_task:
        logger.info("Stopping background polling...")
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    logger.info("Shutting down Crypto Lakehouse API")


app = FastAPI(
    title="AI-Native Crypto Trading Data Lakehouse",
    description="Local-first portfolio project with medallion architecture, data quality controls, and LLM-powered analytics.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="")
app.include_router(assets_router, prefix="")
app.include_router(market_data_router, prefix="")
app.include_router(analytics_router, prefix="")
app.include_router(polling_router, prefix="")
app.include_router(portfolio_router, prefix="")
app.include_router(quality_router, prefix="")
app.include_router(assistant_router, prefix="")


@app.get("/")
def root():
    return {
        "name": "Crypto Lakehouse API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
