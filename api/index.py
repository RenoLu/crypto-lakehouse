from http.server import BaseHTTPRequestHandler
import json


def handler(request):
    path = request.get("path", "/")

    if path == "/health":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "ok", "version": "0.1.0"})
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "<h1>Crypto Lakehouse</h1><p>API is running</p>"
    }
