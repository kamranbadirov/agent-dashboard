import pytest

from board.core import github

ME = "me"


@pytest.fixture(autouse=True)
def login(monkeypatch):
    monkeypatch.setattr(github, "_me", ME)


@pytest.fixture
def pr():
    def make(**changes):
        base = {
            "key": "acme/web#1",
            "author": ME,
            "repo": "web",
            "number": 1,
            "title": "ABC-1 Add a thing",
            "url": "https://github.com/acme/web/pull/1",
            "state": "OPEN",
            "isDraft": False,
            "reviewDecision": None,
            "mergeable": "MERGEABLE",
            "branch": "ABC-1/feat/thing",
            "unresolvedThreads": 0,
            "newComments": 0,
            "checks": "SUCCESS",
            "closedAt": None,
            "commitsSinceReview": 0,
            "answered": False,
        }
        return {**base, **changes}
    return make
