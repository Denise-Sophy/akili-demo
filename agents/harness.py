"""Akili v2 agent harness (Strands).

Coordinator agent -> specialist agents (exposed to it as tools) -> MCP tools.
The user's own bearer token is forwarded to the MCP server, so authorization is
enforced by the server, not by the model. A prompt injection can make an agent
*ask* for another client's data; the server still refuses it.
"""
import os

from strands import Agent, tool
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient

from observability import trace

MCP_URL = os.environ.get("AKILI_MCP_URL", "http://localhost:8000/mcp")
# Cost-first defaults: routing needs judgement (Sonnet), data lookups don't (Haiku).
COORDINATOR_MODEL = os.environ.get("AKILI_COORDINATOR_MODEL", "claude-sonnet-5-5")
SPECIALIST_MODEL = os.environ.get("AKILI_SPECIALIST_MODEL", "claude-haiku-4-5")

# Capability boundaries: each specialist only sees the MCP tools for its job.
CLIENT_TOOLS = {"list_clients", "get_client_brief", "get_deal_status", "search_decisions", "recall_decisions"}
OPS_TOOLS = {"list_clients", "get_open_action_items", "get_overdue_items", "get_sprint_status"}
COORDINATOR_TOOLS = {"remember_decision", "recall_decisions"}

ACCESS_RULE = (
    "If a tool returns an access or permission error, tell the user plainly they don't have access "
    "to that data. Never guess, fill in, or reuse data from elsewhere to cover the gap."
)

CLIENT_PROMPT = (
    "You are Akili's client-intelligence specialist. Answer questions about a specific client's "
    "deals, meetings and past decisions using only your tools. Cite which tool each fact came from. "
    + ACCESS_RULE
)
OPS_PROMPT = (
    "You are Akili's operations specialist. Answer questions about action items, owners, due dates, "
    "overdue work and sprint progress using only your tools. " + ACCESS_RULE
)
COORDINATOR_PROMPT = (
    "You are Akili, Romel Ventures' team assistant. You don't read data yourself; you delegate.\n"
    "- client_intelligence: a client's deals, meetings, briefs, and what was decided in meetings.\n"
    "- operations: action items, owners, due dates, overdue work, sprints.\n"
    "- remember_decision: only when the user explicitly states a decision to record.\n"
    "- recall_decisions: when asked what was decided before and it may have been recorded in memory.\n"
    "A client brief already includes that client's open action items, so a request for a brief or overview "
    "goes to client_intelligence alone. Delegate to both specialists only when the user explicitly asks "
    "for something from each (e.g. a brief AND what's overdue). Questions unrelated to Romel's clients "
    "or operations: answer briefly that it's out of scope, without calling tools. " + ACCESS_RULE
)
SINGLE_PROMPT = (
    "You are Akili, Romel Ventures' team assistant. Answer questions about clients, meetings, decisions, "
    "action items and sprints using only your tools. Use remember_decision only when the user explicitly "
    "states a decision to record. Questions unrelated to Romel's clients or operations: answer briefly that "
    "it's out of scope, without calling tools. " + ACCESS_RULE
)


def make_model(model_id: str) -> AnthropicModel:
    client_args = {"api_key": os.environ["ANTHROPIC_API_KEY"]} if os.environ.get("ANTHROPIC_API_KEY") else {}
    return AnthropicModel(client_args=client_args, model_id=model_id, max_tokens=8000)


def akili_mcp(token: str, trace_id: str) -> MCPClient:
    headers = {"Authorization": f"Bearer {token}", "X-Trace-Id": trace_id}
    return MCPClient(url=MCP_URL, headers=headers)


def _pick(mcp_tools: list, names: set[str]) -> list:
    return [t for t in mcp_tools if t.tool_name in names]


def build_coordinator(mcp_tools: list) -> Agent:
    @tool
    def client_intelligence(question: str) -> str:
        """Ask the client specialist about one client's deals, meetings, briefs or past decisions.

        Args:
            question: The full question, including the client's name.
        """
        agent = Agent(model=make_model(SPECIALIST_MODEL), tools=_pick(mcp_tools, CLIENT_TOOLS),
                      system_prompt=CLIENT_PROMPT, callback_handler=None)
        return trace.run_agent("client_intelligence", agent, question, SPECIALIST_MODEL)

    @tool
    def operations(question: str) -> str:
        """Ask the operations specialist about action items, owners, overdue work or sprints.

        Args:
            question: The full question, including any client name.
        """
        agent = Agent(model=make_model(SPECIALIST_MODEL), tools=_pick(mcp_tools, OPS_TOOLS),
                      system_prompt=OPS_PROMPT, callback_handler=None)
        return trace.run_agent("operations", agent, question, SPECIALIST_MODEL)

    return Agent(
        model=make_model(COORDINATOR_MODEL),
        tools=[client_intelligence, operations, *_pick(mcp_tools, COORDINATOR_TOOLS)],
        system_prompt=COORDINATOR_PROMPT,
        callback_handler=None,
    )


def build_single(mcp_tools: list) -> Agent:
    """Baseline for the evals: one agent holding every tool, no delegation."""
    return Agent(model=make_model(COORDINATOR_MODEL), tools=mcp_tools,
                 system_prompt=SINGLE_PROMPT, callback_handler=None)


def ask(question: str, token: str, mode: str = "multi") -> tuple[str, list[dict]]:
    """Run one question end to end. Returns (answer, trace events)."""
    trace_id = trace.start_run()
    mcp = akili_mcp(token, trace_id)
    with mcp:
        mcp_tools = mcp.list_tools_sync()
        if mode == "multi":
            answer = trace.run_agent("coordinator", build_coordinator(mcp_tools), question, COORDINATOR_MODEL)
        else:
            answer = trace.run_agent("single_agent", build_single(mcp_tools), question, COORDINATOR_MODEL)
    return answer, trace.events()
