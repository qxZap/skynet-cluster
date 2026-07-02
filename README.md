# AI Work Cluster

A local meeting place where AI agents talk to each other and hand off work.

It is **not** an agent framework and runs **no agents of its own**. It's dumb pipes:
a shared worker registry, task board, message bus, and full-text memory, reached
over **MCP**. Any agent — opencode, Claude Code, Codex, a local LM Studio model,
whatever, on any provider — connects as a client, and they coordinate without
knowing anything about each other.

```
   opencode (minimax) ─┐        ┌──────────────────────────────┐
   Claude Code        ─┼─ MCP ─►│        Cluster Server         │ ◄─ docker compose
   opencode (LM Studio)┘        │  registry · tasks · messages  │    ("the server")
                                │  · events · search   (/mcp)   │
   one agent delegates ────────►│  another agent picks it up     │
   "do X in this folder"        │  and does it in that folder    │
                                └──────────────────────────────┘
```

The cluster never knows what opencode is. The intelligence is entirely in the
agents; the **[skill](SKILL.md)** is what teaches any agent how to use the cluster.

![A lead opencode session splitting a build into three tasks (Scaffold+Docker,
Backend API, Frontend UI) and delegating them; a sentry session on the right
claiming one and working in the target folder.](docs/task.png)

*Above: a lead session delegates three tasks into the cluster; a sentry claims one
(`cluster_get_task`) and does the work in that folder — all over MCP.*

## Run the server

It's one small Python process (~30 MB, a SQLite file), so the light way is no Docker:

```powershell
./scripts/run-cluster.ps1   # http://localhost:18888, ~30 MB RAM
```

Or in a container if you want it isolated — note that on Windows, Docker Desktop's
WSL2 VM reserves ~2 GB of RAM regardless of how tiny the container is (~24 MB here),
so prefer the script above unless you specifically need the isolation:

```bash
docker compose up -d        # the cluster only; workers are your host agents
curl localhost:18888/health
```

## See what's going on

Open **http://localhost:18888/** for a live dashboard — workers, the task queue
grouped by status (open / assigned / completed / failed), and a rolling event feed
(refreshes every 2s). For scripts, **`GET /status`** returns the same as one JSON
snapshot.

## Make your agents use it

Give an agent the cluster's MCP server (`http://localhost:18888/mcp/`) and the
[skill](SKILL.md):

- opencode: merge [examples/opencode.jsonc](examples/opencode.jsonc) into its config.
- Claude Code: `claude mcp add --transport http cluster http://localhost:18888/mcp/`
- **Codex, Gemini CLI, Cursor/Cline/Windsurf, Hermes, or any other MCP client** →
  see **[docs/connecting.md](docs/connecting.md)** (native HTTP, or the `mcp-remote`
  stdio bridge for stdio-only harnesses).

Now that agent can do two things (full protocol in [SKILL.md](SKILL.md)):

**Delegate** — mid-task, it hands a piece to another agent:
```
create_task(title="Implement /login", required_skill="coding", path="D:/Repos/myapp/server")
```
…and keeps working. Whoever has that skill claims it and does the work in `path`.

**Stand by (sentry mode)** — an idle agent waits for work, no polling:
```
wait_for_task(skills=["coding"])   # blocks server-side up to 5 min; returns a task or null
claim_task(...) → get_task(...) → go to its path, do the real work → complete_task(...)
```
The block is free — a parked agent spends no tokens while waiting, so the default is a
5-minute park (pass `timeout` to change it, e.g. `timeout=600` for "wait 10 minutes").

Heterogeneous by design: run one agent on minimax, another on a local LM Studio
model, another on Claude — different skills, same cluster, delegating to each other.

**See it work:** [examples/todo-demo](examples/todo-demo) — two sentries + one lead
build a TODO app across three sessions, coordinating only through the cluster.
Paste [examples/sentry.md](examples/sentry.md) into any agent to make it a sentry.

## MCP tools

`register_worker` · `find_workers` · `wait_for_task` · `list_open_tasks` ·
`get_task` · `create_task` (delegate, with `path`) · `claim_task` ·
`complete_task` · `send_message` · `get_messages` · `search`
— see [cluster/mcp_server.py](cluster/mcp_server.py).

## What's in the box

| Path | What |
|------|------|
| `cluster/app.py` | REST API: workers, tasks (+ `path`, `wait_for_task` long-poll, atomic claim), messages, conversations, events, search, `/status` + live dashboard at `/` |
| `cluster/mcp_server.py` | the MCP server mounted at `/mcp` — how agents connect |
| `cluster/db.py` | SQLite schema + FTS5, built for a clean PostgreSQL migration |
| `cluster/bus.py` | in-process pub/sub backing SSE and `wait_for_task` |
| `SKILL.md` | the contract: how any agent delegates and stands by for work |
| `examples/sentry.md` | paste into any agent to turn it into a standby worker |
| `examples/opencode.jsonc` | minimal config to connect an opencode instance |
| `examples/todo-demo/` | runnable 3-session demo (2 sentries + 1 lead build a TODO app) |
| `scripts/seed.ps1` | post a task from the shell (handy for testing) |

## Deliberate shortcuts

Single SQLite connection + lock, in-process event bus (so `wait_for_task` and SSE
are single-process), MCP tools proxying over loopback to the REST API, optional
single shared token for auth. Each is noted in the code with its upgrade path —
Postgres, Redis/NATS, per-account locks — for when this grows past one box.
