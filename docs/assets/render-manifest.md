# Render manifest

Written by `docs/assets/build_assets.sh`. Every number below is read from the VP3 file or the PNG that the same run produced.

| Item | Value |
|---|---|
| Repo HEAD at render time | `a795612` |
| Last commit that changed `tools/` (pipeline code) | `a377b2d 2026-10-09` |
| Uncommitted changes under `tools/` | none |
| Ink/Stitch commit (vendored clone) | `d59c9ab1e` |
| Python / Pillow / pystitch | 3.13.15 / 12.3.0 / unknown |
| Hero first panel | target render written by invert_ink.py --dump-dir |

Definitions

- Stitch count is `pystitch` `count_stitches()` on the final VP3. It counts every command: needle stitches, trims, jumps, colour changes and the END command. The needle-stitch column counts STITCH commands only.
- Colour blocks are colour changes plus one. Thread hexes are in block order.
- Stitched size is the `pystitch` `bounds()` box of the final VP3 (units are 0.1 mm).
- Seconds are wall time on the author's machine (Ryzen 5 5600X). The `run.sh` figure covers digitizing, the Ink/Stitch export, `trim_vp3.py` and both previews.
- Images are palette PNGs, no metadata (Pillow `info` and EXIF empty, only IHDR/PLTE/IDAT/IEND chunks). Files are at most 400 KB and 1600 px wide.

## Summary

| Image | Pixels | KB | Stitches | Needle stitches | Colour blocks | Stitched size mm | run.sh seconds |
|---|---|---|---|---|---|---|---|
| `docs/assets/gallery-bomb.png` | 1576 x 555 | 361 | 21,864 | 21,777 | 6 | 90.6 x 90.3 | 28.8 |
| `docs/assets/gallery-four-leaf-clover.png` | 1576 x 539 | 299 | 17,503 | 17,330 | 6 | 75.7 x 73.3 | 19.1 |
| `docs/assets/gallery-midnight-epicure.png` | 1576 x 554 | 345 | 16,309 | 16,205 | 6 | 80.4 x 80.3 | 32.8 |
| `docs/assets/gallery-peace.png` | 1576 x 559 | 319 | 7,248 | 7,174 | 1 | 60.8 x 61.4 | 26.0 |
| `docs/assets/gallery-reaper-spider.png` | 1576 x 521 | 325 | 12,509 | 12,394 | 5 | 70.3 x 65.5 | 32.9 |
| `docs/assets/gallery-skyfowl.png` | 1576 x 599 | 368 | 17,065 | 16,933 | 5 | 69.5 x 75.8 | 46.3 |
| `docs/assets/gallery-back-nine-skulls.png` | 1576 x 531 | 363 | 61,308 | 61,072 | 4 | 190.5 x 181.3 | 44.3 |
| `docs/assets/hero-scavenger-inverted.png` | 1576 x 383 | 189 | 54,233 | 54,141 | 2 | 259.8 x 168.6 | 16.5 |

## gallery-bomb.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/bomb.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 21,864 |
| Needle stitches / trims / jumps | 21,777 / 76 / 5 |
| Colour blocks | 6 |
| Thread hexes | #f2ecd7, #faad19, #fd5f1d, #727779, #9f1826, #101821 |
| Stitched size | 90.6 x 90.3 mm |
| Seconds | run 28.8 |
| Image file | `docs/assets/gallery-bomb.png`, 360,929 bytes (361 KB), 1576 x 555 px, 256-colour palette, sha256 `1fb0b2f93709a03b` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 6 --size-mm 90 --config patch_descriptions/border_black.yaml input/nano_banana/bomb.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-four-leaf-clover.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/four-leaf-clover.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 17,503 |
| Needle stitches / trims / jumps | 17,330 / 162 / 5 |
| Colour blocks | 6 |
| Thread hexes | #ebdfbe, #eab11f, #cd9060, #179a40, #0a592b, #141817 |
| Stitched size | 75.7 x 73.3 mm |
| Seconds | run 19.1 |
| Image file | `docs/assets/gallery-four-leaf-clover.png`, 298,681 bytes (299 KB), 1576 x 539 px, 256-colour palette, sha256 `ecb91423c120146f` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 6 --size-mm 75 --config patch_descriptions/border_black.yaml input/nano_banana/four-leaf-clover.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-midnight-epicure.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/midnight-epicure.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 16,309 |
| Needle stitches / trims / jumps | 16,205 / 93 / 5 |
| Colour blocks | 6 |
| Thread hexes | #ece6d3, #c4c2c3, #989797, #b16523, #595858, #1e1c1d |
| Stitched size | 80.4 x 80.3 mm |
| Seconds | run 32.8 |
| Image file | `docs/assets/gallery-midnight-epicure.png`, 344,986 bytes (345 KB), 1576 x 554 px, 256-colour palette, sha256 `c9e82a8cdd6a480b` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 6 --size-mm 80 --config patch_descriptions/border_black.yaml input/nano_banana/midnight-epicure.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-peace.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/peace.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 7,248 |
| Needle stitches / trims / jumps | 7,174 / 73 / 0 |
| Colour blocks | 1 |
| Thread hexes | #221a14 |
| Stitched size | 60.8 x 61.4 mm |
| Seconds | run 26.0 |
| Image file | `docs/assets/gallery-peace.png`, 318,678 bytes (319 KB), 1576 x 559 px, 256-colour palette, sha256 `7558a4f16c6d85a3` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 2 --size-mm 60 --config patch_descriptions/border_black.yaml input/nano_banana/peace.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-reaper-spider.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/reaper-spider.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 12,509 |
| Needle stitches / trims / jumps | 12,394 / 106 / 4 |
| Colour blocks | 5 |
| Thread hexes | #a8a9ab, #c97303, #626568, #343b45, #010101 |
| Stitched size | 70.3 x 65.5 mm |
| Seconds | run 32.9 |
| Image file | `docs/assets/gallery-reaper-spider.png`, 325,329 bytes (325 KB), 1576 x 521 px, 256-colour palette, sha256 `1dd0d9d03ec16e37` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 6 --size-mm 70 --config patch_descriptions/border_black.yaml input/nano_banana/reaper-spider.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-skyfowl.png

