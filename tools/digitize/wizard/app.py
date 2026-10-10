"""The guided wizard: the order of the questions. Screens come from a Prompter."""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import core
from .core import (CUSTOM_HOOP_MAX, CUSTOM_HOOP_MIN, CUSTOM_SIZE_MIN, DEFAULT_SIZE_MM, HOOP_LARGE, HOOP_SMALL,
                   ImageReport, JobSpec, fmt_box, fmt_mm)
from .prompter import Cancelled, Choice, Prompter

TOTAL_STEPS = 7

USAGE = """Usage: python3 digitize.py            start the guided wizard
       python3 digitize.py setup      one-time install
       python3 digitize.py doctor     check that everything is ready"""

NOT_INTERACTIVE = """The guided wizard asks questions, so it needs a real terminal. This is not one, so nothing was run.
To run the same steps without questions, use run.sh with flags, for example:

  tools/digitize/run.sh --colors 6 --size-mm 100 --fit-mm 120x120 path/to/picture.png

  --colors N        how many thread colours at most
  --size-mm N       length of the longest side of the patch
  --fit-mm WxH      the biggest area in mm the stitching may fill (the hoop)
  --key-background  remove a plain, non-transparent background first (png, jpg, webp only)

The SVG goes to output_inkstitch_svg/ and the VP3 to output_vp3/. See docs/USAGE.md."""

NEEDS_SETUP = """The tool is not set up yet (%s).
Run this once:
  python3 digitize.py setup
Then start the tool again with: python3 digitize.py"""


def preflight(root: Path, check_imports: bool = True) -> List[str]:
    """What is missing, in plain words. Cheap: no export is run."""
    problems = []
    if not (root / "tools" / "digitize" / "run.sh").is_file():
        problems.append("tools/digitize/run.sh is missing")
    if not (root / ".venv" / "bin" / "python").exists():
        problems.append("there is no .venv folder")
    if not (root / "inkstitch" / "inkstitch.py").is_file():
        problems.append("Ink/Stitch is not downloaded")
    for mod in (("pystitch", "PIL", "numpy", "rich", "questionary") if check_imports else ()):
        try:
            __import__(mod)
        except ImportError:
            problems.append("the Python library %s is not installed" % mod)
    return problems


def _ask_picture(p: Prompter, inspect: Callable[[Path], ImageReport]):
    p.step(1, TOTAL_STEPS, "Which picture?")
    p.say("Drag the picture file into this window, or type its path. png, jpg, jpeg and webp work. "
          "Press Enter with nothing typed to quit.", "dim")
    while True:
        raw = p.ask_path("Picture file")
        if not raw.strip():
            raise Cancelled()
        path = core.parse_picture_path(raw)
        problem = core.check_picture_file(path)
        if problem:
            p.say(problem, "bad")
            continue
        report = inspect(path)
        if not report.ok:
            p.say(report.error, "bad")
            continue
        return path, report


def _ask_hoop(p: Prompter):
    p.step(3, TOTAL_STEPS, "Which hoop?")
    p.say("The hoop sets the biggest area the machine can stitch. The patch is made to fit inside it.", "dim")
    pick = p.choose("Hoop", [
        Choice("120 x 120 mm (most patches)", "small"),
        Choice("260 x 200 mm (large back patch)", "large"),
        Choice("Custom size", "custom")], "small")
    if pick == "small":
        return HOOP_SMALL
    if pick == "large":
        return HOOP_LARGE
    w = round(p.ask_number("Hoop width in mm", 120, CUSTOM_HOOP_MIN, CUSTOM_HOOP_MAX), 1)
    h = round(p.ask_number("Hoop height in mm", 120, CUSTOM_HOOP_MIN, CUSTOM_HOOP_MAX), 1)
    return (w, h)


def _ask_size(p: Prompter, hoop):
    p.step(4, TOTAL_STEPS, "How big should the patch be?")
    p.say("This is the length of the patch's longest side. A picture has no real size, so you decide. "
          "The patch never gets bigger than the hoop.", "dim")
    pick = p.choose("Patch size", [
        Choice("%s mm on the longest side (default)" % fmt_mm(DEFAULT_SIZE_MM), "default"),
        Choice("Fill the hoop", "fill"),
        Choice("Custom size", "custom")], "default")
    if pick == "default":
        return DEFAULT_SIZE_MM
    if pick == "fill":
        return None
    return round(p.ask_number("Longest side in mm", DEFAULT_SIZE_MM, CUSTOM_SIZE_MIN, max(hoop)), 1)


def _ask_colors(p: Prompter) -> int:
    p.step(5, TOTAL_STEPS, "How many thread colours?")
    p.say("Every extra colour means one more thread change at the machine, and a longer job.", "dim")
    return p.choose("Colours", [
        Choice("Let the program decide (up to %d)" % core.COLORS_AUTO, core.COLORS_AUTO),
        Choice("Fewer colours (up to %d): fewer thread changes, simpler look" % core.COLORS_FEWER, core.COLORS_FEWER),
        Choice("More colours (up to %d): more detail, more thread changes" % core.COLORS_MORE, core.COLORS_MORE)],
        core.COLORS_AUTO)


