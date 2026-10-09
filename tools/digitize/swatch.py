#!/usr/bin/env python3
"""Calibration swatch: the vadmel fill/satin settings on one small sew-out.

Writes a ready-to-sew Ink/Stitch SVG (mm user units: ``width``/``height`` in mm,
``viewBox`` in the same mm).  Thread colours are grouped into layers in stitch
order.  Everything is separate and ``trim_after``; VP3 has no jump command, so
an untrimmed move would be sewn.

Contents (review.md 2.9):
  A. 3 x 3 grid of two-colour squares.  Columns vary fill ``row_spacing_mm``
     (0.30 / 0.35 / 0.40), rows vary ``pull_compensation_mm`` (0 / 0.2 / 0.3).
     The light square fills a 1 mm-wider dark frame sewn first, edge to edge, so
     an opening seam shows the fabric.  Fill angle 0 puts vertical row-end seams
     on the left/right and horizontal row-side seams on top/bottom.
  B. A row of three fills at row_spacing 0.35 / pull 0.25 with
     ``fill_underlay_angle`` default, ``"90 0"`` (two passes), and off.
  C. Eight 30 mm centre-line satin columns at widths 1.0 / 1.5 / 2.5 / 4.0 mm,
     each plain and each with center-walk + contour underlay (inset 0.4 mm).
  D. A legend next to the SVG mapping every cell position (mm, top-left) to its
     settings.  Printed too.

Usage:
    tools/digitize/swatch.py [--light HEX] [--dark HEX] [--size small|normal]
                             [--out output_inkstitch_svg/swatch_vadmel.svg]
"""
import argparse
import os

LIGHT_DEFAULT = "#ffffff"
DARK_DEFAULT = "#87f70f"          # the dark "neighbour" colour

SPACINGS = (0.30, 0.35, 0.40)     # grid columns: fill row_spacing_mm
PULLS = (0.0, 0.2, 0.3)           # grid rows: fill pull_compensation_mm
B_ROW_SPACING = 0.35
B_PULL = 0.25
B_VARIANTS = (("default", None), ("two passes", "90 0"), ("off", False))
FRAME_SPACING = 0.35
FRAME_ANGLE = 90                  # 90 deg to the light fill, the worst seam case

SATIN_WIDTHS = (1.0, 1.5, 2.5, 4.0)
SATIN_ZIGZAG = 0.35
SATIN_PULL = 0.2
CONTOUR_INSET = 0.4

SIZES = {
    "normal": dict(margin=6.0, cell=12.0, wall=1.0, gap=3.0, col_gap=12.0,
                   satin_len=30.0, satin_pitch=6.0),
    "small": dict(margin=4.0, cell=12.0, wall=1.0, gap=2.0, col_gap=6.0,
                  satin_len=30.0, satin_pitch=5.5),
}

META = (("min_stitch_len_mm", "0.1"),
        ("collapse_len_mm", "3"),
        ("min_satin_stroke_width_mm", "0.5"),
        ("inkstitch_svg_version", "4"))


def _hex(value):
    value = value.strip()
    if not value.startswith("#"):
        value = "#" + value
    return value.lower()


def _rect(x, y, w, h):
    return (f"M {x:.2f},{y:.2f} L {x + w:.2f},{y:.2f} "
            f"L {x + w:.2f},{y + h:.2f} L {x:.2f},{y + h:.2f} Z")


def _frame_d(x, y, outer, inner):
    """Outer square with an even-odd hole; the light fill is the exact hole."""
    off = (outer - inner) / 2.0
    return f"{_rect(x, y, outer, outer)} {_rect(x + off, y + off, inner, inner)}"


def _attrs(items):
    return " ".join(f'inkstitch:{k}="{v}"' for k, v in items)


