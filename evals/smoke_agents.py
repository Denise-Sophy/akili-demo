"""Wiring check for the agent layer with no model calls (free): connect via Strands,
list MCP tools, and build both agent graphs.

    python -m evals.smoke_agents
"""
from dotenv import load_dotenv

load_dotenv()

from agents import harness  # noqa: E402
from app import token_for  # noqa: E402

mcp = harness.akili_mcp(token_for("denise"), "smoke-test")
with mcp:
    tools = mcp.list_tools_sync()
    names = sorted(t.tool_name for t in tools)
    print("MCP tools:", names)
    missing = (harness.CLIENT_TOOLS | harness.OPS_TOOLS | harness.COORDINATOR_TOOLS) - set(names)
    assert not missing, f"server is missing tools the agents expect: {missing}"
    coordinator = harness.build_coordinator(tools)
    single = harness.build_single(tools)
    print("coordinator tools:", sorted(coordinator.tool_names))
    print("single-agent tools:", len(single.tool_names))
print("OK")
