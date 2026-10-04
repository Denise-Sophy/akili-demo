"""Per-run tracing: one JSONL line per agent step with tokens, latency, cost and tools.

The same trace_id is sent to the MCP server as X-Trace-Id, so a line in
logs/traces.jsonl joins to the allow/deny lines in logs/audit.jsonl.
"""
import datetime as dt
import json
import os
import time
import uuid

from observability.costs import cost_usd

TRACE_LOG = os.environ.get("AKILI_TRACE_LOG", "logs/traces.jsonl")

# One run at a time (CLI and evals). Switch to contextvars before serving concurrent users.
_run: dict = {"trace_id": None, "events": []}


def start_run() -> str:
    _run["trace_id"] = uuid.uuid4().hex[:12]
    _run["events"] = []
    return _run["trace_id"]


def events() -> list[dict]:
    return list(_run["events"])


def record(**fields) -> dict:
    line = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "trace_id": _run["trace_id"], **fields}
    _run["events"].append(line)
    os.makedirs(os.path.dirname(TRACE_LOG) or ".", exist_ok=True)
    with open(TRACE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return line


def _usage(result) -> tuple[int, int]:
    usage = getattr(getattr(result, "metrics", None), "accumulated_usage", None) or {}
    return int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))


def _tools(result) -> list[str]:
    return sorted((getattr(getattr(result, "metrics", None), "tool_metrics", None) or {}).keys())


def run_agent(agent_name: str, agent, prompt: str, model_id: str) -> str:
    """Invoke a Strands agent and record one trace event for it."""
    t0 = time.perf_counter()
    result, status = None, "ok"
    try:
        result = agent(prompt)
        return str(result)
    except Exception as e:
        status = f"error: {type(e).__name__}: {e}"
        raise
    finally:
        tokens_in, tokens_out = _usage(result)
        record(
            kind="agent",
            agent=agent_name,
            model=model_id,
            latency_ms=round((time.perf_counter() - t0) * 1000),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=cost_usd(model_id, tokens_in, tokens_out),
            tools=_tools(result),
            status=status,
        )


def summarise(evts: list[dict]) -> dict:
    agents = [e for e in evts if e.get("kind") == "agent"]
    return {
        "agent_calls": len(agents),
        "input_tokens": sum(e["input_tokens"] for e in agents),
        "output_tokens": sum(e["output_tokens"] for e in agents),
        "cost_usd": round(sum(e["cost_usd"] for e in agents), 6),
        # The top-level agent is recorded last and its latency covers the nested calls.
        "latency_ms": agents[-1]["latency_ms"] if agents else 0,
    }
