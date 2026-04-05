"""
preprocessor.py
---------------
Handles image loading (from file path or URL), resizing, grayscale conversion,
noise reduction, and edge/threshold detection.

Returns a binary (black-on-white) PIL Image ready for vectorisation.
"""

import io
import requests
import numpy as np
import cv2
from PIL import Image

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def preprocess_image(
    source,                     # file path str | bytes | PIL.Image | URL str
    max_dimension: int = 1024,
    blur_radius: int = 1,
    threshold_mode: str = "auto",   # "auto" | "canny" | "binary"
    canny_low: int = 50,
    canny_high: int = 150,
    binary_threshold: int = 128,
    invert: bool = False,
) -> Image.Image:
    """
    Full pre-processing pipeline.

    Returns a binary PIL Image (mode "L") where drawing strokes are BLACK (0)
    and the background is WHITE (255).  This is the format Potrace expects.
    """
    pil_img = _load_image(source)
    pil_img = _resize(pil_img, max_dimension)
    gray_np = _to_gray_np(pil_img)
    gray_np = _denoise(gray_np, blur_radius)
    binary_np = _binarise(gray_np, threshold_mode, canny_low, canny_high, binary_threshold)

    if invert:
        binary_np = cv2.bitwise_not(binary_np)

    return Image.fromarray(binary_np)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_image(source) -> Image.Image:
    """Accept file-path string, raw bytes, URL string, or PIL.Image."""
    if isinstance(source, Image.Image):
        return source.convert("RGB")

    if isinstance(source, (bytes, bytearray)):
        return Image.open(io.BytesIO(source)).convert("RGB")

    if isinstance(source, str):
        if source.startswith("http://") or source.startswith("https://"):
            resp = requests.get(
                source,
                timeout=20,
                headers=_HEADERS,
                allow_redirects=True,
            )
            if resp.status_code >= 400:
                raise ValueError(
                    f"Could not fetch image from URL (HTTP {resp.status_code}). "
                    "Try downloading the image and uploading it directly."
                )
            ct = resp.headers.get("content-type", "")
            if "html" in ct:
                raise ValueError(
                    "The URL returned an HTML page, not an image. "
                    "Use a direct image link (ending in .jpg, .png, etc.)."
                )
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        # Treat as file path
        return Image.open(source).convert("RGB")

    raise TypeError(f"Unsupported source type: {type(source)}")


def _resize(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    scale = min(max_dim / w, max_dim / h, 1.0)   # never upscale
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    return img


def _to_gray_np(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("L"))
    return arr


def _denoise(gray: np.ndarray, blur_radius: int) -> np.ndarray:
    if blur_radius > 0:
        k = blur_radius * 2 + 1          # must be odd
        gray = cv2.GaussianBlur(gray, (k, k), 0)
    return gray


def _binarise(
    gray: np.ndarray,
    mode: str,
    canny_low: int,
    canny_high: int,
    binary_threshold: int,
) -> np.ndarray:
    """
    Returns a uint8 array where strokes = 0 (BLACK), background = 255 (WHITE).
    """
    if mode == "canny":
        edges = cv2.Canny(gray, canny_low, canny_high)
        # Canny: edges=255, bg=0  →  invert for Potrace convention
        return cv2.bitwise_not(edges)

    if mode == "auto":
        # Otsu's method — best for general images
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return binary

    # mode == "binary"
    _, binary = cv2.threshold(gray, binary_threshold, 255, cv2.THRESH_BINARY)
    return binary
