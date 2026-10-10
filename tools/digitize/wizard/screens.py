"""Terminal screens: rich for output, questionary for the questions.

Everything that touches questionary is in three methods (_ask_text, _select, _confirm), so the
demo recorder (screens_demo.py) can replace just those and render every screen as an SVG.
"""
from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator, Optional, Sequence, Tuple

from . import core
from .core import fmt_box, fmt_mm
from .prompter import Cancelled, Choice, Prompter

STYLES = {"info": "", "good": "green", "warn": "yellow", "bad": "bold red", "dim": "dim"}


class RichPrompter(Prompter):
    def __init__(self, console: Optional[Any] = None):
        from rich.console import Console
        self.console = console or Console()

    # ---- the only places that read the keyboard ----
    def _ask_text(self, message: str, default: str = "", validate: Optional[Callable[[str], Any]] = None) -> str:
        import questionary
        answer = questionary.text(message, default=default, validate=validate).ask()
        if answer is None:
            raise Cancelled()
        return answer

    def _select(self, message: str, choices: Sequence[Choice], default: Any) -> Any:
        import questionary
        items = [questionary.Choice(title=c.label, value=c.value) for c in choices]
        start = next((i for i, c in zip(items, choices) if c.value == default), None)
        answer = questionary.select(message, choices=items, default=start, use_shortcuts=False,
                                    instruction="(arrow keys, then Enter)").ask()
        if answer is None:
            raise Cancelled()
        return answer

    def _confirm(self, message: str, default: bool) -> bool:
        import questionary
        answer = questionary.confirm(message, default=default).ask()
        if answer is None:
            raise Cancelled()
        return bool(answer)

    # ---- output ----
    def step(self, n: int, total: int, title: str) -> None:
        self.console.print()
        self.console.rule("[bold]Step %d of %d[/bold]   %s" % (n, total, title), align="left")

    def say(self, text: str, kind: str = "info") -> None:
        self.console.print(text, style=STYLES.get(kind, ""), markup=False, highlight=False)

    def ask_path(self, message: str, hint: str = "") -> str:
        return self._ask_text(message)

    def choose(self, message, choices, default):
        return self._select(message, choices, default)

    def ask_number(self, message, default, lo, hi):
        def check(text: str):
            try:
                v = float(text.replace(",", "."))
            except ValueError:
                return "Type a number, for example 120"
            return True if lo <= v <= hi else "Type a number from %s to %s" % (fmt_mm(lo), fmt_mm(hi))
        text = self._ask_text("%s (%s to %s)" % (message, fmt_mm(lo), fmt_mm(hi)), fmt_mm(default), check)
        return float(text.replace(",", "."))

    def confirm(self, message, default=True):
        return self._confirm(message, default)

    def show_choices(self, rows: Sequence[Tuple[str, str]]) -> None:
        from rich.table import Table
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold")
        t.add_column()
        for a, b in rows:
            t.add_row(a, b)
        self.console.print(t)

    @contextlib.contextmanager
    def progress(self) -> Iterator[Callable[[str], None]]:
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(),
                      console=self.console, transient=True) as bar:
            task = bar.add_task("Starting", total=None)
            yield lambda text: bar.update(task, description=text)

    def show_results(self, result: core.JobResult) -> None:
        from rich.table import Table
        from rich.text import Text
        spec, m = result.spec, result.measure
        c = self.console
        if result.status == "failed":
            c.print("The run failed. Nothing was saved.", style="bold red")
            c.print(result.message)
            for line in result.log_tail:
                c.print("  " + line, style="dim", markup=False, highlight=False)
            return
        if result.status == "ok":
            c.print("Done. The patch fits the hoop.", style="bold green")
        else:
            c.print(result.message, style="bold red", markup=False)
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold")
        t.add_column()
        t.add_row("Stitched size", "%s x %s mm   (hoop area %s)" % (fmt_mm(m.width_mm), fmt_mm(m.height_mm),
                                                                       fmt_box(spec.hoop)))
        t.add_row("Stitches", format(m.stitches, ","))
        t.add_row("Colour changes", "%d   (%d thread colours)" % (m.color_changes, len(m.threads)))
        order = Text()
        for i, hexv in enumerate(m.threads, 1):
            order.append("%d " % i)
            order.append("   ", style="on " + hexv)
            order.append(" %s   " % hexv)
        t.add_row("Sewing order", order)
        if len(result.passes) > 1:
            a, b = result.passes[0], result.passes[-1]
            t.add_row("Fit correction", "first run %s x %s mm was too big; run again with Fit box %s"
                      % (fmt_mm(a.measure.width_mm), fmt_mm(a.measure.height_mm), fmt_box(b.box)))
        c.print(t)
        c.print()
        c.print("Files are in: %s" % result.folder, markup=False, highlight=False)
        for name in result.files:
            c.print("  " + name, markup=False, highlight=False)
        if spec.notes:
            c.print()
            c.print("About the picture", style="bold")
            for n in spec.notes:
                c.print("  - " + n, style="dim", markup=False, highlight=False)
        if result.warnings:
            c.print()
            c.print("Warnings", style="bold")
            for w in result.warnings:
                c.print("  - " + w, style="yellow", markup=False, highlight=False)
        c.print()
        c.print("The same text is saved as summary.txt in that folder.", style="dim")
