import pytest

from board.core import github
from board.core.github import commits_since_review, fetch_pr


def commit(oid, at, login="author"):
    return {"commit": {"oid": oid, "committedDate": at, "author": {"user": {"login": login}}}}


def review(login, oid, at, state="COMMENTED"):
    return {"author": {"login": login}, "state": state, "submittedAt": at, "commit": {"oid": oid} if oid else None}


def pull(reviews, history):
    return {"reviews": {"nodes": reviews}, "history": {"nodes": history}}


HISTORY = [commit("a", "2026-01-01"), commit("b", "2026-01-02"), commit("c", "2026-01-03")]


def test_no_review_from_the_viewer():
    assert commits_since_review(pull([review("other", "a", "2026-01-01")], HISTORY), "author", "me") == (None, [])
    assert commits_since_review({}, "author", "me") == (None, [])


def test_counts_commits_after_the_reviewed_commit():
    base, newer = commits_since_review(pull([review("me", "a", "2026-01-01")], HISTORY), "author", "me")
    assert base == "a"
    assert [c["oid"] for c in newer] == ["b", "c"]


def test_uses_the_latest_review():
    reviews = [review("me", "a", "2026-01-01"), review("me", "b", "2026-01-02", state="APPROVED")]
    base, newer = commits_since_review(pull(reviews, HISTORY), "author", "me")
    assert base == "b"
    assert [c["oid"] for c in newer] == ["c"]


def test_ignores_pending_and_dismissed_reviews():
    reviews = [review("me", "a", "2026-01-01"), review("me", "c", "2026-01-03", state="DISMISSED")]
    assert commits_since_review(pull(reviews, HISTORY), "author", "me")[0] == "a"


def test_falls_back_to_dates_when_the_reviewed_commit_is_gone():
    base, newer = commits_since_review(pull([review("me", "gone", "2026-01-02")], HISTORY), "author", "me")
    assert base == "gone"
    assert [c["oid"] for c in newer] == ["c"]


def test_skips_the_viewers_own_commits_on_another_authors_pr():
    history = HISTORY + [commit("d", "2026-01-04", login="me")]
    _, newer = commits_since_review(pull([review("me", "a", "2026-01-01")], history), "author", "me")
    assert [c["oid"] for c in newer] == ["b", "c"]


def test_keeps_own_commits_on_the_viewers_own_pr():
    history = [commit("a", "2026-01-01", login="me"), commit("b", "2026-01-02", login="me")]
    _, newer = commits_since_review(pull([review("me", "a", "2026-01-01")], history), "me", "me")
    assert [c["oid"] for c in newer] == ["b"]


def graphql(**changes):
    pr = {
        "number": 5, "title": "ABC-1 Add a thing", "url": "https://github.com/acme/web/pull/5",
        "state": "OPEN", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED", "mergeable": "MERGEABLE",
        "headRefName": "ABC-1/feat/thing", "updatedAt": "2026-01-05", "closedAt": None,
        "author": {"login": "me"},
        "comments": {"nodes": []},
        "reviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
        "commits": {"nodes": [{"commit": {"oid": "head", "committedDate": "2026-01-03", "statusCheckRollup": {"state": "SUCCESS"}}}]},
        "history": {"nodes": []},
        **changes,
    }
    return {"data": {"repository": {"pullRequest": pr}}}


@pytest.fixture
def gh(monkeypatch):
    monkeypatch.setattr(github, "_pr_cache", {})
    calls = []

    def answer(data):
        def fake(args):
            calls.append(args)
            return data
        monkeypatch.setattr(github, "gh_json", fake)
        return calls
    return answer


def test_fetch_pr_shapes_the_result(gh):
    gh(graphql())
    pr = fetch_pr("acme", "web", 5)
    assert pr["key"] == "acme/web#5"
    assert pr["author"] == "me"
    assert pr["branch"] == "ABC-1/feat/thing"
    assert pr["checks"] == "SUCCESS"
    assert pr["headOid"] == "head"
    assert (pr["unresolvedThreads"], pr["newComments"], pr["commitsSinceReview"]) == (0, 0, 0)
    assert pr["answered"] is False
    assert pr["sinceReviewUrl"] is None


def test_fetch_pr_counts_only_open_threads(gh):
    threads = [
        {"isResolved": False, "isOutdated": False},
        {"isResolved": True, "isOutdated": False},
        {"isResolved": False, "isOutdated": True},
    ]
    gh(graphql(reviewThreads={"nodes": threads}))
    assert fetch_pr("acme", "web", 5)["unresolvedThreads"] == 1


def test_fetch_pr_counts_comments_from_people_after_the_last_push(gh):
    comments = [
        {"author": {"login": "reviewer"}, "createdAt": "2026-01-04"},
        {"author": {"login": "reviewer"}, "createdAt": "2026-01-02"},
        {"author": {"login": "me"}, "createdAt": "2026-01-04"},
        {"author": {"login": "linear"}, "createdAt": "2026-01-04"},
        {"author": {"login": "dependabot[bot]"}, "createdAt": "2026-01-04"},
    ]
    gh(graphql(comments={"nodes": comments}))
    assert fetch_pr("acme", "web", 5)["newComments"] == 1


def test_fetch_pr_is_answered_when_pushed_after_the_review(gh):
    gh(graphql(reviews={"nodes": [review("reviewer", "old", "2026-01-02", state="CHANGES_REQUESTED")]}))
    pr = fetch_pr("acme", "web", 5)
    assert pr["answered"] is True
    assert pr["reviewers"] == ["reviewer"]


def test_fetch_pr_is_not_answered_when_the_review_is_newer(gh):
    gh(graphql(reviews={"nodes": [review("reviewer", "head", "2026-01-04", state="CHANGES_REQUESTED")]}))
    assert fetch_pr("acme", "web", 5)["answered"] is False


def test_fetch_pr_links_to_the_changes_since_the_review(gh):
    gh(graphql(
        author={"login": "author"},
        reviews={"nodes": [review("me", "a", "2026-01-01")]},
        history={"nodes": [commit("a", "2026-01-01"), commit("head", "2026-01-03")]},
    ))
    pr = fetch_pr("acme", "web", 5)
    assert pr["commitsSinceReview"] == 1
    assert pr["sinceReviewUrl"] == "https://github.com/acme/web/pull/5/files/a..head"


def test_fetch_pr_caches_the_answer(gh):
    calls = gh(graphql())
    first = fetch_pr("acme", "web", 5)
    assert fetch_pr("acme", "web", 5) is first
    assert len(calls) == 1


def test_fetch_pr_returns_none_when_gh_fails(gh):
    gh(None)
    assert fetch_pr("acme", "web", 5) is None
