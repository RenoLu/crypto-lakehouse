from pathlib import Path

import duckdb

from app.core.config import settings
from app.core.logging import logger


class DuckDBRepo:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.duckdb_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self._create_views()

    def _create_views(self) -> None:
        silver_root = settings.silver_path
        gold_root = settings.gold_path

        silver_candles = str(silver_root / "market_candles" / "**" / "*.parquet")
        gold_daily = str(gold_root / "asset_daily_metrics" / "*.parquet")
        gold_exposures = str(gold_root / "portfolio_exposures" / "*.parquet")
        gold_quality = str(gold_root / "data_quality_breaks" / "*.parquet")
        gold_predictions = str(gold_root / "asset_price_predictions" / "*.parquet")

        views = {
            "v_market_candles": f"""
                CREATE OR REPLACE VIEW v_market_candles AS
                SELECT * FROM read_parquet('{silver_candles}', hive_partitioning=true)
            """,
            "v_asset_daily_metrics": f"""
                CREATE OR REPLACE VIEW v_asset_daily_metrics AS
                SELECT * FROM read_parquet('{gold_daily}', hive_partitioning=true)
            """,
            "v_portfolio_exposures": f"""
                CREATE OR REPLACE VIEW v_portfolio_exposures AS
                SELECT * FROM read_parquet('{gold_exposures}', hive_partitioning=true)
            """,
            "v_data_quality_breaks": f"""
                CREATE OR REPLACE VIEW v_data_quality_breaks AS
                SELECT * FROM read_parquet('{gold_quality}', hive_partitioning=true)
            """,
            "v_asset_price_predictions": f"""
                CREATE OR REPLACE VIEW v_asset_price_predictions AS
                SELECT * FROM read_parquet('{gold_predictions}', hive_partitioning=true)
            """,
        }

        for name, sql in views.items():
            try:
                self.conn.execute(sql)
                logger.debug(f"Created DuckDB view: {name}")
            except Exception as e:
                logger.warning(f"Failed to create view {name}: {e}")

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        if params:
            # Convert named params (:name) to positional (?) for DuckDB
            import re
            param_names = re.findall(r':(\w+)', sql)
            sql_positional = re.sub(r':(\w+)', '?', sql)
            param_values = [params[name] for name in param_names]
            result = self.conn.execute(sql_positional, param_values).fetchall()
        else:
            result = self.conn.execute(sql).fetchall()
        columns = [desc[0] for desc in self.conn.description] if self.conn.description else []
        return [dict(zip(columns, row, strict=False)) for row in result]

    def query_df(self, sql: str, params: dict | None = None):
        import polars as pl
        if params:
            return pl.from_pandas(self.conn.execute(sql, params).fetchdf())
        return pl.from_pandas(self.conn.execute(sql).fetchdf())

    def table_exists(self, name: str) -> bool:
        try:
            result = self.conn.execute(
                f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{name}'"
            ).fetchone()
            return result[0] > 0 if result else False
        except Exception:
            return False

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DuckDBRepo":
        return self

    def __exit__(self, *args) -> None:
        self.close()
