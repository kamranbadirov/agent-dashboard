import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..config import GITHUB_ORG
from ..root import repo_names


def open_prs(repo, ticket):
    out = subprocess.run(
        ["gh", "pr", "list", "--repo", f"{GITHUB_ORG}/{repo}", "--state", "open", "--search", ticket,
         "--json", "number,title,headRefName,author"],
        capture_output=True, text=True, timeout=25,
    )
    try:
        found = json.loads(out.stdout) if out.returncode == 0 else []
    except ValueError:
        found = []
    return [{"repo": repo, "number": p["number"], "title": p["title"], "branch": p["headRefName"],
             "author": (p.get("author") or {}).get("login", "")} for p in found]


def search(ticket):
    repos = repo_names() + repo_names(mobile=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [pr for prs in pool.map(lambda r: open_prs(r, ticket), repos) for pr in prs]
