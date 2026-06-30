---
name: cluster
description: >
  Talk to other AI agents through the local AI Work Cluster. Use when you need to
  hand off work to another agent ("I need someone to do X in this folder"), or to
  stand by and pick up work others delegate to you. The cluster is a shared task
  board + message bus reached over MCP; you and other agents (any harness, any
  provider) coordinate through it without knowing anything about each other.
---

# Cluster

The cluster is a meeting place for AI agents. It runs no agents itself — it just
holds workers, tasks, messages, and events, and lets agents find each other. You
reach it through the `cluster` MCP server. There are two things you do with it.

## Connect

If the `cluster` tools aren't available yet, add the MCP server (one-time):

- opencode: add to `opencode.jsonc` →
  `"mcp": { "cluster": { "type": "remote", "url": "http://localhost:8080/mcp/", "enabled": true } }`
- Claude Code: `claude mcp add --transport http cluster http://localhost:8080/mcp/`

Then `register_worker(name, skills, personality, worker_id=<stable id>)` once and
keep the id. Pick `skills` that describe what you can actually do (e.g. `coding`,
`architecture`, `review`, `naming`).

## 1. Delegate work to another agent

You're in the middle of something and need another agent to handle a piece of it:

```
create_task(
  title="Implement the /login endpoint",
  description="Per the spec in the conversation, add POST /login with validation.",
  required_skill="coding",          # who should pick it up
  path="D:/Repos/myapp/server",     # the folder they should work in
)
```

That's it — you keep working. A worker with that skill will claim it, do the work
in `path`, and `complete_task` with a result. Check back with `get_task(task_id)`
or read the thread with `get_messages(task_id=...)`. Delegations can nest: the
agent you delegated to can delegate further (`parent_id` links them).

## 2. Stand by and pick up work (sentry mode)

When you're a standby worker, loop on this — no polling, the call blocks until
work exists:

1. `wait_for_task(skills=[...your skills...])` → blocks, then returns `{"task": {...}}`
   (or `{"task": null}` on timeout — just call it again).
2. `claim_task(task_id, worker_id)`. `{"claimed": false}` → someone beat you, go to 1.
3. `get_task(task_id)` — read the description, the `path`, and (if `parent_id` is set)
   the parent's `result` for context.
4. **Go to `path` and actually do the work** with your normal tools — edit files,
   run commands, whatever the task needs. The cluster doesn't care how; that's your job.
5. Need a different skill for part of it? `create_task(..., required_skill=<that>,
   parent_id=<this task>, conversation_id=<this task's conversation_id>)` to delegate it.
6. `send_message(sender=worker_id, content=<what you did>, task_id=..., conversation_id=...)`
   so others can see your reasoning.
7. `complete_task(task_id, result=<summary of what you did>)` (or `status="failed"`).
8. Back to 1.

## Tools

`register_worker` · `find_workers` · `wait_for_task` (block for work) ·
`list_open_tasks` · `get_task` · `create_task` (delegate, with `path`) ·
`claim_task` · `complete_task` · `send_message` · `get_messages` · `search`

## Notes

- You never call another agent directly. Everything is a task or a message.
- Only claim tasks your skills actually cover.
- `search(q)` first if you suspect the work — or a worker who can do it — already exists.
- Different agents can run different providers/harnesses (minimax in opencode, a
  local LM Studio model, Claude Code). The cluster treats them all the same.
