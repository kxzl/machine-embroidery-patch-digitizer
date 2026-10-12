#!/usr/bin/env python3
"""Fit check: does the stitched VP3 fit the Fit box? Usage: fit_check.py [outdir]. Adversarial synthetic patches, both Hoop presets, plus how --size-mm maps to stitched size. Needs the Ink/Stitch export, takes about 3 minutes."""
import os, subprocess, sys, time, zipfile
from PIL import Image, ImageDraw

WT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fit_check"
PY = f"{WT}/.venv/bin/python"
os.makedirs(OUT, exist_ok=True)
RED, YEL, DRK = (192, 57, 43, 255), (241, 196, 15, 255), (26, 26, 26, 255)


def wide():
    im = Image.new("RGBA", (1500, 420), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, 1489, 409), radius=120, fill=RED)
    d.ellipse((600, 110, 900, 310), fill=YEL)
    d.rectangle((120, 190, 480, 230), fill=DRK); d.rectangle((1020, 190, 1380, 230), fill=DRK)
    return im


def tall():
    return wide().transpose(Image.Transpose.ROTATE_90)


def spike():
    im = Image.new("RGBA", (1400, 900), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((50, 50, 850, 850), fill=RED); d.ellipse((300, 300, 600, 600), fill=YEL)
    d.rectangle((850, 443, 1395, 457), fill=DRK)  # 14 px spike, about 1.3 mm at 120 mm
    return im


def edge():
    im = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 999, 999), radius=60, fill=RED)
    d.rounded_rectangle((60, 60, 939, 939), radius=40, outline=DRK, width=40)
    d.ellipse((350, 350, 650, 650), fill=YEL)
    return im


DESIGNS = {"wide": wide, "tall": tall, "spike": spike, "edge": edge}
PRESETS = [(120, 120), (260, 200)]


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=WT, capture_output=True, text=True, **kw)


def stitched(svg, tag):
    env = dict(os.environ, PYTHONPATH="tools/wxstub", INKSTITCH_OFFLINE_SCRIPT="true")
    z = f"{OUT}/{tag}.zip"
    with open(z, "wb") as fh:
        r = subprocess.run([PY, "inkstitch/inkstitch.py", "--extension=zip", "--format-vp3=True", svg],
                           cwd=WT, env=env, stdout=fh, stderr=subprocess.PIPE)
    vp3 = f"{OUT}/{tag}.vp3"
    with zipfile.ZipFile(z) as zf:
        open(vp3, "wb").write(zf.read(zf.namelist()[0]))
    run([PY, "tools/digitize/travel_vp3.py", vp3])
    run([PY, "tools/digitize/trim_vp3.py", vp3, "8"])
    import pystitch
    p = pystitch.read(vp3)
    x0, y0, x1, y1 = p.bounds()
    return (x1 - x0) / 10.0, (y1 - y0) / 10.0, p.count_stitches()


rows = []
for name, fn in DESIGNS.items():
    png = f"{OUT}/{name}.png"; fn().save(png)
    for (fw, fh) in PRESETS:
        tag = f"{name}_{fw}x{fh}"; svg = f"{OUT}/{tag}.svg"
        t0 = time.time()
        v = run([PY, "tools/digitize/vectorize.py", "--fit-mm", f"{fw}x{fh}", "--colors", "3", png, svg])
        open(f"{OUT}/{tag}.vec.log", "w").write(v.stdout + v.stderr)
        if v.returncode != 0 or not os.path.exists(svg):
            rows.append((name, f"{fw}x{fh}", "vectorize FAILED", "", "", "")); continue
        w, h, n = stitched(svg, tag)
        ok = w <= fw and h <= fh
        rows.append((name, f"{fw}x{fh}", f"{w:.1f} x {h:.1f}", f"{n}", "PASS" if ok else "OVER", f"{time.time()-t0:.0f}s"))
        print(rows[-1], flush=True)

# how does the OLD --size-mm map to stitched size?
map_rows = []
for name in ("wide", "edge"):
    tag = f"{name}_size100"; svg = f"{OUT}/{tag}.svg"
    v = run([PY, "tools/digitize/vectorize.py", "--size-mm", "100", "--colors", "3", f"{OUT}/{name}.png", svg])
    if v.returncode == 0:
        w, h, n = stitched(svg, tag)
        map_rows.append((name, f"--size-mm 100", f"{w:.1f} x {h:.1f}", f"longest {max(w, h):.1f}"))
        print(map_rows[-1], flush=True)

with open(f"{OUT}/t3_results.md", "w") as fh:
    fh.write("| design | fit box mm | stitched mm | stitches | result | time |\n|---|---|---|---|---|---|\n")
    for r in rows:
        fh.write("| " + " | ".join(r) + " |\n")
    fh.write("\n| design | flag | stitched mm | note |\n|---|---|---|---|\n")
    for r in map_rows:
        fh.write("| " + " | ".join(r) + " |\n")
open(f"{OUT}/T3_DONE", "w").write("done")
print("T3 DONE", flush=True)
