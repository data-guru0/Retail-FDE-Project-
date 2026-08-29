"""ReturnGuard MCP tools backend — streamable-HTTP MCP server (MCP SDK v2).
Agents never reach this directly; ContextForge sits in front (per-agent scoping).
"""
from __future__ import annotations

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import tools

mcp = MCPServer("returnguard-tools", instructions="ReturnGuard return-review tools")


@mcp.tool()
def get_order(order_id: str) -> dict:
    """Fetch an order header and its line items by order id."""
    return tools.get_order(order_id)


@mcp.tool()
def check_policy(category: str, days_since_order: int, refund_amount: float) -> dict:
    """Active return-policy text for this case + window/high-value verdict."""
    return tools.check_policy(category, days_since_order, refund_amount)


@mcp.tool()
def get_customer_history(user_id: str) -> dict:
    """Order/return counts, prior denials, and return rate for a customer."""
    return tools.get_customer_history(user_id)


@mcp.tool()
def flag_ring(user_id: str) -> dict:
    """Accounts sharing an address/device/payment fingerprint with this user."""
    return tools.flag_ring(user_id)


# local docker network — allow the compose service hostnames + localhost
_sec = TransportSecuritySettings(
    allowed_hosts=["mcp-server:8070", "mcp-server", "localhost:8070", "localhost",
                   "127.0.0.1:8070", "127.0.0.1"],
    allowed_origins=["*"],
)
app = mcp.streamable_http_app(transport_security=_sec)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8070)
