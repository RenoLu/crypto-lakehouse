def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "<h1>It works! Pure Python handler</h1>"
    }
