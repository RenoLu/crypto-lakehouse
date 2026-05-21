import re

BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "COPY", "ATTACH", "INSTALL", "LOAD", "PRAGMA", "REPLACE",
    "TRUNCATE", "MERGE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    "UNION", "INTERSECT", "EXCEPT",
]

COMMENT_PATTERNS = [
    r"/\*.*?\*/",  # Block comments
    r"--[^\n]*",   # Line comments
    r"#[^\n]*",    # MySQL-style comments
]


def _strip_comments(sql: str) -> str:
    for pattern in COMMENT_PATTERNS:
        sql = re.sub(pattern, "", sql, flags=re.DOTALL | re.IGNORECASE)
    return sql


def _normalize_whitespace(sql: str) -> str:
    sql = re.sub(r'\s+', ' ', sql)
    return sql.strip()


def is_safe_sql(sql: str) -> tuple[bool, str]:
    cleaned = _strip_comments(sql)
    normalized = _normalize_whitespace(cleaned).upper()

    if not normalized.startswith("SELECT"):
        return False, "Only SELECT statements are allowed"

    for keyword in BLOCKED_KEYWORDS:
        pattern = r'\b' + keyword + r'\b'
        if re.search(pattern, normalized):
            return False, f"Blocked keyword detected: {keyword}"

    if ";" in normalized:
        parts = [p.strip() for p in normalized.split(";") if p.strip()]
        if len(parts) > 1:
            return False, "Multiple statements detected; only single SELECT allowed"

    if re.search(r'0x[0-9a-f]+', normalized):
        return False, "Hex encoding detected"

    if re.search(r'char\s*\(', normalized):
        return False, "CHAR() function detected"

    return True, "OK"


def sanitize_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    if "limit" not in sql.lower():
        sql += " LIMIT 100"
    return sql
