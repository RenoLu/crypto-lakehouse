import re

BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "COPY", "ATTACH", "INSTALL", "LOAD", "PRAGMA", "REPLACE",
    "TRUNCATE", "MERGE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
]


def is_safe_sql(sql: str) -> tuple[bool, str]:
    normalized = sql.strip().upper()

    if not normalized.startswith("SELECT"):
        return False, "Only SELECT statements are allowed"

    for keyword in BLOCKED_KEYWORDS:
        pattern = r'\b' + keyword + r'\b'
        if re.search(pattern, normalized):
            return False, f"Blocked keyword detected: {keyword}"

    if ";" in normalized and len(normalized.split(";")) > 1:
        parts = [p.strip() for p in normalized.split(";") if p.strip()]
        for part in parts:
            if not part.upper().startswith("SELECT"):
                return False, "Multiple statements detected; only single SELECT allowed"

    return True, "OK"


def sanitize_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    if "limit" not in sql.lower():
        sql += " LIMIT 100"
    return sql
