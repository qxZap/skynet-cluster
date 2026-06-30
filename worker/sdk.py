"""WorkerClient — the lightweight SDK. Adding a worker = a few calls.

    w = WorkerClient(base, name="Codex", skills=["coding"])
    w.register()
    for ev in w.events():        # SSE, no polling
        ...
    w.claim_task(task_id)
    w.message(content="done", conversation_id=...)
    w.complete_task(task_id, result="...")
"""
import json
import os

import httpx


class WorkerClient:
    def __init__(self, base_url: str, name: str, *, provider=None, model=None,
                 description=None, personality=None, skills=None, tools=None,
                 context_window=None, max_parallel_tasks=1, token=None, worker_id=None):
        self.base = base_url.rstrip("/")
        self.token = token or os.environ.get("CLUSTER_TOKEN")
        self.id = worker_id
        self.meta = dict(name=name, provider=provider, model=model, description=description,
                         personality=personality, skills=skills or [], tools=tools or [],
                         context_window=context_window, max_parallel_tasks=max_parallel_tasks)
        h = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.http = httpx.Client(base_url=self.base, headers=h, timeout=30)

    def _check(self, r):
        r.raise_for_status()
        return r.json()

    def register(self):
        body = {**self.meta}
        if self.id:
            body["id"] = self.id
        self.id = self._check(self.http.post("/workers/register", json=body))["id"]
        return self.id

    def heartbeat(self, status="online"):
        self.http.post(f"/workers/{self.id}/heartbeat", params={"status": status})

    def create_task(self, title, description="", required_skill=None, assigned_worker=None,
                    parent_id=None, conversation_id=None, priority=0):
        return self._check(self.http.post("/tasks", json=dict(
            title=title, description=description, required_skill=required_skill,
            assigned_worker=assigned_worker, parent_id=parent_id,
            conversation_id=conversation_id, priority=priority, creator=self.id)))

    def get_task(self, tid):
        return self._check(self.http.get(f"/tasks/{tid}"))

    def claim_task(self, tid):
        """Returns True if we got it, False if another worker beat us (409)."""
        r = self.http.post(f"/tasks/{tid}/assign", json={"worker": self.id})
        if r.status_code == 409:
            return False
        r.raise_for_status()
        return True

    def complete_task(self, tid, result="", status="completed"):
        return self._check(self.http.post(f"/tasks/{tid}/complete",
                                          json={"result": result, "status": status}))

    def message(self, content, conversation_id=None, task_id=None, receiver=None, role="worker", metadata=None):
        return self._check(self.http.post("/messages", json=dict(
            sender=self.id, content=content, conversation_id=conversation_id,
            task_id=task_id, receiver=receiver, role=role, metadata=metadata or {})))

    def search(self, q, kind=None):
        return self._check(self.http.get("/search", params={"q": q, "kind": kind}))

    def find_worker(self, skill):
        return self._check(self.http.get("/workers", params={"skill": skill}))["items"]

    def events(self):
        """Yield events from the cluster SSE stream forever (reconnects on drop)."""
        while True:
            try:
                with self.http.stream("GET", "/events/stream", timeout=None) as resp:
                    for line in resp.iter_lines():
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload and payload != "{}":
                                yield json.loads(payload)
            except (httpx.HTTPError, json.JSONDecodeError):
                pass  # reconnect
