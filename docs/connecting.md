# Connecting a harness to the cluster

The cluster exposes a **streamable-HTTP MCP** endpoint:

```
http://localhost:18888/mcp/
```

Any MCP-capable agent harness connects one of two ways:

- **A — native HTTP.** The harness speaks streamable-HTTP MCP: just give it the URL.
- **B — stdio bridge.** The harness only speaks stdio MCP: wrap the URL with
  [`mcp-remote`](https://www.npmjs.com/package/mcp-remote), which bridges a remote
  HTTP server to stdio:

  ```
  npx -y mcp-remote http://localhost:18888/mcp/
  ```

After connecting, give the agent the behaviour: load [`../SKILL.md`](../SKILL.md), or
paste [`../examples/sentry.md`](../examples/sentry.md) to make it a standby sentry.

> If you run the cluster on another port or host, replace `localhost:18888`
> everywhere below. In Docker it's the host port from `docker-compose.yml`.

---

## opencode — native HTTP

Merge [`../examples/opencode.jsonc`](../examples/opencode.jsonc) into your config
(`~/.config/opencode/opencode.jsonc`), or add just:

```jsonc
{
  "mcp": {
    "cluster": { "type": "remote", "url": "http://localhost:18888/mcp/", "enabled": true }
  }
}
```

## Claude Code — native HTTP

```bash
claude mcp add --transport http cluster http://localhost:18888/mcp/
```

## Codex CLI — stdio bridge

Codex speaks stdio MCP, so bridge with `mcp-remote`. In `~/.codex/config.toml`:

```toml
[mcp_servers.cluster]
command = "npx"
args = ["-y", "mcp-remote", "http://localhost:18888/mcp/"]
```

(If your Codex build supports an HTTP transport directly, you can point it at the
URL instead — but the bridge above works on every version.)

## Gemini CLI — native HTTP

In `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "cluster": { "httpUrl": "http://localhost:18888/mcp/" }
  }
}
```

## Cursor / Windsurf / Cline (and other IDE agents) — native HTTP

Most use an `mcp.json` with a `url` field. For Cursor, `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cluster": { "url": "http://localhost:18888/mcp/" }
  }
}
```

Windsurf (`~/.codeium/windsurf/mcp_config.json`) and Cline (its MCP settings) use the
same shape. If a client offers only a "command" field, use the stdio bridge instead:
`command: "npx"`, `args: ["-y", "mcp-remote", "http://localhost:18888/mcp/"]`.

## Hermes and any other MCP client

There's nothing cluster-specific to configure — the cluster is a standard MCP server.
Pick the pattern your harness supports:

- Speaks **streamable HTTP** → give it `http://localhost:18888/mcp/`.
- Speaks **stdio only** → run it against `npx -y mcp-remote http://localhost:18888/mcp/`.

Then load [`../SKILL.md`](../SKILL.md). The tools appear (often namespaced, e.g.
`cluster_wait_for_task`) and the agent drives the cluster like any other.

---

## Verify the connection

- **From the harness:** ask it to *"call the cluster tool `list_open_tasks`"* — a fresh
  cluster returns `0`.
- **Raw check** that the endpoint is up and lists tools:

  ```bash
  curl -s -X POST http://localhost:18888/mcp/ \
    -H 'content-type: application/json' \
    -H 'accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | grep -o '"name":"[a-z_]*"'
  ```

You should see `register_worker`, `wait_for_task`, `create_task`, `claim_task`, … —
the full toolset in [`../cluster/mcp_server.py`](../cluster/mcp_server.py).
