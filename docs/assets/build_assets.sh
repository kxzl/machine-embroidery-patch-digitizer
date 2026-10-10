#!/usr/bin/env bash
# Regenerate every README gallery and hero image in docs/assets/ and the
# render manifest docs/assets/render-manifest.md.
#
#   bash docs/assets/build_assets.sh        (run from the repo root or anywhere)
#
# What it does
#   1. Runs the CURRENT pipeline (tools/digitize/run.sh, Ink/Stitch export
#      included) once per image. Every command is printed into the manifest
#      exactly as it was executed.
#   2. Cuts the stitch plan and coverage renders into 3-panel sheets,
#      re-encodes them as palette PNGs (no metadata) and checks size caps.
#   3. Writes docs/assets/render-manifest.md from the real VP3 files.
#
# Needs (all gitignored, present on the author's machine only)
#   .venv/                              Python 3.13 venv with the pipeline deps
#   inkstitch/                          vendored Ink/Stitch checkout
#   input/nano_banana/<slug>.png        six AI patch images
#   input/Scavenger's Daughter Upgrade Patch2.svg   hero artwork
#   patch_descriptions/border_black.yaml            shared border config
#   work/back-nine-skulls_keyed.png     keyed Back Nine Skulls (no original exists)
#   rsvg-convert                        SVG to PNG
# Scratch files go to work/readme_assets/ and the usual output_* folders.
#
# Optional: HERO_SOURCE=rsvg uses an rsvg-convert render of the derived SVG as
# the first hero panel. Default is the target render that invert_ink.py writes
# (--dump-dir): the rsvg render draws each centipede plate as a 0.1 mm rail
# outline, because plates are authored as Ink/Stitch rail satins.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY=.venv/bin/python
RUNS=work/readme_assets
OUT=docs/assets
HERO_SOURCE="${HERO_SOURCE:-target}"
BORDER_CFG=patch_descriptions/border_black.yaml
HERO_ART="input/Scavenger's Daughter Upgrade Patch2.svg"
HERO_BASE="Scavenger's Daughter Inverted"
HERO_SVG="work/$HERO_BASE.svg"
BACK9_KEYED=work/back-nine-skulls_keyed.png

# slug | colours | size mm | image given to run.sh | --key-background (yes/no)
# Colours and sizes come from the "## Spec" section of
# patch_descriptions/prompts/<slug>.md. back-nine-skulls is already keyed
# (the original image no longer exists), so run.sh gets the keyed PNG as is.
GALLERY=(
  "bomb|6|90|input/nano_banana/bomb.png|yes"
  "four-leaf-clover|6|75|input/nano_banana/four-leaf-clover.png|yes"
  "midnight-epicure|6|80|input/nano_banana/midnight-epicure.png|yes"
  "peace|2|60|input/nano_banana/peace.png|yes"
  "reaper-spider|6|70|input/nano_banana/reaper-spider.png|yes"
  "skyfowl|6|75|input/nano_banana/skyfowl.png|yes"
  "back-nine-skulls|4|190|$BACK9_KEYED|no"
)

need() { [[ -e "$1" ]] || { echo "missing prerequisite: $1" >&2; exit 1; }; }
need "$PY"; need inkstitch/inkstitch.py; need "$BORDER_CFG"; need "$HERO_ART"
need "$BACK9_KEYED"
command -v rsvg-convert >/dev/null || { echo "missing prerequisite: rsvg-convert" >&2; exit 1; }
for row in "${GALLERY[@]}"; do IFS='|' read -r _s _c _z src _k <<<"$row"; need "$src"; done

rm -rf "$RUNS"
mkdir -p "$RUNS" "$OUT" work

# show: print a command the way it would be typed (quote what needs quoting)
show() {
  local out="" a
  for a in "$@"; do
    if [[ "$a" =~ ^[A-Za-z0-9_./:=,@%+-]+$ ]]; then out+="$a "; else out+="\"$a\" "; fi
  done
  printf '%s\n' "${out% }"
}

