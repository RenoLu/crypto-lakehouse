SCHEMA_CONTEXT = """
## Available Tables and Views

### v_market_candles (silver layer)
Normalized OHLCV candle data from Binance.
Columns: source, symbol, base_asset, quote_asset, interval, open_time_utc, close_time_utc, open, high, low, close, volume, quote_volume, trade_count, ingestion_time_utc

### v_asset_daily_metrics (gold layer)
Daily aggregated metrics per asset.
Columns: symbol, date, open, high, low, close, volume, quote_volume, trade_count, daily_return, high_low_range, dollar_volume, volatility_7d, volatility_30d, sma_7, sma_30, drawdown, vwap_approx, liquidity_proxy

### v_portfolio_exposures (gold layer)
Current portfolio positions with market values.
Columns: symbol, asset_name, quantity, asset_type, entry_price, entry_date, market_value, allocation_pct, daily_pnl, total_nav, as_of_date

### v_data_quality_breaks (gold layer)
Data quality check results.
Columns: check_name, severity, dataset, symbol, interval, event_time_utc, description, detected_at_utc, suggested_action

## Query Rules
- SELECT only. No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, COPY, ATTACH, INSTALL, LOAD, PRAGMA.
- Use LIMIT for large result sets.
- Prefer aggregations for summary questions.
- Dates are in ISO format or can be compared as strings.
"""
