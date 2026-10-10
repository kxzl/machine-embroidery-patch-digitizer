"""Fit a straight-line colour gradient to a raster region.

Pure functions, no I/O. The pipeline names the stop colours of a gradient region
(for example golden yellow, orange, deep red); this module finds where in the
image such a region is and which straight line its colour ramp follows, so
vectorize.py can emit it as an Ink/Stitch linear gradient fill.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage import color


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"not a #rrggbb colour: {h!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_lab(rgb) -> np.ndarray:
    """(..., 3) RGB in 0..255 -> (N, 3) CIELAB."""
    a = np.asarray(rgb, dtype=float).reshape(-1, 1, 3) / 255.0
    return color.rgb2lab(a).reshape(-1, 3)


def resolve_stops(stop_hexes, centroids_rgb, max_delta_e: float = 30.0) -> list[int]:
    """Index of the nearest palette colour (CIELAB) for each stop hex."""
    cents = rgb_to_lab(centroids_rgb)
    out: list[int] = []
    for h in stop_hexes:
        lab = rgb_to_lab([hex_to_rgb(h)])[0]
        d = np.linalg.norm(cents - lab, axis=1)
        i = int(d.argmin())
        if d[i] > max_delta_e:
            raise ValueError(f"gradient stop {h} is {d[i]:.0f} dE from the nearest palette colour")
        if i in out:
            raise ValueError(f"gradient stop {h} resolves to the same palette colour as an earlier stop")
        out.append(i)
    return out


def regions(mask: np.ndarray, min_area_px: int) -> list[np.ndarray]:
    """8-connected components of mask with at least min_area_px pixels, largest first."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return []
    sizes = np.bincount(lab.ravel())[1:]
    order = np.argsort(-sizes, kind="stable")
    return [lab == (int(i) + 1) for i in order if sizes[i] >= min_area_px]


def _project(lab_pixels: np.ndarray, stops_lab: np.ndarray):
    """Position s in 0..1 of each pixel's nearest point on the polyline through the stops."""
    seg = np.diff(stops_lab, axis=0)
    seglen = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seglen)])
    total = float(cum[-1])
    if total <= 1e-6:
        return None, None
    best_d = np.full(len(lab_pixels), np.inf)
    best_s = np.zeros(len(lab_pixels))
    for k in range(len(seglen)):
        if seglen[k] <= 1e-9:
            continue
        t = np.clip(((lab_pixels - stops_lab[k]) @ seg[k]) / seglen[k] ** 2, 0.0, 1.0)
        d = np.linalg.norm(lab_pixels - (stops_lab[k] + t[:, None] * seg[k]), axis=1)
        better = d < best_d
        best_d = np.where(better, d, best_d)
        best_s = np.where(better, (cum[k] + t * seglen[k]) / total, best_s)
    return best_s, cum / total


def _plane(xy: np.ndarray, s: np.ndarray):
    a = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
    coef, *_ = np.linalg.lstsq(a, s, rcond=None)
    return coef, s - a @ coef


def fit_region(lab_pixels, xy, stops_lab, min_r2: float = 0.5, min_span: float = 0.3,
               trim: float = 0.02):
    """Fit s ~ a*x + b*y + c, where s is the colour's position along the stop polyline.

    Returns None when the region is not a usable gradient (no colour ramp, a poor
    straight-line fit, or the ramp changes less than min_span across the region).
    Otherwise a dict with the stop offsets and the two gradient endpoints in pixel
    coordinates (x, y; y down), where s is 0 at p1 and 1 at p2.
    """
    lab_pixels = np.asarray(lab_pixels, dtype=float)
    xy = np.asarray(xy, dtype=float)
    stops_lab = np.asarray(stops_lab, dtype=float)
    if len(lab_pixels) < 3 or len(stops_lab) < 2:
        return None
    s, offsets = _project(lab_pixels, stops_lab)
    if s is None:
        return None
    coef, res = _plane(xy, s)
    if 0.0 < trim < 1.0 and len(s) > 20:
        keep = np.abs(res) <= np.quantile(np.abs(res), 1.0 - trim)
        coef, res = _plane(xy[keep], s[keep])
        xy, s = xy[keep], s[keep]
    ss_tot = float(((s - s.mean()) ** 2).sum())
    if ss_tot <= 1e-12:
        return None
    r2 = 1.0 - float((res ** 2).sum()) / ss_tot
    if r2 < min_r2:
        return None
    g = coef[:2]
    gn = float(np.hypot(*g))
    if gn < 1e-12:
        return None
    u = g / gn
    proj = xy @ u
    span = gn * float(proj.max() - proj.min())
    if span < min_span:
        return None
    m = xy.mean(axis=0)
    s_m = float(coef[0] * m[0] + coef[1] * m[1] + coef[2])
    p1 = m + (0.0 - s_m) * g / gn ** 2
    p2 = m + (1.0 - s_m) * g / gn ** 2
    return {
        "offsets": [float(o) for o in offsets],
        "p1": (float(p1[0]), float(p1[1])),
        "p2": (float(p2[0]), float(p2[1])),
        "r2": float(r2),
        "span": float(span),
        "angle_deg": float(np.degrees(np.arctan2(g[1], g[0]))),
    }
