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

- Python 3.12
- [Claude Code](https://claude.com/claude-code)
- [GitHub CLI](https://cli.github.com/), logged in with `gh auth login`
- macOS (the terminal board uses `open` to open links)

## Install

```bash
git clone https://github.com/kamranbadirov/agent-dashboard.git
cd agent-dashboard
python3 -m venv .venv
.venv/bin/pip install textual
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
| `e` | Show or hide inactive agents |
| `r` | Refresh now |
| `q` | Quit |

The board refreshes every 20 seconds.

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

Example:

```bash
PORT=8080 STALE_HOURS=12 python3 server.py
```

## Notes

- The server listens only on `127.0.0.1`. Other machines cannot reach it.
- The dashboard caches PR data for 90 seconds to limit GitHub API calls.
- The PR search and ticket links point to the `pheedloop` GitHub org and Linear workspace. Change them in `server.py` and `board.py` for your own org.
