#!/usr/bin/env bash
# One-shot: image -> pre-digitized SVG + VP3 machine file.
# Usage: tools/digitize/run.sh [flags] <input image|svg>
#   --colors N | --border-mm W | --no-border | --density MM
#   --no-satin-outlines | --satin-max-mm W
#   --no-trim | --trim-mm N | --config F
#   --width-mm W | --height-mm H | --border-color HEX | --skip-colors HEX[,HEX]
#   --size-mm N | --key-background  (key a flat background to alpha first)
#   --overlap-mm N  (svg inputs: max overlap of a later colour over an earlier)
#   --seam-pull-mm MM  (svg inputs: pull a later colour back off a colour edge so
#                   its thread finishes on the drawn edge; default 0.2)
#   --fill-angle DEG | --satinize-colors HEX[,HEX]  (both paths)
#   --background HEX  (preview canvas colour; default: --config's fabric_color:,
#                      else white)
#   --no-export   (skip the Ink/Stitch VP3 export, produce SVG only)
set -euo pipefail

FLAGS=()
IMG=""
NO_EXPORT=0
KEY_BG=0
BACKGROUND=""
CONFIG=""
while [[ $# -gt 0 ]]; do
  a="$1"; shift
  case "$a" in
    --background) BACKGROUND="$1"; shift ;;
    --background=*) BACKGROUND="${a#*=}" ;;
    --config) CONFIG="$1"; FLAGS+=("$a" "$1"); shift ;;
    --config=*) CONFIG="${a#*=}"; FLAGS+=("$a") ;;
    --*=*) FLAGS+=("$a") ;;
    --colors|--border-mm|--trim-mm|--density|--satin-max-mm|--size-mm|\
    --overlap-mm|--seam-pull-mm|--width-mm|--height-mm|--border-color|--skip-colors|\
    --fill-angle|--satinize-colors)
      FLAGS+=("$a" "$1"); shift ;;
    --key-background) KEY_BG=1 ;;
    --no-export) NO_EXPORT=1 ;;
    -*) FLAGS+=("$a") ;;
    *) IMG="$a" ;;
  esac
done
: "${IMG:?usage: run.sh [--no-trim] [--colors N] [--border-mm W] [--config F] <input.webp|png|jpg|svg>}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# preview canvas colour: --background wins, else the config's fabric_color:
if [[ -z "$BACKGROUND" && -n "$CONFIG" ]]; then
  BACKGROUND="$(.venv/bin/python - "$CONFIG" <<'PY'
import sys
try:
    import yaml
    cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    cfg = {}
print((cfg.get("fabric_color") or "").strip())
PY
)"
fi
PREVIEW_BG=()
if [[ -n "$BACKGROUND" ]]; then
  PREVIEW_BG=(--background "$BACKGROUND")
fi

BASE="$(basename "$IMG")"
BASE="${BASE%.webp}"; BASE="${BASE%.png}"; BASE="${BASE%.jpg}"; BASE="${BASE%.jpeg}"; BASE="${BASE%.svg}"

EXT="${IMG##*.}"
EXT_LC="$(printf '%s' "$EXT" | tr '[:upper:]' '[:lower:]')"
if [[ "$EXT_LC" == "svg" ]]; then
  SCRIPT=tools/digitize/svg_digitize.py
else
  SCRIPT=tools/digitize/vectorize.py
  # svg-only flags would be mis-parsed by vectorize.py; drop them (and values)
  FWD=()
  i=0
  while [[ $i -lt ${#FLAGS[@]} ]]; do
    a="${FLAGS[$i]}"
    case "$a" in
      --width-mm|--height-mm|--border-color|--skip-colors|--overlap-mm|\
      --seam-pull-mm)
        [[ "$a" == *=* ]] || i=$((i + 1)) ;;
      --width-mm=*|--height-mm=*|--border-color=*|--skip-colors=*|--overlap-mm=*|\
      --seam-pull-mm=*) ;;
      *) FWD+=("$a") ;;
    esac
    i=$((i + 1))
  done
  FLAGS=("${FWD[@]}")
fi

OUT_SVG="output_inkstitch_svg/$BASE.svg"
mkdir -p work output_inkstitch_svg output_vp3

if [[ "$KEY_BG" == "1" ]]; then
  if [[ "$EXT_LC" == "svg" ]]; then
    echo "note: --key-background applies to raster inputs only; ignoring for $IMG"
  else
    KEYED="work/${BASE}_keyed.png"
    .venv/bin/python tools/digitize/key_background.py "$IMG" "$KEYED"
    IMG="$KEYED"
  fi
fi

echo "== digitizing $IMG -> $OUT_SVG  (flags: ${FLAGS[*]:-none})"
.venv/bin/python "$SCRIPT" "${FLAGS[@]}" "$IMG" "$OUT_SVG"

if [[ "$NO_EXPORT" == "1" ]]; then
  echo "== skipping VP3 export (--no-export)"
  echo "== done: $OUT_SVG"
  exit 0
fi

echo "== exporting VP3"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
  "$OUT_SVG" > "work/$BASE.zip" 2>"work/$BASE.err"

.venv/bin/python - "$BASE" <<'PYEOF'
import sys, zipfile
base = sys.argv[1]
z = zipfile.ZipFile(f"work/{base}.zip")
names = z.namelist()
print("  zip contents:", names)
open(f"output_vp3/{base}.vp3", "wb").write(z.read(names[0]))
import pystitch
p = pystitch.read(f"output_vp3/{base}.vp3")
xs = [s[0] for s in p.stitches]; ys = [s[1] for s in p.stitches]
n_changes = sum(1 for s in p.stitches if len(s) > 2 and (s[2] & pystitch.COMMAND_MASK) == pystitch.COLOR_CHANGE)
threads = []
for i in range(n_changes + 1):
    t = p.get_thread_or_filler(i)
    threads.append(str(getattr(t, "thread", t)))
print(f"  -> output_vp3/{base}.vp3  ({p.count_stitches()} stitches, "
      f"{n_changes} colour change(s), {(max(xs)-min(xs))/10:.0f}x{(max(ys)-min(ys))/10:.0f} mm)")
print(f"  threads: {threads}")
PYEOF

echo "== stitch plan"
.venv/bin/python tools/digitize/trim_vp3.py "output_vp3/$BASE.vp3" 8
# two renders: hairlines show the individual stitches (layout check), thread
# width shows what the fabric will actually look like (coverage check).  At
# 1 px hairlines a satin band reads as a dashed line, at 0.5 mm it reads as a
# solid mass -- neither alone tells the whole story.
.venv/bin/python tools/digitize/preview.py "output_vp3/$BASE.vp3" \
  "output_vp3/${BASE}_stitchplan.png" --width 1600 --line-width 1 "${PREVIEW_BG[@]}"
.venv/bin/python tools/digitize/preview.py "output_vp3/$BASE.vp3" \
  "output_vp3/${BASE}_coverage.png" --width 1600 --thread-mm 0.5 "${PREVIEW_BG[@]}"

echo "== done: $OUT_SVG and output_vp3/$BASE.vp3"
