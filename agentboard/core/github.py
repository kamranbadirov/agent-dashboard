import json
import subprocess
import threading
import time

from .config import PR_CACHE_SECONDS


_pr_cache = {}


_pr_lock = threading.Lock()


def gh_json(args):
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=25
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


PR_QUERY = """
query($owner:String!,$repo:String!,$num:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$num){
      number title url state isDraft reviewDecision headRefName updatedAt
      author{login}
      comments(last:30){nodes{author{login} createdAt}}
      reviews(last:30){nodes{author{login} state submittedAt commit{oid}}}
      reviewThreads(first:100){nodes{isResolved isOutdated comments(first:1){nodes{author{login}}}}}
      commits(last:1){nodes{commit{oid committedDate statusCheckRollup{state}}}}
      history: commits(last:50){nodes{commit{oid committedDate author{user{login}}}}}
    }
  }
}
"""


def commits_since_review(pr, author, viewer):
    mine = [
        r for r in (pr.get("reviews") or {}).get("nodes") or []
        if (r.get("author") or {}).get("login") == viewer
        and r.get("state") in ("CHANGES_REQUESTED", "COMMENTED", "APPROVED")
        and r.get("commit")
    ]
    if not mine:
        return None, []
    last_review = max(mine, key=lambda r: r.get("submittedAt") or "")
    base = last_review["commit"]["oid"]
    history = [n.get("commit") or {} for n in (pr.get("history") or {}).get("nodes") or []]
    oids = [c.get("oid") for c in history]
    if base in oids:
        newer = history[oids.index(base) + 1:]
    else:
        newer = [c for c in history if (c.get("committedDate") or "") > (last_review.get("submittedAt") or "")]
    if author != viewer:
        newer = [c for c in newer if ((c.get("author") or {}).get("user") or {}).get("login") != viewer]
    return base, newer


def fetch_pr(owner, repo, num, stamp=None):
    key = f"{owner}/{repo}#{num}"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and (now - cached[0] < PR_CACHE_SECONDS or (stamp and cached[2] == stamp)):
            return cached[1]
    data = gh_json(
        [
            "api", "graphql",
            "-f", f"query={PR_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"num={num}",
        ]
    )
    pr = (((data or {}).get("data") or {}).get("repository") or {}).get("pullRequest")
    result = None
    if pr:
        me = (pr.get("author") or {}).get("login")
        last_commit = ((pr.get("commits") or {}).get("nodes") or [{}])[-1].get("commit") or {}
        pushed_at = last_commit.get("committedDate") or ""
        bots = lambda login: (login or "").endswith("[bot]") or login in ("github-actions", "linear", "linear-code")
        unresolved = [
            th for th in (pr.get("reviewThreads") or {}).get("nodes") or []
            if not th.get("isResolved") and not th.get("isOutdated")
        ]
        new_comments = [
            c for c in (pr.get("comments") or {}).get("nodes") or []
            if (c.get("author") or {}).get("login") not in (me,) and not bots((c.get("author") or {}).get("login"))
            and c.get("createdAt", "") > pushed_at
        ]
        reviews = [
            r for r in (pr.get("reviews") or {}).get("nodes") or []
            if (r.get("author") or {}).get("login") != me and r.get("state") in ("CHANGES_REQUESTED", "COMMENTED", "APPROVED")
        ]
        base, newer = commits_since_review(pr, me, my_login())
        head = last_commit.get("oid")
        result = {
            "key": key,
            "author": me,
            "repo": repo,
            "number": pr["number"],
            "title": pr["title"],
            "url": pr["url"],
            "state": pr["state"],
            "isDraft": pr["isDraft"],
            "reviewDecision": pr.get("reviewDecision"),
            "branch": pr.get("headRefName"),
            "unresolvedThreads": len(unresolved),
            "newComments": len(new_comments),
            "reviewers": sorted({(r.get("author") or {}).get("login") for r in reviews}),
            "checks": (last_commit.get("statusCheckRollup") or {}).get("state"),
            "updatedAt": pr.get("updatedAt"),
            "headOid": head,
            "commitsSinceReview": len(newer),
            "sinceReviewUrl": f"{pr['url']}/files/{base}..{head}" if newer and base and head else None,
        }
    with _pr_lock:
        _pr_cache[key] = (now, result, stamp)
    return result


def my_open_prs():
    key = "__mine__"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and now - cached[0] < PR_CACHE_SECONDS:
            return cached[1]
    data = gh_json(
        [
            "search", "prs", "--author=@me", "--owner=pheedloop", "--state=open",
            "--limit", "60", "--json", "number,title,repository,url",
        ]
    ) or []
    with _pr_lock:
        _pr_cache[key] = (now, data, None)
    return data


def reviewed_prs():
    key = "__reviewed__"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and now - cached[0] < PR_CACHE_SECONDS:
            return cached[1]
    data = gh_json(
        [
            "search", "prs", "--reviewed-by=@me", "--owner=pheedloop", "--state=open",
            "--limit", "40", "--json", "number,title,repository,url,author,updatedAt",
        ]
    ) or []
    data = [pr for pr in data if (pr.get("author") or {}).get("login") != my_login()]
    with _pr_lock:
        _pr_cache[key] = (now, data, None)
    return data


_me = None


def my_login():
    global _me
    if _me is None:
        try:
            _me = subprocess.run(
                ["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, timeout=15
            ).stdout.strip()
        except Exception:
            _me = ""
    return _me
