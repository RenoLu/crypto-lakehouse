from pathlib import Path

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    # Binance.US: US-accessible public market data, keyless, 1000 bars/call,
    # identical kline schema to global Binance. Override via BINANCE_BASE_URL
    # (e.g. https://data-api.binance.vision for deeper global history when not geo-blocked).
    binance_base_url: str = "https://api.binance.us"
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
    prediction_intervals: str = "1m,5m,1h,1d"
    prediction_horizon: int = 24  # fallback when an interval isn't in prediction_horizons
    prediction_horizons: str = "1m:30,5m:24,1h:24,1d:14"
    prediction_lookback: int = 400
    prediction_sample_count: int = 16  # Monte-Carlo samples per series (balances band quality vs CI time)
    prediction_temperature: float = 0.6  # lower = more stable / less divergent
    prediction_top_p: float = 0.9
    prediction_band_low: float = 0.1  # lower quantile for the uncertainty band
    prediction_band_high: float = 0.9  # upper quantile for the uncertainty band
    prediction_lookbacks: str = "256,512"  # selectable lookback presets (precomputed per variant)
    prediction_modes: str = "sampled,deterministic"  # selectable forecast modes

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
    def prediction_horizon_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for part in self.prediction_horizons.split(","):
            key, _, val = part.strip().partition(":")
            try:
                out[key.strip()] = int(val)
            except ValueError:
                continue
        return out

    @property
    def prediction_lookback_list(self) -> list[int]:
        out: list[int] = []
        for part in self.prediction_lookbacks.split(","):
            try:
                out.append(int(part.strip()))
            except ValueError:
                continue
        return out

    @property
    def prediction_mode_list(self) -> list[str]:
        return [m.strip() for m in self.prediction_modes.split(",") if m.strip()]

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
