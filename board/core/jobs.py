import json
import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
STEP_MARK = "▎"
WARN_MARK = "! "
LOG_LINES = 200
COUNT_RE = re.compile(r"^\S+\s+(\d+)\s")

_jobs = {}
_lock = threading.Lock()


class Busy(Exception):
    pass


class Job:
    """Runs root's commands one after another and keeps their output. With --json, root prints its
    plan as a table, then one "ok" event for each action it applied, in plan order. Other programs
    announce a step with a line that starts with ▎."""

    def __init__(self, label, slug, commands, on_done=None, meta=None):
        self.id = uuid.uuid4().hex[:8]
        self.label = label
        self.slug = slug
        self.commands = commands
        self.on_done = on_done
        self.meta = meta or {}  # what the screens need to describe this job: flow, platform, expected steps
        self.agent = None  # the record of the agent started once the job is done
        self.state = "running"
        self.steps = []
        self.plan = []
        self.applied = 0
        self.failure = None
        self.log = deque(maxlen=LOG_LINES)
        self.warnings = []
        self.started = time.time()
        self.reported = False
        self.notice = None  # a follow-up result worth showing, such as the agent failing to start

    @property
    def current_step(self):
        return self.steps[-1] if self.steps else "Starting"

    @property
    def progress(self):
        """How far along, from 0 to 1: root's applied actions out of its plan, else the announced steps."""
        if self.state == "done":
            return 1.0
        if self.plan:
            return min(1.0, self.applied / max(1, sum(count for _, count in self.plan)))
        total = max(len(self.meta.get("expected", [])), len(self.steps), 1)
        return max(0, len(self.steps) - 1) / total

    @property
    def error(self):
        if self.state != "failed":
            return None
        return self.failure or next((line for line in reversed(self.log) if line.strip()), "Failed.")

    def plan_steps(self):
        """The plan rows that are done, then the one in progress, so the last one is the current step."""
        out, applied = [], self.applied
        for label, count in self.plan:
            out.append(label)
            if applied < count:
                break
            applied -= count
        return out

    def read_event(self, event):
        kind = event.get("event")
        message = event.get("message") or ""
        if kind == "table":
            rows = [row for row in event.get("rows") or [] if len(row) >= 2 and str(row[0]).isdigit()]
            for row in rows:
                match = COUNT_RE.match(row[1])
                self.plan.append((row[1], int(match.group(1)) if match else 1))
            self.meta["expected"] = [label for label, _ in self.plan]
            self.log.extend("  ".join(str(cell) for cell in row) for row in event.get("rows") or [])
        elif kind == "ok":
            self.applied += 1
            self.log.append(f"✓ {message}")
        elif kind in ("warn", "skip"):
            if kind == "warn":
                self.warnings.append(message)
            self.log.append(f"! {message}")
        elif kind in ("error", "attention"):
            hint = event.get("hint")
            self.failure = f"{message}\n{hint}" if hint else message
            self.log.append(f"✕ {message}")
            if hint:
                self.log.append(f"  {hint}")
        else:
            text = " — ".join(str(part) for part in (event.get("title") or message, event.get("detail")) if part)
            if text:
                self.log.append(text)
        if self.plan:
            self.steps = self.plan_steps()

    def read_output(self, process):
        for raw in process.stdout:
            line = ANSI_RE.sub("", raw).rstrip()
            if line.startswith("{"):
                try:
                    self.read_event(json.loads(line))
                    continue
                except ValueError:
                    pass
            if line.startswith(STEP_MARK):
                self.steps.append(line.lstrip(STEP_MARK).strip())
            elif line.strip().startswith(WARN_MARK):
                self.warnings.append(line.strip()[len(WARN_MARK):])
            self.log.append(line)

    def run_command(self, command):
        for argv in command.steps:
            process = subprocess.Popen(
                argv, cwd=command.cwd, env={**os.environ, **command.env}, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True,
            )
            self.read_output(process)
            if process.wait() != 0:
                return False
        return True

    def run(self):
        ok = all(self.run_command(command) for command in self.commands)
        self.state = "done" if ok else "failed"
        if self.on_done:
            self.on_done(self)


def start(label, slug, commands, on_done=None, meta=None):
    with _lock:
        if any(j.slug == slug and j.state == "running" for j in _jobs.values()):
            raise Busy(f"{label} is already in progress.")
        job = Job(label, slug, commands, on_done, meta)
        _jobs[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return job


def listed():
    """Jobs the board should still show: running ones, and failed ones until dismissed."""
    return [j for j in _jobs.values() if j.state != "done"]


def finished_unreported():
    done = [j for j in _jobs.values() if j.state != "running" and not j.reported]
    for job in done:
        job.reported = True
    return done


def dismiss(job_id):
    job = _jobs.get(job_id)
    if not job or job.state == "running":
        return False, "That job is still running."
    del _jobs[job_id]
    return True, "Removed."
