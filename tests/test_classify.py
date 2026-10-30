from board.core.classify import action_reasons, asked_after_close, classify, is_review_agent


def test_pending_question_needs_an_answer():
    info = {"pendingTool": "AskUserQuestion", "pendingQuestion": "Which one?"}
    assert action_reasons(info, [], "waiting") == ["answer question"]


def test_pending_tool_needs_approval():
    assert action_reasons({"pendingTool": "Bash"}, [], "idle") == ["approve Bash"]


def test_busy_agent_with_pending_tool_needs_nothing():
    assert action_reasons({"pendingTool": "Bash"}, [], "busy") == []


def test_waiting_without_tool_uses_waiting_for():
    assert action_reasons({"waitingFor": "permission"}, [], "waiting") == ["permission"]
    assert action_reasons({}, [], "waiting") == ["input needed"]


def test_comments_count_new_comments_and_unresolved_threads(pr):
    reasons = action_reasons({}, [pr(newComments=1, unresolvedThreads=2)], "idle")
    assert reasons == ["3 comments on web#1"]


def test_answered_pr_ignores_threads_and_changes_requested(pr):
    answered = pr(unresolvedThreads=2, reviewDecision="CHANGES_REQUESTED", answered=True)
    assert action_reasons({}, [answered], "idle") == []


def test_own_pr_reasons(pr):
    assert action_reasons({}, [pr(reviewDecision="CHANGES_REQUESTED")], "idle") == ["changes requested on web#1"]
    assert action_reasons({}, [pr(mergeable="CONFLICTING")], "idle") == ["resolve conflicts on web#1"]
    assert action_reasons({}, [pr(checks="FAILURE")], "idle") == ["checks failing on web#1"]
    assert action_reasons({}, [pr(reviewDecision="APPROVED")], "idle") == ["merge web#1"]
    assert action_reasons({}, [pr(isDraft=True)], "idle") == ["mark web#1 ready"]


def test_approved_draft_is_not_ready_to_merge(pr):
    assert action_reasons({}, [pr(isDraft=True, reviewDecision="APPROVED")], "idle") == ["mark web#1 ready"]


def test_closed_pr_gives_no_reason(pr):
    assert action_reasons({}, [pr(state="MERGED", checks="FAILURE")], "idle") == []


def test_other_authors_pr_only_reports_new_commits(pr):
    theirs = pr(author="someone", checks="FAILURE", commitsSinceReview=2)
    assert action_reasons({}, [theirs], "idle") == ["2 new commits on web#1 since your review"]
    assert action_reasons({}, [pr(author="someone", commitsSinceReview=1)], "idle") == [
        "1 new commit on web#1 since your review"
    ]


def test_review_agent(pr):
    assert is_review_agent({}, [pr(author="someone")])
    assert is_review_agent({"title": "Review the login PR"}, [])
    assert not is_review_agent({"title": "Review my PR"}, [pr()])
    assert not is_review_agent({"title": "Chat"}, [])


def test_asked_after_close(pr):
    closed = pr(state="MERGED", closedAt="2026-01-02T00:00:00Z")
    assert asked_after_close({"lastPromptAt": "2026-01-03T00:00:00Z"}, [closed])
    assert not asked_after_close({"lastPromptAt": "2026-01-01T00:00:00Z"}, [closed])
    assert not asked_after_close({}, [closed])


def test_all_prs_closed_is_done(pr):
    status, _ = classify("idle", True, {}, [pr(state="MERGED", closedAt="2026-01-02T00:00:00Z")])
    assert status == "done"


def test_prompt_after_merge_reopens_the_session(pr):
    info = {"lastPromptAt": "2026-01-03T00:00:00Z"}
    status, reasons = classify("idle", True, info, [pr(state="MERGED", closedAt="2026-01-02T00:00:00Z")])
    assert (status, reasons) == ("your_move", ["agent finished"])


def test_busy_agent_is_working_even_with_reasons(pr):
    status, reasons = classify("busy", True, {}, [pr(checks="FAILURE")])
    assert status == "working"
    assert reasons == ["checks failing on web#1"]


def test_reasons_make_it_your_move(pr):
    assert classify("idle", True, {}, [pr(checks="FAILURE")])[0] == "your_move"
    assert classify("idle", False, {}, [pr(checks="FAILURE")])[0] == "your_move"


def test_review_agent_states(pr):
    theirs = pr(author="someone")
    assert classify("idle", True, {}, [theirs]) == ("reviewing", ["review agent idle"])
    assert classify("idle", False, {}, [theirs]) == ("ended", [])


def test_open_pr_with_nothing_to_do_waits_on_reviewers(pr):
    assert classify("idle", True, {}, [pr()]) == ("in_review", ["waiting on reviewers"])
    assert classify("idle", False, {}, [pr()]) == ("in_review", ["waiting on reviewers"])


def test_session_without_prs(pr):
    assert classify("idle", False, {}, []) == ("ended", [])
    assert classify("idle", True, {}, []) == ("your_move", ["agent finished"])
