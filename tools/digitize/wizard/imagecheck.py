"""Look at a picture the way the pipeline will: transparency, artwork bounds, plain background.

Mirrors vectorize.load_image and design_scale, so the pixels per mm quoted to the user match
what the pipeline will compute. Needs Pillow and numpy; scipy is used when present.
"""
from __future__ import annotations

from pathlib import Path

from .core import ImageReport

ALPHA_CUT = 128          # vectorize.load_image: alpha below this is transparent
CORNER = 8               # vectorize.design_scale and key_background: corner block size
BG_T0, BG_T1 = 10.0, 40.0   # key_background defaults: fully transparent below t0, opaque above t1
FRAME_SHARE = 0.9        # assumption: share of the outer frame within BG_T1 of the corner colour


def inspect(path: Path) -> ImageReport:
    try:
        import numpy as np
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        return ImageReport(ok=False, error="The picture check needs Pillow and numpy (%s). "
                                           "Run: python3 digitize.py doctor" % exc)
    try:
        with Image.open(str(path)) as im:
            arr = np.array(im.convert("RGBA"))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return ImageReport(ok=False, error="I cannot read %s as a picture (%s). Is it really a png, jpg or webp "
                                           "file? Try opening it in an image viewer." % (path.name, exc))
    h, w = arr.shape[:2]
    if h < 2 or w < 2:
        return ImageReport(ok=False, error="%s is only %d x %d pixels, too small to use." % (path.name, w, h))

    transparent = arr[..., 3] < ALPHA_CUT
    if transparent.any():
        dx, dy, dw, dh = _alpha_bounds(transparent, w, h)
        return ImageReport(width=w, height=h, design_w=dw, design_h=dh,
                           design_x=dx, design_y=dy, kind="transparent")

    rgb = arr[..., :3].astype(float)
    p = CORNER
    corners = np.concatenate([rgb[:p, :p].reshape(-1, 3), rgb[:p, -p:].reshape(-1, 3),
                              rgb[-p:, :p].reshape(-1, 3), rgb[-p:, -p:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(rgb - bg, axis=-1)
    fg = dist > BG_T1
    if fg.any():
        ys, xs = np.where(fg)
        dx, dy = int(xs.min()), int(ys.min())
        dw, dh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    else:
        dx = dy = 0
        dw, dh = w, h
    block = [np.median(b.reshape(-1, 3), axis=0) for b in
             (rgb[:p, :p], rgb[:p, -p:], rgb[-p:, :p], rgb[-p:, -p:])]
    corners_agree = all(np.linalg.norm(c - bg) <= BG_T0 for c in block)
    frame = np.concatenate([dist[:2].ravel(), dist[-2:].ravel(), dist[:, :2].ravel(), dist[:, -2:].ravel()])
    plain = corners_agree and float((frame <= BG_T1).mean()) >= FRAME_SHARE
    return ImageReport(width=w, height=h, design_w=dw, design_h=dh,
                       design_x=dx, design_y=dy,
                       kind="plain_background" if plain else "busy_background",
                       background_hex="#%02x%02x%02x" % tuple(int(round(v)) for v in bg) if plain else "")


def _alpha_bounds(transparent, w: int, h: int):
    """Bounds of the opaque parts. Like the pipeline: specks are ignored when scipy is available."""
    import numpy as np
    opaque = ~transparent
    try:
        from scipy import ndimage
        lbl, n = ndimage.label(opaque)
        if n:
            sizes = ndimage.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
            cut = max(100, int(0.0001 * w * h))
            keep = [i + 1 for i, s in enumerate(sizes) if s >= cut]
            if keep:
                opaque = np.isin(lbl, keep)
    except ImportError:
        pass
    ys, xs = np.where(opaque)
    if not len(xs):
        return 0, 0, w, h
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
