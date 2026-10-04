"""Invoke the Lambda handler locally with fake Function URL (payload v2) events. Free, no AWS.

    python -m evals.lambda_local_check
"""
import json
import os

HOST = "test123.lambda-url.eu-west-1.on.aws"
os.environ["AKILI_ALLOWED_HOSTS"] = HOST
os.environ["AKILI_AUDIT_LOG"] = "stdout"

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import token_for  # noqa: E402
from server.lambda_handler import handler  # noqa: E402

PROTOCOL = "2025-06-18"


def event(body: dict, token: str, host: str = HOST, extra: dict | None = None) -> dict:
    headers = {
        "host": host,
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "authorization": f"Bearer {token}",
        "x-trace-id": "lambda-local-check",
        **(extra or {}),
    }
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": "/mcp", "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "http": {"method": "POST", "path": "/mcp", "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4", "userAgent": "check"},
            "domainName": host, "stage": "$default", "requestId": "r1", "accountId": "anonymous",
            "apiId": "test123", "time": "04/Oct/2026:12:00:00 +0000", "timeEpoch": 0,
        },
        "body": json.dumps(body), "isBase64Encoded": False,
    }


def main() -> None:
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "check", "version": "0"}}}
    r = handler(event(init, token_for("denise")), None)
    print("initialize:", r["statusCode"], r["body"][:160])
    proto = json.loads(r["body"]).get("result", {}).get("protocolVersion", PROTOCOL) if r["statusCode"] == 200 else PROTOCOL
    hdr = {"mcp-protocol-version": proto}

    def call(tool: str, args: dict, user: str) -> dict:
        body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        return handler(event(body, token_for(user), extra=hdr), None)

    r = call("get_client_brief", {"client": "acme"}, "denise")
    print("denise -> acme brief:", r["statusCode"], "| data returned:", "Bluebird" in r["body"],
          "| email masked:", "EMAIL_REDACTED" in r["body"])
    r = call("get_client_brief", {"client": "acme"}, "globex_lead")
    print("globex_lead -> acme brief:", r["statusCode"], "| refused:", "No access to 'acme'" in r["body"],
          "| leaked:", "Bluebird" in r["body"])
    print("foreign host:", handler(event(init, token_for("denise"), host="evil.example.com"), None)["statusCode"])
    print("bad token:", handler(event(init, "wrong-token"), None)["statusCode"])


if __name__ == "__main__":
    main()
