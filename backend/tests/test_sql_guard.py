from app.assistant.sql_guard import is_safe_sql, sanitize_sql


def test_select_is_safe():
    safe, reason = is_safe_sql("SELECT * FROM v_market_candles LIMIT 10")
    assert safe is True
    assert reason == "OK"


def test_insert_is_blocked():
    safe, _reason = is_safe_sql("INSERT INTO v_market_candles VALUES (1, 2, 3)")
    assert safe is False


def test_update_is_blocked():
    safe, _reason = is_safe_sql("UPDATE v_market_candles SET close = 100")
    assert safe is False


def test_delete_is_blocked():
    safe, _reason = is_safe_sql("DELETE FROM v_market_candles WHERE symbol = 'BTCUSDT'")
    assert safe is False


def test_drop_is_blocked():
    safe, _reason = is_safe_sql("DROP TABLE v_market_candles")
    assert safe is False


def test_alter_is_blocked():
    safe, _reason = is_safe_sql("ALTER TABLE v_market_candles ADD COLUMN x INT")
    assert safe is False


def test_create_is_blocked():
    safe, _reason = is_safe_sql("CREATE TABLE test (id INT)")
    assert safe is False


def test_copy_is_blocked():
    safe, _reason = is_safe_sql("COPY v_market_candles TO '/tmp/out.csv'")
    assert safe is False


def test_pragma_is_blocked():
    safe, _reason = is_safe_sql("PRAGMA database_list")
    assert safe is False


def test_select_with_subquery_is_safe():
    sql = "SELECT * FROM v_market_candles WHERE date = (SELECT MAX(date) FROM v_asset_daily_metrics)"
    safe, _reason = is_safe_sql(sql)
    assert safe is True


def test_non_select_is_blocked():
    safe, _reason = is_safe_sql("  \n  SELECT 1; DROP TABLE users")
    assert safe is False


def test_sanitize_adds_limit():
    sql = "SELECT * FROM v_market_candles"
    result = sanitize_sql(sql)
    assert "LIMIT 100" in result


def test_sanitize_removes_trailing_semicolon():
    sql = "SELECT * FROM v_market_candles;"
    result = sanitize_sql(sql)
    assert not result.endswith(";")


def test_sanitize_preserves_existing_limit():
    sql = "SELECT * FROM v_market_candles LIMIT 50"
    result = sanitize_sql(sql)
    assert "LIMIT 50" in result
