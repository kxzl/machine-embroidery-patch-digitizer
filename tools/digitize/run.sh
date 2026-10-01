#!/usr/bin/env bash
# One-shot: image -> pre-digitized SVG + VP3 machine file.
# Usage: tools/digitize/run.sh [flags] <input image>
#   --colors N | --border-mm W | --no-border | --density MM
#   --no-satin-outlines | --satin-max-mm W
#   --no-trim | --trim-mm N | --config F
#   --no-export   (skip the Ink/Stitch VP3 export, produce SVG only)
set -euo pipefail

FLAGS=()
IMG=""
NO_EXPORT=0
while [[ $# -gt 0 ]]; do
  a="$1"; shift
  case "$a" in
    --config=*|--colors=*|--border-mm=*|--trim-mm=*|--density=*|--satin-max-mm=*) FLAGS+=("$a") ;;
    --config|--colors|--border-mm|--trim-mm|--density|--satin-max-mm)
      FLAGS+=("$a" "$1"); shift ;;
    --no-export) NO_EXPORT=1 ;;
    -*) FLAGS+=("$a") ;;
    *) IMG="$a" ;;
  esac
done
: "${IMG:?usage: run.sh [--no-trim] [--colors N] [--border-mm W] [--config F] <input.webp|png|jpg>}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BASE="$(basename "$IMG")"
BASE="${BASE%.webp}"; BASE="${BASE%.png}"; BASE="${BASE%.jpg}"; BASE="${BASE%.jpeg}"

mkdir -p work

echo "== vectorizing $IMG -> work/$BASE.svg  (flags: ${FLAGS[*]:-none})"
.venv/bin/python tools/digitize/vectorize.py "${FLAGS[@]}" "$IMG" "work/$BASE.svg"

if [[ "$NO_EXPORT" == "1" ]]; then
  echo "== skipping VP3 export (--no-export)"
  exit 0
fi

echo "== exporting VP3"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
  "work/$BASE.svg" > "work/$BASE.zip" 2>"work/$BASE.err"

.venv/bin/python - "$BASE" <<'PYEOF'
import sys, zipfile
base = sys.argv[1]
z = zipfile.ZipFile(f"work/{base}.zip")
print("  zip contents:", z.namelist())
n = z.namelist()[0]
data = z.read(n)
open(f"work/{base}.vp3", "wb").write(data)
import pystitch
p = pystitch.read(f"work/{base}.vp3")
xs = [s[0] for s in p.stitches]; ys = [s[1] for s in p.stitches]
print(f"  -> {base}.vp3  ({p.count_stitches()} stitches, "
      f"{(max(xs)-min(xs))/10:.0f}x{(max(ys)-min(ys))/10:.0f} mm)")
PYEOF

echo "== done: work/$BASE.svg and work/$BASE.vp3"
