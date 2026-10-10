"""Render every wizard screen as an SVG, for the README.

    python3 -m tools.digitize.wizard.screens_demo <output folder> [--image PICTURE]

The screens are the real ones (RichPrompter) driven by scripted answers. Only the keyboard
prompts are drawn as static text, and the pipeline run is replaced by a sample result, so the
numbers on the results screens are examples, not a measurement. Needs rich (and Pillow).
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any, List, Optional, Sequence

from . import core
from .app import run_wizard
from .core import JobResult, Measure, Pass
from .prompter import DEFAULT, CANCEL, Cancelled, Choice
from .screens import RichPrompter

SAMPLE_THREADS = ["#e8590c", "#1a1a1a", "#f2c200", "#ffffff", "#2f6fba"]


class DemoPrompter(RichPrompter):
    """RichPrompter whose prompts are scripted and drawn as text; saves one SVG per screen."""

    def __init__(self, out_dir: Path, answers: Sequence[Any]):
        from rich.console import Console
        super().__init__(Console(record=True, width=100, file=io.StringIO(), force_terminal=True,
                                 color_system="truecolor"))
        self.out_dir, self.answers, self.count, self.title, self.dirty = Path(out_dir), deque(answers), 0, "start", False

    def _flush(self) -> None:
        if not self.dirty:
            return
        self.count += 1
        name = "%02d-%s.svg" % (self.count, re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-"))
        (self.out_dir / name).write_text(self.console.export_svg(title="Digitize Patches", clear=True),
                                         encoding="utf-8")
        self.dirty = False

    def finish(self) -> None:
        self._flush()

    def step(self, n, total, title):
        self._flush()
        self.title = "step %d %s" % (n, title)
        super().step(n, total, title)
        self.dirty = True

    def say(self, text, kind="info"):
        super().say(text, kind)
        self.dirty = True

    def _answer(self, default):
        a = self.answers.popleft()
        if a is CANCEL:
            raise Cancelled()
        return default if a is DEFAULT else a

    def _ask_text(self, message, default="", validate=None):
        a = self._answer(default)
        self.console.print("[bold cyan]?[/bold cyan] %s  [cyan]%s[/cyan]" % (message, a), markup=True, highlight=False)
        self.dirty = True
        return str(a)

    def _select(self, message, choices, default):
        a = self._answer(default)
        self.console.print("[bold cyan]?[/bold cyan] [bold]%s[/bold]" % message)
        for c in choices:
            on = c.value == a
            self.console.print(("[cyan]  > %s[/cyan]" if on else "    %s") % c.label, highlight=False)
        self.dirty = True
        return a

    def _confirm(self, message, default):
        a = bool(self._answer(default))
        self.console.print("[bold cyan]?[/bold cyan] %s  [cyan]%s[/cyan]" % (message, "Yes" if a else "No"))
        self.dirty = True
        return a

    def progress(self):
        import contextlib

        @contextlib.contextmanager
        def static():
            self._flush()
            self.title = "running"
            self.console.print()
            self.console.rule("[bold]Running[/bold]", align="left")

            def update(text):
                self._last = text
            self._last = ""
            yield update
            self.console.print("[cyan]⠙[/cyan] %s  [dim]0:00:41[/dim]" % (self._last or "Making the embroidery file"))
            self.dirty = True
            self._flush()
        return static()


def sample_result(spec: core.JobSpec, folder: Path, status: str = "ok") -> JobResult:
    if status == "ok":
        m = Measure(width10=988, height10=762, stitches=27267, color_changes=4, threads=SAMPLE_THREADS)
        passes = [Pass(1, spec.hoop, Measure(width10=1229, height10=1000)), Pass(2, (117.1, 120.0), m)]
        r = JobResult("ok", spec, "Scavenger-s-Daughter-test", folder, passes=passes, measure=m)
        r.warnings = ["The stitched design is 98.8 mm wide and ends 21.2 mm from the edge of the 120 mm hoop area."][:0]
    else:
        m = Measure(width10=1231, height10=1146, stitches=31020, color_changes=3, threads=SAMPLE_THREADS[:4])
        r = JobResult("too_big", spec, "Scavenger-s-Daughter-test", folder, passes=[Pass(1, spec.hoop, m)], measure=m)
        r.message = ("TOO BIG FOR THE HOOP: the stitched design is 123.1 x 114.6 mm; the hoop area is 120 x 120 mm. "
                     "The files were kept for a look, but do not sew them.")
        r.warnings = core.edge_warnings(m, spec.hoop)
    r.files = ["Scavenger-s-Daughter-test.svg", "Scavenger-s-Daughter-test.vp3",
               "Scavenger-s-Daughter-test_coverage.png", "Scavenger-s-Daughter-test_stitchplan.png", "summary.txt"]
    return r


def sample_image(tmp: Path) -> Path:
    from PIL import Image, ImageDraw
    p = tmp / "Scavenger's Daughter test.png"
    im = Image.new("RGBA", (1000, 760), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((20, 20, 980, 740), fill=(232, 89, 12, 255))
    im.save(str(p))
    return p


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    image: Optional[Path] = None
    if "--image" in args:
        i = args.index("--image")
        image = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wizard-demo-") as t:
        tmp = Path(t)
        picture = image or sample_image(tmp)
        from .imagecheck import inspect

        def runner(spec, root, policy=core.KEEP_BOTH, on_stage=None):
            if on_stage:
                on_stage("Making the embroidery file")
            return sample_result(spec, Path("output") / "Scavenger-s-Daughter-test")

        # happy path: quoted path with an apostrophe, custom colours left on default
        p = DemoPrompter(out, ["'%s'" % picture, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT])
        run_wizard(p, tmp, runner=runner, inspect=inspect)
        p.finish()
        # the same screen when the stitched design does not fit the hoop
        p.step(7, 7, "Results when too big")
        p.show_results(sample_result(core.JobSpec(picture, hoop=core.HOOP_SMALL, size_mm=None),
                                     Path("output") / "Scavenger-s-Daughter-test", "too_big"))
        p.finish()
    print("wrote %d SVG screens to %s" % (len(list(out.glob("*.svg"))), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
