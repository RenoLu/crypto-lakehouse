from http.server import BaseHTTPRequestHandler
import json
import os
import posixpath


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def safe_static_path(request_path: str) -> str | None:
    normalized = posixpath.normpath(request_path.lstrip("/"))
    if normalized.startswith("..") or normalized.startswith("/"):
        return None
    full_path = os.path.join(STATIC_DIR, normalized)
    real_path = os.path.realpath(full_path)
    real_static = os.path.realpath(STATIC_DIR)
    if not real_path.startswith(real_static):
        return None
    return full_path


def handler(request):
    path = request.get("path", "/")

    if path == "/health":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "ok", "version": "0.1.0"})
        }

    if path.startswith("/assets/") or path.endswith((".js", ".css", ".png", ".svg", ".ico")):
        safe_path = safe_static_path(path)
        if safe_path and os.path.isfile(safe_path):
            content_type = "application/javascript" if path.endswith(".js") else "text/css" if path.endswith(".css") else "text/html"
            with open(safe_path, "r", encoding="utf-8") as f:
                body = f.read()
            return {
                "statusCode": 200,
                "headers": {"Content-Type": content_type},
                "body": body
            }
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "text/plain"},
            "body": "Not Found"
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "<h1>Crypto Lakehouse</h1><p>API is running</p>"
    }
