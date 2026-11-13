import http.client
import os
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..root import platform_dir, root_const, root_dir, slugify
from .commands import NEW_FLOWS, review_slug

PROXY_PORT = 443
SHARED_BACKEND_PORT = 80


def succeeds(argv, timeout=15):
    try:
        return subprocess.run(argv, capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def proxy_running():
    try:
        socket.create_connection(("localhost", PROXY_PORT), timeout=1).close()
        return True
    except OSError:
        return False


def shared_backend_up():
    try:
        conn = http.client.HTTPConnection("localhost", SHARED_BACKEND_PORT, timeout=2)
        conn.request("GET", "/")
        status = conn.getresponse().status
        conn.close()
        return 200 <= status < 500
    except (OSError, http.client.HTTPException):
        return False


def check(label, ok, fix, run=None, warn=False):
    return {"label": label, "ok": ok, "fix": fix, "run": run, "warn": warn}


def has_gum():
    return check("gum installed", bool(shutil.which("gum")), "brew install gum", ["brew", "install", "gum"])


def has_proxy():
    return check("portless proxy running", bool(shutil.which("portless")) and proxy_running(),
                 "sudo portless proxy start --https", ["sudo", "portless", "proxy", "start", "--https"])


def has_gh_login():
    return check("GitHub login", succeeds(["gh", "auth", "status"]), "gh auth login", ["gh", "auth", "login"])


def has_docker():
    return check("Docker running", succeeds(["docker", "info"]), "Start Docker Desktop", ["open", "-a", "Docker"])


def has_aws():
    profile = os.environ.get("AWS_PROFILE", "default")
    return check("AWS login", succeeds(["aws", "configure", "export-credentials", "--profile", profile]),
                 f"aws sso login --profile {profile}", ["aws", "sso", "login", "--profile", profile])


def has_shared_database():
    volume = root_const("pikachu", "SHARED_DB_VOLUME")
    return check("Shared pikachu database", succeeds(["docker", "volume", "inspect", volume]),
                 "make backend, from the root folder", ["make", "backend"])


def has_shared_backend():
    return check("Shared backend up", shared_backend_up(), "make backend. The platform can still be created.",
                 ["make", "backend"], warn=True)


def folder_free(slug):
    return lambda: check(f"Folder platform-{slug} is free", not platform_dir(slug).exists(),
                         f"Clean platform-{slug} first")


def checks_for(flow, answers):
    if flow == "backend":
        return [has_docker]
    if flow in ("clean", "browser"):
        return []
    if flow == "review_only":
        return [has_gh_login]
    slug = slugify(answers["branch"]) if flow in NEW_FLOWS else review_slug(answers)
    checks = [has_gum, has_proxy, folder_free(slug)]
    if flow == "review":
        checks.append(has_gh_login)
    if answers["backend"] == "isolated":
        checks += [has_docker, has_aws, has_shared_database]
    else:
        checks.append(has_shared_backend)
    return checks


def passed(results):
    return all(r["ok"] or r["warn"] for r in results)


def fixable(results):
    return next((r for r in results if not r["ok"] and r["run"]), None)


def fix_cwd():
    return str(root_dir())


def run(flow, answers):
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda c: c(), checks_for(flow, answers)))
