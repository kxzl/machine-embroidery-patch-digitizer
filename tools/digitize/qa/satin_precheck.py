#!/usr/bin/env python3
"""Find satin columns that crash the Ink/Stitch export, and optionally drop them.

Some outline satins have a rail geometry Ink/Stitch cannot build (a short hook or
loop narrower than the satin: `IndexError: tuple index out of range` in
`flattened_sections`). The crash aborts the whole VP3 export and the traceback does
not name the element. This script builds each satin column on its own, the way the
export does, and reports the ids that raise.

Usage:
    PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \\
      .venv/bin/python tools/digitize/qa/satin_precheck.py IN.svg [--fix OUT.svg]

Prints one line per bad satin ("bad satin: ID") and a summary. With --fix the bad
satins are removed from OUT.svg (a hook shorter than the satin is wide leaves no
visible gap; the fill underneath stays). Exit code 0 always, so run.sh can call it.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "inkstitch"))
sys.path.insert(0, str(ROOT / "tools" / "wxstub"))
os.environ.setdefault("INKSTITCH_OFFLINE_SCRIPT", "true")

from lib.elements.satin_column import SatinColumn  # noqa: E402
from lib.extensions.base import InkstitchExtension  # noqa: E402


class SatinPrecheck(InkstitchExtension):
    bad = []
    total = 0

    def effect(self):
        if not self.get_elements():
            return
        for el in self.elements:
            if not isinstance(el, SatinColumn):
                continue
            SatinPrecheck.total += 1
            try:
                el.to_stitch_groups(None)
            except Exception:                       # noqa: BLE001 - any failure is a bad satin
                SatinPrecheck.bad.append(el.node.get("id"))


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    src = argv[0]
    out = argv[argv.index("--fix") + 1] if "--fix" in argv else None
    SatinPrecheck().run(args=[src], output=os.devnull)     # inkex would print the SVG to stdout
    for i in SatinPrecheck.bad:
        print(f"bad satin: {i}")
    print(f"satin precheck: {SatinPrecheck.total} satin(s), {len(SatinPrecheck.bad)} bad")
    if out and SatinPrecheck.bad:
        text = Path(src).read_text()
        for i in SatinPrecheck.bad:
            text = re.sub(r'<path id="%s"[^>]*/>\s*' % re.escape(i), "", text)
        Path(out).write_text(text)
        print(f"removed {len(SatinPrecheck.bad)} bad satin(s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
