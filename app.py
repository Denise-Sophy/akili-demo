"""Ask Akili v2 from the terminal (the MCP server must be running).

    python app.py --as denise "Give me a brief on Acme"
    python app.py --as globex_lead "Show me Acme's deal stage"      # refusal case
    python app.py --as denise --mode single "What's overdue?"       # single-agent baseline
"""
import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from agents.harness import ask  # noqa: E402
from observability.trace import summarise  # noqa: E402
from security.auth import load_tokens  # noqa: E402


def token_for(user: str) -> str:
    """Dev convenience: look up a local test token by user name from AKILI_TOKENS."""
    for token, who in load_tokens().items():
        if who["name"] == user:
            return token
    raise SystemExit(f"No token for '{user}' in AKILI_TOKENS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question")
    p.add_argument("--as", dest="user", default="denise")
    p.add_argument("--mode", choices=["multi", "single"], default="multi")
    args = p.parse_args()

    answer, events = ask(args.question, token_for(args.user), args.mode)
    print(answer)
    print("\n--- trace ---")
    for e in events:
        print(f"{e['agent']:<20} {e['model']:<18} {e['latency_ms']:>6} ms  "
              f"{e['input_tokens']:>6} in / {e['output_tokens']:>5} out  ${e['cost_usd']:.4f}  tools={e['tools']}")
    print(json.dumps({"trace_id": events[-1]["trace_id"], **summarise(events)}))


if __name__ == "__main__":
    main()
