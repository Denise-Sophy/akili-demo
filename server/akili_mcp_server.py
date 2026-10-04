"""Akili MCP server v2: client-scoped, role-scoped, audited, PII-masked.

Run (from the repo root):  uvicorn server.akili_mcp_server:app --port 8000
Endpoint: http://localhost:8000/mcp

Every tool goes through guard(): authenticate -> check role scope -> check client
scope -> audit (allow or deny) -> run -> redact PII. TLS, WAF and gateway-level
rate limits belong in front of this process (see docs/architecture.md); EdgeGate
below is the in-process stand-in for the prototype.
"""
import datetime as dt
import json
import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv

load_dotenv()

from mcp.server.mcpserver import Context, MCPServer  # noqa: E402  (mcp 2.x; was FastMCP in 1.x)
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from memory import store  # noqa: E402
from security.auth import Identity, authorize, identify, load_tokens, visible_clients  # noqa: E402
from security.pii import redact  # noqa: E402
from server import data  # noqa: E402

AUDIT_LOG = os.environ.get("AKILI_AUDIT_LOG", "logs/audit.jsonl")
RATE_LIMIT_PER_MIN = int(os.environ.get("AKILI_RATE_LIMIT_PER_MIN", "120"))
TOKENS = load_tokens()


def audit(who: str, tool: str, client: str, decision: str, trace_id: str, reason: str = "") -> None:
    line = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "trace_id": trace_id,
        "who": who,
        "tool": tool,
        "client": client,
        "decision": decision,
    }
    if reason:
        line["reason"] = reason
    if AUDIT_LOG == "stdout":  # on Lambda: stdout lands in CloudWatch Logs
        print(json.dumps({"audit": line}), flush=True)
        return
    os.makedirs(os.path.dirname(AUDIT_LOG) or ".", exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def guard(ctx: Context, tool: str, scope: str | None, client: str | None = None) -> tuple[Identity, str | None]:
    headers = ctx.headers or {}
    trace_id = headers.get("x-trace-id", "-")
    ident = identify(headers.get("authorization", ""), TOKENS)
    if not ident:
        audit("anonymous", tool, client or "-", "deny", trace_id, "unauthenticated")
        raise ToolError("Access denied: unauthenticated")
    try:
        c = authorize(ident, scope, client, data.all_clients())
    except PermissionError as e:
        audit(ident.name, tool, client or "-", "deny", trace_id, str(e))
        # ToolError (not a bare exception) so mcp 2.x passes the reason to the agent.
        raise ToolError(f"Access denied: {e}") from e
    audit(ident.name, tool, c or "-", "allow", trace_id)
    return ident, c


def _short(meeting: dict) -> dict:
    return {**meeting, "summary": str(meeting.get("summary", ""))[:400]}


mcp = MCPServer("Akili")


@mcp.tool()
def list_clients(ctx: Context) -> list[str]:
    """List the clients this caller is allowed to query."""
    ident, _ = guard(ctx, "list_clients", None)
    return sorted(visible_clients(ident, data.all_clients()))


@mcp.tool()
def get_client_brief(ctx: Context, client: str) -> dict:
    """One-stop brief for a client: deal status, open action items, latest meetings."""
    _, c = guard(ctx, "get_client_brief", "client:read", client)
    meetings = sorted(data.for_client("meetings", c), key=lambda r: str(r.get("date", "")), reverse=True)
    return redact({
        "client": c,
        "deals": data.for_client("deals", c),
        "open_action_items": [r for r in data.for_client("action_items", c) if data.is_open(r)],
        "latest_meetings": [_short(m) for m in meetings[:3]],
    })


@mcp.tool()
def get_deal_status(ctx: Context, client: str) -> list[dict]:
    """Current deal stages for one client."""
    _, c = guard(ctx, "get_deal_status", "client:read", client)
    return redact(data.for_client("deals", c))


@mcp.tool()
def search_decisions(ctx: Context, client: str, query: str) -> list[dict]:
    """Keyword search over one client's meeting history. Returns the top 5 matches."""
    _, c = guard(ctx, "search_decisions", "client:read", client)
    words = [w for w in query.lower().split() if len(w) > 2]
    scored = []
    for m in data.for_client("meetings", c):
        text = f"{m.get('title', '')} {m.get('summary', '')}".lower()
        score = sum(text.count(w) for w in words)
        if score:
            scored.append((score, m))
    scored.sort(key=lambda s: s[0], reverse=True)
    return redact([_short(m) for _, m in scored[:5]])


@mcp.tool()
def get_open_action_items(ctx: Context, client: str) -> list[dict]:
    """Open action items for one client, with owners and due dates."""
    _, c = guard(ctx, "get_open_action_items", "ops:read", client)
    return redact([r for r in data.for_client("action_items", c) if data.is_open(r)])


@mcp.tool()
def get_overdue_items(ctx: Context) -> list[dict]:
    """Overdue open action items across every client this caller can access."""
    ident, _ = guard(ctx, "get_overdue_items", "ops:read")
    today = dt.date.today().isoformat()
    out = []
    for c in sorted(visible_clients(ident, data.all_clients())):
        for r in data.for_client("action_items", c):
            if data.is_open(r) and str(r.get("due", "")) and str(r["due"]) < today:
                out.append(r)
    return redact(out)


@mcp.tool()
def get_sprint_status(ctx: Context, client: str) -> list[dict]:
    """Sprint targets and progress for one client."""
    _, c = guard(ctx, "get_sprint_status", "ops:read", client)
    return redact(data.for_client("sprints", c))


@mcp.tool()
def remember_decision(ctx: Context, client: str, decision: str, rationale: str = "") -> dict:
    """Record a decision the user explicitly stated, with its rationale, in long-term memory."""
    ident, c = guard(ctx, "remember_decision", "memory:write", client)
    row_id = store.remember(ident.name, c, redact(decision), redact(rationale))
    return {"saved": True, "id": row_id, "client": c}


@mcp.tool()
def recall_decisions(ctx: Context, client: str, query: str = "") -> list[dict]:
    """Recall decisions previously recorded for a client (optionally filtered by keyword)."""
    _, c = guard(ctx, "recall_decisions", "client:read", client)
    return redact(store.recall(c, query))


# Module-level so the window survives across apps built by build_app() (one per Lambda invocation).
_RATE_WINDOWS: dict[str, deque] = defaultdict(deque)


class EdgeGate(BaseHTTPMiddleware):
    """Prototype edge layer: reject bad tokens and rate-limit per caller before MCP.

    In production this moves to the API gateway / WAF; the per-tool checks in
    guard() stay, because the edge can't know which client a tool call targets.
    """

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return JSONResponse({"ok": True})
        ident = identify(request.headers.get("authorization", ""), TOKENS)
        if not ident:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        now = time.monotonic()
        window = _RATE_WINDOWS[ident.name]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MIN:
            return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "60"})
        window.append(now)
        return await call_next(request)


# DNS-rebinding protection stays on. Locally only localhost is accepted; when deployed,
# AKILI_ALLOWED_HOSTS lists the public hostname(s), e.g. "akili-mcp-xyz.a.run.app".
_public_hosts = [h.strip() for h in os.environ.get("AKILI_ALLOWED_HOSTS", "").split(",") if h.strip()]
_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *_public_hosts],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", *(f"https://{h}" for h in _public_hosts)],
)


def build_app():
    """A fresh ASGI app. The MCP session manager can only run once per app, so the
    Lambda handler builds one per invocation; uvicorn uses the single `app` below."""
    built = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=_security)
    built.add_middleware(EdgeGate)
    return built


app = build_app()
