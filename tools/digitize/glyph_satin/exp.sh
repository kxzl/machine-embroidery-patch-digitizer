#!/usr/bin/env bash
# exp.sh <svg> : Ink/Stitch -> vp3 + trim + previews, next to the svg.
set -euo pipefail
R="$(cd "$(dirname "$0")/../../.." && pwd)"
S="$1"; B="${S%.svg}"
cd "$R"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true timeout 900 .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True "$S" > "$B.zip" 2>"$B.err" || { echo FAIL; tail -20 "$B.err"; exit 1; }
.venv/bin/python - "$B" <<'PY'
import sys, zipfile
b=sys.argv[1]; z=zipfile.ZipFile(b+".zip"); open(b+".vp3","wb").write(z.read(z.namelist()[0]))
PY
.venv/bin/python tools/digitize/trim_vp3.py "$B.vp3" 8
.venv/bin/python tools/digitize/preview.py "$B.vp3" "${B}_plan.png" --width 1600 --line-width 1 --background 101010 >/dev/null
.venv/bin/python tools/digitize/preview.py "$B.vp3" "${B}_cov.png" --width 1600 --thread-mm 0.5 --background 101010 >/dev/null
.venv/bin/python tools/digitize/qa/jam_check.py "$B.vp3" || true