| Field | Value |
|---|---|
| Source file | `input/nano_banana/skyfowl.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 17,065 |
| Needle stitches / trims / jumps | 16,933 / 123 / 4 |
| Colour blocks | 5 |
| Thread hexes | #e4bc7e, #ce8f20, #f26e22, #a01a24, #0f141e |
| Stitched size | 69.5 x 75.8 mm |
| Seconds | run 46.3 |
| Image file | `docs/assets/gallery-skyfowl.png`, 367,502 bytes (368 KB), 1576 x 599 px, 256-colour palette, sha256 `e4a3cf7fc893694e` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --key-background --colors 6 --size-mm 75 --config patch_descriptions/border_black.yaml input/nano_banana/skyfowl.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## gallery-back-nine-skulls.png

| Field | Value |
|---|---|
| Source file | `work/back-nine-skulls_keyed.png` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 61,308 |
| Needle stitches / trims / jumps | 61,072 / 229 / 3 |
| Colour blocks | 4 |
| Thread hexes | #eee0c0, #97726a, #661720, #300612 |
| Stitched size | 190.5 x 181.3 mm |
| Seconds | run 44.3 |
| Image file | `docs/assets/gallery-back-nine-skulls.png`, 363,476 bytes (363 KB), 1576 x 531 px, 256-colour palette, sha256 `8163ad91af761f4d` |

Commands, in order (run from the repo root):

```
tools/digitize/run.sh --colors 4 --size-mm 190 --config patch_descriptions/border_black.yaml work/back-nine-skulls_keyed.png
```

Panels: source image, `output_vp3/<name>_stitchplan.png` (1 px stitch lines), `output_vp3/<name>_coverage.png` (0.5 mm thread width), each cropped below the preview header and scaled to the sheet.

## hero-scavenger-inverted.png

| Field | Value |
|---|---|
| Source file | `input/Scavenger's Daughter Upgrade Patch2.svg` |
| Pipeline commit | HEAD `a795612`, last change under `tools/` `a377b2d 2026-10-09` |
| Stitches (count_stitches) | 54,233 |
| Needle stitches / trims / jumps | 54,141 / 89 / 1 |
| Colour blocks | 2 |
| Thread hexes | #87f70f, #ffffff |
| Stitched size | 259.8 x 168.6 mm |
| Seconds | derive 17.9, run 16.5, render_svg 0.1 |
| Image file | `docs/assets/hero-scavenger-inverted.png`, 188,558 bytes (189 KB), 1576 x 383 px, 256-colour palette, sha256 `336d6c05d54ca2f8` |

Commands, in order (run from the repo root):

```
.venv/bin/python tools/digitize/invert_ink.py --ink "#030503" --paper "#ffffff" --plate-satin-colors "#87f70f" --border-mm 2.0 --fit-mm 260x200 --dump-dir work/readme_assets/hero-dump "input/Scavenger's Daughter Upgrade Patch2.svg" "work/Scavenger's Daughter Inverted.svg"
tools/digitize/run.sh --width-mm 260 --height-mm 200 --no-border --config work/readme_assets/scavenger_inverted.yaml --background "#101010" "work/Scavenger's Daughter Inverted.svg"
rsvg-convert -w 1560 -b "#101010" "output_inkstitch_svg/Scavenger's Daughter Inverted.svg" -o work/readme_assets/hero-inkstitch.png
```

Panels: derived artwork, `rsvg-convert` render of the Ink/Stitch SVG, `output_vp3/<name>_stitchplan.png`. Previews use fabric colour `#101010`.

