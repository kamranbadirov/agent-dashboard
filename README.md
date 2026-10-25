# Agent Dashboard

![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-5A4FCF)
![Claude Code](https://img.shields.io/badge/for-Claude%20Code-D97757?logo=anthropic&logoColor=white)
![GitHub CLI](https://img.shields.io/badge/needs-gh%20CLI-181717?logo=github)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple)
![Dependencies](https://img.shields.io/badge/server-no%20dependencies-brightgreen)

A local board that shows all your Claude Code agents in one place.
It tells you which agents are running, which ones need you, and what state their pull requests are in.

## What it does

The dashboard reads the session files that Claude Code writes to `~/.claude/`.
For each session, it finds the title, the last reply, the Linear tickets, and the GitHub PRs.
Then it uses the `gh` CLI to get the live state of each PR.

Each agent goes into one group:

| Group | Meaning |
|-------|---------|
| **Needs you** | The agent asks a question, waits for a tool approval, or has a PR with comments, failed checks, or an approval to merge. |
| **Running** | The agent works now. |
| **Reviewing PRs** | The agent reviews a PR that somebody else wrote. |
| **Waiting on reviewers** | The PR is open and has no action for you. |
| **Done** | All PRs of the session are merged or closed. |
| **Inactive** | The session ended or had no activity for 24 hours. |

You can use the dashboard in two ways:
- **Web board** in the browser.
- **Terminal board** (TUI, a text interface that runs in the terminal).

## Requirements

- Python 3.10 or newer (the terminal board uses `textual-image`)
- [Claude Code](https://claude.com/claude-code)
- [GitHub CLI](https://cli.github.com/), logged in with `gh auth login`
- macOS (the terminal board uses `open` to open links)

## Install

```bash
git clone https://github.com/kamranbadirov/agent-dashboard.git
cd agent-dashboard
python3.11 -m venv .venv
.venv/bin/pip install textual textual-image
```

The web board uses only the Python standard library.
Only the terminal board needs `textual`.

## Usage

### Web board

```bash
python3 server.py
```

Open http://localhost:7777.

### Terminal board

```bash
python3 server.py --tui
```

| Key | Action |
|-----|--------|
| `↑` `↓` / `j` `k` | Move between agents |
| `Enter` | Resume the selected agent with `claude --resume` |
| `o` | Open the session on claude.ai |
| `p` | Open the first PR |
| `t` | Open the first Linear ticket |
| `x` | Close the selected agent, or remove an ended one |
| `e` | Show or hide inactive agents |
| `r` | Refresh now |
| `q` | Quit |

The board refreshes every 20 seconds.
You can also click the `✕` on a card, or the button in the preview pane.

### Closing and removing agents

Every card has a `✕` button. What it does depends on the agent:

- **Running agent:** the dashboard asks you to confirm, then stops the agent with `SIGTERM`.
- **Ended or done agent:** the dashboard removes the card at once. It does not stop anything.

The dashboard saves removed sessions in `dismissed.json`.
A removed session comes back only if it has new activity.

The dashboard also closes agents by itself when all their PRs are merged or closed and the agent is idle.
Agents that are busy are never closed this way.
To turn this off, set `AUTO_CLOSE_MERGED=0`.

### Raw JSON

```bash
python3 server.py --json
```

This prints the full state once and exits.

## Configuration

Set these environment variables to change the defaults:

| Variable | Default | Meaning |
|----------|---------|---------|
| `PORT` | `7777` | The port for the web board. |
| `ENDED_LOOKBACK_HOURS` | `72` | How far back to look for ended sessions. |
| `STALE_HOURS` | `24` | Hours without activity before an agent becomes inactive. |
| `AUTO_CLOSE_MERGED` | `1` | Set to `0` to stop the dashboard from closing idle agents whose PRs are all merged or closed. |

Example:

```bash
PORT=8080 STALE_HOURS=12 python3 server.py
```

## Project layout

```
server.py              entry point (web board, --tui, --json)
board/
  core/                no UI and no HTTP; both boards use it
    config.py          paths, env vars, constants
    transcript.py      read a Claude Code session transcript
    github.py          gh CLI calls and the PR cache
    sessions.py        live and ended sessions, close an agent
    classify.py        decide which group an agent belongs to
    store.py           dismissed.json and titles.json
    state.py           build_state(), the one function the boards call
    notify.py          desktop notifications for new commits
  web/                 HTTP server and static/ (the page)
  assets/              repo images, shared by both boards
  tui/                 terminal board: app, theme, icons, format, widgets/, screens
```

Imports only point down: `web` and `tui` use `core`, never the other way round.

## Notes

- The server listens only on `127.0.0.1`. Other machines cannot reach it.
- The close and remove actions (`POST /api/close` and `/api/dismiss`) accept only requests to `localhost` or `127.0.0.1` with a JSON body.
- The dashboard caches PR data for 90 seconds to limit GitHub API calls.
- The PR search and ticket links point to the `pheedloop` GitHub org and Linear workspace. Change them in `board/core/github.py` and `board/tui/app.py` (and `board/web/static/index.html`) for your own org.
