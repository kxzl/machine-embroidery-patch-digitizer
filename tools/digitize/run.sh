#!/usr/bin/env bash
# One-shot: image -> pre-digitized SVG + VP3 machine file.
# Usage: tools/digitize/run.sh [flags] <input image|svg>
#   --colors N | --border-mm W | --no-border | --density MM
#   --no-satin-outlines | --satin-max-mm W
#   --no-trim | --trim-mm N | --config F
#   --width-mm W | --height-mm H | --border-color HEX | --skip-colors HEX[,HEX]
#   --size-mm N | --key-background  (key a flat background to alpha first)
#   --fit-mm WxH  (raster inputs: Fit box in mm; dropped for svg inputs)
#   --overlap-mm N  (svg inputs: max overlap of a later colour over an earlier)
#   --seam-pull-mm MM  (svg inputs: pull a later colour back off a colour edge so
#                   its thread finishes on the drawn edge; default 0.2)
#   --fill-angle DEG | --satinize-colors HEX[,HEX]  (both paths)
#   --underlap-mm N | --raster-pull-mm N  (raster fills: fabric compensation;
#                   underlap default 0.6 mm, raster pull default 0)
#   --profile NAME  (raster fills: fabric profile, e.g. vadmel -> density 0.35,
#                   underlap 0.6, raster pull 0.25, full/satin underlay)
#   --background HEX  (preview canvas colour; default: --config's fabric_color:,
#                      else the profile's, else white)
#   --no-travel-under | --travel-max-mm N  (travel_vp3.py: a same-colour trim becomes a
#                   running stitch under later stitching instead of a cut; default on,
#                   runs up to 60 mm; --config's travel: section works too)
#   --no-export   (skip the Ink/Stitch VP3 export, produce SVG only)
set -euo pipefail

FLAGS=()
IMG=""
NO_EXPORT=0
KEY_BG=0
KEEP_ENCLOSED=""
BACKGROUND=""
CONFIG=""
NO_TRAVEL=0
TRAVEL_ARGS=()
while [[ $# -gt 0 ]]; do
  a="$1"; shift
  case "$a" in
    --background) BACKGROUND="$1"; shift ;;
    --background=*) BACKGROUND="${a#*=}" ;;
    --config) CONFIG="$1"; FLAGS+=("$a" "$1"); shift ;;
    --config=*) CONFIG="${a#*=}"; FLAGS+=("$a") ;;
    --*=*) FLAGS+=("$a") ;;
    --colors|--border-mm|--trim-mm|--density|--satin-max-mm|--size-mm|\
    --satin-taper|--overlap-mm|--seam-pull-mm|--width-mm|--height-mm|--border-color|--skip-colors|\
    --fill-angle|--satinize-colors|--palette|--palette-mode|\
    --underlap-mm|--raster-pull-mm|--profile|--fit-mm)
      FLAGS+=("$a" "$1"); shift ;;
    --key-background) KEY_BG=1 ;;
    --keep-enclosed) KEEP_ENCLOSED="--keep-enclosed" ;;
    --no-export) NO_EXPORT=1 ;;
    --no-travel-under) NO_TRAVEL=1 ;;
    --travel-max-mm) TRAVEL_ARGS+=(--travel-max-mm "$1"); shift ;;
    --travel-max-mm=*) TRAVEL_ARGS+=(--travel-max-mm "${a#*=}") ;;
    -*) FLAGS+=("$a") ;;
    *) IMG="$a" ;;
  esac
done
: "${IMG:?usage: run.sh [--no-trim] [--colors N] [--border-mm W] [--config F] <input.webp|png|jpg|svg>}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# preview canvas colour: --background wins, else the config's fabric_color:, else
# the fabric colour implied by the config's profile: (vadmel -> #101010).
if [[ -z "$BACKGROUND" && -n "$CONFIG" ]]; then
  BACKGROUND="$(.venv/bin/python - "$CONFIG" <<'PY'
import sys
try:
    import yaml
    cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    cfg = {}
bg = str(cfg.get("fabric_color") or "").strip()
if not bg and str(cfg.get("profile") or "").strip().lower() == "vadmel":
    bg = "#101010"
print(bg)
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
  # raster-only flags (palette pinning) would be mis-parsed by svg_digitize.py
  FWD=()
  i=0
  while [[ $i -lt ${#FLAGS[@]} ]]; do
    a="${FLAGS[$i]}"
    case "$a" in
      --palette|--palette-mode|--underlap-mm|--raster-pull-mm|--profile|--fit-mm) i=$((i + 1)) ;;
      --palette=*|--palette-mode=*|--underlap-mm=*|--raster-pull-mm=*|--profile=*|--fit-mm=*) ;;
      --no-skip-last) ;;
      *) FWD+=("$a") ;;
    esac
    i=$((i + 1))
  done
  FLAGS=("${FWD[@]}")
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
    .venv/bin/python tools/digitize/key_background.py "$IMG" "$KEYED" $KEEP_ENCLOSED
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

# satin precheck, Ink/Stitch export, travel-under, trim, both previews and the jam
# check live in export_svg.sh, which the web UI's Make stitch plan runs too
EXPORT_ARGS=(--work-dir work "${PREVIEW_BG[@]}" "${TRAVEL_ARGS[@]}")
if [[ -n "$CONFIG" ]]; then
  EXPORT_ARGS+=(--config "$CONFIG")
fi
if [[ "$NO_TRAVEL" == "1" ]]; then
  EXPORT_ARGS+=(--no-travel-under)
fi
bash tools/digitize/export_svg.sh "$OUT_SVG" "output_vp3/$BASE" "${EXPORT_ARGS[@]}"

echo "== done: $OUT_SVG and output_vp3/$BASE.vp3"
