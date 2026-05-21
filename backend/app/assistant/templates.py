from app.core.logging import logger

QUERY_TEMPLATES: dict[str, dict] = {
    "highest_volatility": {
        "keywords": ["highest", "volatility", "most volatile", "riskiest"],
        "sql": "SELECT symbol, volatility_7d, volatility_30d FROM v_asset_daily_metrics WHERE date = (SELECT MAX(date) FROM v_asset_daily_metrics) ORDER BY volatility_7d DESC LIMIT 5",
        "explanation": "Shows assets ranked by 7-day and 30-day rolling volatility.",
    },
    "largest_return": {
        "keywords": ["largest", "return", "biggest gain", "biggest drop", "best performer", "worst performer"],
        "sql": "SELECT symbol, daily_return, date FROM v_asset_daily_metrics WHERE date = (SELECT MAX(date) FROM v_asset_daily_metrics) ORDER BY ABS(daily_return) DESC LIMIT 5",
        "explanation": "Shows assets with the largest absolute daily returns.",
    },
    "stale_prices": {
        "keywords": ["stale", "stale price", "missing data", "old data"],
        "sql": "SELECT symbol, severity, description, detected_at_utc FROM v_data_quality_breaks WHERE check_name = 'stale_price' ORDER BY detected_at_utc DESC LIMIT 10",
        "explanation": "Shows stale price alerts from the quality check system.",
    },
    "quality_breaks": {
        "keywords": ["quality", "breaks", "errors", "data quality", "issues"],
        "sql": "SELECT check_name, severity, symbol, description, detected_at_utc FROM v_data_quality_breaks ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'ERROR' THEN 2 WHEN 'WARNING' THEN 3 ELSE 4 END LIMIT 20",
        "explanation": "Shows all data quality breaks ordered by severity.",
    },
    "portfolio_nav": {
        "keywords": ["nav", "portfolio", "total value", "net worth", "portfolio value"],
        "sql": "SELECT symbol, asset_name, quantity, market_value, allocation_pct, daily_pnl, total_nav FROM v_portfolio_exposures ORDER BY allocation_pct DESC",
        "explanation": "Shows current portfolio positions with NAV and allocations.",
    },
    "nav_change": {
        "keywords": ["changed", "change", "nav change", "portfolio change", "what changed"],
        "sql": "SELECT symbol, daily_pnl, daily_return, market_value FROM v_portfolio_exposures ORDER BY ABS(daily_pnl) DESC LIMIT 5",
        "explanation": "Shows portfolio positions ranked by daily P&L impact.",
    },
    "moving_average": {
        "keywords": ["moving average", "sma", "average price", "ma"],
        "sql": "SELECT symbol, date, close, sma_7, sma_30 FROM v_asset_daily_metrics WHERE date >= (SELECT MAX(date) - INTERVAL 30 DAY FROM v_asset_daily_metrics) ORDER BY symbol, date DESC LIMIT 30",
        "explanation": "Shows recent close prices with 7-day and 30-day moving averages.",
    },
    "drawdown": {
        "keywords": ["drawdown", "max drawdown", "worst loss"],
        "sql": "SELECT symbol, MIN(drawdown) as max_drawdown, date FROM v_asset_daily_metrics GROUP BY symbol ORDER BY max_drawdown ASC LIMIT 5",
        "explanation": "Shows maximum drawdown per asset.",
    },
    "volume_analysis": {
        "keywords": ["volume", "liquidity", "trading volume"],
        "sql": "SELECT symbol, SUM(volume) as total_volume, SUM(quote_volume) as total_quote_volume, AVG(liquidity_proxy) as avg_liquidity FROM v_asset_daily_metrics WHERE date >= (SELECT MAX(date) - INTERVAL 7 DAY FROM v_asset_daily_metrics) GROUP BY symbol ORDER BY total_quote_volume DESC",
        "explanation": "Shows 7-day volume and liquidity metrics per asset.",
    },
    "price_summary": {
        "keywords": ["price", "current price", "latest price", "how much"],
        "sql": "SELECT symbol, close, date, high, low, daily_return FROM v_asset_daily_metrics WHERE date = (SELECT MAX(date) FROM v_asset_daily_metrics) ORDER BY symbol",
        "explanation": "Shows latest daily close prices for all assets.",
    },
}


def match_template(question: str) -> dict | None:
    q = question.lower()
    best_score = 0
    best_template = None

    for name, tmpl in QUERY_TEMPLATES.items():
        score = sum(1 for kw in tmpl["keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best_template = {**tmpl, "name": name}

    if best_score == 0:
        return None

    logger.info(f"Matched template: {best_template['name']} (score={best_score})")
    return best_template
