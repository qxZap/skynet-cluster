"""Event-driven worker daemon: park on the cluster, wake a real harness on work.

This is NOT a coded agent — it's a thin supervisor. It blocks on the cluster's
SSE event stream (no polling) and, when a task appears that matches this worker's
skills, it dispatches one `opencode run` from a bounded pool. The opencode
instance is the actual worker; this just hands it the task id + instructions.

    python scripts/worker_daemon.py --name Coder --id wkr-coder \
        --skills coding,debugging --persona "fast implementer"

Env: CLUSTER_URL (default http://localhost:8080), OPENCODE_CONFIG, WORKER_MODEL.
Needs: httpx, opencode on PATH logged into the model.
"""
import argparse
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

CLUSTER = os.environ.get("CLUSTER_URL", "http://localhost:8080")
MODEL = os.environ.get("WORKER_MODEL", "minimax-coding-plan/MiniMax-M3")

PROMPT = """You are '{name}', a worker in a distributed AI cluster.
Your skills: {skills}. Personality: {persona}.
You are ALREADY registered as worker_id='{wid}'. Do NOT call register_worker.

A task is waiting for you:  task_id = {task_id}

Steps: claim_task('{task_id}', '{wid}'). If claimed is false, stop — someone else
took it. Otherwise get_task, do the work in plain text, optionally delegate
sub-tasks needing other skills via create_task, send_message with your result,
then complete_task. Do not touch the filesystem; your deliverable is the text you post.
"""


class Daemon:
    def __init__(self, a):
        self.name, self.wid = a.name, a.id
        self.skills = [s.strip() for s in a.skills.split(",") if s.strip()]
        self.persona = a.persona
        self.pool = ThreadPoolExecutor(max_workers=a.max_parallel)
        self.seen: set[str] = set()
        self.lock = threading.Lock()
        self.http = httpx.Client(base_url=CLUSTER, timeout=30)

    def log(self, *m):
        print(f"[{self.name}]", *m, flush=True)

    def register(self):
        self.http.post("/workers/register", json={
            "id": self.wid, "name": self.name, "skills": self.skills,
            "personality": self.persona, "provider": "opencode", "model": MODEL})
        self.log(f"registered {self.wid} skills={self.skills} — waiting for work")

    def matches(self, required_skill, assigned_worker):
        return (not assigned_worker) and required_skill in self.skills

    def dispatch(self, task_id):
        with self.lock:
            if task_id in self.seen:
                return
            self.seen.add(task_id)
        self.log(f"task {task_id} matches — dispatching opencode")
        self.pool.submit(self._run, task_id)

    def _run(self, task_id):
        prompt = PROMPT.format(name=self.name, skills=", ".join(self.skills),
                               persona=self.persona, task_id=task_id, wid=self.wid)
        try:
            subprocess.run(["opencode", "run", "-m", MODEL,
                            "--dangerously-skip-permissions", prompt],
                           cwd=os.path.dirname(os.environ.get("OPENCODE_CONFIG", "")) or None,
                           timeout=900)
            self.log(f"finished dispatch for {task_id}")
        except Exception as e:  # noqa: BLE001
            self.log(f"dispatch for {task_id} errored: {e}")

    def run(self):
        self.register()
        # catch tasks created before we connected
        for t in self.http.get("/tasks", params={"status": "open"}).json()["items"]:
            if self.matches(t.get("required_skill"), t.get("assigned_worker")):
                self.dispatch(t["id"])
        # then park on the event stream — woken only when something happens
        while True:
            try:
                with self.http.stream("GET", "/events/stream", timeout=None) as r:
                    for line in r.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        import json
                        payload = line[5:].strip()
                        if not payload or payload == "{}":
                            continue
                        ev = json.loads(payload)
                        if ev.get("type") == "task_created":
                            d = ev["data"]
                            if self.matches(d.get("required_skill"), d.get("assigned_worker")):
                                self.dispatch(ev["ref_id"])
            except (httpx.HTTPError, ValueError):
                self.log("event stream dropped, reconnecting")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--skills", required=True, help="comma-separated")
    p.add_argument("--persona", default="pragmatic")
    p.add_argument("--max-parallel", type=int, default=2)
    Daemon(p.parse_args()).run()
