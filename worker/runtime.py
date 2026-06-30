"""Worker runtime: register, listen on SSE, claim matching tasks, think, report.

Concurrency comes from running many of these processes (see docker-compose).
Within one worker, up to max_parallel_tasks run at once on a thread pool while
the event loop keeps consuming — one slow task never blocks the next.
"""
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from providers import make_provider
from sdk import WorkerClient

_DELEGATE_RE = re.compile(r"```delegate\s*(\{.*?\})\s*```", re.DOTALL)


def parse_delegations(text: str) -> list[dict]:
    """Pull `delegate` JSON blocks out of an LLM reply. Bad JSON is ignored."""
    out = []
    for m in _DELEGATE_RE.finditer(text):
        try:
            d = json.loads(m.group(1))
            if d.get("skill") and d.get("title"):
                out.append(d)
        except json.JSONDecodeError:
            pass
    return out


def build_prompt(w: WorkerClient, task: dict, roster_skills: list[str]) -> str:
    parent = ""
    if task.get("parent_id"):
        p = w.get_task(task["parent_id"])
        if p.get("result"):
            parent = f"\nContext from the parent task ({p['title']}):\n{p['result'][:1500]}\n"
    others = sorted(s for s in roster_skills if s not in w.meta["skills"])
    delegate_hint = ""
    if others:
        delegate_hint = (
            f"\nOther workers in the cluster have these skills: {', '.join(others)}.\n"
            "If finishing this task truly needs a skill you don't have, append ONE fenced block:\n"
            '```delegate\n{"skill":"<skill>","title":"<subtask title>","description":"<what they should do>"}\n```\n'
        )
    return (
        f"You are {w.meta['name']}, a worker in a distributed AI cluster.\n"
        f"Personality: {w.meta.get('personality') or 'pragmatic'}.\n"
        f"Your skills: {', '.join(w.meta['skills'])}.\n\n"
        f"TASK: {task['title']}\n{task.get('description','')}\n{parent}"
        f"{delegate_hint}\n"
        "Do the work now. Be concise and concrete. "
        "Respond in plain text only — do not call tools or edit files."
    )


class Worker:
    def __init__(self):
        self.client = WorkerClient(
            os.environ.get("CLUSTER_URL", "http://localhost:8080"),
            name=os.environ["WORKER_NAME"],
            provider=os.environ.get("WORKER_PROVIDER", "opencode"),
            model=os.environ.get("WORKER_MODEL"),
            personality=os.environ.get("WORKER_PERSONALITY"),
            description=os.environ.get("WORKER_DESCRIPTION"),
            skills=[s.strip() for s in os.environ.get("WORKER_SKILLS", "").split(",") if s.strip()],
            max_parallel_tasks=int(os.environ.get("WORKER_MAX_PARALLEL", "2")),
            worker_id=os.environ.get("WORKER_ID"),
        )
        self.provider = make_provider()
        self.pool = ThreadPoolExecutor(max_workers=self.client.meta["max_parallel_tasks"])
        self._handling: set[str] = set()
        self._lock = threading.Lock()

    def log(self, *a):
        print(f"[{self.client.meta['name']}]", *a, flush=True)

    def mine(self, task: dict) -> bool:
        return bool(set(task.get("required_skill", "").split(",")) & set(self.client.meta["skills"])) \
            if task.get("required_skill") else False

    def consider(self, tid: str, required_skill, assigned_worker):
        with self._lock:
            if tid in self._handling:
                return
            self._handling.add(tid)
        directly_mine = assigned_worker == self.client.id
        skill_match = (not assigned_worker) and required_skill in self.client.meta["skills"]
        if not (directly_mine or skill_match):
            with self._lock:
                self._handling.discard(tid)
            return
        if not directly_mine and not self.client.claim_task(tid):
            self.log(f"task {tid} already claimed, skipping")
            with self._lock:
                self._handling.discard(tid)
            return
        self.log(f"claimed task {tid}")
        self.pool.submit(self.handle, tid)

    def handle(self, tid: str):
        try:
            task = self.client.get_task(tid)
            roster = {s for w in self.client.http.get("/workers").json()["items"] for s in w.get("skills", [])}
            prompt = build_prompt(self.client, task, list(roster))
            self.client.message(f"working on: {task['title']}", conversation_id=task["conversation_id"], task_id=tid, role="system")
            result = self.provider.send(prompt)
            for d in parse_delegations(result):
                child = self.client.create_task(
                    title=d["title"], description=d.get("description", ""),
                    required_skill=d["skill"], parent_id=tid, conversation_id=task["conversation_id"])
                self.log(f"delegated '{d['title']}' -> skill={d['skill']} (task {child['id']})")
                self.client.message(f"delegating to a '{d['skill']}' worker: {d['title']}",
                                    conversation_id=task["conversation_id"], task_id=tid, role="worker")
            self.client.message(result, conversation_id=task["conversation_id"], task_id=tid, role="worker")
            self.client.complete_task(tid, result=result)
            self.log(f"completed task {tid}")
        except Exception as e:  # noqa: BLE001 - report, don't crash the worker
            self.log(f"task {tid} failed: {e}")
            try:
                self.client.complete_task(tid, result=str(e), status="failed")
            except Exception:
                pass
        finally:
            with self._lock:
                self._handling.discard(tid)

    def run(self):
        self.client.register()
        self.log(f"registered id={self.client.id} skills={self.client.meta['skills']} provider={self.provider.metadata()}")
        # sweep tasks created before we connected
        for t in self.client.http.get("/tasks", params={"status": "open"}).json()["items"]:
            self.consider(t["id"], t.get("required_skill"), t.get("assigned_worker"))
        for ev in self.client.events():
            if ev["type"] == "task_created":
                d = ev["data"]
                self.consider(ev["ref_id"], d.get("required_skill"), d.get("assigned_worker"))


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        t = parse_delegations('blah ```delegate\n{"skill":"coding","title":"do x","description":"y"}\n``` end')
        assert t == [{"skill": "coding", "title": "do x", "description": "y"}], t
        assert parse_delegations("no block here") == []
        assert parse_delegations('```delegate\n{bad json}\n```') == []
        print("selfcheck ok")
    else:
        Worker().run()
