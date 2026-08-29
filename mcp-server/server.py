"""ReturnGuard MCP tools backend — streamable-HTTP MCP server.
Agents never reach this directly; ContextForge sits in front (per-agent scoping).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("returnguard-tools", host="0.0.0.0", port=8070, streamable_http_path="/mcp")


@mcp.tool()
def get_order(order_id: str) -> dict:
    """Fetch an order header and its line items by order id."""
    return tools.get_order(order_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
