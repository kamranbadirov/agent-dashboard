# Agent dashboard

A local board for Claude Code agents. It reads `~/.claude/` session files, asks `gh` for PR state, and shows the result as a terminal board.

## Commands

- `make setup`: install gh, tmux, the icon font and Python 3.11, create `.venv`, install `requirements.txt`
- `make tui` (or `python3 server.py`): terminal board
- `python3 server.py --json`: print the state once, useful to check a change in `core/`
- `.venv/bin/python -m pyflakes board`: lint (install pyflakes in the venv first)

There is no test suite. Check a change by comparing `--json` output before and after, and by using Textual's `App.run_test()` for a headless check.

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
    state.py         build_state(), the one function the board calls
    notify.py        desktop notifications for new commits and for agents that need you
    cache.py         JSON file saved in batches
    root.py          find the root checkout, list its platforms
    jobs.py          run root's scripts in a thread, keep their steps and output
    ptyhost.py       the tmux host: start, capture, resize and attach board agents
    rexpane.py       inside Rex: show a board agent in a Rex pane beside the board
    tmux.conf        the board's own tmux config; the user's ~/.tmux.conf never applies
    agents.py        start and resume agents: in the board or in a terminal app
    wizard/          the work wizard without UI: flows.py (questions), commands.py, preflight.py, prs.py, run.py
  tui/               terminal board (Textual)
    wizard/          the wizard screen and its inputs; it only renders core/wizard/flows.py
    widgets/terminal.py   outside Rex: the read-only agent preview in the right panel; a key attaches to tmux
  assets/            repo images
```

## Rules

- Imports only point down: `tui` uses `core`, never the reverse.
- New actions (rename, close, dismiss) go in `core/`. The board only calls them.
- Repo logos come from `board/assets/<repo>.png`. To add a repo, add the file. Do not list repos in code.
- The terminal board needs Python 3.10+ because of `textual-image`. Its dependencies are pinned in `requirements.txt` because `tui/widgets/repo_image.py` uses `textual-image` internals.
- Terminal layout comes in whole rows and columns. Spacing in pixels (such as 8px) can only be matched sideways, not vertically.
- `titles.json`, `dismissed.json`, `agents.json` and `terminals/` are local state and are gitignored.
- The work wizard (key `w` in the terminal board) runs the scripts of the root checkout (`ROOT_REPO`; when it is not set, the dashboard's parent folder if that is a root checkout, else `~/Documents/root`). Questions are data in `core/wizard/flows.py`; to add or change a question, change it there, not in `tui/`. Answers reach root only through its environment variable overrides (`BRANCH`, `BACKEND`, `PRS`, `PLATFORM`, ...). Commands are argv lists, never shell strings. The repo list is read from root's `scripts/_lib.sh`, not copied.
- tmux hosts the agents that the board starts. Each agent is one tmux session on the private socket `agent-board`. The board starts tmux with `core/tmux.conf`.
- A tmux session outlives the board. After a board restart, an agent with a live tmux session is still alive. The board does not start it again.
- Inside Rex (`REX_SESSION` and `REX_BLOCK` set, `rex` on the PATH), the board shows agents in a Rex pane to its right. Enter or a click on a board agent opens the pane with `rex split`, and the pane runs `tmux attach`. Moving to another board agent runs `tmux switch-client` on that pane. It does not open a new pane. `ctrl+]` in the pane detaches and closes it. The right panel then shows only the preview.
- Outside Rex, the right panel shows the agent. It reads `tmux capture-pane` every 250 ms in a thread, and only while the panel shows. Enter or a printable key on the panel suspends the board and runs `tmux attach`. `ctrl+]` detaches and goes back to the board.
- Enter on an ended board agent starts `claude --resume` in tmux, then shows it.
- `tmux pipe-pane` appends the agent's output to `terminals/<id>.log`. This `pipe-pane` command string is the one shell string, and `shlex.quote` quotes its path.
- If `tmux` is missing, the panel shows one error. The board does not crash.
- `AGENT_COMMAND` replaces `claude`. Use it to test with a fake agent.
- Writes are cheap by design: tmux appends agent output to the log, and `agents.json` is saved once after a quiet moment through a temp file and rename (`core/cache.py`). Do not write to disk per chunk or per keystroke.

## Design

The tile follows "option C": a colored rail on the left, then title and time, the status, and a bottom row with the ticket chip, round repo logos and the ✎ ✕ buttons. Do not show PR numbers. Each logo opens its PR.

## Git

- Do not add Claude, a co-author line or "Generated with" text to commit messages or PR descriptions.
- Work on a feature branch, not `main`.
