"""
tracer.py
---------
Converts a binary PIL Image into a list of vector polylines using either:
  1. Potrace (preferred) — smooth Bézier curves converted via svgpathtools
  2. OpenCV contours    — fallback when Potrace is unavailable

Returns a list of polylines in SVG-pixel coordinates.
"""

import io
import subprocess
import tempfile
import os
from typing import List, Tuple

import numpy as np
import cv2
from PIL import Image

try:
    import svgpathtools
    _HAS_SVG = True
except ImportError:
    _HAS_SVG = False

Point = Tuple[float, float]
Polyline = List[Point]


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def trace_to_svg(
    binary_img: Image.Image,
    backend: str = "auto",        # "potrace" | "opencv" | "auto"
    samples_per_segment: int = 20,
    min_area: float = 10.0,       # minimum contour area (OpenCV fallback)
) -> List[Polyline]:
    """
    Trace a binary image into a list of polylines.

    Args:
        binary_img         : PIL Image in mode "L" — strokes BLACK, bg WHITE
        backend            : vectorisation engine to use
        samples_per_segment: Bézier curve sample density (Potrace path)
        min_area           : smallest OpenCV contour to keep (fallback)

    Returns:
        List[Polyline] – each polyline is a list of (x, y) float tuples in
        the coordinate space of the source image (pixels).
    """
    if backend == "auto":
        backend = "potrace" if _potrace_available() else "opencv"

    if backend == "potrace":
        try:
            return _trace_potrace(binary_img, samples_per_segment)
        except Exception as exc:
            print(f"[tracer] Potrace failed ({exc}), falling back to OpenCV")
            backend = "opencv"

    return _trace_opencv(binary_img, min_area)


# ──────────────────────────────────────────────────────────────────────────────
# Potrace backend
# ──────────────────────────────────────────────────────────────────────────────

def _potrace_available() -> bool:
    try:
        result = subprocess.run(
            ["potrace", "--version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _trace_potrace(img: Image.Image, samples_per_segment: int) -> List[Polyline]:
    """
    Run potrace CLI:  BMP → SVG → parse with svgpathtools → sample into polylines.
    """
    if not _HAS_SVG:
        raise RuntimeError("svgpathtools not installed")

    # Write BMP to a temp file (potrace reads BMP/PBM natively)
    with tempfile.TemporaryDirectory() as tmpdir:
        bmp_path = os.path.join(tmpdir, "input.bmp")
        svg_path = os.path.join(tmpdir, "output.svg")

        # Potrace needs black = foreground; our binary has strokes=0 (black)
        bmp_img = img.convert("1")           # 1-bit: 0 = black = draw
        bmp_img.save(bmp_path)

        result = subprocess.run(
            ["potrace", "-s", "-o", svg_path, bmp_path],
            capture_output=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

        paths, _attrs, _svg_attrs = svgpathtools.svg2paths2(svg_path)

    from utils.svg_utils import svg_paths_to_polylines
    return svg_paths_to_polylines(paths, samples_per_segment=samples_per_segment)


# ──────────────────────────────────────────────────────────────────────────────
# OpenCV contour fallback
# ──────────────────────────────────────────────────────────────────────────────

def _trace_opencv(img: Image.Image, min_area: float) -> List[Polyline]:
    """
    Find contours in the binary image and return them as polylines.
    Contours with area < min_area are discarded as visual noise.
    """
    gray = np.array(img.convert("L"))

    # Invert so foreground (strokes) = white for findContours
    inv = cv2.bitwise_not(gray)
    _, binary = cv2.threshold(inv, 127, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(
        binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS
    )

    polylines: List[Polyline] = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue

        # Approximate to reduce point count slightly
        eps = 0.3
        approx = cv2.approxPolyDP(cnt, eps, closed=True)
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]

        if len(pts) >= 2:
            pts.append(pts[0])       # close the shape
            polylines.append(pts)

    return polylines
