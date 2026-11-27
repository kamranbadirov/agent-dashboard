import importlib

from board.core import config, github, links


def test_ticket_url_uses_the_linear_workspace(monkeypatch):
    monkeypatch.setattr(links, "LINEAR_WORKSPACE", "acme")
    assert links.ticket_url("ABC-1") == "https://linear.app/acme/issue/ABC-1"


def test_org_and_workspace_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_ORG", "acme")
    monkeypatch.delenv("LINEAR_WORKSPACE", raising=False)
    try:
        importlib.reload(config)
        assert (config.GITHUB_ORG, config.LINEAR_WORKSPACE) == ("acme", "acme")
        monkeypatch.setenv("LINEAR_WORKSPACE", "acme-team")
        importlib.reload(config)
        assert config.LINEAR_WORKSPACE == "acme-team"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_pr_searches_use_the_configured_org(monkeypatch):
    calls = []
    monkeypatch.setattr(github, "_pr_cache", {})
    monkeypatch.setattr(github, "GITHUB_ORG", "acme")
    monkeypatch.setattr(github, "gh_json", lambda args: calls.append(args) or [])
    github.my_open_prs()
    github.reviewed_prs()
    github.branch_prs("web", "ABC-1/feat/thing")
    assert "--owner=acme" in calls[0]
    assert "--owner=acme" in calls[1]
    assert "acme/web" in calls[2]


def test_opener_depends_on_the_platform(monkeypatch):
    monkeypatch.setattr(links.sys, "platform", "darwin")
    assert links.opener() == ["open"]
    monkeypatch.setattr(links.sys, "platform", "linux")
    monkeypatch.setattr(links.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert links.opener() == ["xdg-open"]
    monkeypatch.setattr(links.shutil, "which", lambda name: None)
    assert links.opener() is None
    monkeypatch.setattr(links.sys, "platform", "win32")
    assert links.opener() is None


def test_open_url_runs_the_opener(monkeypatch):
    runs = []
    monkeypatch.setattr(links, "opener", lambda: ["xdg-open"])
    monkeypatch.setattr(links.subprocess, "Popen", lambda argv, **kwargs: runs.append(argv))
    links.open_url("https://example.com")
    assert runs == [["xdg-open", "https://example.com"]]


def test_open_url_falls_back_to_the_browser_module(monkeypatch):
    opened = []
    monkeypatch.setattr(links, "opener", lambda: None)
    monkeypatch.setattr(links.webbrowser, "open", opened.append)
    links.open_url("https://example.com")
    assert opened == ["https://example.com"]
