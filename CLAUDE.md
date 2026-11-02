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
    group.py         one tile for each ticket: group sessions by their main ticket
    plain.py         "In plain words": Haiku explains a ticket simply; cached in plain.json
    store.py         dismissed.json and titles.json
    assets.py        repo images found in board/assets
    state.py         build_state(), the one function the board calls
    notify.py        desktop notifications for new commits and for agents that need you
    cache.py         JSON file saved in batches
    root.py          find the root checkout, list its platforms
    jobs.py          run root's scripts in a thread, keep their steps and output
    ptyhost.py       the tmux host: start, capture, resize and attach board agents
    rexpane.py       inside Rex: show a board agent in a Rex pane beside the board
    procs.py         programs in board tmux that are not agents: dev servers, the backend, check fixes
    tmux.conf        the board's own tmux config; the user's ~/.tmux.conf never applies
    agents.py        start and resume agents in board tmux; also open one in a Rex tab or a terminal app
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
- `titles.json`, `dismissed.json`, `agents.json`, `plain.json` and `terminals/` are local state and are gitignored.
- The work wizard (key `w` in the terminal board) runs the scripts of the root checkout (`ROOT_REPO`; when it is not set, the dashboard's parent folder if that is a root checkout, else `~/Documents/root`). Questions are data in `core/wizard/flows.py`; to add or change a question, change it there, not in `tui/`. Answers reach root only through its environment variable overrides (`BRANCH`, `BACKEND`, `PRS`, `PLATFORM`, ...). Commands are argv lists, never shell strings. The repo list is read from root's `scripts/_lib.sh`, not copied.
- tmux hosts the agents that the board starts. Each agent is one tmux session on the private socket `agent-board`. The board starts tmux with `core/tmux.conf`.
- Every agent the board starts runs in board tmux, also with "In a new Rex tab" or "In another terminal". That choice only opens one more view, which runs `tmux attach`.
- An agent waits for you when its `~/.claude/sessions/<pid>.json` says `"status": "waiting"`. The transcript is not enough, because Claude Code writes a pending AskUserQuestion to it late. A click on the alert of a board agent brings the board's terminal app to the front (`BOARD_APP_ID`), and the board selects that agent.
- A tmux session outlives the board. After a board restart, an agent with a live tmux session is still alive. The board does not start it again.
- Inside Rex (`REX_SESSION` and `REX_BLOCK` set, `rex` on the PATH), the board shows agents in a Rex pane to its right. Enter or a click on a board agent opens the pane with `rex split`, and the pane runs `tmux attach`. Moving to another board agent runs `tmux switch-client` on that pane. It does not open a new pane. `ctrl+]` in the pane detaches and closes it. `q` closes the pane as the board quits; the agents keep running in tmux. The right panel then shows only the preview.
- Outside Rex, the right panel shows the agent. It reads `tmux capture-pane` every 250 ms in a thread, and only while the panel shows. Enter or a printable key on the panel suspends the board and runs `tmux attach`. `ctrl+]` detaches and goes back to the board.
- Enter on an ended board agent starts `claude --resume` in tmux, then shows it.
- Enter on a live session that runs outside the board offers to move it in. After a confirm, the board stops it (SIGTERM), waits until the old process exits, then resumes it in board tmux. A busy session is not moved.
- Programs that may ask for input run in board tmux too, never in another terminal app: `make run` (dev servers), `make backend` and the fix for a failed check. Each one is a tmux session named `proc-<kind>-<name>`, and it shows as a tile. Its pane stays after the program exits (`remain-on-exit`), so you can read the output. `x` stops it.
- `tmux pipe-pane` appends the agent's output to `terminals/<id>.log`. This `pipe-pane` command string is the one shell string, and `shlex.quote` quotes its path.
- If `tmux` is missing, the panel shows one error. The board does not crash.
- `AGENT_COMMAND` replaces `claude`. Use it to test with a fake agent.
- Writes are cheap by design: tmux appends agent output to the log, and `agents.json` is saved once after a quiet moment through a temp file and rename (`core/cache.py`). Do not write to disk per chunk or per keystroke.

## Design

The tile follows "option C": a colored rail on the left, then title and time, the status, and a bottom row with the ticket chip, round repo logos and the ✎ ✕ buttons. Do not show PR numbers. Each logo opens its PR.

A tile is a ticket. The sessions whose main ticket is the same share one tile (`core/group.py`). The main ticket is the first one found: the platform's branch, then the transcript, then the titles of the session's own PRs. A PR is the session's own when the session opened it (`gh pr create` in its transcript) or works on its branch. A PR the session only links does not count. The tile shows the most urgent status of its sessions and "N sessions", and it has no ✎ ✕. A session with no ticket keeps a tile of its own.

The side panel starts with the title, then one quiet row of actions with their keys (`⏎ Open  p PR  t Ticket  n Rename  x Stop`). There is no red button. "Stop" reads "Dismiss" for an ended session. For a ticket, the panel lists its sessions as numbered rows. `1` to `9` or a click picks and opens one, and the actions apply to the picked session. Enter opens the lead session: the most urgent live one, else the newest.

Under the action row, "In plain words" explains the tile's main ticket for a newcomer: the big picture (the parent project's goal), what it is, why it matters, and done when. Haiku writes it with the Linear tools (`claude -p`), in a thread. "Where it stands" is the first two sentences of the lead session's recap, with no model call. The text is saved in `plain.json`. When you view a ticket whose last check is over `PLAIN_RECHECK_SECONDS` old (1 hour), Haiku gets the saved `updatedAt` and returns "unchanged" or new text. `u` reads the ticket again now. Linear has no API key here, so only Claude can see a change. Outside Rex, a board agent's panel shows its terminal, so the block shows only for other tiles.

## Git

- Do not add Claude, a co-author line or "Generated with" text to commit messages or PR descriptions.
- Work on a feature branch, not `main`.
