"""Deterministic security checks against a running MCP server. No LLM, no API cost.

    uvicorn server.akili_mcp_server:app --port 8000     # terminal 1
    python -m evals.security_check                       # terminal 2

Exits non-zero if any check fails, so it can gate a deploy.
"""
import asyncio
import json
import os
import sys

import httpx2
from dotenv import load_dotenv

load_dotenv()

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from app import token_for  # noqa: E402

URL = os.environ.get("AKILI_MCP_URL", "http://localhost:8000/mcp")


async def call(user: str, tool: str, args: dict) -> tuple[bool, str]:
    """Returns (is_error, text) for one tool call made as `user`."""
    headers = {"Authorization": f"Bearer {token_for(user)}", "X-Trace-Id": "security-check"}
    async with httpx2.AsyncClient(headers=headers, timeout=30) as http, \
            streamable_http_client(URL, http_client=http) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            text = " ".join(getattr(c, "text", "") for c in result.content)
            return bool(result.is_error), text


async def main() -> int:
    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail[:120]})" if detail and not ok else ""))

    r = httpx2.post(URL, json={}, headers={"Accept": "application/json, text/event-stream"})
    check("no token -> 401", r.status_code == 401, str(r.status_code))
    r = httpx2.post(URL, json={}, headers={"Authorization": "Bearer wrong", "Accept": "application/json, text/event-stream"})
    check("bad token -> 401", r.status_code == 401, str(r.status_code))

    err, text = await call("denise", "get_client_brief", {"client": "Acme"})
    check("lead can read Acme brief", not err and "bluebird" in text.lower(), text)
    check("PII masked in brief (email)", "wanjiru@acme.example" not in text and "EMAIL_REDACTED" in text, text)
    check("PII masked in brief (phone)", "712 345 678" not in text and "PHONE_REDACTED" in text, text)

    err, text = await call("globex_lead", "get_client_brief", {"client": "acme"})
    check("globex_lead refused Acme", err and "No access to 'acme'" in text and "bluebird" not in text.lower(), text)

    err, text = await call("globex_lead", "get_client_brief", {"client": "globex"})
    check("globex_lead can read Globex", not err and "heron" in text.lower(), text)

    err, text = await call("globex_lead", "get_overdue_items", {})
    check("overdue scoped to own clients", not err and "acme" not in text.lower() and "initech" not in text.lower(), text)

    err, text = await call("ops_intern", "get_deal_status", {"client": "acme"})
    check("ops role lacks client:read", err and "client:read" in text, text)

    err, text = await call("ops_intern", "get_open_action_items", {"client": "acme"})
    check("ops role can read own action items", not err and "pilot scope" in text.lower(), text)

    err, text = await call("globex_lead", "remember_decision", {"client": "globex", "decision": "x"})
    check("client_lead cannot write memory", err and "memory:write" in text, text)

    err, text = await call("denise", "remember_decision",
                           {"client": "initech", "decision": "Use Option B pricing", "rationale": "call me on 0722 000 111"})
    check("lead can write memory", not err, text)
    err, text = await call("denise", "recall_decisions", {"client": "initech", "query": "Option B"})
    check("memory recall works and is PII-masked", not err and "option b" in text.lower() and "0722 000 111" not in text, text)

    audit_path = os.environ.get("AKILI_AUDIT_LOG", "logs/audit.jsonl")
    if audit_path != "stdout" and ("localhost" in URL or "127.0.0.1" in URL):
        with open(audit_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if '"security-check"' in line]
        check("denials are audited", any(r["decision"] == "deny" and r["who"] == "globex_lead" for r in rows))
    else:
        print("SKIP  denials are audited (remote server: check its logs, e.g. CloudWatch)")

    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
