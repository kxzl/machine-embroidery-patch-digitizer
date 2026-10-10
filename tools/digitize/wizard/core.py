"""Wizard core: job spec, picture checks, fit correction, pipeline run, output folder.

Standard library only, so it imports on any Python and the fast tests need no
third-party package. Picture inspection (Pillow) and VP3 measurement (pystitch) live
in `imagecheck.py` and `vp3.py` and are handed in as plain callables.

Pinned values come from docs/design/guided-tool-readme-review.md, section 5.
"""
from __future__ import annotations

import errno
import glob
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[3]

# ---- pinned values (design contract, section 5) ---------------------------------
HOOP_SMALL = (120.0, 120.0)        # default, most patches
HOOP_LARGE = (260.0, 200.0)        # large back patch
DEFAULT_SIZE_MM = 100.0            # Patch size: longest side
WARN_EDGE_MM = 2.0                 # warn when the design ends this close to the Fit box edge
MIN_PX_PER_MM = 3.0                # the pipeline's own resolution warning
CUSTOM_HOOP_MIN, CUSTOM_HOOP_MAX = 20.0, 400.0   # proposed bounds, confirm at pause 2
SATIN_BORDER_MM = 2.5              # pipeline default border is 2.5 mm (vectorize.py border-mm)
EDGE_TOUCH_PX = 1                  # artwork this close to the picture edge counts as touching it

# ---- values from the task brief, not from the design table ----------------------
COLORS_AUTO, COLORS_FEWER, COLORS_MORE = 6, 4, 8
CUSTOM_SIZE_MIN = 10.0             # mm, assumption: smallest Patch size the wizard offers
SLUG_MAX = 80
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

KEEP_BOTH, OVERWRITE = "keep_both", "overwrite"

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_CANCELLED = 0, 1, 2, 130


# ---- small value types -----------------------------------------------------------


@dataclass
class ImageReport:
    """What the picture check found. Built by imagecheck.inspect, or by hand in tests."""

    ok: bool = True
    error: str = ""
    width: int = 0                 # whole picture, pixels
    height: int = 0
    design_w: int = 0              # the artwork's own bounds, pixels (what the pipeline scales)
    design_h: int = 0
    design_x: int = -1             # top-left of the artwork bounds, pixels (-1 = not measured)
    design_y: int = -1
    kind: str = "transparent"      # transparent | plain_background | busy_background
    background_hex: str = ""       # plain background colour, e.g. "#fefffe"


@dataclass
class Measure:
    """Stitched extent of a VP3 in 0.1 mm units (pystitch units), plus the plan."""

    width10: int
    height10: int
    stitches: int = 0
    color_changes: int = 0
    threads: List[str] = field(default_factory=list)   # "#rrggbb" in sewing order

    @property
    def thread_colours(self) -> int:
        """Distinct spools: a colour sewn twice is still one Thread colour."""
        return len(set(self.threads))

    @property
    def width_mm(self) -> float:
        return self.width10 / 10.0

    @property
    def height_mm(self) -> float:
        return self.height10 / 10.0


@dataclass
class JobSpec:
    image: Path
    key_background: bool = False
    hoop: Tuple[float, float] = HOOP_SMALL
    size_mm: Optional[float] = DEFAULT_SIZE_MM    # None = fill the hoop
    colors: int = COLORS_AUTO
    notes: List[str] = field(default_factory=list)   # plain advice carried into summary.txt


@dataclass
class Pass:
    number: int
    box: Tuple[float, float]
    measure: Measure


