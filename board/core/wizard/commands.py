from dataclasses import dataclass

from ..root import platform_dir, repo_names, root_bin, root_const, root_dir, slugify

UNATTENDED = ["--yes", "--json"]
NEW_FLOWS = ("new", "ticket")
PLATFORM_FLOWS = NEW_FLOWS + ("review",)
IN_TMUX_FLOWS = ("backend",)
AGENT_FLOWS = ("review_only",)
BROWSER_HOST = ["bash", "scripts/browser-host.sh"]


@dataclass
class Command:
    steps: list
    env: dict
    cwd: str
    slug: str
    platform: str = ""


def backend_flag(answers):
    return "--backend" if answers["backend"] == "isolated" else "--no-backend"


def repos_flag(answers):
    if answers.get("mobile") != "yes":
        return []
    return ["--repos", ",".join((root_const("repos", "REQUIRED_REPO_NAMES") or []) + repo_names(mobile=True))]


def review_specs(answers):
    return answers["picked"] if answers["find"] == "ticket" else answers["specs"].split()


def review_prs(answers):
    """The PRs picked for a review as {repo, number}, known from the questions, so no lookup is needed."""
    return [{"repo": repo, "number": int(number)} for repo, _, number in (spec.partition("=") for spec in review_specs(answers))]


def review_slug(answers):
    if answers["find"] == "ticket":
        return slugify(f"review-{answers['ticket']}")
    repos = sorted({spec.split("=")[0] for spec in review_specs(answers)})
    return slugify("review-" + "-".join(repos))


def new_work(answers):
    slug = slugify(answers["branch"])
    argv = [root_bin(), "new", answers["branch"], "--slug", slug, backend_flag(answers), *repos_flag(answers), *UNATTENDED]
    return [Command([argv], {}, str(root_dir()), slug, str(platform_dir(slug)))]


def review(answers):
    slug = review_slug(answers)
    argv = [root_bin(), "new", *review_specs(answers), "--slug", slug, backend_flag(answers), *UNATTENDED]
    return [Command([argv], {}, str(root_dir()), slug, str(platform_dir(slug)))]


def clean(answers):
    return [
        Command([[root_bin(), "rm", name[len("platform-"):], *UNATTENDED]], {}, str(root_dir()), name[len("platform-"):])
        for name in answers["platforms"]
    ]


def backend(answers):
    if answers["action"] == "stop":
        return [Command([[root_bin(), "down", "--backend", "--yes"]], {}, str(root_dir()), "backend")]
    return [Command([[root_bin(), "up", "--backend"]], {}, str(root_dir()), "backend")]


def browser(answers):
    steps = {"start": [BROWSER_HOST + ["start"]], "restart": [BROWSER_HOST + ["stop"], BROWSER_HOST + ["start"]],
             "stop": [BROWSER_HOST + ["stop"]]}[answers["action"]]
    return [Command(steps, {"AGENT_BROWSER_HEADED": "1"}, str(root_dir()), "browser")]


def review_only(answers):
    ticket = answers["ticket"]
    return [Command([["claude", f"/ticket-review {ticket}"]], {}, str(root_dir()), slugify(f"review-only-{ticket}"))]


BUILDERS = {"review_only": review_only, "new": new_work, "ticket": new_work, "review": review, "clean": clean, "backend": backend, "browser": browser}


def build(flow, answers):
    return BUILDERS[flow](answers)


def describe(command):
    """The command as a person would type it, one variable per line."""
    lines = [f"{key}='{value}' \\" for key, value in command.env.items()]
    return "\n".join(lines + [" ".join(command.steps[-1])])


def expected_steps(flow, answers):
    """Root prints its plan first, so the steps come from the plan once the job starts."""
    return []
