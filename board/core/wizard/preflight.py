import os
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..root import lib_value, platform_dir, slugify
from .commands import review_slug

PROXY_PORT = 443


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


def check(label, ok, fix):
    return {"label": label, "ok": ok, "fix": fix}


def has_gum():
    return check("gum installed", bool(shutil.which("gum")), "brew install gum")


def has_proxy():
    return check("portless proxy running", bool(shutil.which("portless")) and proxy_running(),
                 "sudo portless proxy start --https")


def has_gh_login():
    return check("GitHub login", succeeds(["gh", "auth", "status"]), "gh auth login")


def has_docker():
    return check("Docker running", succeeds(["docker", "info"]), "Start Docker Desktop")


def has_aws():
    profile = os.environ.get("AWS_PROFILE", "default")
    return check("AWS login", succeeds(["aws", "configure", "export-credentials", "--profile", profile]),
                 f"aws sso login --profile {profile}")


def has_shared_database():
    volume = lib_value("MAIN_DB_VOLUME")
    return check("Shared pikachu database", succeeds(["docker", "volume", "inspect", volume]),
                 "make backend, from the root folder")


def folder_free(slug):
    return lambda: check(f"Folder platform-{slug} is free", not platform_dir(slug).exists(),
                         f"Clean platform-{slug} first")


def checks_for(flow, answers):
    if flow == "backend":
        return [has_docker]
    if flow in ("clean", "browser"):
        return []
    slug = slugify(answers["branch"]) if flow == "new" else review_slug(answers)
    checks = [has_gum, has_proxy, folder_free(slug)]
    if flow == "review":
        checks.append(has_gh_login)
    if answers["backend"] == "isolated":
        checks += [has_docker, has_aws, has_shared_database]
    return checks


def run(flow, answers):
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda c: c(), checks_for(flow, answers)))
