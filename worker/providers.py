"""Provider plugins. A provider is how a worker actually thinks.

No provider-specific code lives outside this module. Add a new model backend
by writing one class with send()/health()/metadata() and listing it in
PROVIDERS — nothing else in the cluster or runtime changes.
"""
import json
import os
import shutil
import subprocess


class Provider:
    def send(self, prompt: str) -> str: ...
    def health(self) -> bool: ...
    def metadata(self) -> dict: ...


class OpencodeProvider(Provider):
    """Drives an opencode process. The worker's brain is a real opencode run."""

    def __init__(self, model: str):
        self.model = model

    def send(self, prompt: str) -> str:
        # --pure: ignore the host's plugins/MCP, this is a clean worker.
        # --format json: line-delimited events; concatenate the text parts.
        proc = subprocess.run(
            ["opencode", "run", "--pure", "--dangerously-skip-permissions",
             "-m", self.model, "--format", "json", prompt],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"opencode failed: {proc.stderr[:500]}")
        out = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "text":
                out.append(ev["part"]["text"])
            elif ev.get("type") == "error":
                raise RuntimeError(f"opencode error: {ev['error']}")
        return "".join(out).strip()

    def health(self) -> bool:
        return shutil.which("opencode") is not None

    def metadata(self) -> dict:
        return {"provider": "opencode", "model": self.model}


class EchoProvider(Provider):
    """Dependency-free fallback for testing the cluster without burning tokens."""

    def __init__(self, model="echo"):
        self.model = model

    def send(self, prompt: str) -> str:
        return f"[echo] {prompt[:300]}"

    def health(self) -> bool:
        return True

    def metadata(self) -> dict:
        return {"provider": "echo", "model": self.model}


PROVIDERS = {"opencode": OpencodeProvider, "echo": EchoProvider}


def make_provider() -> Provider:
    kind = os.environ.get("WORKER_PROVIDER", "opencode")
    model = os.environ.get("WORKER_MODEL", "minimax-coding-plan/MiniMax-M3")
    cls = PROVIDERS.get(kind, OpencodeProvider)
    return cls(model) if kind != "echo" else EchoProvider(model)
