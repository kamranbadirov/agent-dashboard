from .. import agents, jobs
from ..config import TICKET_RE
from ..root import platform_urls
from .commands import NEW_FLOWS, PLATFORM_FLOWS, build, expected_steps, review_prs


def ticket_in(text):
    match = TICKET_RE.search(text or "")
    return match.group(1) if match else ""


def agent_prompt(flow, answers):
    if flow in NEW_FLOWS:
        return None if answers["agent"] == "none" else f"/devs:implement {ticket_in(answers['branch'])}".strip()
    if flow == "review":
        return f"/devs:code-review {answers.get('ticket', '')}".strip()
    return None


def job_label(flow, answers):
    if flow in NEW_FLOWS:
        return answers["branch"]
    if flow == "review":
        return f"Review {answers.get('ticket') or ' '.join(answers['specs'].split())}"
    if flow == "clean":
        return "Clean " + ", ".join(answers["platforms"])
    return {"backend": "Shared backend", "browser": "Shared browser"}[flow] + ": " + answers["action"]


def start_agent_when_done(flow, answers, command):
    prompt = agent_prompt(flow, answers)
    if not prompt:
        return None

    def on_done(job):
        if job.state == "done":
            ok, message, record = agents.start_agent(
                command.platform, prompt, answers["where"], answers.get("terminal_app"), job.label,
                review_prs(answers) if flow == "review" else None)
            job.agent = record
            job.notice = None if ok else message

    return on_done


def job_meta(flow, answers, command):
    meta = {"flow": flow, "expected": expected_steps(flow, answers), "agent_prompt": agent_prompt(flow, answers),
            "where": answers.get("where"), "terminal_app": answers.get("terminal_app")}
    if flow in PLATFORM_FLOWS:
        meta["platform"] = command.platform
        meta["urls"] = platform_urls(command.slug, answers["backend"] == "isolated")
    return meta


def launch(flow, answers):
    commands = build(flow, answers)
    slug = "clean-" + commands[0].slug if flow == "clean" else commands[0].slug
    return jobs.start(job_label(flow, answers), slug, commands, start_agent_when_done(flow, answers, commands[0]),
                      job_meta(flow, answers, commands[0]))
