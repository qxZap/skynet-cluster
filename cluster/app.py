"""Cluster server — the only thing workers talk to.

REST + SSE over localhost. SQLite for persistence, FTS5 for search, an
in-process bus for event streaming. Cursor pagination everywhere.
"""
import asyncio
import json
import os
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import bus, db
from .mcp_server import mcp, mcp_app

TOKEN = os.environ.get("CLUSTER_TOKEN")  # ponytail: one shared token, unset = open (localhost)

# the MCP streamable-http session manager must run for the lifetime of the app
app = FastAPI(title="AI Work Cluster", version="0.1.0",
              lifespan=lambda _: mcp.session_manager.run())


def auth(authorization: str = Header(default="")):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad or missing token")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def emit(type_: str, actor: str | None, ref_id: str | None, data: dict | None = None):
    eid = _id("evt")
    db.execute(
        "INSERT INTO events(id,type,actor,ref_id,data,created_at) VALUES (?,?,?,?,?,?)",
        (eid, type_, actor, ref_id, json.dumps(data or {}), db.now()),
    )
    bus.publish({"id": eid, "type": type_, "actor": actor, "ref_id": ref_id, "data": data or {}})


def paginate(rows, limit):
    """rows are ordered by seq DESC; return page + next_cursor (the seq to pass back)."""
    items = [db.row_to_dict(r) for r in rows[:limit]]
    next_cursor = str(rows[limit - 1]["seq"]) if len(rows) >= limit and rows else None
    for it in items:
        it.pop("seq", None)
    return {"items": items, "next_cursor": next_cursor}


# ---------- models ----------
class WorkerIn(BaseModel):
    name: str
    provider: str | None = None
    model: str | None = None
    description: str | None = None
    personality: str | None = None
    skills: list[str] = []
    tools: list[str] = []
    context_window: int | None = None
    max_parallel_tasks: int = 1
    id: str | None = None


class TaskIn(BaseModel):
    title: str
    description: str = ""
    creator: str | None = None
    assigned_worker: str | None = None
    required_skill: str | None = None
    priority: int = 0
    parent_id: str | None = None
    dependencies: list[str] = []
    conversation_id: str | None = None


class AssignIn(BaseModel):
    worker: str


class CompleteIn(BaseModel):
    result: str = ""
    status: str = "completed"  # completed | failed


class MessageIn(BaseModel):
    sender: str | None = None
    receiver: str | None = None
    conversation_id: str | None = None
    task_id: str | None = None
    role: str = "worker"
    content: str = ""
    metadata: dict = Field(default_factory=dict)


class ConversationIn(BaseModel):
    participants: list[str] = []
    title: str | None = None


# ---------- health ----------
@app.get("/health")
def health():
    n = db.query_one("SELECT COUNT(*) c FROM workers WHERE status='online'")
    return {"status": "ok", "workers_online": n["c"] if n else 0}


# ---------- workers ----------
@app.post("/workers/register", dependencies=[Depends(auth)])
def register_worker(w: WorkerIn):
    wid = w.id or _id("wkr")
    db.execute(
        """INSERT INTO workers(id,name,provider,model,description,personality,skills,tools,
             context_window,max_parallel_tasks,status,heartbeat,registered_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name,provider=excluded.provider,
             model=excluded.model,description=excluded.description,personality=excluded.personality,
             skills=excluded.skills,tools=excluded.tools,context_window=excluded.context_window,
             max_parallel_tasks=excluded.max_parallel_tasks,status='online',heartbeat=excluded.heartbeat""",
        (wid, w.name, w.provider, w.model, w.description, w.personality,
         json.dumps(w.skills), json.dumps(w.tools), w.context_window,
         w.max_parallel_tasks, "online", db.now(), db.now()),
    )
    db.index("worker", wid, f"{w.name} {w.description or ''} {' '.join(w.skills)}")
    emit("worker_joined", wid, wid, {"name": w.name, "skills": w.skills})
    return {"id": wid}


