import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
STEP_MARK = "▎"
LOG_LINES = 200

_jobs = {}
_lock = threading.Lock()


class Busy(Exception):
    pass


class Job:
    """Runs root's scripts one after another and keeps their output. A line starting with ▎
    is a new step, which is how root's scripts announce each stage."""

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
        self.log = deque(maxlen=LOG_LINES)
        self.started = time.time()
        self.reported = False
        self.notice = None  # a follow-up result worth showing, such as the agent failing to start

    @property
    def current_step(self):
        return self.steps[-1] if self.steps else "Starting"

    @property
    def progress(self):
        """How far along, from 0 to 1, going by the steps root usually announces."""
        if self.state == "done":
            return 1.0
        total = max(len(self.meta.get("expected", [])), len(self.steps), 1)
        return max(0, len(self.steps) - 1) / total

    @property
    def error(self):
        return next((line for line in reversed(self.log) if line.strip()), "Failed.") if self.state == "failed" else None

    def read_output(self, process):
        for raw in process.stdout:
            line = ANSI_RE.sub("", raw).rstrip()
            if line.startswith(STEP_MARK):
                self.steps.append(line.lstrip(STEP_MARK).strip())
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
