from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class Option:
    value: str
    label: str
    detail: str = ""
    badge: str = ""  # a short warning shown before the label, such as "uncommitted"
    tag: str = ""  # a small note under the detail, such as the make command it replaces


@dataclass
class Question:
    id: str
    kind: str  # "choice", "text" or "multi"
    title: str
    help: str = ""
    options: Any = None  # a list of Option, or a function of the answers that returns one
    default: Optional[str] = None
    when: Optional[Callable] = None  # function of the answers; the question is skipped when it returns False
    validate: Optional[Callable] = None  # function of (value, answers); returns an error message or None
    short: str = ""  # a short name for the summary, such as "Backend"
    label: str = ""  # the caption above a text field
    hint: str = ""  # small help under a text field
    preview: Optional[Callable] = None  # function of (value, answers); returns (label, value) pairs for a text answer


@dataclass
class Flow:
    key: str
    label: str
    detail: str
    tag: str
    questions: list
    typed_confirm: Optional[Callable] = None  # function of the answers; the word to type before going ahead, or None


def visible(questions, answers):
    return [q for q in questions if q.when is None or q.when(answers)]


def options_for(question, answers):
    options = question.options
    return options(answers) if callable(options) else (options or [])
