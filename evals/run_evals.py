"""Behavioural regression suite for the Akili agents (costs real API tokens).

    python -m evals.run_evals                 # coordinator + specialists
    python -m evals.run_evals --mode single   # one agent with every tool (baseline)
    python -m evals.run_evals --mode both     # both, side by side
    python -m evals.run_evals --only sec      # case ids starting with "sec"

Grading is deterministic (no LLM judge): which specialists ran, which MCP tools
ran, required/forbidden strings in the answer, and the server's audit log
(joined on trace_id) to prove a forbidden client was never served.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agents.harness import ask  # noqa: E402
from app import token_for  # noqa: E402
from observability.trace import summarise  # noqa: E402

HERE = Path(__file__).resolve().parent
SPECIALISTS = {"client_intelligence", "operations"}
AUDIT_LOG = os.environ.get("AKILI_AUDIT_LOG", "logs/audit.jsonl")


def served_clients(trace_id: str) -> set[str]:
    if not os.path.exists(AUDIT_LOG):
        return set()
    out = set()
    with open(AUDIT_LOG, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("trace_id") == trace_id and row.get("decision") == "allow":
                out.add(row.get("client"))
    return out


def grade(case: dict, answer: str, events: list[dict], mode: str) -> dict:
    text = answer.lower()
    routes = {e["agent"] for e in events if e["agent"] in SPECIALISTS}
    tools = set().union(*(set(e["tools"]) for e in events)) - SPECIALISTS if events else set()
    checks = {}
    if mode == "multi" and "expect_route" in case:
        checks["route"] = routes == set(case["expect_route"])
    if "expect_tools_any" in case:
        checks["tool"] = bool(tools & set(case["expect_tools_any"]))
    if case.get("expect_no_tools"):
        checks["no_tools"] = not tools
    if "expect_in_answer" in case:
        checks["answer"] = all(s in text for s in case["expect_in_answer"])
    if "forbid_in_answer" in case:
        checks["no_leak"] = not any(s.lower() in text for s in case["forbid_in_answer"])
    if "forbid_client" in case:
        checks["server_refused"] = case["forbid_client"] not in served_clients(events[-1]["trace_id"])
    return checks


def run(mode: str, cases: list[dict], budget: dict) -> dict:
    rows = []
    for case in cases:
        if budget["spent"] >= budget["max"]:
            print(f"[{mode}] budget cap ${budget['max']:.2f} reached (${budget['spent']:.4f} spent); skipping the rest")
            break
        try:
            answer, events = ask(case["prompt"], token_for(case["user"]), mode)
            checks = grade(case, answer, events, mode)
            usage = summarise(events)
        except Exception as e:  # a crash is a failed case, not a crashed suite
            answer, checks, usage = f"ERROR: {e}", {"ran": False}, summarise([])
        budget["spent"] += usage["cost_usd"]
        passed = all(checks.values())
        rows.append({"id": case["id"], "type": case["type"], "passed": passed, "checks": checks,
                     "answer": answer, **usage})
        flags = " ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in checks.items())
        print(f"[{mode}] {case['id']:<9} {'PASS' if passed else 'FAIL'}  {flags}  ${usage['cost_usd']:.4f}  {usage['latency_ms']} ms")

    def rate(key: str) -> str:
        scored = [r["checks"][key] for r in rows if key in r["checks"]]
        return f"{sum(scored)}/{len(scored)}" if scored else "n/a"

    summary = {
        "mode": mode,
        "cases_passed": f"{sum(r['passed'] for r in rows)}/{len(rows)}",
        "routing_accuracy": rate("route"),
        "tool_selection": rate("tool"),
        "no_leak": rate("no_leak"),
        "server_refused": rate("server_refused"),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / max(len(rows), 1)),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["multi", "single", "both"], default="multi")
    p.add_argument("--only", default="", help="run only case ids with this prefix")
    p.add_argument("--max-usd", type=float, default=0.75,
                   help="stop starting new cases once estimated spend reaches this (list prices, an upper bound)")
    args = p.parse_args()

    cases = [c for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8")) if c["id"].startswith(args.only)]
    modes = ["multi", "single"] if args.mode == "both" else [args.mode]
    budget = {"spent": 0.0, "max": args.max_usd}
    results = {m: run(m, cases, budget) for m in modes}
    print(f"\nestimated spend this run: ${budget['spent']:.4f}")

    print()
    for m in modes:
        print(json.dumps(results[m]["summary"]))
    out = HERE / "results" / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{args.mode}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
