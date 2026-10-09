#!/usr/bin/env python3
"""Render an embroidery file (VP3/DST/PES/...) to a colour PNG preview.

Colours come from the file's thread list, so a VP3 stitch plan looks like the
finished patch instead of flat grey.  Jumps and trims are drawn faintly so the
travel path is still visible.

Usage:
    python tools/digitize/preview.py work/design.vp3 work/design_plan.png
    python tools/digitize/preview.py in.dst out.png --width 1200 --margin 24
    python tools/digitize/preview.py in.vp3 out.png --crop 0,0,60,40   # top-left 60x40 mm
    python tools/digitize/preview.py in.vp3 out.png --crop 40,10,80,50 --line-width 2
    python tools/digitize/preview.py in.vp3 out.png --background 101010  # dark fabric

``--background HEX`` sets the canvas colour (default ``#ffffff``, the historic
output).  Threads whose colour is within RGB distance 60 of it get a 1 px
contrasting outline so white thread on white (or black on black) stays visible.

``--crop X0,Y0,X1,Y1`` is in mm relative to the design's own bounding box, with
(0,0) at the **top-left** of the design (image convention), so ``--crop 0,0,60,40``
is the top-left corner of the patch.  Useful for judging stitch coverage and
hotspots close up.
"""
import argparse

import pystitch
from PIL import Image, ImageDraw


def _rgb(thread):
    if hasattr(thread, "get_red"):
        return (thread.get_red(), thread.get_green(), thread.get_blue())
    value = getattr(thread, "thread", thread) or "#000000"
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def parse_background(text):
    """'RRGGBB' or '#RRGGBB' -> (r, g, b)."""
    value = text.strip().lstrip("#")
    if len(value) != 6:
        raise SystemExit("--background must be a 6-digit HEX colour, e.g. 101010")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise SystemExit("--background must be a 6-digit HEX colour, e.g. 101010")


def _near(c, bg, threshold=60):
    """True when colour c is close enough to the background to need an outline."""
    return sum((a - b) ** 2 for a, b in zip(c, bg)) <= threshold ** 2


def parse_crop(text):
    """'X0,Y0,X1,Y1' mm, origin top-left of the design -> (x0, y0, x1, y1)."""
    try:
        x0, y0, x1, y1 = (float(v) for v in text.replace(";", ",").split(","))
    except ValueError:
        raise SystemExit("--crop must be X0,Y0,X1,Y1 in mm")
    if x1 <= x0 or y1 <= y0:
        raise SystemExit("--crop needs X1 > X0 and Y1 > Y0")
    return x0, y0, x1, y1


def render(path, out, width=900, margin=20, background=(255, 255, 255),
           jump_color=(205, 205, 205), crop=None, line_width=1, thread_mm=0.0):
    pattern = pystitch.read(path)
    stitches = [s for s in pattern.stitches if len(s) >= 2]
    if not stitches:
        raise SystemExit(f"no stitches in {path}")

    xs = [s[0] for s in stitches]
    ys = [s[1] for s in stitches]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    design_w, design_h = (maxx - minx) / 10, (maxy - miny) / 10
    if crop is not None:
        # crop is in mm from the design's top-left corner, and the renderer
        # below draws y growing down the image, so both axes are measured from
        # the design's own minimum; mirroring y here crops the wrong band
        cx0, cy0, cx1, cy1 = crop
        minx, maxx = minx + cx0 * 10, minx + cx1 * 10
        miny, maxy = miny + cy0 * 10, miny + cy1 * 10
        if maxx <= minx or maxy <= miny:
            raise SystemExit("--crop is outside the design")
    span = max(maxx - minx, maxy - miny) or 1
    scale = (width - 2 * margin) / span
    header = 18
    w = int((maxx - minx) * scale) + 2 * margin
    h = int((maxy - miny) * scale) + 2 * margin + header
    img = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(img)
    # print the stitched size so the operator can verify the scale at a glance
    label = f"{design_w:.1f} x {design_h:.1f} mm"
    if crop is not None:
        label += (f"   crop {crop[0]:g},{crop[1]:g}..{crop[2]:g},{crop[3]:g} mm"
                  f" ({(maxx - minx) / 10:.1f} x {(maxy - miny) / 10:.1f} mm shown)")
    label += (f"   ({pattern.count_stitches()} stitches, "
              f"{len(pattern.get_unique_threadlist() or [])} threads)")
    draw.text((6, 3), label, fill=(90, 90, 90))

    def px(x, y):
        return (int((x - minx) * scale) + margin, int((y - miny) * scale) + margin + header)

    # A satin lays 0.4 mm threads touching each other; drawing its stitches as
    # 1 px hairlines makes a solid band look like a dashed line.  With
    # --thread-mm the lines are drawn at the real thread width instead.
    stitch_width = line_width
    if thread_mm > 0:
        stitch_width = max(line_width, int(round(thread_mm * 10 * scale)))

    color_index = 0
    prev = None
    for s in stitches:
        cmd = s[2] & pystitch.COMMAND_MASK if len(s) > 2 else pystitch.STITCH
        if cmd == pystitch.COLOR_CHANGE:
            color_index += 1
            prev = None
            continue
        if cmd == pystitch.END:
            break
        point = px(s[0], s[1])
        if prev is not None:
            if cmd == pystitch.STITCH:
                rgb = _rgb(pattern.get_thread_or_filler(color_index))
                if _near(rgb, background):
                    # thread would disappear into the canvas; outline it first
                    outline = (0, 0, 0) if sum(rgb) > 3 * 128 else (255, 255, 255)
                    draw.line([prev, point], fill=outline, width=stitch_width + 2)
                draw.line([prev, point], fill=rgb, width=stitch_width)
            elif cmd == pystitch.JUMP:
                draw.line([prev, point], fill=jump_color, width=line_width)
        if cmd in (pystitch.JUMP, pystitch.TRIM, pystitch.STOP):
            prev = None
        else:
            prev = point

    img.save(out)
    return w, h


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--margin", type=int, default=20)
    ap.add_argument("--crop", default=None,
                    help="X0,Y0,X1,Y1 in mm from the design's top-left corner")
    ap.add_argument("--line-width", type=int, default=1, dest="line_width",
                    help="stitch line width in px (default 1)")
    ap.add_argument("--thread-mm", type=float, default=0.0, dest="thread_mm",
                    help="draw stitches at this real thread width in mm (default: "
                         "off, 1 px hairlines); 0.4 shows satin bands as solid")
    ap.add_argument("--background", default="#ffffff",
                    help="canvas colour as HEX (default ffffff); thread within RGB "
                         "distance 60 gets a contrasting outline so it stays visible")
    args = ap.parse_args()
    w, h = render(args.input, args.output, width=args.width, margin=args.margin,
                  background=parse_background(args.background),
                  crop=parse_crop(args.crop) if args.crop else None,
                  line_width=args.line_width, thread_mm=args.thread_mm)
    print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
