#!/usr/bin/env bash
# Export one Ink/Stitch SVG to a VP3 machine file and the two preview PNGs.
#
# Usage: tools/digitize/export_svg.sh <svg> <out_prefix> [--background HEX]
#   <svg>          the Slice's SVG. The satin precheck may fix it in place.
#   <out_prefix>   writes <out_prefix>.vp3, <out_prefix>_stitchplan.png,
#                  <out_prefix>_coverage.png, <out_prefix>.zip and <out_prefix>.err
#   --background HEX  preview canvas colour; run.sh works it out from the config
#
# It echoes the same "== ..." stage lines as run.sh, so the caller can follow along.
# No timeout: Cancel stops it (qa/export.sh's timeout 1800 would kill a long cold export).
set -euo pipefail

SVG=""
OUT=""
BACKGROUND=""
while [[ $# -gt 0 ]]; do
  a="$1"; shift
  case "$a" in
    --background) BACKGROUND="$1"; shift ;;
    --background=*) BACKGROUND="${a#*=}" ;;
    -*) echo "note: ignoring unknown flag $a" >&2 ;;
    *) if [[ -z "$SVG" ]]; then SVG="$a"; else OUT="$a"; fi ;;
  esac
done
USAGE="usage: export_svg.sh <svg> <out_prefix> [--background HEX]"
: "${SVG:?$USAGE}"
: "${OUT:?$USAGE}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DIR="$(dirname "$OUT")"
BASE="$(basename "$OUT")"
mkdir -p "$DIR"

PREVIEW_BG=()
if [[ -n "$BACKGROUND" ]]; then
  PREVIEW_BG=(--background "$BACKGROUND")
fi

echo "== satin precheck"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python tools/digitize/qa/satin_precheck.py "$SVG" --fix "$SVG" || true

echo "== exporting VP3"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
  "$SVG" > "$DIR/$BASE.zip" 2>"$DIR/$BASE.err"

.venv/bin/python - "$DIR/$BASE.zip" "$DIR/$BASE.vp3" <<'PYEOF'
import sys, zipfile
zip_path, vp3_path = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zip_path)
names = z.namelist()
print("  zip contents:", names)
open(vp3_path, "wb").write(z.read(names[0]))
import pystitch
p = pystitch.read(vp3_path)
xs = [s[0] for s in p.stitches]; ys = [s[1] for s in p.stitches]
n_changes = sum(1 for s in p.stitches if len(s) > 2 and (s[2] & pystitch.COMMAND_MASK) == pystitch.COLOR_CHANGE)
threads = []
for i in range(n_changes + 1):
    t = p.get_thread_or_filler(i)
    threads.append(str(getattr(t, "thread", t)))
print(f"  -> {vp3_path}  ({p.count_stitches()} stitches, "
      f"{n_changes} colour change(s), {(max(xs)-min(xs))/10:.0f}x{(max(ys)-min(ys))/10:.0f} mm)")
print(f"  threads: {threads}")
PYEOF

echo "== stitch plan"
.venv/bin/python tools/digitize/trim_vp3.py "$DIR/$BASE.vp3" 8
# two renders: hairlines show the individual stitches (layout check), thread
# width shows what the fabric will actually look like (coverage check).  At
# 1 px hairlines a satin band reads as a dashed line, at 0.5 mm it reads as a
# solid mass -- neither alone tells the whole story.
.venv/bin/python tools/digitize/preview.py "$DIR/$BASE.vp3" \
  "$DIR/${BASE}_stitchplan.png" --width 1600 --line-width 1 "${PREVIEW_BG[@]}"
.venv/bin/python tools/digitize/preview.py "$DIR/$BASE.vp3" \
  "$DIR/${BASE}_coverage.png" --width 1600 --thread-mm 0.5 "${PREVIEW_BG[@]}"

echo "== jam check"
.venv/bin/python tools/digitize/qa/jam_check.py "$DIR/$BASE.vp3" || true

echo "== done: $DIR/$BASE.vp3 and $DIR/${BASE}_stitchplan.png"