# timed NAME LABEL CMD...: log the command, run it, record the wall seconds
timed() {
  local name="$1" label="$2"; shift 2
  show "$@" >> "$RUNS/$name.cmds"
  local t0 t1 rc=0
  t0=$(date +%s.%N)
  "$@" > "$RUNS/$name.$label.log" 2>&1 || rc=$?
  t1=$(date +%s.%N)
  if (( rc != 0 )); then
    tail -n 40 "$RUNS/$name.$label.log" >&2
    echo "FAILED: $name ($label), exit $rc" >&2
    exit 1
  fi
  awk -v a="$t0" -v b="$t1" -v l="$label" 'BEGIN{printf "%s\t%.1f\n", l, b-a}' >> "$RUNS/$name.seconds"
}

# images.tsv: name kind source alpha_src vp3 plan coverage p1 p2 caption1
printf 'name\tkind\tsource\talpha\tvp3\tplan\tcoverage\tp1\tp2\tcaption1\n' > "$RUNS/images.tsv"

# ---- gallery -----------------------------------------------------------
for row in "${GALLERY[@]}"; do
  IFS='|' read -r slug colors size src key <<<"$row"
  name="gallery-$slug"
  args=(tools/digitize/run.sh)
  [[ "$key" == yes ]] && args+=(--key-background)
  args+=(--colors "$colors" --size-mm "$size" --config "$BORDER_CFG" "$src")
  echo "== $name"
  timed "$name" run "${args[@]}"
  base="$(basename "$src" .png)"
  if [[ "$key" == yes ]]; then
    alpha="work/${base}_keyed.png"; cap="1. Source image"
  else
    alpha="$src"; cap="1. Keyed source (background removed)"
  fi
  printf '%s\tgallery\t%s\t%s\toutput_vp3/%s.vp3\toutput_vp3/%s_stitchplan.png\toutput_vp3/%s_coverage.png\t\t\t%s\n' \
    "$name" "$src" "$alpha" "$base" "$base" "$base" "$cap" >> "$RUNS/images.tsv"
done

# ---- hero: Scavenger's Daughter Inverted --------------------------------
name=hero-scavenger-inverted
echo "== $name"
# the config run.sh was given for the original run (work/scavenger_inverted.yaml)
cat > "$RUNS/scavenger_inverted.yaml" <<'YAML'
density: 0.30
seam_pull_mm: 0.2
border:
  mode: auto
trim:
  enabled: true
  threshold_mm: 3.0
YAML
# 1. derive the inverted artwork (black ink = bare fabric, plates = rail satins)
timed "$name" derive "$PY" tools/digitize/invert_ink.py --ink "#030503" --paper "#ffffff" \
  --plate-satin-colors "#87f70f" --border-mm 2.0 --fit-mm 260x200 \
  --dump-dir "$RUNS/hero-dump" "$HERO_ART" "$HERO_SVG"
# 2. digitize and export (Fit box 260 x 200 mm). --background only colours the
#    preview PNGs so white thread shows; the VP3 is not affected.
timed "$name" run tools/digitize/run.sh --width-mm 260 --height-mm 200 --no-border \
  --config "$RUNS/scavenger_inverted.yaml" --background "#101010" "$HERO_SVG"
# 3. render the Ink/Stitch SVG that run.sh wrote
timed "$name" render_svg rsvg-convert -w 1560 -b "#101010" \
  "output_inkstitch_svg/$HERO_BASE.svg" -o "$RUNS/hero-inkstitch.png"
if [[ "$HERO_SOURCE" == rsvg ]]; then
  timed "$name" render_src rsvg-convert -w 1560 -b "#101010" "$HERO_SVG" -o "$RUNS/hero-source.png"
  P1="$RUNS/hero-source.png"; CAP1="1. Inverted SVG (rsvg-convert)"
else
  P1="$RUNS/hero-dump/target.png"; CAP1="1. Artwork: black ink is bare fabric"
fi
printf '%s\thero\t%s\t\toutput_vp3/%s.vp3\toutput_vp3/%s_stitchplan.png\toutput_vp3/%s_coverage.png\t%s\t%s\t%s\n' \
  "$name" "$HERO_ART" "$HERO_BASE" "$HERO_BASE" "$HERO_BASE" "$P1" "$RUNS/hero-inkstitch.png" "$CAP1" >> "$RUNS/images.tsv"

