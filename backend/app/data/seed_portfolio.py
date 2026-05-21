
import polars as pl

from app.core.logging import logger
from app.data.lake_paths import ensure_dir, gold_portfolio_positions_dir

PORTFOLIO_SCHEMA = {
    "symbol": pl.Utf8,
    "asset_name": pl.Utf8,
    "quantity": pl.Float64,
    "asset_type": pl.Utf8,
    "entry_price": pl.Float64,
    "entry_date": pl.Utf8,
    "notes": pl.Utf8,
}


def seed_portfolio() -> pl.DataFrame:
    rows = [
        {
            "symbol": "BTCUSDT",
            "asset_name": "Bitcoin",
            "quantity": 0.5,
            "asset_type": "crypto",
            "entry_price": 65000.0,
            "entry_date": "2025-01-15",
            "notes": "Long-term hold",
        },
        {
            "symbol": "ETHUSDT",
            "asset_name": "Ethereum",
            "quantity": 5.0,
            "asset_type": "crypto",
            "entry_price": 3200.0,
            "entry_date": "2025-02-01",
            "notes": "Staking candidate",
        },
        {
            "symbol": "SOLUSDT",
            "asset_name": "Solana",
            "quantity": 50.0,
            "asset_type": "crypto",
            "entry_price": 140.0,
            "entry_date": "2025-03-10",
            "notes": "High-growth L1",
        },
        {
            "symbol": "CASH",
            "asset_name": "US Dollar",
            "quantity": 25000.0,
            "asset_type": "cash",
            "entry_price": 1.0,
            "entry_date": "2025-01-01",
            "notes": "Reserve cash",
        },
    ]

    df = pl.DataFrame(rows, schema=PORTFOLIO_SCHEMA)
    logger.info(f"Seeded portfolio with {len(df)} positions")
    return df


def write_portfolio_positions(df: pl.DataFrame) -> None:
    target_dir = ensure_dir(gold_portfolio_positions_dir())
    output_path = target_dir / "portfolio_positions.parquet"
    df.write_parquet(str(output_path))
    logger.info(f"Wrote portfolio positions: {output_path}")


def load_portfolio_positions() -> pl.DataFrame:
    target_dir = gold_portfolio_positions_dir()
    files = list(target_dir.glob("*.parquet"))
    if not files:
        logger.warning("No portfolio positions found; seeding default portfolio")
        df = seed_portfolio()
        write_portfolio_positions(df)
        return df
    return pl.scan_parquet([str(f) for f in files]).collect()
