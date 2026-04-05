"""
svg_utils.py
------------
Helpers to convert svgpathtools Path objects into plain polylines (lists of
(x, y) float tuples) and to scale / translate them into printer-bed coordinates.
"""

import math
from typing import List, Tuple
import svgpathtools

# Type aliases
Point = Tuple[float, float]
Polyline = List[Point]


# ──────────────────────────────────────────────────────────────────────────────
# SVG path → polylines
# ──────────────────────────────────────────────────────────────────────────────

def svg_paths_to_polylines(
    paths: list,
    samples_per_segment: int = 20,
    min_length: float = 0.5,
) -> List[Polyline]:
    """
    Convert a list of svgpathtools Path objects into polylines.

    Each Path becomes one Polyline (list of (x, y) tuples).
    Very short paths (below min_length in SVG units) are discarded as noise.
    """
    polylines: List[Polyline] = []

    for path in paths:
        try:
            pts = _sample_path(path, samples_per_segment)
        except Exception:
            continue

        if not pts:
            continue

        # Filter noise: skip paths that are too short
        if _polyline_length(pts) < min_length:
            continue

        polylines.append(pts)

    return polylines


def _sample_path(path, samples_per_segment: int) -> Polyline:
    """Uniformly sample a svgpathtools Path into (x, y) tuples."""
    pts: Polyline = []
    n_segments = len(path)
    if n_segments == 0:
        return pts

    for seg in path:
        n = samples_per_segment
        for i in range(n + 1):
            t = i / n
            try:
                pt = seg.point(t)
                pts.append((pt.real, pt.imag))
            except Exception:
                pass
    return pts


def _polyline_length(pts: Polyline) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        total += math.hypot(dx, dy)
    return total


# ──────────────────────────────────────────────────────────────────────────────
# Bounding-box helpers
# ──────────────────────────────────────────────────────────────────────────────

def estimate_bounds(polylines: List[Polyline]) -> Tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) across all polylines."""
    all_x = [p[0] for pl in polylines for p in pl]
    all_y = [p[1] for pl in polylines for p in pl]

    if not all_x:
        return (0.0, 0.0, 1.0, 1.0)

    return (min(all_x), min(all_y), max(all_x), max(all_y))


# ──────────────────────────────────────────────────────────────────────────────
# Scaling
# ──────────────────────────────────────────────────────────────────────────────

def scale_polylines(
    polylines: List[Polyline],
    bed_width: float = 220.0,
    bed_height: float = 220.0,
    margin: float = 5.0,
    flip_y: bool = True,
) -> List[Polyline]:
    """
    Scale & translate polylines to fit within the printer bed.

    Args:
        bed_width / bed_height : printer bed dimensions in mm
        margin                 : border margin in mm on each side
        flip_y                 : SVG Y increases downward; G-code Y increases
                                  upward — flip it so the image isn't mirrored
    Returns:
        New list of scaled polylines in mm coordinates.
    """
    if not polylines:
        return polylines

    sx_min, sy_min, sx_max, sy_max = estimate_bounds(polylines)
    src_w = sx_max - sx_min or 1.0
    src_h = sy_max - sy_min or 1.0

    target_w = bed_width  - 2 * margin
    target_h = bed_height - 2 * margin

    scale = min(target_w / src_w, target_h / src_h)

    # Centre on bed
    offset_x = margin + (target_w - src_w * scale) / 2.0
    offset_y = margin + (target_h - src_h * scale) / 2.0

    scaled: List[Polyline] = []
    for poly in polylines:
        new_poly: Polyline = []
        for (x, y) in poly:
            nx = (x - sx_min) * scale + offset_x
            if flip_y:
                # Invert Y: SVG origin is top-left; G-code origin is bottom-left
                ny = (sy_max - y) * scale + offset_y
            else:
                ny = (y - sy_min) * scale + offset_y
            new_poly.append((nx, ny))
        scaled.append(new_poly)

    return scaled