# ---- compose sheets, check them, write the manifest ---------------------
"$PY" - "$RUNS" "$OUT" "$HERO_SOURCE" <<'PY'
import csv, hashlib, math, os, platform, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
import pystitch
import PIL

RUNS, OUT, HERO_SOURCE = sys.argv[1], sys.argv[2], sys.argv[3]

CARD_W, GAP, PAD, CAP_H = 520, 8, 8, 34       # sheet geometry in px
MAX_W, MAX_KB, TARGET_KB = 1600, 400, 380     # published limits
PREVIEW_HEADER = 18                           # preview.py draws a text header
PREVIEW_MARGIN = 20                           # and a margin around the design
WHITE, DARK = (255, 255, 255), (16, 16, 16)
FONT_PATHS = ["/usr/share/fonts/TTF/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def flat(im, bg):
    im = im.convert("RGBA")
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im)
    return base.convert("RGB")


def source_panel(src, alpha_src):
    """Original image cropped to the patch silhouette (alpha of the keyed copy)."""
    key = Image.open(alpha_src).convert("RGBA")
    mask = key.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    x0, y0, x1, y1 = mask.getbbox()
    m = int(round(max(x1 - x0, y1 - y0) * PREVIEW_MARGIN / (1600 - 2 * PREVIEW_MARGIN)))
    box = (max(0, x0 - m), max(0, y0 - m), min(key.width, x1 + m), min(key.height, y1 + m))
    return flat(Image.open(src), WHITE).crop(box)


def plan_panel(path):
    im = Image.open(path).convert("RGB")
    return im.crop((0, PREVIEW_HEADER, im.width, im.height))


def pad_to_preview(im, bg):
    """Scale to the design width preview.py uses and add its margin."""
    w = 1600 - 2 * PREVIEW_MARGIN
    im = im.convert("RGB").resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    out = Image.new("RGB", (im.width + 2 * PREVIEW_MARGIN, im.height + 2 * PREVIEW_MARGIN), bg)
    out.paste(im, (PREVIEW_MARGIN, PREVIEW_MARGIN))
    return out


