from dataclasses import dataclass

from ..root import platform_dir, root_dir, slugify

PREPARE = [["make", "prepare"], ["make", "_source_repos"]]


@dataclass
class Command:
    steps: list
    env: dict
    cwd: str
    slug: str
    platform: str = ""


def yes_no(value):
    return "yes" if value in ("yes", "isolated") else "no"


def backend_env(answers):
    env = {"BACKEND": yes_no(answers["backend"])}
    if answers["backend"] == "isolated":
        env["SEED_DEMO"] = "1" if answers.get("seed") == "yes" else "0"
    return env


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
    env = {"BRANCH": answers["branch"], "SLUG": slug, "MOBILE": answers["mobile"], **backend_env(answers)}
    return [Command(PREPARE + [["bash", "scripts/new.sh"]], env, str(root_dir()), slug, str(platform_dir(slug)))]


def review(answers):
    slug = review_slug(answers)
    env = {"PRS": " ".join(review_specs(answers)), "SLUG": slug, **backend_env(answers)}
    return [Command(PREPARE + [["bash", "scripts/review.sh"]], env, str(root_dir()), slug, str(platform_dir(slug)))]


def clean(answers):
    return [
        Command([["bash", "scripts/clean.sh"]], {"PLATFORM": name, "YES": "1"}, str(root_dir()), name[len("platform-"):])
        for name in answers["platforms"]
    ]


BUILDERS = {"new": new_work, "review": review, "clean": clean}


def build(flow, answers):
    return BUILDERS[flow](answers)


def describe(command):
    """The command as a person would type it, one variable per line."""
    lines = [f"{key}='{value}' \\" for key, value in command.env.items()]
    return "\n".join(lines + [" ".join(command.steps[-1])])


def expected_steps(flow, answers):
    """The stages root's scripts usually announce, so progress can show what is still ahead.
    Steps that root announces but this list lacks are added as they appear."""
    if flow == "clean":
        return ["Tearing down " + name for name in answers["platforms"]]
    first = ["Creating root worktree", "Fetching latest develop", "Adding child-repo worktrees"]
    if flow == "review":
        first = ["Searching open PRs", "Creating review platform", "Fetching PR branches", "Adding child-repo worktrees"]
    mobile = ["Adding mobile-app worktrees"] if answers.get("mobile") == "yes" else []
    backend = ["Bootstrapping isolated pikachu backend"] if answers.get("backend") == "isolated" else []
    return first + mobile + ["Writing .worktree.env + env files", "Copying local files"] + backend + ["Frontend deps"]
