# Agent Dashboard

![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
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
| **Needs you** | The agent asks a question, waits for a tool approval, or has a PR with comments, failed checks, or an approval to merge. The tile flashes red until you click it or open it, then it turns a darker red. When you push a commit after the newest review, its open threads and "changes requested" no longer count. |
| **Running** | The agent works now. |
| **Reviewing PRs** | The agent reviews a PR that somebody else wrote. |
| **Waiting on reviewers** | The PR is open and has no action for you. |
| **Done** | All PRs of the session are merged or closed. |
| **Inactive** | The session ended. A running agent stays on the board until you stop it. |

The dashboard is a terminal board (TUI, a text interface that runs in the terminal).

## Requirements

- Python 3.10 or newer (the terminal board uses `textual-image`)
- [Claude Code](https://claude.com/claude-code)
- [GitHub CLI](https://cli.github.com/), logged in with `gh auth login`
- [tmux](https://github.com/tmux/tmux) (`brew install tmux`). It hosts the agents that the board starts.
- macOS (the terminal board uses `open` to open links)

## Install

```bash
git clone https://github.com/kamranbadirov/agent-dashboard.git
cd agent-dashboard
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The packages in `requirements.txt` are pinned because `textual-image` is used through its internals.

## Usage

```bash
python3 server.py
```

| Key | Action |
|-----|--------|
| `↑` `↓` / `j` `k` | Move between agents |
| `Enter` | Show the selected agent in the right half of the board. Press `Enter` or a printable key there to attach to the agent in tmux. `ctrl+]` detaches and goes back to the board. |
| `o` | Open the session on claude.ai |
| `p` | Open the first PR |
| `t` | Open the first Linear ticket |
| `x` | Close the selected agent, or remove an ended one. On a Done tile with a platform, it then opens Clean up with that platform picked. |
| `s` | Start work on a ticket. Type the ticket ID; Claude reads it in Linear and picks the branch, the backend and the mobile apps. You can change any of them before you start. |
| `c` | Clean up platforms. Platforms whose PRs are all merged or closed come first. |
| `n` | Start a new chat. It runs in the root checkout (set `CHAT_DIR` to change it), with no ticket, branch or platform. |
| `R` | Rename the selected agent |
| `D` | Start the dev servers (`make run`) of the selected tile's platform. Inside Rex they open in the pane below the agent. A second `D` shows the running ones. |
| `w` | Open the work wizard: new work, PR review, review only (a Claude review agent with no platform), clean up, the shared backend and the shared browser. |
| `e` | Show or hide inactive and done agents |
| `a` | Show or hide chats with no ticket or PR. `e` still decides about ended and done ones. |
| `r` | Refresh now |
| `q` | Quit |

The board refreshes every 20 seconds.

### Agents in tmux

The board starts each agent in its own tmux session.
tmux uses a private socket (`agent-board`) and the board's own config (`board/core/tmux.conf`).
Your `~/.tmux.conf` does not apply.

- The right half of the board shows the agent's screen. It does not take keys.
- `Enter` or a printable key attaches your terminal to the agent. Your terminal draws it at full speed.
- `ctrl+]` detaches and brings the board back.
- The agent keeps running when you quit the board. The next board start finds it again.
- A key on an ended agent resumes it with `claude --resume` and attaches at once.
- tmux saves the agent's output in `terminals/<id>.log`.

To see the sessions yourself, run `tmux -L agent-board ls`.

### Closing and removing agents

Press `x` on an agent. What it does depends on the agent:

- **Running agent:** the dashboard asks you to confirm, then stops the agent with `SIGTERM`.
- **Ended or done agent:** the dashboard removes the tile at once. It does not stop anything.

The dashboard saves removed sessions in `dismissed.json`.
A removed session comes back only if it has new activity.

The dashboard can also close idle agents whose PRs are all merged or closed.
This is off, because an agent often keeps working after its PRs merge, and the close ends it without a warning.
To turn it on, set `AUTO_CLOSE_MERGED=1`. Agents that are busy are never closed this way.
To close them yourself, press `X` (shift+x). The board lists the done sessions that still run and asks before it stops them.

### Raw JSON

```bash
python3 server.py --json
```

This prints the full state once and exits.

## Configuration

Set these environment variables to change the defaults:

| Variable | Default | Meaning |
|----------|---------|---------|
| `ENDED_LOOKBACK_HOURS` | `72` | How far back to look for ended sessions. |
| `NOTIFY_NEEDS_YOU` | `1` | Set to `0` to stop the desktop notification when an agent asks a question or waits for a tool approval. |
| `INFER_MODEL` | `haiku` | The Claude model that reads a ticket when you press `s`. |
| `CHAT_DIR` | the root checkout | The folder where `n` starts a new chat. It must exist. If it is a git repo, keep it on a branch with no ticket ID. |
| `AUTO_CLOSE_MERGED` | `0` | Set to `1` to let the dashboard close idle agents whose PRs are all merged or closed. |

Example:

```bash
ENDED_LOOKBACK_HOURS=24 python3 server.py
```

## Project layout

```
server.py              entry point (terminal board, --json)
board/
  core/                no UI and no HTTP; the board uses it
    config.py          paths, env vars, constants
    transcript.py      read a Claude Code session transcript
    github.py          gh CLI calls and the PR cache
    sessions.py        live and ended sessions, close an agent
    classify.py        decide which group an agent belongs to
    store.py           dismissed.json and titles.json
    state.py           build_state(), the one function the board calls
    notify.py          desktop notifications for new commits
  assets/              repo images; add <repo>.png to show a new repo
  tui/                 terminal board: app, theme, icons, format, widgets/, screens
```

Imports only point down: `tui` uses `core`, never the other way round.

## Notes

- The dashboard caches PR data for 5 minutes to limit GitHub API calls.
- The PR search and ticket links point to the `pheedloop` GitHub org and Linear workspace. Change them in `board/core/github.py` and `board/tui/app.py` for your own org.
