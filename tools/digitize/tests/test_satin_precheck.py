"""satin_precheck.py finds satin columns that crash the Ink/Stitch export and removes them.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_satin_precheck.py -v
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "digitize" / "qa" / "satin_precheck.py"
PY = ROOT / ".venv" / "bin" / "python"

SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="100mm" height="100mm" viewBox="0 0 2000 2000">
  <g inkscape:groupmode="layer" id="outlines">
    <path id="good" style="fill:none;stroke:#000000;stroke-width:40" inkstitch:satin_column="true" d="M 200,500 L 1200,520"/>
    <path id="hook" style="fill:none;stroke:#000000;stroke-width:40.6" inkstitch:satin_column="true" d="M 1994.0,1143.0 L 2026.0,1107.0 L 2030.0,1162.0 L 2013.0,1161.0"/>
  </g>
</svg>
"""


def run(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "tools" / "wxstub"), INKSTITCH_OFFLINE_SCRIPT="true")
    return subprocess.run([str(PY), str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=120)


@unittest.skipUnless(PY.exists() and (ROOT / "inkstitch").exists(), "needs the repo venv and the inkstitch checkout")
class SatinPrecheckTests(unittest.TestCase):
    def test_reports_and_removes_the_hook_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.svg"
            out = Path(tmp) / "out.svg"
            src.write_text(SVG)
            r = run(str(src), "--fix", str(out))
            self.assertIn("bad satin: hook", r.stdout)
            self.assertNotIn("bad satin: good", r.stdout)
            self.assertIn("2 satin(s), 1 bad", r.stdout)
            text = out.read_text()
            self.assertIn('id="good"', text)
            self.assertNotIn('id="hook"', text)

    def test_clean_svg_is_not_rewritten(self):
        clean = SVG.replace('d="M 1994.0,1143.0 L 2026.0,1107.0 L 2030.0,1162.0 L 2013.0,1161.0"',
                            'd="M 200,900 L 1200,920"')
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.svg"
            out = Path(tmp) / "out.svg"
            src.write_text(clean)
            r = run(str(src), "--fix", str(out))
            self.assertIn("0 bad", r.stdout)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
