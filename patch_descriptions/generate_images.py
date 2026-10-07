#!/usr/bin/env python3
"""Generate patch images with Google's Gemini image model ("Nano Banana").

Reads the paste-ready prompt out of each patch file under
patch_descriptions/prompts/, calls the Gemini image API once per patch, and
saves a PNG per patch into input/nano_banana/.

Auth: the API key is read from (in order) $GEMINI_API_KEY, then
/tmp/opencode/gemini_key, then ~/.config/opencode/gemini_key. The key is never
printed.

Usage:
    .venv/bin/python patch_descriptions/generate_images.py            # all patches
    .venv/bin/python patch_descriptions/generate_images.py bomb skyfowl
    .venv/bin/python patch_descriptions/generate_images.py --force    # overwrite
    .venv/bin/python patch_descriptions/generate_images.py --model gemini-2.5-flash-image
    .venv/bin/python patch_descriptions/generate_images.py --list-models
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "patch_descriptions" / "prompts"
OUT_DIR = ROOT / "input" / "nano_banana"
API = "https://generativelanguage.googleapis.com/v1beta"

# Preferred image models, newest first. The script falls back to the first
# candidate the key can actually use, so an unknown future id is fine.
MODEL_CANDIDATES = [
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-preview",
]


def read_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    for p in (Path("/tmp/opencode/gemini_key"),
              Path.home() / ".config" / "opencode" / "gemini_key"):
        if p.is_file() and p.read_text().strip():
            return p.read_text().strip()
    sys.exit("error: no API key. Set GEMINI_API_KEY or write it to "
             "/tmp/opencode/gemini_key")


def http_json(url: str, payload: dict | None = None, timeout: int = 180) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="GET" if data is None else "POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:800]}") from None


def list_models(key: str) -> list[str]:
    out = http_json(f"{API}/models?key={key}")
    names = [m["name"].split("/")[-1] for m in out.get("models", [])]
    return sorted(names)


def pick_model(key: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    available = set(list_models(key))
    for cand in MODEL_CANDIDATES:
        if cand in available:
            return cand
    image_models = sorted(m for m in available if "image" in m)
    if image_models:
        return image_models[-1]
    sys.exit(f"error: no image model available. Models seen: {sorted(available)}")


def extract_prompt(path: Path) -> str:
    text = path.read_text()
    # the paste-ready prompt is the first fenced block after the "## Prompt" head
    head = text.split("## Prompt", 1)
    if len(head) != 2:
        sys.exit(f"error: no '## Prompt' section in {path}")
    m = re.search(r"```[^\n]*\n(.*?)```", head[1], re.S)
    if not m:
        sys.exit(f"error: no fenced prompt block in {path}")
    return m.group(1).strip()


def generate(key: str, model: str, prompt: str) -> bytes:
    url = f"{API}/models/{model}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"imageConfig": {"aspectRatio": "1:1"}},
    }
    try:
        out = http_json(url, body)
    except RuntimeError as e:
        # some models reject imageConfig; retry once without it
        if "imageConfig" not in str(e) and "aspect" not in str(e).lower():
            raise
        out = http_json(url, {"contents": [{"parts": [{"text": prompt}]}]})

    cands = out.get("candidates") or []
    if not cands:
        fb = out.get("promptFeedback", {})
        raise RuntimeError(f"no candidates (blocked?): {json.dumps(fb)[:400]}")
    for part in cands[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    finish = cands[0].get("finishReason")
    raise RuntimeError(f"no image in response (finishReason={finish})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("patches", nargs="*", help="slugs (default: all)")
    ap.add_argument("--model")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds between calls (default 3)")
    args = ap.parse_args()

    key = read_key()
    if args.list_models:
        print("\n".join(list_models(key)))
        return

    model = pick_model(key, args.model)
    print(f"model: {model}")

    slugs = args.patches or sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    failures = []
    for i, slug in enumerate(slugs):
        src = PROMPTS_DIR / f"{slug}.md"
        if not src.is_file():
            failures.append(slug)
            print(f"  {slug}: MISSING prompt file")
            continue
        dst = OUT_DIR / f"{slug}.png"
        if dst.exists() and not args.force:
            print(f"  {slug}: exists, skipped ({dst.relative_to(ROOT)})")
            continue
        prompt = extract_prompt(src)
        try:
            png = generate(key, model, prompt)
            dst.write_bytes(png)
            print(f"  {slug}: OK -> {dst.relative_to(ROOT)} ({len(png)//1024} KB)")
        except Exception as e:  # noqa: BLE001 - report and keep going
            failures.append(slug)
            print(f"  {slug}: FAILED - {e}")
        if i != len(slugs) - 1:
            time.sleep(args.delay)

    print(f"\ndone: {len(slugs) - len(failures)}/{len(slugs)} generated")
    if failures:
        print("failed:", ", ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
