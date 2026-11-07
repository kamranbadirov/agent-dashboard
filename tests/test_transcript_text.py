import json

from board.core.transcript import is_pr_create, read_head, read_tail, result_text, text_of, tickets_in


def test_text_of_string_and_blocks():
    assert text_of({"content": "hello"}) == "hello"
    blocks = [{"type": "text", "text": "one"}, {"type": "tool_use", "name": "Bash"}, {"type": "text", "text": "two"}]
    assert text_of({"content": blocks}) == "one\ntwo"
    assert text_of(None) == ""
    assert text_of({}) == ""


def test_tickets_in_finds_tickets_in_order():
    assert tickets_in("Work on DAT-630, then ENG-12") == ["DAT-630", "ENG-12"]
    assert tickets_in(None) == []


def test_tickets_in_skips_look_alikes():
    assert tickets_in("Save as UTF-8 with SHA-256, see RFC-2616 and DAT-107") == []


def test_tickets_in_skips_system_reminders():
    text = "Fix DAT-5 <system-reminder>mentions ABC-99\nhere</system-reminder>"
    assert tickets_in(text) == ["DAT-5"]


def test_is_pr_create():
    assert is_pr_create({"name": "Bash", "input": {"command": "gh pr create --fill"}})
    assert is_pr_create({"name": "mcp__github__create_pull_request"})
    assert not is_pr_create({"name": "Bash", "input": {"command": "gh pr view 3"}})
    assert not is_pr_create({"name": "Read", "input": {"command": "gh pr create"}})


def test_result_text():
    assert result_text({"content": "plain"}) == "plain"
    assert result_text({"content": [{"type": "text", "text": "a"}, "skip", {"text": "b"}]}) == "a\nb"
    assert result_text({}) == ""


def test_read_head_stops_at_the_limit_and_skips_bad_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"n": 1}\nnot json\n{"n": 2}\n{"n": 3}\n')
    assert read_head(path, limit=3) == [{"n": 1}, {"n": 2}]


def test_read_tail_reads_a_small_file_whole(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"n": 1}\nbroken\n{"n": 2}\n')
    assert read_tail(path) == [{"n": 1}, {"n": 2}]


def test_read_tail_drops_the_cut_line_of_a_large_file(tmp_path, monkeypatch):
    monkeypatch.setattr("board.core.transcript.TAIL_BYTES", 40)
    path = tmp_path / "t.jsonl"
    lines = [json.dumps({"n": n, "pad": "x" * 10}) for n in range(10)]
    path.write_text("\n".join(lines) + "\n")
    tail = read_tail(path)
    assert tail
    assert tail[-1]["n"] == 9
    assert all(rec["pad"] == "x" * 10 for rec in tail)
    assert len(tail) < 10
