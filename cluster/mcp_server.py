"""MCP server the cluster exposes so REAL agent harnesses become workers.

Point any MCP-capable harness (opencode, Claude Code, Codex, ...) at
http://localhost:8080/mcp and it self-drives the cluster through these tools —
no coded worker loop, the harness's own agent IS the worker.

ponytail: tools proxy over loopback to the cluster's own REST API instead of
re-implementing routing/claim/event logic. Same process, identical code path,
negligible overhead at localhost scale. Collapse into a shared service layer
only if the loopback hop ever shows up in a profile.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

SELF = os.environ.get("SELF_URL", "http://127.0.0.1:8080")
TOKEN = os.environ.get("CLUSTER_TOKEN")
_H = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

mcp = FastMCP("ai-work-cluster", stateless_http=True, streamable_http_path="/")


async def _call(method: str, path: str, **kw):
    async with httpx.AsyncClient(base_url=SELF, headers=_H, timeout=30) as c:
        r = await c.request(method, path, **kw)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def register_worker(name: str, skills: list[str], personality: str = "",
                          provider: str = "", model: str = "", worker_id: str = "") -> dict:
    """Join the cluster as a worker. Call this first; remember the returned id.
    Pass worker_id to keep a stable identity across restarts (re-register is idempotent)."""
    return await _call("POST", "/workers/register", json={
        "name": name, "skills": skills, "personality": personality,
        "provider": provider or None, "model": model or None, "id": worker_id or None})


@mcp.tool()
async def find_workers(skill: str = "") -> list:
    """List workers, optionally filtered to those with a given skill."""
    return (await _call("GET", "/workers", params={"skill": skill or None}))["items"]


@mcp.tool()
async def list_open_tasks(skill: str = "") -> list:
    """Open, unclaimed tasks. Pass your skill to see ones you can take."""
    p = {"status": "open"}
    if skill:
        p["required_skill"] = skill
    return (await _call("GET", "/tasks", params=p))["items"]


@mcp.tool()
async def get_task(task_id: str) -> dict:
    """Full detail for one task (description, result, parent, conversation)."""
    return await _call("GET", f"/tasks/{task_id}")


@mcp.tool()
async def create_task(title: str, description: str = "", required_skill: str = "",
                      parent_id: str = "", conversation_id: str = "") -> dict:
    """Create a task. Set required_skill to delegate to a worker with that skill."""
    return await _call("POST", "/tasks", json={
        "title": title, "description": description,
        "required_skill": required_skill or None, "parent_id": parent_id or None,
        "conversation_id": conversation_id or None})


@mcp.tool()
async def claim_task(task_id: str, worker_id: str) -> dict:
    """Atomically claim a task. {'claimed': false} means someone else got it first."""
    async with httpx.AsyncClient(base_url=SELF, headers=_H, timeout=30) as c:
        r = await c.post(f"/tasks/{task_id}/assign", json={"worker": worker_id})
        if r.status_code == 409:
            return {"claimed": False}
        r.raise_for_status()
        return {"claimed": True}


@mcp.tool()
async def complete_task(task_id: str, result: str, status: str = "completed") -> dict:
    """Finish a task with your result. status='failed' if you couldn't do it."""
    return await _call("POST", f"/tasks/{task_id}/complete",
                       json={"result": result, "status": status})


@mcp.tool()
async def send_message(sender: str, content: str, conversation_id: str = "",
                       task_id: str = "", receiver: str = "") -> dict:
    """Post a message to a conversation/task so other workers see your reasoning."""
    return await _call("POST", "/messages", json={
        "sender": sender, "content": content,
        "conversation_id": conversation_id or None, "task_id": task_id or None,
        "receiver": receiver or None})


@mcp.tool()
async def get_messages(conversation_id: str = "", task_id: str = "", limit: int = 50) -> list:
    """Read a conversation or a task's discussion."""
    return (await _call("GET", "/messages", params={
        "conversation_id": conversation_id or None, "task_id": task_id or None,
        "limit": limit}))["items"]


@mcp.tool()
async def search(q: str, kind: str = "") -> list:
    """Full-text search across messages, tasks, workers, conversations."""
    return (await _call("GET", "/search", params={"q": q, "kind": kind or None}))["results"]


mcp_app = mcp.streamable_http_app()