def run_wizard(p: Prompter, root: Path = core.ROOT, *, runner: Optional[Callable] = None,
               inspect: Optional[Callable[[Path], ImageReport]] = None) -> int:
    """Ask the questions, run the pipeline, show the results. Returns the exit code."""
    runner = runner or core.run_job
    if inspect is None:
        from .imagecheck import inspect  # needs Pillow
    try:
        path, report = _ask_picture(p, inspect)

        p.step(2, TOTAL_STEPS, "Picture check")
        for line in core.image_advice(report):
            p.say(line, "info")
        key_bg = False
        notes = list(core.image_advice(report))
        if report.kind == "plain_background":
            key_bg = p.confirm("Remove the plain background before stitching?", True)
        elif report.kind == "busy_background":
            p.say("Tip: save the artwork as a png with a transparent background and run the wizard again.", "warn")
        for line in core.resolution_advice(report, DEFAULT_SIZE_MM):
            p.say(line, "good" if core.px_per_mm(report, DEFAULT_SIZE_MM) >= core.MIN_PX_PER_MM else "warn")

        hoop = _ask_hoop(p)
        size = _ask_size(p, hoop)
        shown = size if size is not None else core.fill_size_mm(report, hoop)
        res_lines = core.resolution_advice(report, shown)
        if shown != DEFAULT_SIZE_MM:      # step 2 already said it for the default size
            for line in res_lines:
                p.say(line, "good" if core.px_per_mm(report, shown) >= core.MIN_PX_PER_MM else "warn")
        turn_lines = core.rotation_advice(report, hoop, size)
        for line in turn_lines:
            p.say(line, "warn")
        notes += res_lines + turn_lines
        colors = _ask_colors(p)

        spec = JobSpec(image=path, key_background=key_bg, hoop=hoop, size_mm=size, colors=colors, notes=notes)
        slug = core.slugify(path.stem)
        out_root = root / "output"
        policy = core.KEEP_BOTH

        p.step(6, TOTAL_STEPS, "Your choices")
        rows = [("Picture", path.name),
                ("Background", "removed first" if key_bg else "left as it is"),
                ("Hoop", fmt_box(hoop)),
                ("Patch size", core.describe_size(spec)),
                ("Colours", core.describe_colors(spec)),
                ("Files go to", "output/%s/" % slug)]
        p.show_choices(rows)
        if os.path.lexists(str(out_root / slug)):
            pick = p.choose("A folder named output/%s already exists. What now?" % slug, [
                Choice("Keep both (the new files go to output/%s)" % core.pick_name(out_root, slug, core.KEEP_BOTH),
                       core.KEEP_BOTH),
                Choice("Replace the old folder", core.OVERWRITE),
                Choice("Cancel", "cancel")], core.KEEP_BOTH)
            if pick == "cancel":
                raise Cancelled()
            policy = pick
        if not p.confirm("Start now? This takes about a minute.", True):
            raise Cancelled()

        try:
            with p.progress() as update:
                result = runner(spec, root, policy=policy, on_stage=update)
        except (Cancelled, KeyboardInterrupt):
            raise
        except Exception as exc:  # unexpected: nothing is half written, run_job cleans up
            p.say("Something went wrong: %s" % exc, "bad")
            p.say("Nothing was saved. Run `python3 digitize.py doctor` to check the setup.", "bad")
            return core.EXIT_FAILED
        p.step(7, TOTAL_STEPS, "Results")
        p.show_results(result)
        return result.exit_code
    except (Cancelled, KeyboardInterrupt):
        p.say("Cancelled. Nothing was written.", "warn")
        return core.EXIT_CANCELLED


def main(argv: Sequence[str], root: Path = core.ROOT, *, prompter: Optional[Prompter] = None,
         is_tty: Optional[bool] = None, runner: Optional[Callable] = None,
         inspect: Optional[Callable] = None) -> int:
    args = list(argv)
    if args in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if args:
        print(USAGE, file=sys.stderr)
        return core.EXIT_USAGE
    tty = (sys.stdin.isatty() and sys.stdout.isatty()) if is_tty is None else is_tty
    if not tty:
        print(NOT_INTERACTIVE)
        return core.EXIT_USAGE
    problems = preflight(Path(root), check_imports=prompter is None)
    if problems:
        print(NEEDS_SETUP % "; ".join(problems))
        return core.EXIT_USAGE
    if prompter is None:
        from .screens import RichPrompter
        prompter = RichPrompter()
    def on_term(_signum, _frame):
        raise KeyboardInterrupt()

    # A closed terminal (SIGHUP) or kill (SIGTERM) must clean up like Ctrl-C does.
    old = {sig: signal.signal(sig, on_term) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        return run_wizard(prompter, Path(root), runner=runner, inspect=inspect)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
