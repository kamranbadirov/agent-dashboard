# Agent dashboard

A local board for Claude Code agents. It reads `~/.claude/` session files, asks `gh` for PR state, and shows the result as a web board and a terminal board.

## Commands

- `make setup`: install gh, the icon font and Python 3.11, create `.venv`, install `requirements.txt`
- `make web` (or `python3 server.py`): web board on http://localhost:7777
- `make tui` (or `python3 server.py --tui`): terminal board
- `python3 server.py --json`: print the state once, useful to check a change in `core/`
- `.venv/bin/python -m pyflakes board`: lint (install pyflakes in the venv first)

There is no test suite. Check a change by comparing `--json` output before and after, and by loading the web page. For the terminal board, use Textual's `App.run_test()` for a headless check.

## Layout

```
server.py            entry point, calls board/__main__.py
board/
  core/              no UI and no HTTP; the only place with data logic
    config.py        paths, env vars, constants
    transcript.py    parse a session transcript
    github.py        gh calls and the PR cache
    sessions.py      live and ended sessions, close an agent
    classify.py      which group an agent belongs to
    store.py         dismissed.json and titles.json
    assets.py        repo images found in board/assets
    state.py         build_state(), the one function both boards call
    notify.py        desktop notifications for new commits
    cache.py         ring buffer, JSON file saved in batches, batched log appender
    root.py          find the root checkout, list its platforms
    jobs.py          run root's scripts in a thread, keep their steps and output
    ptyhost.py       a program in a pseudo-terminal, with its output saved
    agents.py        start and resume agents: in the board, in cmux, or in a terminal app
    wizard/          the work wizard without UI: flows.py (questions), commands.py, preflight.py, prs.py, run.py
  web/               HTTP server and static/index.html
  tui/               terminal board (Textual)
    wizard/          the wizard screen and its inputs; it only renders core/wizard/flows.py
    widgets/terminal.py   the typeable agent terminal in the right panel
  assets/            repo images, shared by both boards
```

## Rules

- Imports only point down: `web` and `tui` use `core`, never the reverse. `core` and `web` use only the standard library, so `make web` works on the system `python3`. Only `tui` needs `requirements.txt`.
- New actions (rename, close, dismiss) go in `core/`. Each board only calls them.
- API routes validate input: reject a missing session ID and a body that is not a JSON object.
- Repo logos come from `board/assets/<repo>.png`. To add a repo, add the file. Do not list repos in code.
- The terminal board needs Python 3.10+ because of `textual-image`. Its dependencies are pinned in `requirements.txt` because `tui/widgets/repo_image.py` uses `textual-image` internals.
- Terminal layout comes in whole rows and columns. Spacing in pixels (such as 8px) can only be matched sideways, not vertically.
- `titles.json`, `dismissed.json`, `agents.json` and `terminals/` are local state and are gitignored.
- The work wizard (key `w` in the terminal board) runs the scripts of the root checkout (`ROOT_REPO`, default `~/Documents/root`). Questions are data in `core/wizard/flows.py`; to add or change a question, change it there, not in `tui/`. Answers reach root only through its environment variable overrides (`BRANCH`, `BACKEND`, `PRS`, `PLATFORM`, ...). Commands are argv lists, never shell strings. The repo list is read from root's `scripts/_lib.sh`, not copied.
- Only the terminal board has the wizard and the agent terminal for now. They use `pyte` (pinned) to draw the terminal. `AGENT_COMMAND` replaces `claude`, which is how to test with a fake agent.
- Writes are cheap by design: terminal output is merged in memory and appended to disk in batches, and `agents.json` is saved once after a quiet moment through a temp file and rename (`core/cache.py`). Do not write to disk per chunk or per keystroke.

## Design

The tile follows "option C": a colored rail on the left, then title and time, the status, and a bottom row with the ticket chip, round repo logos and the ✎ ✕ buttons. Do not show PR numbers. Each logo opens its PR. The web card and the terminal tile should look the same.

## Git

- Do not add Claude, a co-author line or "Generated with" text to commit messages or PR descriptions.
- Work on a feature branch, not `main`.
