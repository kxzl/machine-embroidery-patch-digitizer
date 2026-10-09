#!/usr/bin/env bash
# Regression gate for the raster path (review.md section 3).
#
# Runs the three reference designs end to end -- key background, vectorize,
# Ink/Stitch VP3 export, trim_vp3 -- and prints one markdown table row per design:
#
#   design | stitches | colour blocks | trims | export s |
#   pullsim uncovered % | pullsim gaps>=0.5mm2 | exposed travel moves >4.5mm | palette
#
# Usage:
#   tools/digitize/qa/regress.sh <outdir> [--vectorize PATH]
#
# --vectorize defaults to tools/digitize/vectorize.py.  Point it at a baseline
# copy to compare, e.g.:
#   mkdir -p /tmp/base && git show HEAD:tools/digitize/vectorize.py > /tmp/base/vectorize.py
#   git show HEAD:tools/digitize/skeleton.py > /tmp/base/skeleton.py
#   git show HEAD:tools/digitize/satinize.py > /tmp/base/satinize.py
#   tools/digitize/qa/regress.sh /tmp/base_out --vectorize /tmp/base/vectorize.py
# (the copies need skeleton/satinize next to them, or rely on the
#  PYTHONPATH=tools/digitize this script sets).
#
# Extra flags can be appended to every vectorize call with the REGRESS_EXTRA
# environment variable, e.g. REGRESS_EXTRA="--underlap-mm 0.6" regress.sh ...
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

OUT=""
VEC=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vectorize) VEC="$2"; shift 2 ;;
    --vectorize=*) VEC="${1#*=}"; shift ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) OUT="$1"; shift ;;
  esac
done
: "${OUT:?usage: regress.sh <outdir> [--vectorize PATH]}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
if [[ -z "$VEC" ]]; then
  VEC="$ROOT/tools/digitize/vectorize.py"
else
  VEC="$(readlink -f "$VEC")"
fi

PY=.venv/bin/python
read -ra VEC_EXTRA <<< "${REGRESS_EXTRA:-}"

# inputs (keyed once, into the output dir)
"$PY" tools/digitize/key_background.py input/patch_book_burner.jpg "$OUT/bb_keyed.png" >/dev/null
"$PY" tools/digitize/key_background.py input/nano_banana/midnight-epicure.png "$OUT/me_keyed.png" >/dev/null
"$PY" tools/digitize/key_background.py input/earth.jpg "$OUT/earth_keyed.png" >/dev/null

echo "| design | stitches | colour blocks | trims | export s | pullsim uncovered % | pullsim gaps>=0.5mm2 | exposed travel moves >4.5mm | palette (hexes) |"
echo "|---|---|---|---|---|---|---|---|---|"

run_design() {
  local display="$1" slug="$2" keyed="$3"; shift 3
  local flags=("$@")
  local svg="$OUT/$slug.svg" vp3="$OUT/$slug.vp3"
  local secs unc gaps exposed stitches blocks trims palette ps tm

  if ! PYTHONPATH="$ROOT/tools/digitize" "$PY" "$VEC" "${VEC_EXTRA[@]}" \
        "${flags[@]}" "$keyed" "$svg" >"$OUT/$slug.vec.log" 2>&1; then
    echo "| $display | vectorize FAILED (see $OUT/$slug.vec.log) | | | | | | | |"
    return 0
  fi

  local t0 t1
  t0=$(date +%s)
  if ! PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
        "$PY" inkstitch/inkstitch.py --extension=zip --format-vp3=True \
        "$svg" >"$OUT/$slug.zip" 2>"$OUT/$slug.err"; then
    echo "| $display | export FAILED (see $OUT/$slug.err) | | | | | | | |"
    return 0
  fi
  t1=$(date +%s)
  secs=$((t1 - t0))

  "$PY" - "$OUT/$slug" <<'PY'
import sys, zipfile
b = sys.argv[1]
z = zipfile.ZipFile(b + ".zip")
open(b + ".vp3", "wb").write(z.read(z.namelist()[0]))
PY
  "$PY" tools/digitize/trim_vp3.py "$vp3" 8 >"$OUT/$slug.trim.log" 2>&1

  read -r stitches blocks trims palette < <("$PY" - "$vp3" <<'PY'
import sys, re, pystitch
p = pystitch.read(sys.argv[1])
M = pystitch.COMMAND_MASK
changes = sum(1 for s in p.stitches if len(s) > 2 and (s[2] & M) == pystitch.COLOR_CHANGE)
trims = sum(1 for s in p.stitches if len(s) > 2 and (s[2] & M) == pystitch.TRIM)
def hexof(t):
    m = re.search(r"#[0-9a-fA-F]{6}", str(t))
    return m.group(0) if m else str(t)
threads = [hexof(p.get_thread_or_filler(i)) for i in range(changes + 1)]
print(p.count_stitches(), len(threads), trims, ",".join(threads))
PY
  )

  ps=$("$PY" tools/digitize/qa/pullsim.py "$svg" "$keyed" 2>/dev/null | grep 'fill pull' || true)
  unc=$(sed -E 's/.*uncovered *([0-9.]+)%.*/\1/' <<<"$ps")
  gaps=$(sed -E 's/.*>=0\.5mm2 *([0-9]+).*/\1/' <<<"$ps")

  tm=$("$PY" tools/digitize/qa/travelmap.py "$vp3" "$OUT/${slug}_travel.png" \
       --red-mm 4.5 2>/dev/null || true)
  exposed=$(grep -oE 'not satin\): [0-9]+' <<<"$tm" | grep -oE '[0-9]+$' || true)
  : "${unc:=?}" "${gaps:=?}" "${exposed:=?}"

  echo "| $display | $stitches | $blocks | $trims | $secs | $unc | $gaps | $exposed | $palette |"
}

run_design "book burner" book_burner "$OUT/bb_keyed.png" --config work/book_burner.yaml
run_design "goat" goat "$OUT/me_keyed.png" --colors 6 --size-mm 80 --config patch_descriptions/border_black.yaml
run_design "earth" earth "$OUT/earth_keyed.png" --colors 3 --size-mm 60