@app.get("/workers")
def list_workers(skill: str | None = None, limit: int = 50, cursor: str | None = None):
    sql = "SELECT rowid AS seq,* FROM workers WHERE 1=1"
    p: list = []
    if skill:
        sql += " AND skills LIKE ?"
        p.append(f'%"{skill}"%')
    if cursor:
        sql += " AND rowid < ?"
        p.append(int(cursor))
    sql += " ORDER BY rowid DESC LIMIT ?"
    p.append(limit + 1)
    return paginate(db.query(sql, tuple(p)), limit)


@app.get("/workers/{wid}")
def get_worker(wid: str):
    r = db.query_one("SELECT rowid AS seq,* FROM workers WHERE id=?", (wid,))
    if not r:
        raise HTTPException(404, "no such worker")
    d = db.row_to_dict(r)
    d.pop("seq", None)
    return d


@app.post("/workers/{wid}/heartbeat", dependencies=[Depends(auth)])
def heartbeat(wid: str, status: str = "online"):
    db.execute("UPDATE workers SET heartbeat=?, status=? WHERE id=?", (db.now(), status, wid))
    return {"ok": True}


# ---------- tasks ----------
@app.post("/tasks", dependencies=[Depends(auth)])
def create_task(t: TaskIn):
    tid = _id("tsk")
    conv = t.conversation_id
    if not conv:
        conv = _id("cnv")
        db.execute(
            "INSERT INTO conversations(id,participants,title,created_at,updated_at) VALUES (?,?,?,?,?)",
            (conv, json.dumps([]), t.title, db.now(), db.now()),
        )
    status = "assigned" if t.assigned_worker else "open"
    db.execute(
        """INSERT INTO tasks(id,title,description,creator,assigned_worker,required_skill,priority,
             parent_id,dependencies,status,conversation_id,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tid, t.title, t.description, t.creator, t.assigned_worker, t.required_skill, t.priority,
         t.parent_id, json.dumps(t.dependencies), status, conv, db.now(), db.now()),
    )
    db.index("task", tid, f"{t.title} {t.description}")
    emit("task_created", t.creator, tid, {
        "title": t.title, "required_skill": t.required_skill,
        "assigned_worker": t.assigned_worker, "parent_id": t.parent_id,
        "conversation_id": conv, "description": t.description,
    })
    return {"id": tid, "conversation_id": conv, "status": status}


@app.get("/tasks")
def list_tasks(status: str | None = None, assigned_worker: str | None = None,
               required_skill: str | None = None, parent_id: str | None = None,
               limit: int = 50, cursor: str | None = None):
    sql = "SELECT seq,* FROM tasks WHERE 1=1"
    p: list = []
    for col, val in (("status", status), ("assigned_worker", assigned_worker),
                     ("required_skill", required_skill), ("parent_id", parent_id)):
        if val is not None:
            sql += f" AND {col}=?"
            p.append(val)
    if cursor:
        sql += " AND seq < ?"
        p.append(int(cursor))
    sql += " ORDER BY seq DESC LIMIT ?"
    p.append(limit + 1)
    return paginate(db.query(sql, tuple(p)), limit)


@app.get("/tasks/{tid}")
def get_task(tid: str):
    r = db.query_one("SELECT seq,* FROM tasks WHERE id=?", (tid,))
    if not r:
        raise HTTPException(404, "no such task")
    d = db.row_to_dict(r)
    d.pop("seq", None)
    return d


@app.post("/tasks/{tid}/assign", dependencies=[Depends(auth)])
def assign_task(tid: str, a: AssignIn):
    r = db.query_one("SELECT status FROM tasks WHERE id=?", (tid,))
    if not r:
        raise HTTPException(404, "no such task")
    # atomic claim: only succeeds if still open/unassigned. prevents two workers grabbing it.
    cur = db.execute(
        "UPDATE tasks SET assigned_worker=?, status='assigned', updated_at=? "
        "WHERE id=? AND (assigned_worker IS NULL OR assigned_worker=?)",
        (a.worker, db.now(), tid, a.worker),
    )
    if cur.rowcount == 0:
        raise HTTPException(409, "task already claimed")
    emit("task_assigned", a.worker, tid, {"worker": a.worker})
    return {"ok": True}


@app.post("/tasks/{tid}/complete", dependencies=[Depends(auth)])
def complete_task(tid: str, c: CompleteIn):
    r = db.query_one("SELECT assigned_worker FROM tasks WHERE id=?", (tid,))
    if not r:
        raise HTTPException(404, "no such task")
    db.execute("UPDATE tasks SET result=?, status=?, updated_at=? WHERE id=?",
               (c.result, c.status, db.now(), tid))
    db.index("task", tid, c.result)
    ev = "task_completed" if c.status == "completed" else "task_failed"
    emit(ev, r["assigned_worker"], tid, {"status": c.status})
    return {"ok": True}


# ---------- conversations & messages ----------
@app.post("/conversations", dependencies=[Depends(auth)])
def create_conversation(c: ConversationIn):
    cid = _id("cnv")
    db.execute(
        "INSERT INTO conversations(id,participants,title,created_at,updated_at) VALUES (?,?,?,?,?)",
        (cid, json.dumps(c.participants), c.title, db.now(), db.now()),
    )
    db.index("conversation", cid, c.title or "")
    emit("conversation_started", None, cid, {"participants": c.participants})
    return {"id": cid}


@app.get("/conversations")
def list_conversations(limit: int = 50, cursor: str | None = None):
    sql = "SELECT rowid AS seq,* FROM conversations WHERE 1=1"
    p: list = []
    if cursor:
        sql += " AND rowid < ?"
        p.append(int(cursor))
    sql += " ORDER BY rowid DESC LIMIT ?"
    p.append(limit + 1)
    return paginate(db.query(sql, tuple(p)), limit)


@app.post("/messages", dependencies=[Depends(auth)])
def post_message(m: MessageIn):
    mid = _id("msg")
    db.execute(
        """INSERT INTO messages(id,sender,receiver,conversation_id,task_id,role,content,metadata,created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (mid, m.sender, m.receiver, m.conversation_id, m.task_id, m.role, m.content,
         json.dumps(m.metadata), db.now()),
    )
    if m.conversation_id:
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), m.conversation_id))
    db.index("message", mid, m.content)
    emit("message_sent", m.sender, mid, {
        "conversation_id": m.conversation_id, "task_id": m.task_id,
        "receiver": m.receiver, "preview": m.content[:200],
    })
    return {"id": mid}