def fill_path(id_, color, d, row_spacing, pull, angle, underlay, trim=True):
    items = [("row_spacing_mm", f"{row_spacing:g}"),
             ("max_stitch_length_mm", "3"),
             ("angle", f"{angle:g}"),
             ("pull_compensation_mm", f"{pull:g}")]
    if underlay is False:
        items.append(("fill_underlay", "false"))
    else:
        items.append(("fill_underlay", "true"))
        if underlay is not None:
            items.append(("fill_underlay_angle", underlay))
    if trim:
        items.append(("trim_after", "true"))
    return (f'<path id="{id_}" style="fill:{color};stroke:none" '
            f'fill-rule="evenodd" {_attrs(items)} d="{d}"/>')


def satin_path(id_, color, x0, x1, y, width, underlay, trim=True):
    items = [("satin_column", "true"),
             ("zigzag_spacing_mm", f"{SATIN_ZIGZAG:g}"),
             ("pull_compensation_mm", f"{SATIN_PULL:g} {SATIN_PULL:g}")]
    if underlay:
        items += [("center_walk_underlay", "true"),
                  ("contour_underlay", "true"),
                  ("contour_underlay_inset_mm", f"{CONTOUR_INSET:g}")]
    if trim:
        items.append(("trim_after", "true"))
    d = f"M {x0:.2f},{y:.2f} L {x1:.2f},{y:.2f}"
    return (f'<path id="{id_}" style="fill:none;stroke:{color};'
            f'stroke-width:{width:.2f};stroke-linejoin:round" '
            f'{_attrs(items)} d="{d}"/>')


def build(light, dark, size):
    P = SIZES[size]
    m, cell, wall, gap = P["margin"], P["cell"], P["wall"], P["gap"]
    inner = cell - 2 * wall
    grid_w = 3 * cell + 2 * gap

    dark_objs, light_objs = [], []
    legend = {"A": [], "B": [], "C": []}
    did = lid = sid = 0

    # A. fill grid -- columns row_spacing, rows pull compensation
    ax, ay = m, m
    for r, pull in enumerate(PULLS):
        for c, sp in enumerate(SPACINGS):
            x = ax + c * (cell + gap)
            y = ay + r * (cell + gap)
            dark_objs.append(fill_path(f"d{did}", dark, _frame_d(x, y, cell, inner),
                                       FRAME_SPACING, 0.0, FRAME_ANGLE, None))
            did += 1
            light_objs.append(fill_path(f"f{lid}", light,
                                        _rect(x + wall, y + wall, inner, inner),
                                        sp, pull, 0.0, None))
            lid += 1
            legend["A"].append((r, c, pull, sp, x, y))

    # B. underlay variants
    by = ay + 3 * cell + 2 * gap + 1.5 * gap
    for c, (name, underlay) in enumerate(B_VARIANTS):
        x = ax + c * (cell + gap)
        dark_objs.append(fill_path(f"d{did}", dark, _frame_d(x, by, cell, inner),
                                   FRAME_SPACING, 0.0, FRAME_ANGLE, None))
        did += 1
        light_objs.append(fill_path(f"f{lid}", light,
                                    _rect(x + wall, by + wall, inner, inner),
                                    B_ROW_SPACING, B_PULL, 0.0, underlay))
        lid += 1
        legend["B"].append((c, name, B_ROW_SPACING, B_PULL, x, by))

    # C. satin columns, plain then underlaid, one pitch apart
    sx0 = ax + grid_w + P["col_gap"]
    sx1 = sx0 + P["satin_len"]
    y = m + 3.0
    for w in SATIN_WIDTHS:
        for name, underlay in (("plain", False), ("underlay", True)):
            light_objs.append(satin_path(f"s{sid}", light, sx0, sx1, y, w, underlay))
            sid += 1
            legend["C"].append((w, name, sx0, sx1, y))
            y += P["satin_pitch"]

    width = max(ax + grid_w, sx1) + m
    height = max(by + cell, y - P["satin_pitch"] + max(SATIN_WIDTHS) / 2.0) + m
    return dark_objs, light_objs, legend, width, height