def sheet(panels):
    """panels: list of (image, caption, background colour). Three cards in a row."""
    iw = CARD_W - 2 * PAD
    ih = max(math.ceil(iw * im.height / im.width) for im, _, _ in panels)
    card_h = PAD + ih + PAD + CAP_H
    n = len(panels)
    sw = n * CARD_W + (n - 1) * GAP
    out = Image.new("RGB", (sw, card_h), WHITE)
    d = ImageDraw.Draw(out)
    f = font(15)
    for i, (im, cap, bg) in enumerate(panels):
        x = i * (CARD_W + GAP)
        d.rectangle([x, 0, x + CARD_W - 1, card_h - 1], outline=(220, 220, 220), fill=WHITE)
        d.rectangle([x + 1, card_h - CAP_H, x + CARD_W - 2, card_h - 2], fill=(249, 249, 249))
        d.rectangle([x + PAD, PAD, x + PAD + iw - 1, PAD + ih - 1], fill=bg)
        s = min(iw / im.width, ih / im.height)
        r = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        out.paste(r, (x + PAD + (iw - r.width) // 2, PAD + (ih - r.height) // 2))
        tw = d.textlength(cap, font=f)
        d.text((x + (CARD_W - tw) / 2, card_h - CAP_H + 8), cap, font=f, fill=(102, 102, 102))
    return out


def save_palette_png(im, path):
    """Palette PNG, no metadata. Fewest-colours-needed search to stay under the cap."""
    for n in (256, 192, 128, 96, 64, 48, 32):
        q = im.convert("RGB").quantize(colors=n, method=Image.Quantize.MEDIANCUT,
                                       dither=Image.Dither.NONE)
        q.save(path, format="PNG", optimize=True)
        if os.path.getsize(path) <= TARGET_KB * 1000:
            return n
    raise SystemExit(f"{path}: {os.path.getsize(path)} bytes with 32 colours, over the cap")


def png_chunks(path):
    data = open(path, "rb").read()
    pos, names = 8, []
    while pos < len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        names.append(data[pos + 4:pos + 8].decode("ascii"))
        pos += 12 + ln
    return names


def check_clean(path):
    im = Image.open(path)
    assert im.width <= MAX_W, f"{path}: wider than {MAX_W}"
    assert os.path.getsize(path) <= MAX_KB * 1000, f"{path}: over {MAX_KB} KB"
    assert dict(im.info) == {}, f"{path}: info {dict(im.info)}"
    assert len(im.getexif()) == 0, f"{path}: EXIF present"
    extra = set(png_chunks(path)) - {"IHDR", "PLTE", "IDAT", "IEND"}
    assert not extra, f"{path}: extra PNG chunks {extra}"


def vp3_stats(path):
    p = pystitch.read(path)
    cmds = [s[2] & pystitch.COMMAND_MASK for s in p.stitches]
    changes = cmds.count(pystitch.COLOR_CHANGE)
    threads = [p.get_thread_or_filler(i).hex_color() for i in range(changes + 1)]
    x0, y0, x1, y1 = p.bounds()
    return dict(commands=p.count_stitches(), needle=cmds.count(pystitch.STITCH),
                trims=cmds.count(pystitch.TRIM), jumps=cmds.count(pystitch.JUMP),
                blocks=changes + 1, threads=threads,
                w=(x1 - x0) / 10, h=(y1 - y0) / 10)


rows = list(csv.DictReader(open(os.path.join(RUNS, "images.tsv"), encoding="utf-8"), delimiter="\t"))
info = []
for r in rows:
    name = r["name"]
    st = vp3_stats(r["vp3"])
    if r["kind"] == "gallery":
        panels = [(source_panel(r["source"], r["alpha"]), r["caption1"], WHITE),
                  (plan_panel(r["plan"]), "2. VP3 stitch plan", WHITE),
                  (plan_panel(r["coverage"]), "3. Coverage (0.5 mm thread)", WHITE)]
    else:
        panels = [(pad_to_preview(Image.open(r["p1"]), DARK), r["caption1"], DARK),
                  (pad_to_preview(Image.open(r["p2"]), DARK), "2. Ink/Stitch SVG render", DARK),
                  (plan_panel(r["plan"]), "3. VP3 stitch plan", DARK)]
    out_path = os.path.join(OUT, name + ".png")
    ncol = save_palette_png(sheet(panels), out_path)
    check_clean(out_path)
    secs = dict(l.split("\t") for l in open(os.path.join(RUNS, name + ".seconds")).read().splitlines())
    cmds = open(os.path.join(RUNS, name + ".cmds"), encoding="utf-8").read().splitlines()
    im = Image.open(out_path)
    info.append(dict(r, st=st, secs=secs, cmds=cmds, ncol=ncol, size=os.path.getsize(out_path),
                     px=im.size, sha=hashlib.sha256(open(out_path, "rb").read()).hexdigest()[:16],
                     out=out_path))
    print(f"{out_path}: {im.size[0]}x{im.size[1]}, {info[-1]['size']/1000:.0f} KB, {ncol} colours")

head = sh("git", "rev-parse", "--short", "HEAD")
tools_commit = sh("git", "log", "-1", "--format=%h %cs", "--", "tools")
dirty = sh("git", "status", "--porcelain", "--", "tools")
ink = sh("git", "-C", "inkstitch", "rev-parse", "--short", "HEAD")

L = []
L.append("# Render manifest")
L.append("")
L.append("Written by `docs/assets/build_assets.sh`. Every number below is read from the "
         "VP3 file or the PNG that the same run produced.")
L.append("")
L.append("| Item | Value |")
L.append("|---|---|")
L.append(f"| Repo HEAD at render time | `{head}` |")
L.append(f"| Last commit that changed `tools/` (pipeline code) | `{tools_commit}` |")
L.append(f"| Uncommitted changes under `tools/` | {'yes' if dirty else 'none'} |")
L.append(f"| Ink/Stitch commit (vendored clone) | `{ink}` |")
L.append(f"| Python / Pillow / pystitch | {platform.python_version()} / {PIL.__version__} / "
         f"{getattr(pystitch, '__version__', 'unknown')} |")
L.append(f"| Hero first panel | {'rsvg-convert render of the derived SVG' if HERO_SOURCE == 'rsvg' else 'target render written by invert_ink.py --dump-dir'} |")
L.append("")
L.append("Definitions")
L.append("")
L.append("- Stitch count is `pystitch` `count_stitches()` on the final VP3. It counts every "
         "command: needle stitches, trims, jumps, colour changes and the END command. "
         "The needle-stitch column counts STITCH commands only.")
L.append("- Colour blocks are colour changes plus one. Thread hexes are in block order.")
L.append("- Stitched size is the `pystitch` `bounds()` box of the final VP3 (units are 0.1 mm).")
L.append("- Seconds are wall time on the author's machine (Ryzen 5 5600X). The `run.sh` "
         "figure covers digitizing, the Ink/Stitch export, `trim_vp3.py` and both previews.")
L.append("- Images are palette PNGs, no metadata (Pillow `info` and EXIF empty, only "
         "IHDR/PLTE/IDAT/IEND chunks). Files are at most 400 KB and 1600 px wide.")
L.append("")
L.append("## Summary")
L.append("")
L.append("| Image | Pixels | KB | Stitches | Needle stitches | Colour blocks | Stitched size mm | run.sh seconds |")
L.append("|---|---|---|---|---|---|---|---|")
for i in info:
    s = i["st"]
    L.append(f"| `{i['out']}` | {i['px'][0]} x {i['px'][1]} | {i['size']/1000:.0f} | "
             f"{s['commands']:,} | {s['needle']:,} | {s['blocks']} | {s['w']:.1f} x {s['h']:.1f} | "
             f"{i['secs']['run']} |")
L.append("")
for i in info:
    s = i["st"]
    L.append(f"## {os.path.basename(i['out'])}")
    L.append("")
    L.append("| Field | Value |")
    L.append("|---|---|")
    L.append(f"| Source file | `{i['source']}` |")
    L.append(f"| Pipeline commit | HEAD `{head}`, last change under `tools/` `{tools_commit}` |")
    L.append(f"| Stitches (count_stitches) | {s['commands']:,} |")
    L.append(f"| Needle stitches / trims / jumps | {s['needle']:,} / {s['trims']} / {s['jumps']} |")
    L.append(f"| Colour blocks | {s['blocks']} |")
    L.append(f"| Thread hexes | {', '.join(s['threads'])} |")
    L.append(f"| Stitched size | {s['w']:.1f} x {s['h']:.1f} mm |")
    L.append("| Seconds | " + ", ".join(f"{k} {v}" for k, v in i["secs"].items()) + " |")
    L.append(f"| Image file | `{i['out']}`, {i['size']:,} bytes ({i['size']/1000:.0f} KB), "
             f"{i['px'][0]} x {i['px'][1]} px, {i['ncol']}-colour palette, sha256 `{i['sha']}` |")
    L.append("")
    L.append("Commands, in order (run from the repo root):")
    L.append("")
    L.append("```")
    L.extend(i["cmds"])
    L.append("```")
    L.append("")
    if i["kind"] == "gallery":
        L.append("Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), "
                 "`output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below "
                 "the preview header and scaled to the sheet.")
    else:
        L.append("Panels: derived artwork, `rsvg-convert` render of the Ink/Stitch SVG, "
                 "`output_vp3/<name>_stitchplan.png`. Previews use fabric colour `#101010`.")
    L.append("")
text = "\n".join(L) + "\n"
assert "—" not in text
open(os.path.join(OUT, "render-manifest.md"), "w", encoding="utf-8").write(text)
print("wrote", os.path.join(OUT, "render-manifest.md"))
PY

echo "== done: $OUT/gallery-*.png $OUT/hero-scavenger-inverted.png $OUT/render-manifest.md"
