import json

import pytest

from board.core import store
from board.core.cache import JsonFile
from board.core.plain import where_it_stands


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DISMISSED_FILE", tmp_path / "dismissed.json")
    monkeypatch.setattr(store, "TITLES_FILE", tmp_path / "titles.json")
    monkeypatch.setattr(store, "live_sessions", lambda: {"live": {}})
    return tmp_path


def test_missing_or_broken_files_read_as_empty(files):
    assert store.load_titles() == {}
    (files / "dismissed.json").write_text("{not json")
    assert store.load_dismissed() == {}


def test_rename_trims_and_saves_the_title(files):
    assert store.rename_session("s1", "  My   new\ttitle ") == (True, "Renamed.")
    assert store.load_titles() == {"s1": "My new title"}


def test_rename_cuts_long_titles(files):
    store.rename_session("s1", "x" * 200)
    assert len(store.load_titles()["s1"]) == 120


def test_empty_title_resets_the_name(files):
    store.rename_session("s1", "Named")
    store.rename_session("s2", "Other")
    assert store.rename_session("s1", "   ") == (True, "Title reset.")
    assert store.load_titles() == {"s2": "Other"}


def test_rename_needs_a_session_id(files):
    assert store.rename_session("", "Title") == (False, "Missing session.")
    assert store.rename_session(None, "Title") == (False, "Missing session.")


def test_dismiss_saves_a_utc_timestamp(files):
    assert store.dismiss_session("s1") == (True, "Removed.")
    stamp = json.loads((files / "dismissed.json").read_text())["s1"]
    assert stamp.endswith("Z") and len(stamp) == len("2026-01-01T00:00:00.000Z")


def test_dismiss_refuses_a_live_session(files):
    assert store.dismiss_session("live") == (False, "Close the agent before removing it.")
    assert store.load_dismissed() == {}


def test_json_file_saves_on_flush_and_reads_back(tmp_path):
    path = tmp_path / "state.json"
    cache = JsonFile(path, {})
    cache.change(lambda data: data.update(a=1))
    assert not path.exists() or json.loads(path.read_text()) == {"a": 1}
    cache.flush()
    assert json.loads(path.read_text()) == {"a": 1}
    assert not (tmp_path / "state.json.tmp").exists()
    assert JsonFile(path, {}).data == {"a": 1}


def test_json_file_flush_without_changes_writes_nothing(tmp_path):
    path = tmp_path / "state.json"
    JsonFile(path, {}).flush()
    assert not path.exists()


def test_where_it_stands_keeps_two_sentences():
    session = {"summary": "Tests pass. The PR is open! Waiting on review."}
    assert where_it_stands(session) == "Tests pass. The PR is open!"
    assert where_it_stands({"summary": "One line"}) == "One line"
    assert where_it_stands(None) == ""
