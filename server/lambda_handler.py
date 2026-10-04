"""AWS Lambda entry point: the same ASGI app, behind a Lambda Function URL.

The MCP session manager can only run once per app instance, and Mangum runs the
app's lifespan around every invocation, so each invocation gets a freshly built
app. The server is stateless, so nothing is lost between calls.
"""
from mangum import Mangum

from server.akili_mcp_server import build_app


def handler(event, context):
    return Mangum(build_app(), lifespan="auto")(event, context)
