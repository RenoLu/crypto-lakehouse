from pathlib import Path

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    binance_base_url: str = "https://data-api.binance.vision"
    duckdb_path: str = str(PROJECT_ROOT / "data" / "duckdb" / "lakehouse.duckdb")
    lakehouse_root: str = str(PROJECT_ROOT / "data" / "lakehouse")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    default_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"
    default_intervals: str = "1m,5m,1h,1d"
    candle_limit: int = 1000
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    polling_enabled: bool = False
    polling_interval_seconds: int = 60
    api_key: str = ""

    # Kronos price prediction (optional; requires the `predict` install extra)
    predictions_enabled: bool = False
    prediction_model: str = "NeoQuasar/Kronos-small"
    prediction_tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"
    prediction_intervals: str = "1h,1d"
    prediction_horizon: int = 24
    prediction_lookback: int = 400
    prediction_sample_count: int = 5

    @property
    def symbols(self) -> list[str]:
        return [s.strip() for s in self.default_symbols.split(",")]

    @property
    def intervals(self) -> list[str]:
        return [i.strip() for i in self.default_intervals.split(",")]

    @property
    def prediction_interval_list(self) -> list[str]:
        return [i.strip() for i in self.prediction_intervals.split(",")]

    @property
    def lakehouse_path(self) -> Path:
        return Path(self.lakehouse_root)

    @property
    def bronze_path(self) -> Path:
        return self.lakehouse_path / "bronze"

    @property
    def silver_path(self) -> Path:
        return self.lakehouse_path / "silver"

    @property
    def gold_path(self) -> Path:
        return self.lakehouse_path / "gold"

    @property
    def duckdb_db_path(self) -> Path:
        return Path(self.duckdb_path)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
