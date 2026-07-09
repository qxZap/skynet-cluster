"""Stdio MCP entrypoint for clients that do not like the HTTP/SSE mounts."""

from .mcp_server import mcp


if __name__ == "__main__":
    mcp.run(transport="stdio")