@app.get("/messages")
def list_messages(conversation_id: str | None = None, task_id: str | None = None,
                  limit: int = 50, cursor: str | None = None):
    sql = "SELECT seq,* FROM messages WHERE 1=1"
    p: list = []
    if conversation_id:
        sql += " AND conversation_id=?"
        p.append(conversation_id)
    if task_id:
        sql += " AND task_id=?"
        p.append(task_id)
    if cursor:
        sql += " AND seq < ?"
        p.append(int(cursor))
    sql += " ORDER BY seq DESC LIMIT ?"
    p.append(limit + 1)
    return paginate(db.query(sql, tuple(p)), limit)


# ---------- search ----------
@app.get("/search")
def search(q: str = Query(...), kind: str | None = None, limit: int = 25):
    sql = "SELECT kind, ref_id, snippet(search_fts,2,'[',']','…',12) AS snippet FROM search_fts WHERE search_fts MATCH ?"
    p: list = [q]
    if kind:
        sql += " AND kind=?"
        p.append(kind)
    sql += " LIMIT ?"
    p.append(limit)
    return {"results": [dict(r) for r in db.query(sql, tuple(p))]}


# ---------- events ----------
@app.get("/events")
def list_events(type: str | None = None, limit: int = 50, cursor: str | None = None):
    sql = "SELECT seq,* FROM events WHERE 1=1"
    p: list = []
    if type:
        sql += " AND type=?"
        p.append(type)
    if cursor:
        sql += " AND seq < ?"
        p.append(int(cursor))
    sql += " ORDER BY seq DESC LIMIT ?"
    p.append(limit + 1)
    return paginate(db.query(sql, tuple(p)), limit)


@app.get("/events/stream")
async def stream_events():
    """SSE: live events for workers. No polling."""
    q = bus.subscribe()

    async def gen():
        try:
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"  # keepalive
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


# real agent harnesses connect here as workers
app.mount("/mcp", mcp_app)
