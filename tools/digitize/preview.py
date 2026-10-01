#!/usr/bin/env python3
"""Render an embroidery file (VP3/DST/PES/...) to a colour PNG preview.

Colours come from the file's thread list, so a VP3 stitch plan looks like the
finished patch instead of flat grey.  Jumps and trims are drawn faintly so the
travel path is still visible.

Usage:
    python tools/digitize/preview.py work/design.vp3 work/design_plan.png
    python tools/digitize/preview.py in.dst out.png --width 1200 --margin 24
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


def render(path, out, width=900, margin=20, background=(255, 255, 255),
           jump_color=(205, 205, 205)):
    pattern = pystitch.read(path)
    stitches = [s for s in pattern.stitches if len(s) >= 2]
    if not stitches:
        raise SystemExit(f"no stitches in {path}")

    xs = [s[0] for s in stitches]
    ys = [s[1] for s in stitches]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny) or 1
    scale = (width - 2 * margin) / span
    w = int((maxx - minx) * scale) + 2 * margin
    h = int((maxy - miny) * scale) + 2 * margin
    img = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(img)

    def px(x, y):
        return (int((x - minx) * scale) + margin, int((y - miny) * scale) + margin)

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
                draw.line([prev, point], fill=_rgb(pattern.get_thread_or_filler(color_index)), width=1)
            elif cmd == pystitch.JUMP:
                draw.line([prev, point], fill=jump_color, width=1)
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
    args = ap.parse_args()
    w, h = render(args.input, args.output, width=args.width, margin=args.margin)
    print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