@dataclass
class JobResult:
    status: str                    # ok | too_big | failed
    spec: JobSpec
    slug: str = ""
    folder: Optional[Path] = None
    files: List[str] = field(default_factory=list)
    passes: List[Pass] = field(default_factory=list)
    measure: Optional[Measure] = None
    warnings: List[str] = field(default_factory=list)
    message: str = ""
    log_tail: List[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_OK if self.status == "ok" else EXIT_FAILED


# ---- text helpers ----------------------------------------------------------------


def fmt_mm(value: float) -> str:
    """120.0 -> '120', 117.14 -> '117.1'."""
    return ("%.1f" % value).rstrip("0").rstrip(".")


def fmt_box(box: Tuple[float, float]) -> str:
    return "%s x %s mm" % (fmt_mm(box[0]), fmt_mm(box[1]))


def slugify(stem: str) -> str:
    """Folder name from a file stem: outside [A-Za-z0-9._-] becomes '-', runs collapse.

    Dashes and dots at the ends are dropped, so the name can never be '.', '..' or a
    hidden folder. Nothing left means 'design'.
    """
    s = re.sub(r"[^A-Za-z0-9._-]", "-", stem)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-.")[:SLUG_MAX].strip("-.")
    return s or "design"


def parse_picture_path(raw: str) -> Path:
    """Turn what the user typed or dropped into a path.

    A path that exists exactly as typed always wins. Otherwise try the forms a terminal
    produces on drag and drop: quotes, backslash escapes, file:// links. `~` expands.
    """
    s = raw.strip()
    cands = [s]
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        cands.append(s[1:-1])
    if s.startswith("file://"):
        cands.append(urllib.parse.unquote(urllib.parse.urlparse(s).path))
    try:
        parts = shlex.split(s)
        if len(parts) == 1:
            cands.append(parts[0])
    except ValueError:
        pass
    cands.append(re.sub(r"\\(.)", r"\1", s))
    for c in cands:
        p = Path(c).expanduser()
        if p.is_file():
            return p
    return Path(cands[1] if len(cands) > 1 and cands[1] != s else s).expanduser()


def check_picture_file(path: Path) -> str:
    """Plain message when the file cannot be used, else ''."""
    if not path.exists():
        return "I cannot find a file at %s. Check the spelling, or drag the file into this window." % path
    if path.is_dir():
        return "%s is a folder. Pick the picture file inside it." % path
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "SVG pictures are not supported in the guided mode yet. Use a png, jpg, jpeg or webp picture."
    if suffix not in PICTURE_SUFFIXES:
        return "%s files are not supported. Use a png, jpg, jpeg or webp picture." % (suffix or "These")
    if not os.access(str(path), os.R_OK):
        return "I am not allowed to read %s." % path
    return ""


# ---- picture advice ----------------------------------------------------------------


def px_per_mm(report: ImageReport, size_mm: float) -> float:
    return max(report.design_w, report.design_h) / size_mm if size_mm > 0 else 0.0


def fill_size_mm(report: ImageReport, hoop: Tuple[float, float]) -> float:
    """Longest side of the design when it fills the Fit box (no rotation)."""
    if not report.design_w or not report.design_h:
        return 0.0
    ppm = max(report.design_w / hoop[0], report.design_h / hoop[1])
    return max(report.design_w, report.design_h) / ppm


def artwork_touches_edge(report: ImageReport) -> bool:
    """True when the artwork bounds reach the picture edge (within EDGE_TOUCH_PX on any side)."""
    if not report.width or not report.height or not report.design_w or not report.design_h:
        return False
    if report.design_x < 0 or report.design_y < 0:      # bounds position was not measured
        return False
    margins = (report.design_x,
               report.design_y,
               report.width - (report.design_x + report.design_w),
               report.height - (report.design_y + report.design_h))
    return min(margins) <= EDGE_TOUCH_PX


def image_advice(report: ImageReport) -> List[str]:
    """Advice that needs only the picture. Never blocks."""
    out = []
    out.append("The picture is %d x %d pixels; the artwork in it is %d x %d pixels."
               % (report.width, report.height, report.design_w, report.design_h))
    if report.kind == "transparent":
        out.append("It has a transparent background. That works best: only the artwork is stitched.")
    elif report.kind == "plain_background":
        out.append("It has a plain background (%s) that is not transparent. "
                   "If it stays, it may be stitched as a big filled area. "
                   "The program can remove it first." % (report.background_hex or "one colour"))
    else:
        out.append("The background is not transparent and not one plain colour. "
                   "The whole picture, background included, will be stitched. "
                   "A picture with a transparent background (png) works much better.")
    if artwork_touches_edge(report):
        out.append("The artwork touches the edge of the picture. "
                   "The satin border is then stitched about %s mm outside the size you chose, "
                   "so the patch comes out bigger than asked. Leave a little empty space around "
                   "the artwork (a few percent of the width on every side) for an exact size."
                   % fmt_mm(SATIN_BORDER_MM))
    return out


def resolution_advice(report: ImageReport, size_mm: float) -> List[str]:
    """Resolution advice at a chosen size. Never blocks."""
    ppm = px_per_mm(report, size_mm)
    need = int(-(-MIN_PX_PER_MM * size_mm // 1))
    long_px = max(report.design_w, report.design_h)
    if ppm >= MIN_PX_PER_MM:
        return ["At %s mm the picture gives %.1f pixels per mm. That is enough detail (the program wants at least %g)."
                % (fmt_mm(size_mm), ppm, MIN_PX_PER_MM)]
    return ["At %s mm the picture gives only %.1f pixels per mm; the program wants at least %g. "
            "Expect rough, stair-stepped edges and lost fine detail. "
            "For %s mm the artwork should be at least %d pixels along its longest side; yours is %d. "
            "Choose a smaller size or use a larger picture."
            % (fmt_mm(size_mm), ppm, MIN_PX_PER_MM, fmt_mm(size_mm), need, long_px)]


def rotation_advice(report: ImageReport, hoop: Tuple[float, float], size_mm: Optional[float]) -> List[str]:
    """Advice only, the picture is never rotated. Empty when turning it would not help."""
    if hoop[0] == hoop[1] or not report.design_w or not report.design_h:
        return []
    now = fill_size_mm(report, hoop)
    turned = fill_size_mm(ImageReport(design_w=report.design_h, design_h=report.design_w), hoop)
    wanted = size_mm if size_mm is not None else turned
    if turned > now * 1.1 and now < wanted:
        return ["Turning the picture 90 degrees would allow %s mm along its longest side instead of %s mm."
                % (fmt_mm(min(turned, wanted)), fmt_mm(now))]
    return []


# ---- fit measurement and correction ---------------------------------------------------


def tenths(mm: float) -> int:
    return int(round(mm * 10))


def overshoot(m: Measure, box: Tuple[float, float]) -> Tuple[float, float]:
    """How far the stitched extent is over the Fit box, per axis, in mm (0 when inside)."""
    return (max(0, m.width10 - tenths(box[0])) / 10.0, max(0, m.height10 - tenths(box[1])) / 10.0)


def corrected_box(box: Tuple[float, float], over: Tuple[float, float]) -> Optional[Tuple[float, float]]:
    """Fit box for the second pass: (W - dw, H - dh). None when nothing sensible is left."""
    w, h = round(box[0] - over[0], 1), round(box[1] - over[1], 1)
    return (w, h) if w > 0 and h > 0 else None


def edge_warnings(m: Measure, box: Tuple[float, float]) -> List[str]:
    """Warn when the stitched design ends within WARN_EDGE_MM of the Fit box edge."""
    out = []
    for name, ext10, side in (("wide", m.width10, box[0]), ("high", m.height10, box[1])):
        gap = (tenths(side) - ext10) / 10.0
        if 0 <= gap < WARN_EDGE_MM:
            out.append("The stitched design is %s mm %s and ends %s mm from the edge of the %s mm hoop area "
                       "(less than %g mm). A hoop clip or a small shift of the fabric could cause trouble."
                       % (fmt_mm(ext10 / 10.0), name, fmt_mm(gap), fmt_mm(side), WARN_EDGE_MM))
    return out


# ---- pipeline command ---------------------------------------------------------------------


def pipeline_args(spec: JobSpec, box: Tuple[float, float]) -> List[str]:
    """Flags for run.sh. The hoop is always a cap (--fit-mm); the size is added on the size route."""
    args = ["--colors", str(spec.colors), "--fit-mm", "%sx%s" % (fmt_mm(box[0]), fmt_mm(box[1]))]
    if spec.size_mm is not None:
        args += ["--size-mm", fmt_mm(spec.size_mm)]
    if spec.key_background:
        args.append("--key-background")
    return args


def manual_command(spec: JobSpec) -> str:
    """The run.sh command a person can type for these choices."""
    return "tools/digitize/run.sh " + " ".join(shlex.quote(a) for a in pipeline_args(spec, spec.hoop)) \
        + " " + shlex.quote(str(spec.image))


def stage_label(line: str) -> Optional[str]:
    """Plain words for a run.sh progress line, or None."""
    if line.startswith("== digitizing"):
        return "Reading the picture and planning the stitches"
    if line.startswith("== exporting"):
        return "Making the embroidery file"
    if line.startswith("== stitch plan"):
        return "Checking the stitch plan and drawing previews"
    return None


# ---- running run.sh -----------------------------------------------------------------------


def _kill_group(proc: subprocess.Popen) -> None:
    """Stop run.sh and everything it started (python, Ink/Stitch), then reap it."""
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    try:  # sweep members that outlived the leader
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _run_pipeline(run_sh: Path, root: Path, args: Sequence[str], image: Path,
                  on_line: Callable[[str], None]) -> int:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(["bash", str(run_sh)] + list(args) + [str(image)], cwd=str(root), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                            errors="replace", bufsize=1, start_new_session=True)
    try:
        with proc.stdout:
            for line in proc.stdout:
                on_line(line.rstrip("\n"))
        proc.wait()
    except BaseException:
        _kill_group(proc)
        raise
    return proc.returncode


def _legacy_dirs(root: Path) -> List[Path]:
    return [root / "output_inkstitch_svg", root / "output_vp3", root / "work"]


def _err_tail(root: Path, base: str, lines: int = 8) -> List[str]:
    try:
        text = (root / "work" / (base + ".err")).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [r for r in text.splitlines() if r.strip()][-lines:]


def _bases_files(root: Path, base: str) -> List[Path]:
    found = []
    for d in _legacy_dirs(root):
        stem = os.path.join(glob.escape(str(d)), glob.escape(base))
        for suffix in (".*", "_*"):
            found += [Path(p) for p in glob.glob(stem + suffix)]
    return found


def _purge(root: Path, base: str) -> None:
    for p in _bases_files(root, base):
        try:
            p.unlink()
        except OSError:
            pass


def _collect(root: Path, base: str, dest: Path) -> None:
    """Move the deliverables of one run into dest and delete the work leftovers."""
    dest.mkdir(parents=True, exist_ok=True)
    work = root / "work"
    for p in _bases_files(root, base):
        if p.parent == work:
            try:
                p.unlink()
            except OSError:
                pass
        else:
            shutil.move(str(p), str(dest / p.name))


def _make_base(slug: str) -> str:
    return "wiz-%s-%s" % (secrets.token_hex(4), slug.replace(".", "_"))


# ---- output folder ---------------------------------------------------------------------------


def pick_name(out_root: Path, slug: str, policy: str) -> str:
    """slug, or slug-2, slug-3 ... when it exists. Only an existing real folder can be overwritten."""
    first = out_root / slug
    if policy == OVERWRITE and (not os.path.lexists(str(first)) or (first.is_dir() and not first.is_symlink())):
        return slug
    n = 1
    while os.path.lexists(str(out_root / (slug if n == 1 else "%s-%d" % (slug, n)))):
        n += 1
    return slug if n == 1 else "%s-%d" % (slug, n)


def _swap_in(stage: Path, final: Path, out_root: Path) -> None:
    """Replace an existing folder: move the old one aside, move the new one in, drop the old."""
    old = out_root / (".wiz-old-" + secrets.token_hex(4))
    os.rename(str(final), str(old))
    try:
        os.rename(str(stage), str(final))
    except BaseException:
        os.rename(str(old), str(final))
        raise
    shutil.rmtree(str(old), ignore_errors=True)


def publish(stage: Path, out_root: Path, slug: str, policy: str,
            before: Callable[[str], None]) -> Path:
    """Move the finished stage folder to output/<name>. `before(name)` runs just before the move."""
    for _ in range(100):
        name = pick_name(out_root, slug, policy)
        final = out_root / name
        before(name)
        try:
            if policy == OVERWRITE and os.path.lexists(str(final)):
                _swap_in(stage, final, out_root)
            else:
                os.rename(str(stage), str(final))
            return final
        except OSError as exc:
            if policy != OVERWRITE and exc.errno in (errno.EEXIST, errno.ENOTEMPTY, errno.ENOTDIR):
                continue  # somebody took the name since we looked: pick the next one
            raise
    raise OSError("could not find a free folder name for %s" % slug)


# ---- summary text -------------------------------------------------------------------------------


# vectorize.py: "warning: satin <id> is <w> mm wide, below Ink/Stitch's <gate> mm gate -- ..."
_SATIN_WARNING_RE = re.compile(
    r"\s*warning:\s*satin\s+[A-Za-z0-9_-]+\s+is\s+([0-9]+(?:\.[0-9]+)?)\s*mm wide,\s*"
    r"below Ink/Stitch's\s+([0-9]+(?:\.[0-9]+)?)\s*mm gate", re.I)
# vectorize.py: "note: dropped N outline satin(s) shorter than their own width (A -> B)"
_DROPPED_NOTE_RE = re.compile(r"\s*note:\s*dropped\s+(\d+)\s+outline satin", re.I)


def _satin_summary(count: int, narrowest: float, gate: str) -> str:
    """One plain line for all the narrow-satin warnings."""
    if count == 1:
        return ("1 thin line is narrower than the %s mm the machine needs for a satin stitch "
                "(it is %.2f mm). It will sew as a thin running stitch. "
                "A bigger patch or a bolder picture gives a better result." % (gate, narrowest))
    return ("%d thin lines are narrower than the %s mm the machine needs for a satin stitch "
            "(the narrowest is %.2f mm). They will sew as a thin running stitch. "
            "A bigger patch or a bolder picture gives a better result." % (count, gate, narrowest))


def _pipeline_warnings(lines: Sequence[str]) -> List[str]:
    """Plain warnings for the summary.

    Every `warning:` line is copied, first letter capitalised, exact duplicates dropped. The
    per-satin gate warnings (one per narrow satin) are collapsed into a single line with the
    count and the narrowest width, and the dropped-outline note becomes one plain sentence, so
    a beginner does not see a flood of near-identical lines.
    """
    out: List[str] = []
    seen = set()
    satin_widths: List[float] = []
    satin_gate = ""
    satin_at: Optional[int] = None
    dropped_total = 0
    dropped_at: Optional[int] = None
    for ln in lines:
        sm = _SATIN_WARNING_RE.match(ln)
        if sm:
            key = re.sub(r"\s+", " ", ln.strip().lower())
            if key not in seen:                       # exact duplicates across passes count once
                seen.add(key)
                satin_widths.append(float(sm.group(1)))
                satin_gate = satin_gate or sm.group(2)
            if satin_at is None:
                satin_at = len(out)
            continue
        dm = _DROPPED_NOTE_RE.match(ln)
        if dm:
            key = re.sub(r"\s+", " ", ln.strip().lower())
            if key not in seen:                       # exact duplicates across passes count once
                seen.add(key)
                dropped_total += int(dm.group(1))
            if dropped_at is None:
                dropped_at = len(out)
            continue
        m = re.match(r"\s*warning:\s*(.+)", ln, re.I)
        if m:
            text = m.group(1).strip()
            text = text[:1].upper() + text[1:]
            if text not in out:
                out.append(text)
    inserts: List[Tuple[int, str]] = []
    if satin_at is not None:
        inserts.append((satin_at, _satin_summary(len(satin_widths), min(satin_widths), satin_gate)))
    if dropped_at is not None:
        inserts.append((dropped_at, "%d very short pieces of outline were left out because they were "
                                    "shorter than they are wide." % dropped_total))
    for idx, text in sorted(inserts, key=lambda t: t[0], reverse=True):
        out.insert(idx, text)
    return out


def describe_size(spec: JobSpec) -> str:
    return "fills the hoop" if spec.size_mm is None else "%s mm longest side" % fmt_mm(spec.size_mm)


def describe_colors(spec: JobSpec) -> str:
    return "up to %d thread colours" % spec.colors


def summary_text(result: JobResult) -> str:
    """Plain-text results, the content of summary.txt."""
    spec, m = result.spec, result.measure
    rows = [("Picture", spec.image.name),
            ("Hoop", fmt_box(spec.hoop)),
            ("Patch size", describe_size(spec)),
            ("Colours", describe_colors(spec)),
            ("Background", "removed first" if spec.key_background else "left as it is")]
    lines = ["Digitize Patches: results", ""]
    if result.status == "too_big" and m:
        lines += ["TOO BIG FOR THE HOOP: the stitched design is %s x %s mm, the hoop area is %s."
                  % (fmt_mm(m.width_mm), fmt_mm(m.height_mm), fmt_box(spec.hoop)),
                  "Do not sew this file. Choose a smaller size and run it again.", ""]
    lines += ["%-17s%s" % (a + ":", b) for a, b in rows]
    if m:
        lines += ["", "%-17s%s x %s mm" % ("Stitched size:", fmt_mm(m.width_mm), fmt_mm(m.height_mm)),
                  "%-17s%s" % ("Stitches:", format(m.stitches, ",")),
                  "%-17s%d (%d thread colours)" % ("Colour changes:", m.color_changes, m.thread_colours),
                  "Sewing order:"]
        lines += ["  %d. %s" % (i, h) for i, h in enumerate(m.threads, 1)]
    if len(result.passes) > 1:
        a, b = result.passes[0], result.passes[-1]
        lines += ["", "Fit correction: the first run came out %s x %s mm, over the %s hoop area. "
                  "It was run again with a Fit box of %s, giving %s x %s mm."
                  % (fmt_mm(a.measure.width_mm), fmt_mm(a.measure.height_mm), fmt_box(spec.hoop),
                     fmt_box(b.box), fmt_mm(b.measure.width_mm), fmt_mm(b.measure.height_mm))]
    if result.folder:
        lines += ["", "Folder: %s" % result.folder, "Files:"] + ["  " + f for f in result.files]
    notes = list(spec.notes) + result.warnings
    if notes:
        lines += ["", "Warnings and advice:"] + ["  - " + n for n in notes]
    if result.message:
        lines += ["", result.message]
    return "\n".join(lines) + "\n"


# ---- the job ---------------------------------------------------------------------------------------


def run_job(spec: JobSpec, root: Path = ROOT, *, policy: str = KEEP_BOTH,
            measure: Optional[Callable[[Path], Measure]] = None,
            on_stage: Optional[Callable[[str], None]] = None,
            run_script: Optional[Path] = None, out_root: Optional[Path] = None) -> JobResult:
    """Run the pipeline for one picture and publish output/<slug>/ on success.

    The pipeline runs under a unique temporary base name, so it cannot touch existing files in
    output_inkstitch_svg/ or output_vp3/. All work happens in a hidden stage folder inside output/;
    it is renamed into place only at the end. Ctrl-C or any failure leaves no output/<slug>/ behind.
    """
    if measure is None:
        from .vp3 import measure as measure  # needs pystitch
    root = Path(root)
    out_root = Path(out_root) if out_root else root / "output"
    run_sh = Path(run_script) if run_script else root / "tools" / "digitize" / "run.sh"
    out_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".wiz-", dir=str(out_root)))
    slug = slugify(spec.image.stem)
    ext = spec.image.suffix.lower()
    bases: List[str] = []
    published = False
    try:
        passes: List[Pass] = []
        kept: List[Tuple[str, Path]] = []      # (base, dest folder) of every finished pass
        log: List[str] = []
        box = spec.hoop
        note = ""
        for number in (1, 2):
            base = _make_base(slug)
            bases.append(base)
            img = stage / "_in" / (base + ext)
            img.parent.mkdir(exist_ok=True)
            shutil.copyfile(str(spec.image), str(img))

            lines: List[str] = []

            def on_line(line: str, lines=lines) -> None:
                lines.append(line)
                label = stage_label(line)
                if label and on_stage:
                    on_stage(label)

            if on_stage:
                on_stage("Starting")
            rc = _run_pipeline(run_sh, root, pipeline_args(spec, box), img, on_line)
            err = _err_tail(root, base)
            dest = stage / ("pass%d" % number)
            _collect(root, base, dest)
            log += lines
            if rc != 0 or not (dest / (base + ".vp3")).is_file() or not (dest / (base + ".svg")).is_file():
                if number == 1:
                    tail = (lines + err)[-12:]
                    return JobResult("failed", spec, slug, log_tail=tail,
                                     message="The pipeline stopped before the files were ready (exit code %s). "
                                             "Nothing was saved." % rc)
                note = "The second run (smaller Fit box) failed, so the first result is kept."
                break
            m = measure(dest / (base + ".vp3"))
            passes.append(Pass(number, box, m))
            kept.append((base, dest))
            over = overshoot(m, spec.hoop)
            if over == (0.0, 0.0) or number == 2:
                break
            nxt = corrected_box(spec.hoop, over)
            if nxt is None:
                break
            box = nxt

        final_pass, (fbase, fdest) = passes[-1], kept[-1]
        m = final_pass.measure
        inside = overshoot(m, spec.hoop) == (0.0, 0.0)
        result = JobResult("ok" if inside else "too_big", spec, slug, passes=passes, measure=m)
        result.warnings = _pipeline_warnings(log) + edge_warnings(m, spec.hoop)
        if note:
            result.warnings.append(note)
        if not inside:
            result.message = ("TOO BIG FOR THE HOOP: the stitched design is %s x %s mm; the hoop area is %s. "
                              "The files were kept for a look, but do not sew them."
                              % (fmt_mm(m.width_mm), fmt_mm(m.height_mm), fmt_box(spec.hoop)))
        # final file names: <slug>.svg, <slug>.vp3, <slug>_stitchplan.png ...
        for p in sorted(fdest.iterdir()):
            os.rename(str(p), str(stage / (slug + p.name[len(fbase):])))
        shutil.rmtree(str(stage / "_in"), ignore_errors=True)
        for _b, d in kept:
            shutil.rmtree(str(d), ignore_errors=True)
        result.files = sorted(p.name for p in stage.iterdir() if p.is_file()) + ["summary.txt"]
        result.files.sort()

        def before(name: str) -> None:
            result.folder = out_root / name
            (stage / "summary.txt").write_text(summary_text(result), encoding="utf-8")

        result.folder = publish(stage, out_root, slug, policy, before)
        published = True
        return result
    finally:
        for b in bases:
            _purge(root, b)
        if not published:
            shutil.rmtree(str(stage), ignore_errors=True)
