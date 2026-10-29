import re
import subprocess

from ..agents import installed_terminals
from ..root import platform_dir, platform_urls, platforms, repo_names, slugify
from .model import Flow, Option, Question
from .prs import search

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
TICKET_ONLY_RE = re.compile(r"[A-Z]{2,6}-\d{1,5}")
TICKET_PREFIX_RE = re.compile(r"[A-Z]{2,6}-\d{1,5}")
DELETE_WORD = "delete"


def check_branch(value, answers):
    if len(value) < 3 or not BRANCH_RE.match(value):
        return "Use letters, numbers, dots, dashes, underscores and slashes."
    if subprocess.run(["git", "check-ref-format", f"refs/heads/{value}"]).returncode != 0:
        return "Git does not accept that branch name."
    if platform_dir(slugify(value)).exists():
        return f"platform-{slugify(value)} already exists."
    return None


def check_ticket(value, answers):
    return None if TICKET_ONLY_RE.fullmatch(value) else "Use a ticket ID like ADX-123."


def check_specs(value, answers):
    repos = repo_names() + repo_names(mobile=True)
    specs = value.split()
    if not specs:
        return "Enter at least one repo=number."
    for spec in specs:
        repo, _, number = spec.partition("=")
        if repo not in repos or not number.isdigit():
            return f"'{spec}' should look like pikachu=4521."
    return None


def check_picked(value, answers):
    return None if value else "Pick at least one."


def branch_preview(value, answers):
    slug = slugify(value)
    ticket = TICKET_PREFIX_RE.match(value)
    return [("Folder", f"../platform-{slug}"), ("Ticket", ticket.group(0) if ticket else "none found in the name"),
            ("Frontend URL", platform_urls(slug, False)["raichu"])]


def pr_options(answers):
    prs = search(answers["ticket"])
    return [Option(f"{p['repo']}={p['number']}", f"{p['repo']} #{p['number']}  {p['title']}",
                   f"{p['branch']} · {p['author']}") for p in prs]


PR_DETAIL = {"finished": "PRs merged or closed, safe to clean", "open": "PR open", "none": "no PR"}


def platform_options(answers):
    out = []
    for p in sorted(platforms(), key=lambda p: (p["prs"] != "finished", p["modified"])):
        detail = PR_DETAIL[p["prs"]] + " · " + ("own backend" if p["isolated"] else "shared backend")
        if p["dirty"]:
            detail += " · uncommitted in " + ", ".join(p["dirty"])
        out.append(Option(p["name"], p["name"], detail, badge="uncommitted" if p["dirty"] else ""))
    return out


def any_dirty(answers):
    chosen = set(answers.get("platforms") or [])
    return any(p["dirty"] for p in platforms() if p["name"] in chosen)


def terminal_options(answers):
    return [Option(name, name) for name in installed_terminals()]


is_isolated = lambda a: a.get("backend") == "isolated"
wants_agent = lambda a: a.get("agent") != "none"
in_terminal = lambda a: a.get("where") == "terminal" and wants_agent(a)

BACKEND = Question("backend", "choice", "Which backend?", "Frontends always run. This decides what they talk to.", [
    Option("shared", "Shared backend", "Uses the pikachu already running. No extra RAM, no AWS."),
    Option("isolated", "Its own backend", "Own pikachu and database. About 1 GiB RAM, needs an AWS login."),
])
SEED = Question("seed", "choice", "Add demo data?", "Adds a QA event, an attendee login and profile fields.", [
    Option("no", "No", "Empty database copied from the shared one."),
    Option("yes", "Yes", "Add the demo event."),
], when=is_isolated)
WHERE = Question("where", "choice", "Where should the agent run?", "You can move it later by resuming the session.", [
    Option("background", "In the board", "No window. Select its tile to see the terminal in the right panel."),
    Option("cmux", "In cmux", "Opens a cmux workspace in the new platform."),
    Option("terminal", "In another terminal", "Opens the terminal app you pick."),
], when=wants_agent)
TERMINAL_APP = Question("terminal_app", "choice", "Which terminal app?", "", terminal_options, when=in_terminal)

NEW_WORK = Flow("new", "Start new work", "New branch, a worktree of every repo, dependencies installed.",
                "make new · about 3 to 6 min", [
    Question("branch", "text", "Which branch?", "The same name is used in every repo.", label="Branch name",
             hint="Start with the Linear ticket ID, for example ADX-123/feat/email-fix.",
             validate=check_branch, preview=branch_preview),
    BACKEND,
    Question("mobile", "choice", "Include the mobile apps?", "Adds the ProjectGo and OnSite worktrees.", [
        Option("no", "No", "Web only."),
        Option("yes", "Yes", "Also set up ProjectGo and OnSite."),
    ]),
    SEED,
    Question("agent", "choice", "Start an agent in it?", "Optional. It starts once the platform is ready.", [
        Option("implement", "Implement the ticket", "Runs /devs:implement with the ticket from the branch name."),
        Option("none", "No agent", "Only create the platform."),
    ]),
    WHERE,
    TERMINAL_APP,
])

REVIEW = Flow("review", "Review pull requests", "Check out PR branches by ticket or PR number and run the app.",
              "make review · about 3 to 6 min", [
    Question("find", "choice", "Which pull requests?", "Search by Linear ticket, or name the PRs yourself.", [
        Option("ticket", "Linear ticket", "Finds open PRs in every repo that mention the ticket."),
        Option("prs", "PR numbers", "You give repo and number, such as pikachu=4521."),
    ]),
    Question("ticket", "text", "Which ticket?", "Open PRs that mention it are listed next.", label="Ticket ID",
             hint="For example ADX-123.", validate=check_ticket, when=lambda a: a.get("find") == "ticket"),
    Question("specs", "text", "Which PRs?", "Name each one as repo=number.", label="PRs",
             hint="Space separated, like pikachu=4521 raichu=892.", validate=check_specs, when=lambda a: a.get("find") == "prs"),
    Question("picked", "multi", "Pick the PRs", "Selected repos run the PR branch. The rest run develop.", pr_options,
             validate=check_picked, when=lambda a: a.get("find") == "ticket"),
    BACKEND,
    SEED,
    WHERE,
    TERMINAL_APP,
])

CLEAN = Flow("clean", "Clean up a platform", "Delete a worktree, its docker stack and its branches.",
             "make clean · under 1 min", [
    Question("platforms", "multi", "Which platforms?", "Select one or more to delete.", platform_options, validate=check_picked),
], typed_confirm=lambda a: DELETE_WORD if any_dirty(a) else None)

FLOWS = {f.key: f for f in (NEW_WORK, REVIEW, CLEAN)}


SHORT = {"branch": "Branch", "backend": "Backend", "mobile": "Mobile apps", "seed": "Demo data", "agent": "Agent",
         "where": "Runs", "terminal_app": "Terminal app", "find": "Search by", "ticket": "Ticket", "specs": "PRs",
         "picked": "PRs", "platforms": "Platforms"}
for _flow in FLOWS.values():
    for _question in _flow.questions:
        _question.short = SHORT.get(_question.id, _question.title)
