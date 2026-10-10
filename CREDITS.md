# Credits and attribution

This repository shows renders of artwork to demonstrate the pipeline. **All artwork remains the property of its creators.** Patch subjects are catalogued on the [Dungeon Crawler Carl wiki](https://dungeon-crawler-carl.fandom.com/wiki/Category:Patches) (wiki text is [CC-BY-SA](https://www.fandom.com/licensing)). If you are a creator named here and have a question about a render, contact the repository owner on GitHub (kxzl).

## Artwork by other people

| Sample file | Patch | Artist | Source |
|---|---|---|---|
| `Bomb_patch.webp` | Bomb Upgrade Patch | u/waterkangaroo (Reddit) | [Bomb Upgrade Patch](https://dungeon-crawler-carl.fandom.com/wiki/Bomb_Upgrade_Patch) |
| `Book_burner_patch.PNG.webp` | Book Burner Patch | u/waterkangaroo (Reddit) | [Book Burner Patch](https://dungeon-crawler-carl.fandom.com/wiki/Book_Burner_Patch) |
| `Skyfowl_patch.webp` | Skyfowl Upgrade Patch | Waterkangaroo | [Skyfowl Upgrade Patch](https://dungeon-crawler-carl.fandom.com/wiki/Skyfowl_Upgrade_Patch) |
| `Scavenger's_Daughter_by_the_dusty_druid.webp` and the layered SVG versions | Scavenger's Daughter Upgrade Patch | @thedustydruid (Instagram) | [Scavenger's Daughter Upgrade Patch](https://dungeon-crawler-carl.fandom.com/wiki/Scavenger%27s_Daughter_Upgrade_Patch) |

## AI-generated images

The gallery source images in the README (`input/nano_banana/*.png`: Bomb, Four-Leaf Clover, Midnight Epicure, Peace, Reaper Spider, Skyfowl, and the Back Nine Skulls source) and the `Gemini_Generated_Image_*.jpg` files were generated with Google Gemini from prompts written by the repository owner.

## Derived files

- The stitch plans, coverage renders and SVG renders in `docs/assets/` are pipeline output made from the images above. `docs/assets/render-manifest.md` lists the exact command for each.
- The hero image shows a two-colour version of Scavenger's Daughter (ink and paper swapped by `tools/digitize/invert_ink.py`), made from the artist's layered SVG.
- `Scavenger's Daughter Upgrade Patch.svg` and `.vp3` are digitized derivatives of the same artwork.

## Tools

Embroidery export is done by [Ink/Stitch](https://inkstitch.org).

The original sample pictures are not committed to this repository (see `.gitignore`). Only the preview renders in `docs/assets/` are.
