from datetime import datetime, timedelta, timezone

from board.tui.format import ago, chips, headline, pr_badges, prs_for


def stamp(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_ago():
    assert ago(None) == ""
    assert ago(stamp(seconds=5)) == "just now"
    assert ago(stamp(minutes=5, seconds=5)) == "5m ago"
    assert ago(stamp(hours=3, seconds=5)) == "3h ago"
    assert ago(stamp(days=2, seconds=5)) == "2d ago"


def test_headline():
    assert headline({"reasons": []}) == "Check the result"
    assert headline({"reasons": ["agent finished"]}) == "Check the result"
    assert headline({"reasons": ["answer question"]}) == "Answer a question"
    assert headline({"reasons": ["input needed"]}) == "Answer a question"
    assert headline({"reasons": ["approve Bash", "merge web#1"]}) == "Approve Bash"
    assert headline({"reasons": ["checks failing on web#1"]}) == "Checks failing on web#1"


def labels(p):
    return [label for label, _ in pr_badges(p)]


def test_closed_pr_badges(pr):
    assert labels(pr(state="MERGED")) == ["merged"]
    assert labels(pr(state="CLOSED", isDraft=True)) == ["closed", "draft"]


def test_quiet_open_pr_is_in_review(pr):
    assert labels(pr()) == ["in review"]
    assert labels(pr(isDraft=True)) == ["draft"]


def test_open_pr_badges(pr):
    busy = pr(commitsSinceReview=1, unresolvedThreads=2, newComments=3,
              reviewDecision="CHANGES_REQUESTED", checks="FAILURE")
    assert labels(busy) == ["1 new commit since your review", "2 unresolved", "3 new comments",
                            "changes requested", "checks failing"]
    assert labels(pr(reviewDecision="APPROVED", checks="PENDING")) == ["approved", "checks running"]


def test_chips_separates_items_with_a_space():
    assert chips(["a", "b"]).plain == " a   b "
    assert chips([]).plain == ""


def test_prs_for_matches_the_title_or_the_branch(pr):
    by_title = pr(title="abc-1 thing", branch="other")
    by_branch = pr(title="thing", branch="ABC-1/feat/thing")
    other = pr(title="ABC-2 thing", branch="ABC-2/feat/thing")
    assert prs_for({"prs": [by_title, by_branch, other]}, "ABC-1") == [by_title, by_branch]
