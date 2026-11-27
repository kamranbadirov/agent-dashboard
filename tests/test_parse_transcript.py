import json

import pytest

from board.core.transcript import conversation_prs, created_prs, parse_transcript, prompt_ticket


def user(text, at="2026-01-01T00:00:00Z", **more):
    return {"type": "user", "timestamp": at, "message": {"content": text}, **more}


def assistant(*blocks, at="2026-01-01T00:01:00Z"):
    return {"type": "assistant", "timestamp": at, "message": {"content": list(blocks)}}


def text(value):
    return {"type": "text", "text": value}


def tool_use(tool_id, name, **tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def tool_result(tool_id, content="ok"):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": content}]}}


@pytest.fixture
def write(tmp_path):
    def make(*records):
        path = tmp_path / "session.jsonl"
        path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records))
        return path
    return make


def test_basic_fields(write):
    path = write(
        user("<command-name>/clear</command-name>", isMeta=True),
        user("Fix the login page", cwd="/work/web", gitBranch="DAT-12/fix/login"),
        assistant(text("Done. The login page works."), at="2026-01-01T00:05:00Z"),
        {"type": "ai-title", "aiTitle": "Fix login"},
    )
    info = parse_transcript(path)
    assert info["firstPrompt"] == "Fix the login page"
    assert info["lastUserPrompt"] == "Fix the login page"
    assert info["lastPromptAt"] == "2026-01-01T00:00:00Z"
    assert info["lastAssistant"] == "Done. The login page works."
    assert info["lastActivity"] == "2026-01-01T00:05:00Z"
    assert info["cwd"] == "/work/web"
    assert info["gitBranch"] == "DAT-12/fix/login"
    assert info["title"] == "Fix login"
    assert info["tickets"] == ["DAT-12"]
    assert info["pendingTool"] is None
    assert "_custom" not in info


def test_custom_title_wins_over_ai_title(write):
    path = write(
        user("hello"),
        {"type": "custom-title", "customTitle": "Mine"},
        {"type": "ai-title", "aiTitle": "Generated"},
    )
    assert parse_transcript(path)["title"] == "Mine"


def test_detached_head_is_not_a_branch(write):
    path = write(user("hello", gitBranch="main"), user("again", gitBranch="HEAD"))
    assert parse_transcript(path)["gitBranch"] == "main"


def test_away_summary_drops_the_config_hint(write):
    path = write(
        user("hello"),
        {"type": "system", "subtype": "away_summary", "content": "Tests pass. (disable recaps in /config)"},
    )
    assert parse_transcript(path)["summary"] == "Tests pass."


def test_tool_without_result_is_pending(write):
    path = write(user("run it"), assistant(tool_use("t1", "Bash", command="make test")))
    info = parse_transcript(path)
    assert info["pendingTool"] == "Bash"
    assert "pendingQuestion" not in info


def test_tool_with_result_is_not_pending(write):
    path = write(user("run it"), assistant(tool_use("t1", "Bash", command="make test")), tool_result("t1"))
    assert parse_transcript(path)["pendingTool"] is None


def test_pending_question(write):
    question = tool_use("q1", "AskUserQuestion", questions=[{"question": "Which database?"}])
    info = parse_transcript(write(user("set it up"), assistant(question)))
    assert info["pendingTool"] == "AskUserQuestion"
    assert info["pendingQuestion"] == "Which database?"


def test_new_prompt_clears_pending_tools(write):
    path = write(user("run it"), assistant(tool_use("t1", "Bash", command="make test")), user("never mind"))
    assert parse_transcript(path)["pendingTool"] is None


def test_title_ticket_comes_before_branch_ticket(write):
    path = write(
        user("Start the work", gitBranch="DAT-2/feat/thing"),
        {"type": "custom-title", "customTitle": "DAT-1 The real one"},
    )
    assert parse_transcript(path)["tickets"] == ["DAT-1", "DAT-2"]


def test_prompt_ticket_needs_a_work_word_or_a_branch(write):
    assert prompt_ticket(write(user("what does DAT-9 say?"))) is None
    assert prompt_ticket(write(user("implement DAT-9"))) == "DAT-9"
    assert prompt_ticket(write(user("/build-ticket DAT-9"))) == "DAT-9"
    assert prompt_ticket(write(user("check out DAT-9/fix/crash and look"))) == "DAT-9"


def test_prompt_ticket_takes_the_latest_and_skips_meta(write):
    path = write(user("implement DAT-1"), user("fix DAT-2"), user("fix DAT-3", isMeta=True))
    assert prompt_ticket(path) == "DAT-2"


def test_ticket_falls_back_to_a_later_prompt(write):
    path = write(user("hello"), user("please implement DAT-44"))
    assert parse_transcript(path)["tickets"] == ["DAT-44"]


def test_conversation_prs_reads_links_from_both_sides(write):
    path = write(
        user("see https://github.com/acme/web/pull/7"),
        assistant(text("Opened https://github.com/acme/api/pull/8 and https://github.com/acme/web/pull/7")),
        user("https://github.com/acme/web/pull/99", isMeta=True),
    )
    assert conversation_prs(path) == {"acme/web#7": ("acme", "web", 7), "acme/api#8": ("acme", "api", 8)}


def test_created_prs_only_counts_prs_the_session_opened(write):
    path = write(
        user("look at https://github.com/acme/web/pull/1"),
        assistant(tool_use("t1", "Bash", command="gh pr create --fill")),
        tool_result("t1", "https://github.com/acme/web/pull/2"),
        assistant(tool_use("t2", "Bash", command="gh pr view 3")),
        tool_result("t2", [{"type": "text", "text": "https://github.com/acme/web/pull/3"}]),
    )
    assert created_prs(path) == ["acme/web#2"]
    assert parse_transcript(path)["createdPrs"] == ["acme/web#2"]