def emit_svg(out, light, dark, dark_objs, light_objs, width, height):
    meta = "".join(f'<inkstitch:{n}>{v}</inkstitch:{n}>' for n, v in META)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkstitch="http://inkstitch.org/namespace" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
        f'width="{width:.2f}mm" height="{height:.2f}mm" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" '
        'inkscape:document-units="mm" sodipodi:docname="swatch_vadmel.svg">',
        f'  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" '
        f'inkscape:document-units="mm" pagewidth="{width:.2f}" '
        f'pageheight="{height:.2f}" inkscape:pageopacity="0.0" '
        'inkscape:pagecheckerboard="0" showgrid="false"/>',
        f'  <metadata id="metadata1">{meta}</metadata>',
        f'  <g inkscape:label="{dark}" inkscape:groupmode="layer" id="color0">',
    ]
    lines += [f"    {o}" for o in dark_objs]
    lines.append("  </g>")
    lines.append(f'  <g inkscape:label="{light}" inkscape:groupmode="layer" id="color1">')
    lines += [f"    {o}" for o in light_objs]
    lines.append("  </g>")
    lines.append("</svg>")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def legend_text(light, dark, size, legend, width, height):
    L = [f"# swatch_vadmel legend ({size})",
         "",
         f"Light thread `{light}`, dark neighbour `{dark}`. All values mm.",
         f"Canvas {width:.1f} x {height:.1f} mm. Fill angle 0 everywhere.",
         "The dark frame is sewn first, the light square edge-to-edge inside it.",
         "Every object is separate with `trim_after`.",
         "",
         "## A - fill grid: light square in a dark frame",
         "Columns = `row_spacing_mm`, rows = `pull_compensation_mm`.",
         "",
         "| row (pull) | col (spacing) | x,y | row_spacing_mm | pull_compensation_mm |",
         "|---|---|---|---|---|"]
    for r, c, pull, sp, x, y in legend["A"]:
        L.append(f"| {r} | {c} | {x:.1f},{y:.1f} | {sp:g} | {pull:g} |")
    L += ["",
          "## B - fill underlay variants (same size/position grid)",
          f"row_spacing_mm {B_ROW_SPACING:g}, pull_compensation_mm {B_PULL:g}.",
          "",
          "| pos | x,y | fill_underlay | fill_underlay_angle |",
          "|---|---|---|---|"]
    for c, name, sp, pull, x, y in legend["B"]:
        under = {"default": "true", "two passes": f'true, "{B_VARIANTS[1][1]}"',
                 "off": "false"}[name]
        L.append(f"| {c} | {x:.1f},{y:.1f} | {under} | {name} |")
    L += ["",
          "## C - centre-line satins (30 mm long)",
          f"zigzag_spacing_mm {SATIN_ZIGZAG:g}, pull_compensation_mm "
          f"{SATIN_PULL:g} on every column.",
          "",
          "| x0..x1 | y | width_mm | underlay |",
          "|---|---|---|---|"]
    for w, name, x0, x1, y in legend["C"]:
        under = ("center_walk + contour, inset 0.4" if name == "underlay"
                 else "none")
        L.append(f"| {x0:.1f}..{x1:.1f} | {y:.1f} | {w:g} | {under} |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--light", default=LIGHT_DEFAULT,
                    help=f"light fill thread (default {LIGHT_DEFAULT})")
    ap.add_argument("--dark", default=DARK_DEFAULT,
                    help=f"dark neighbour thread (default {DARK_DEFAULT})")
    ap.add_argument("--size", choices=sorted(SIZES), default="normal")
    ap.add_argument("--out", default="output_inkstitch_svg/swatch_vadmel.svg")
    args = ap.parse_args()

    light, dark = _hex(args.light), _hex(args.dark)
    dark_objs, light_objs, legend, width, height = build(light, dark, args.size)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    emit_svg(args.out, light, dark, dark_objs, light_objs, width, height)

    legend_path = os.path.splitext(args.out)[0] + "_legend.md"
    text = legend_text(light, dark, args.size, legend, width, height)
    with open(legend_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"wrote {args.out} ({width:.1f} x {height:.1f} mm, "
          f"{len(dark_objs)} frames, {len(light_objs)} light objects)")
    print(f"wrote {legend_path}")


if __name__ == "__main__":
    main()
