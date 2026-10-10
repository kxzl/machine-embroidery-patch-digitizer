"""The questions the wizard asks, as an interface, and a scripted stand-in for tests.

Standard library only. The real screens (rich and questionary) are in screens.py.
"""
from __future__ import annotations

import contextlib
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Sequence, Tuple


class Cancelled(Exception):
    """The person quit (Ctrl-C at a prompt, an empty answer to 'which picture', or a Cancel choice)."""


@dataclass
class Choice:
    label: str
    value: Any
    note: str = ""


class Prompter:
    """Every screen the wizard shows. One question per screen."""

    interactive = True

    def step(self, n: int, total: int, title: str) -> None: ...
    def say(self, text: str, kind: str = "info") -> None: ...        # info | good | warn | bad | dim
    def ask_path(self, message: str, hint: str = "") -> str: ...
    def choose(self, message: str, choices: Sequence[Choice], default: Any) -> Any: ...
    def ask_number(self, message: str, default: float, lo: float, hi: float) -> float: ...
    def confirm(self, message: str, default: bool = True) -> bool: ...
    def show_choices(self, rows: Sequence[Tuple[str, str]]) -> None: ...
    def progress(self) -> "contextlib.AbstractContextManager[Callable[[str], None]]": ...
    def show_results(self, result: Any) -> None: ...


DEFAULT = object()     # scripted answer meaning "press Enter" (the default)
CANCEL = object()      # scripted answer meaning Ctrl-C


class FakePrompter(Prompter):
    """Answers from a list, in order. Records everything shown in `events`."""

    def __init__(self, answers: Sequence[Any] = ()):
        self.answers = deque(answers)
        self.events: List[Tuple[str, Any]] = []

    def _next(self, kind: str, default: Any) -> Any:
        if not self.answers:
            raise AssertionError("the wizard asked for more answers than the test gave: %s" % kind)
        a = self.answers.popleft()
        if a is CANCEL:
            raise Cancelled()
        return default if a is DEFAULT else a

    def step(self, n, total, title):
        self.events.append(("step", (n, total, title)))

    def say(self, text, kind="info"):
        self.events.append(("say", (kind, text)))

    def ask_path(self, message, hint=""):
        self.events.append(("ask_path", message))
        return self._next("path", "")

    def choose(self, message, choices, default):
        self.events.append(("choose", (message, [c.value for c in choices], default)))
        while True:
            a = self._next("choice", default)
            if a in [c.value for c in choices]:
                return a
            self.events.append(("rejected", a))

    def ask_number(self, message, default, lo, hi):
        self.events.append(("ask_number", (message, default, lo, hi)))
        while True:
            a = self._next("number", default)
            if lo <= a <= hi:
                return float(a)
            self.events.append(("rejected", a))

    def confirm(self, message, default=True):
        self.events.append(("confirm", message))
        return bool(self._next("confirm", default))

    def show_choices(self, rows):
        self.events.append(("show_choices", list(rows)))

    @contextlib.contextmanager
    def progress(self) -> Iterator[Callable[[str], None]]:
        self.events.append(("progress", "start"))
        yield lambda text: self.events.append(("stage", text))
        self.events.append(("progress", "end"))

    def show_results(self, result):
        self.events.append(("results", result))

    # helpers for tests
    def kinds(self, kind: str) -> list:
        return [p for k, p in self.events if k == kind]

    def said(self) -> str:
        return "\n".join(t for _k, t in self.kinds("say"))
