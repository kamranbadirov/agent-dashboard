from board.core.group import group, lead_of, merged_prs, rank, ticket_title


def session(sid, status="working", tickets=("ABC-1",), at="2026-01-01T00:00:00Z", **more):
    return {"sessionId": sid, "status": status, "tickets": list(tickets), "lastActivity": at,
            "title": f"Session {sid}", "prs": [], "alive": True, **more}


def test_rank_orders_by_urgency():
    assert rank({"status": "your_move"}) < rank({"status": "working"}) < rank({"status": "done"})
    assert rank({"status": "unknown"}) > rank({"status": "ended"})


def test_lead_is_the_most_urgent_live_session():
    ended = session("a", status="your_move", alive=False)
    live = session("b", status="working")
    assert lead_of([ended, live])["sessionId"] == "b"


def test_lead_falls_back_to_ended_sessions():
    old = session("a", status="ended", alive=False, at="2026-01-01T00:00:00Z")
    new = session("b", status="ended", alive=False, at="2026-01-02T00:00:00Z")
    assert lead_of([old, new])["sessionId"] == "b"


def test_merged_prs_keeps_each_pr_once():
    pr = {"key": "acme/web#1"}
    a = session("a", prs=[pr])
    b = session("b", prs=[pr, {"key": "acme/api#2"}])
    assert [p["key"] for p in merged_prs([a, b])] == ["acme/web#1", "acme/api#2"]


def test_ticket_title_prefers_the_newest_pr_that_names_the_ticket():
    prs = [
        {"title": "ABC-1 Old title", "updatedAt": "2026-01-01"},
        {"title": "abc-1 New title", "updatedAt": "2026-01-02"},
        {"title": "ABC-2 Other", "updatedAt": "2026-01-03"},
    ]
    assert ticket_title("ABC-1", [session("a")], prs) == "abc-1 New title"


def test_ticket_title_falls_back_to_the_newest_session():
    old = session("a", at="2026-01-01T00:00:00Z")
    new = session("b", at="2026-01-02T00:00:00Z")
    assert ticket_title("ABC-1", [old, new], []) == "Session b"


def test_single_session_keeps_its_own_tile():
    only = session("a")
    assert group([only]) == [only]


def test_session_without_ticket_keeps_its_own_tile():
    chat = session("a", tickets=())
    other = session("b", tickets=())
    assert group([chat, other]) == [chat, other]


def test_sessions_with_the_same_ticket_share_a_tile():
    a = session("a", status="working", at="2026-01-01T00:00:00Z")
    chat = session("c", tickets=())
    b = session("b", status="your_move", tickets=("ABC-1", "ABC-9"), at="2026-01-02T00:00:00Z", alive=False)
    tiles = group([a, chat, b])
    assert [t["sessionId"] for t in tiles] == ["ticket:ABC-1", "c"]
    tile = tiles[0]
    assert tile["status"] == "your_move"
    assert tile["alive"] is True
    assert tile["tickets"] == ["ABC-1", "ABC-9"]
    assert tile["lastActivity"] == "2026-01-02T00:00:00Z"
    assert [s["sessionId"] for s in tile["group"]] == ["b", "a"]
    assert tile["lead"]["sessionId"] == "a"


def test_dev_servers_do_not_decide_the_tile():
    agent = session("a", status="working")
    server = session("s", status="your_move", proc={"kind": "up"}, at="2026-01-02T00:00:00Z")
    tile = group([agent, server])[0]
    assert tile["status"] == "working"
    assert tile["title"] == "Session a"
    assert tile["proc"] is None
