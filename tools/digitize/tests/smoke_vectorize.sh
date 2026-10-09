#!/usr/bin/env bash
# Smoke test for tools/digitize/vectorize.py: runs the Earth case end-to-end
# (key -> vectorize) and checks that a non-empty SVG + preview are written.
# No golden file; exit 0 iff the pipeline runs and writes its outputs.
set -eu
root="$(cd "$(dirname "$0")/../../.." && pwd)"; cd "$root"
tmp="$(mktemp -d)"
.venv/bin/python tools/digitize/key_background.py input/earth.jpg "$tmp/earth.png" >/dev/null
.venv/bin/python tools/digitize/vectorize.py --colors 3 --size-mm 60 "$tmp/earth.png" "$tmp/earth.svg" >/dev/null
test -s "$tmp/earth.svg"
test -s "$tmp/earth_posterized.png"
echo "smoke_vectorize: ok ($tmp/earth.svg)"
rm -rf "$tmp"
