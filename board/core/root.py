import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import ROOT_REPO
from .github import branch_prs

ENV_LINE_RE = re.compile(r"^(\w+)='(.*)'$")


class RootMissing(Exception):
    pass


def root_dir():
    if not (ROOT_REPO / "bin" / "root").is_file():
        raise RootMissing(f"No root checkout at {ROOT_REPO}. Set ROOT_REPO to its path.")
    return ROOT_REPO


def root_bin():
    return str(root_dir() / "bin" / "root")


def root_const(module, name):
    text = (root_dir() / "src" / "lib" / f"{module}.ts").read_text()
    match = re.search(rf"\bconst {name}\s*=\s*(\[[^\]]*\]|\"[^\"]*\"|\d+)", text)
    if not match:
        return None
    value = match.group(1)
    if value.startswith("["):
        return re.findall(r'"([^"]+)"', value)
    return value.strip('"')


def repo_names(mobile=False):
    return root_const("repos", "MOBILE_REPO_NAMES" if mobile else "APP_REPO_NAMES") or []


def slugify(text):
    return re.sub(r"[^a-z0-9-]", "-", text.replace("/", "-").lower())


FRONTEND_DIRS = {"raichu": "raichu", "portals": "Charmander/portals", "ditto": "ditto"}


def platform_urls(branch, isolated):
    label = slugify(branch.rsplit("/", 1)[-1])
    urls = {name: f"https://{label}.{name}.localhost" for name in FRONTEND_DIRS}
    slug = slugify(branch)[: int(root_const("platform", "DNS_LABEL_LENGTH") or 60)]
    urls["pikachu"] = f"https://{slug}.pikachu.localhost" if isolated else "https://pikachu.localhost"
    return urls


def portless_url(path, name):
    try:
        out = subprocess.run(["portless", "get", name], cwd=path, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    host = out.stdout.strip().split("://", 1)[-1].split(":", 1)[0] if out.returncode == 0 else ""
    return f"https://{host}" if host else None


def live_urls(platform, guess):
    platform = Path(platform)
    env = read_env(platform / ".worktree.env")
    urls = dict(guess)
    for name, folder in FRONTEND_DIRS.items():
        if (platform / folder).is_dir():
            urls[name] = portless_url(platform / folder, name) or urls[name]
    urls["raichu"] = env.get("RAICHU_URL") or urls["raichu"]
    urls["pikachu"] = env.get("PIKACHU_URL") or urls["pikachu"]
    return urls


def browser_port():
    out = subprocess.run(["bash", "scripts/browser-host.sh", "port"], cwd=root_dir(), capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


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


def platform_of(path):
    if not path:
        return None
    path = Path(path)
    return next((p for p in (path, *path.parents) if p.name.startswith("platform-")), None)


def platform_branch(path):
    platform = platform_of(path)
    return read_env(platform / ".worktree.env").get("BRANCH") if platform else None


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
