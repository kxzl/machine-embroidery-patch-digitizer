#!/usr/bin/env bash
# export.sh <svg> -> <svg base>.vp3 + previews next to it.
# Repo-relative: resolves the repo root from this script's location.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
S="$1"; B="${S%.svg}"
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true timeout 1800 \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
  "$S" > "$B.zip" 2>"$B.err" || { echo FAIL; tail "$B.err"; exit 1; }
.venv/bin/python - "$B" <<'PY'
import sys, zipfile, pystitch, math
b=sys.argv[1]; z=zipfile.ZipFile(b+".zip"); open(b+".vp3","wb").write(z.read(z.namelist()[0]))
p=pystitch.read(b+".vp3")
trims=sum(1 for s in p.stitches if (s[2]&pystitch.COMMAND_MASK)==pystitch.TRIM)
cc=sum(1 for s in p.stitches if (s[2]&pystitch.COMMAND_MASK)==pystitch.COLOR_CHANGE)
last=None; thread=0; longm=0
for x,y,c in p.stitches:
    c&=pystitch.COMMAND_MASK
    if c==pystitch.TRIM: last=None; continue
    if c!=pystitch.STITCH: continue
    if last:
        L=math.hypot(x-last[0],y-last[1])/10
        if L<=8: thread+=L
        else: longm+=1
    last=(x,y)
print(f"{b}: {p.count_stitches()} stitches, {trims} trims, {cc} colour changes, thread {thread/1000:.1f} m, moves>8mm untrimmed {longm}")
PY
.venv/bin/python tools/digitize/preview.py "$B.vp3" "${B}_stitchplan.png" \
  --width 1600 --line-width 1 >/dev/null
.venv/bin/python tools/digitize/preview.py "$B.vp3" "${B}_coverage.png" \
  --width 1600 --thread-mm 0.5 >/dev/null
