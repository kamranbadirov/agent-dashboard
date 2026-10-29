import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import ROOT_REPO
from .github import branch_prs

ENV_LINE_RE = re.compile(r"^(\w+)='(.*)'$")
ARRAY_RE = r"^{name}=\(([^)]*)\)"


class RootMissing(Exception):
    pass


def root_dir():
    if not (ROOT_REPO / "scripts" / "new.sh").is_file():
        raise RootMissing(f"No root checkout at {ROOT_REPO}. Set ROOT_REPO to its path.")
    return ROOT_REPO


def lib_text():
    return (root_dir() / "scripts" / "_lib.sh").read_text()


def repo_names(mobile=False):
    # root's _lib.sh is the one list of repos, so read it instead of copying it here
    name = "MOBILE_REPOS" if mobile else "ALL_REPOS"
    match = re.search(ARRAY_RE.format(name=name), lib_text(), re.M)
    return match.group(1).split() if match else []


def lib_value(name):
    match = re.search(rf'^{name}="?([^"\n]+)"?$', lib_text(), re.M)
    return match.group(1) if match else None


def slugify(text):
    return re.sub(r"[^a-z0-9-]", "-", text.replace("/", "-").lower())


def platform_urls(slug, isolated):
    # the hostnames root's _lib.sh gives a platform (dns_host_label, raichu_app_host, pikachu_api_host)
    label = slug[: int(lib_value("DEV_HOST_LABEL_LENGTH") or 60)]
    urls = {name: f"https://{label}.{name}.localhost" for name in ("raichu", "portals", "ditto")}
    urls["pikachu"] = f"https://{label}.pikachu.localhost" if isolated else "https://pikachu.localhost"
    return urls


def platform_dir(slug):
    return root_dir().parent / f"platform-{slug}"


def read_env(path):
    env = {}
    try:
        for line in path.read_text().splitlines():
            match = ENV_LINE_RE.match(line)
            if match:
                env[match.group(1)] = match.group(2)
    except OSError:
        pass
    return env


def dirty_repos(platform):
    dirty = []
    for repo in repo_names() + repo_names(mobile=True):
        path = platform / repo
        if not path.exists():
            continue
        out = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True)
        if out.stdout.strip():
            dirty.append(repo)
    return dirty


def current_branch(path):
    out = subprocess.run(["git", "-C", str(path), "branch", "--show-current"], capture_output=True, text=True)
    return out.stdout.strip()


def pr_state(platform):
    prs = []
    for repo in repo_names() + repo_names(mobile=True):
        path = platform / repo
        branch = current_branch(path) if path.exists() else ""
        if branch:
            prs += branch_prs(repo, branch)
    if not prs:
        return "none"
    return "open" if any(p["state"] == "OPEN" for p in prs) else "finished"


def describe_platform(path):
    env = read_env(path / ".worktree.env")
    return {
        "name": path.name,
        "slug": path.name[len("platform-"):],
        "path": str(path),
        "branch": env.get("BRANCH"),
        "isolated": env.get("PIKACHU_MODE") == "isolated",
        "dirty": dirty_repos(path),
        "prs": pr_state(path),
        "modified": path.stat().st_mtime if path.exists() else 0,
    }


def platforms():
    out = subprocess.run(
        ["git", "-C", str(root_dir()), "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    paths = [Path(line.split(" ", 1)[1]) for line in out.stdout.splitlines() if line.startswith("worktree ")]
    paths = [p for p in paths if p.name.startswith("platform-")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(describe_platform, paths))
