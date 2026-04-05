"""
optimizer.py
------------
Path optimisation: nearest-neighbour path ordering to minimise pen lifts,
short-path filtering, and optional segment merging.
"""

import math
from typing import List, Tuple

Point = Tuple[float, float]
Polyline = List[Point]


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def optimize_paths(
    polylines: List[Polyline],
    min_path_length: float = 1.0,    # mm — discard shorter paths
    merge_threshold: float = 0.5,    # mm — join paths whose endpoints are closer
) -> List[Polyline]:
    """
    1. Filter out paths shorter than min_path_length.
    2. Merge collinear / end-to-end neighbouring paths.
    3. Reorder paths using greedy nearest-neighbour to minimise travel distance.

    Returns a new list of optimised polylines.
    """
    polylines = _filter_short(polylines, min_path_length)
    polylines = _merge_endpoints(polylines, merge_threshold)
    polylines = _nearest_neighbour_sort(polylines)
    return polylines


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 – filter short paths
# ──────────────────────────────────────────────────────────────────────────────

def _filter_short(polylines: List[Polyline], min_len: float) -> List[Polyline]:
    return [p for p in polylines if _length(p) >= min_len]


def _length(poly: Polyline) -> float:
    total = 0.0
    for i in range(1, len(poly)):
        total += _dist(poly[i - 1], poly[i])
    return total


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 – merge end-to-end segments
# ──────────────────────────────────────────────────────────────────────────────

def _merge_endpoints(
    polylines: List[Polyline], threshold: float
) -> List[Polyline]:
    """
    If the end of polyline A is within `threshold` mm of the start of polyline B,
    concatenate them to avoid a pen-lift travel move.
    """
    if not polylines:
        return polylines

    merged: List[Polyline] = [list(polylines[0])]

    for poly in polylines[1:]:
        prev_end = merged[-1][-1]
        cur_start = poly[0]

        if _dist(prev_end, cur_start) <= threshold:
            # Extend last polyline — skip duplicate junction point
            merged[-1].extend(poly[1:])
        else:
            merged.append(list(poly))

    return merged


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 – nearest-neighbour reordering
# ──────────────────────────────────────────────────────────────────────────────

def _nearest_neighbour_sort(polylines: List[Polyline]) -> List[Polyline]:
    """
    Greedy nearest-neighbour: always go to the polyline whose *start* or *end*
    point is closest to the current pen position.  If the closest point is the
    polyline's end, it is reversed before appending (to draw in the right
    direction without extra travel).
    """
    if not polylines:
        return polylines

    remaining = list(polylines)
    ordered: List[Polyline] = []

    # Start at origin
    cur_pos: Point = (0.0, 0.0)

    while remaining:
        best_idx = 0
        best_dist = math.inf
        best_reversed = False

        for i, poly in enumerate(remaining):
            d_start = _dist(cur_pos, poly[0])
            d_end   = _dist(cur_pos, poly[-1])

            if d_start <= d_end:
                d = d_start
                rev = False
            else:
                d = d_end
                rev = True

            if d < best_dist:
                best_dist = d
                best_idx = i
                best_reversed = rev

        chosen = remaining.pop(best_idx)
        if best_reversed:
            chosen = chosen[::-1]

        ordered.append(chosen)
        cur_pos = chosen[-1]

    return ordered
