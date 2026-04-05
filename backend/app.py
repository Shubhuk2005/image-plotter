"""
app.py
------
Flask backend for the Image → G-code pen plotter converter.

Full pipeline:
  Image → Preprocess → Trace (SVG) → Optimise → Scale
       → Pen-plotter G-code          (Z-axis pen control, no E)
       → STL mesh                    (extruded traces for 3D visualisation)
       → FDM Sliced G-code           (layered extrusion for 3D printing)

Routes
------
POST /api/convert           — full pipeline, returns all artefacts as JSON
GET  /api/health            — health check
GET  /                      — serves root index.html
GET  /<path:filename>       — serves repository static assets
"""

import io
import os
import base64
import traceback

import numpy as np
import cv2
from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from flask_cors import CORS
from PIL import Image

# ── Browser-like headers for URL fetching ────────────────────────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

# ── Pipeline modules ──────────────────────────────────────────────────────────
from pipeline import (
    preprocess_image, trace_to_svg, optimize_paths, generate_gcode,
    polylines_to_stl, stl_available,
    slice_to_fdm_gcode, slicer_stats,
)
from utils import scale_polylines

# ── Resolve repository root ───────────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff"}
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024   # 20 MB

# ── In-memory file cache (stores last generated outputs) ─────────────────────
# Maps file type → (bytes_or_str, mime, filename)
_file_cache: dict = {}


@app.get("/api/download/<filetype>")
def download_file(filetype: str):
    """
    Serve a cached output file with a proper Content-Disposition header so the
    browser always saves it with the correct filename (not a UUID blob name).

    filetype: "pen_gcode" | "fdm_gcode" | "stl"
    """
    if filetype not in _file_cache:
        return jsonify({"error": "No file cached yet. Run a conversion first."}), 404

    content, mime, filename = _file_cache[filetype]

    if isinstance(content, str):
        # G-code must be pure 7-bit ASCII — replace any stray unicode chars
        safe_ascii = content.encode("ascii", errors="replace").decode("ascii")
        data = safe_ascii.encode("ascii")
        mime = "text/plain; charset=us-ascii"
    else:
        data = content  # already bytes (STL binary)

    return Response(
        data,
        status=200,
        headers={
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Static frontend
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    resp = send_from_directory(REPO_ROOT, "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

@app.get("/<path:filename>")
def static_files(filename):
    resp = send_from_directory(REPO_ROOT, filename)
    # Never cache JS or CSS — always serve fresh
    if filename.endswith((".js", ".css")):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "stl_support": stl_available(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Demo endpoint — run full pipeline on a built-in test image
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/demo")
def demo():
    """
    Run the full pipeline on a built-in generated test image (no upload needed).
    Accepts the same parameter form fields as /api/convert.
    Returns the same JSON response shape.
    """
    try:
        from PIL import ImageDraw
        # Build a synthetic "apple" silhouette
        test_img = Image.new("RGB", (512, 512), "white")
        draw = ImageDraw.Draw(test_img)
        draw.ellipse([80, 60, 430, 450], fill="black")     # body
        draw.rectangle([230, 15, 270, 70], fill="black")   # stem
        draw.ellipse([260, 8, 360, 65], fill="black")      # leaf

        buf = io.BytesIO()
        test_img.save(buf, "PNG")
        buf.seek(0)

        # Replicate form data defaults (override with POST params if provided)
        from flask import request as r
        orig = request
        # Inject the synthetic file as bytes — borrow the convert() handler
        import werkzeug.datastructures as wds
        img_bytes_demo = buf.getvalue()

        # Forward to convert pipeline directly
        # (Re-use all the same logic by calling the internal helpers)
        fget = lambda k, d: float(r.form.get(k, d))
        iget = lambda k, d: int(r.form.get(k, d))
        sget = lambda k, d: r.form.get(k, d)

        bed_width     = fget("bed_width",    220)
        bed_height    = fget("bed_height",   220)
        feed_rate     = fget("feed_rate",    3000)
        travel_rate   = fget("travel_rate",  6000)
        pen_up_z      = fget("pen_up_z",     5)
        pen_down_z    = fget("pen_down_z",   0)
        threshold     = sget("threshold",    "auto")
        canny_low     = iget("canny_low",    50)
        canny_high    = iget("canny_high",   150)
        blur          = iget("blur",         1)
        invert        = bool(iget("invert",  0))
        backend       = sget("backend",      "auto")
        min_area      = fget("min_area",     10)
        max_dim       = iget("max_dim",      512)
        margin        = fget("margin",       5)
        layer_height  = fget("layer_height", 0.2)
        trace_height  = fget("trace_height", 2.0)
        pen_width_mm  = fget("pen_width_mm", 0.5)
        hotend_temp   = fget("hotend_temp",  200)
        bed_temp      = fget("bed_temp",     60)
        gen_stl       = bool(iget("generate_stl", 1))

        orig_pil  = test_img
        orig_b64  = _pil_to_b64(orig_pil)

        binary_img = preprocess_image(img_bytes_demo, max_dimension=max_dim,
                                      blur_radius=blur, threshold_mode=threshold,
                                      canny_low=canny_low, canny_high=canny_high,
                                      invert=invert)
        proc_b64 = _pil_to_b64(binary_img.convert("RGB"))

        raw_polylines = trace_to_svg(binary_img, backend=backend, min_area=min_area)
        if not raw_polylines:
            return jsonify({"error": "No paths found in demo image."}), 422

        scaled    = scale_polylines(raw_polylines, bed_width=bed_width,
                                    bed_height=bed_height, margin=margin)
        optimised = optimize_paths(scaled)

        pen_gcode = generate_gcode(optimised, feed_rate=feed_rate,
                                   travel_rate=travel_rate,
                                   pen_up_z=pen_up_z, pen_down_z=pen_down_z)

        stl_bytes = None
        stl_b64   = None
        if gen_stl and stl_available():
            stl_bytes = polylines_to_stl(optimised, pen_width=pen_width_mm,
                                         trace_height=trace_height, base_thickness=0.0,
                                         bed_width=bed_width, bed_height=bed_height)
            if stl_bytes:
                stl_b64 = base64.b64encode(stl_bytes).decode()

        fdm_gcode = slice_to_fdm_gcode(optimised, layer_height=layer_height,
                                       trace_height=trace_height, pen_width=pen_width_mm,
                                       print_speed=feed_rate, travel_speed=travel_rate,
                                       hotend_temp=hotend_temp, bed_temp=bed_temp)
        sl_stats  = slicer_stats(optimised, layer_height, trace_height)
        path_b64  = _render_toolpath(optimised, bed_width, bed_height)

        total_pts = sum(len(p) for p in optimised)
        stats = {
            "paths":             len(optimised),
            "points":            total_pts,
            "pen_lifts":         max(0, len(optimised) - 1),
            "slicer_layers":     sl_stats["layers"],
            "slicer_travel_mm":  sl_stats["estimated_total_travel_mm"],
            "stl_bytes":         len(stl_bytes) if stl_bytes else 0,
        }

        # ── Cache files for /api/download/* endpoints ─────────────────────────
        _file_cache["pen_gcode"] = (pen_gcode, "text/plain; charset=utf-8", "plotter_pen.gcode")
        _file_cache["fdm_gcode"] = (fdm_gcode, "text/plain; charset=utf-8", "plotter_fdm_sliced.gcode")
        if stl_bytes:
            _file_cache["stl"] = (stl_bytes, "application/octet-stream", "plotter.stl")

        return jsonify({
            "pen_gcode":      pen_gcode,
            "fdm_gcode":      fdm_gcode,
            "stl_b64":        stl_b64,
            "stl_size_bytes": len(stl_bytes) if stl_bytes else 0,
            "preview_orig":   orig_b64,
            "preview_proc":   proc_b64,
            "preview_path":   path_b64,
            "stats":          stats,
        })

    except Exception:
        tb = traceback.format_exc()
        print(tb)
        return jsonify({"error": "Demo pipeline failed", "detail": tb}), 500




# ─────────────────────────────────────────────────────────────────────────────
# Main conversion endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/convert")
def convert():
    """
    Full pipeline:  Image → SVG polylines → Pen G-code + STL + FDM G-code

    Form fields
    -----------
    file / url           : image source
    bed_width            : mm  (default 220)
    bed_height           : mm  (default 220)
    feed_rate            : mm/min drawing speed  (default 3000)
    travel_rate          : mm/min travel speed   (default 6000)
    pen_up_z             : mm  (default 5)
    pen_down_z           : mm  (default 0)
    threshold            : auto | canny | binary  (default auto)
    canny_low/high       : Canny thresholds  (default 50/150)
    blur                 : Gaussian blur radius  (default 1)
    invert               : 0|1  (default 0)
    backend              : auto | potrace | opencv  (default auto)
    min_area             : min contour area px²  (default 10)
    max_dim              : max image dimension  (default 1024)
    margin               : bed margin mm  (default 5)
    layer_height         : FDM layer height mm  (default 0.2)
    trace_height         : FDM extrusion height mm  (default 2.0)
    pen_width_mm         : FDM line width mm  (default 0.5)
    hotend_temp          : °C  (default 200)
    bed_temp             : °C  (default 60)
    generate_stl         : 0|1 — include STL in response  (default 1)

    Response JSON
    -------------
    {
      "pen_gcode":      str,   # Pen-plotter G-code (no E axis)
      "fdm_gcode":      str,   # FDM sliced G-code  (with E axis)
      "stl_b64":        str,   # Base64-encoded binary STL (or null)
      "stl_size_bytes": int,
      "preview_orig":   str,   # base64 PNG
      "preview_proc":   str,
      "preview_path":   str,
      "stats": {
        "paths", "points", "pen_lifts",
        "slicer_layers", "slicer_travel_mm"
      }
    }
    """
    try:
        # ── Parse params ──────────────────────────────────────────────────────
        fget = lambda k, d: float(request.form.get(k, d))
        iget = lambda k, d: int(request.form.get(k, d))
        sget = lambda k, d: request.form.get(k, d)

        bed_width     = fget("bed_width",     220)
        bed_height    = fget("bed_height",    220)
        feed_rate     = fget("feed_rate",     3000)
        travel_rate   = fget("travel_rate",   6000)
        pen_up_z      = fget("pen_up_z",      5)
        pen_down_z    = fget("pen_down_z",    0)
        threshold     = sget("threshold",     "auto")
        canny_low     = iget("canny_low",     50)
        canny_high    = iget("canny_high",    150)
        blur          = iget("blur",          1)
        invert        = bool(iget("invert",   0))
        backend       = sget("backend",       "auto")
        min_area      = fget("min_area",      10)
        max_dim       = iget("max_dim",       1024)
        margin        = fget("margin",        5)
        layer_height  = fget("layer_height",  0.2)
        trace_height  = fget("trace_height",  2.0)
        pen_width_mm  = fget("pen_width_mm",  0.5)
        hotend_temp   = fget("hotend_temp",   200)
        bed_temp      = fget("bed_temp",      60)
        gen_stl       = bool(iget("generate_stl", 1))

        # ── Load image ────────────────────────────────────────────────────────
        source = _get_image_source(request)
        img_bytes: bytes = None  # always work with raw bytes downstream

        if isinstance(source, bytes):
            img_bytes = source
            orig_pil  = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        else:
            # source is a URL string
            try:
                import requests as req_lib
                resp = req_lib.get(
                    source, timeout=20,
                    headers=_BROWSER_HEADERS,
                    allow_redirects=True,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code >= 400:
                    return jsonify({
                        "error": (
                            f"URL returned HTTP {resp.status_code}. "
                            "The server blocked the request — please download "
                            "the image and upload it directly."
                        )
                    }), 422
                if "html" in ct.lower():
                    return jsonify({
                        "error": (
                            "The URL returned an HTML page, not an image. "
                            "Use a direct image URL (ending in .jpg, .png, etc.)."
                        )
                    }), 422
                img_bytes = resp.content
                orig_pil  = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            except Exception as fetch_err:
                return jsonify({
                    "error": (
                        f"Could not fetch image from URL: {fetch_err}. "
                        "Please upload the image file directly instead."
                    )
                }), 422

        orig_b64 = _pil_to_b64(orig_pil)

        # ── Step 1 Preprocess — always pass bytes, never the URL ──────────────
        binary_img = preprocess_image(
            img_bytes,
            max_dimension=max_dim,
            blur_radius=blur,
            threshold_mode=threshold,
            canny_low=canny_low,
            canny_high=canny_high,
            invert=invert,
        )
        proc_b64 = _pil_to_b64(binary_img.convert("RGB"))

        # ── Step 2 Trace (SVG) ────────────────────────────────────────────────
        raw_polylines = trace_to_svg(binary_img, backend=backend, min_area=min_area)

        if not raw_polylines:
            return jsonify({"error": "No paths found. Try different threshold settings."}), 422

        # ── Step 3 Scale to bed ───────────────────────────────────────────────
        scaled = scale_polylines(
            raw_polylines, bed_width=bed_width, bed_height=bed_height, margin=margin
        )

        # ── Step 4 Optimise paths ─────────────────────────────────────────────
        optimised = optimize_paths(scaled)

        # ── Step 5 Pen-plotter G-code ─────────────────────────────────────────
        pen_gcode = generate_gcode(
            optimised,
            feed_rate=feed_rate,
            travel_rate=travel_rate,
            pen_up_z=pen_up_z,
            pen_down_z=pen_down_z,
        )

        # ── Step 6 STL mesh ───────────────────────────────────────────────────
        stl_bytes = None
        stl_b64   = None
        if gen_stl and stl_available():
            stl_bytes = polylines_to_stl(
                optimised,
                pen_width=pen_width_mm,
                trace_height=trace_height,
                base_thickness=0.0,
                bed_width=bed_width,
                bed_height=bed_height,
            )
            if stl_bytes:
                stl_b64 = base64.b64encode(stl_bytes).decode()

        # ── Step 7 FDM Slicing ────────────────────────────────────────────────
        fdm_gcode = slice_to_fdm_gcode(
            optimised,
            layer_height=layer_height,
            trace_height=trace_height,
            pen_width=pen_width_mm,
            print_speed=feed_rate,
            travel_speed=travel_rate,
            hotend_temp=hotend_temp,
            bed_temp=bed_temp,
        )
        sl_stats = slicer_stats(optimised, layer_height, trace_height)

        # ── Toolpath preview ──────────────────────────────────────────────────
        path_b64 = _render_toolpath(optimised, bed_width, bed_height)

        # ── Stats ─────────────────────────────────────────────────────────────
        total_pts = sum(len(p) for p in optimised)
        stats = {
            "paths":              len(optimised),
            "points":             total_pts,
            "pen_lifts":          max(0, len(optimised) - 1),
            "slicer_layers":      sl_stats["layers"],
            "slicer_travel_mm":   sl_stats["estimated_total_travel_mm"],
            "stl_bytes":          len(stl_bytes) if stl_bytes else 0,
        }

        # ── Cache files for /api/download/* endpoints ─────────────────────────
        _file_cache["pen_gcode"] = (pen_gcode, "text/plain; charset=utf-8", "plotter_pen.gcode")
        _file_cache["fdm_gcode"] = (fdm_gcode, "text/plain; charset=utf-8", "plotter_fdm_sliced.gcode")
        if stl_bytes:
            _file_cache["stl"] = (stl_bytes, "application/octet-stream", "plotter.stl")

        return jsonify({
            "pen_gcode":      pen_gcode,
            "fdm_gcode":      fdm_gcode,
            "stl_b64":        stl_b64,
            "stl_size_bytes": len(stl_bytes) if stl_bytes else 0,
            "preview_orig":   orig_b64,
            "preview_proc":   proc_b64,
            "preview_path":   path_b64,
            "stats":          stats,
        })

    except Exception:
        tb = traceback.format_exc()
        print(tb)
        return jsonify({"error": "Internal server error", "detail": tb}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_image_source(req):
    if "file" in req.files and req.files["file"].filename:
        f = req.files["file"]
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")
        return f.read()
    url = req.form.get("url", "").strip()
    if url:
        return url
    raise ValueError("No image file or URL provided")


def _pil_to_b64(img: Image.Image, max_side: int = 800) -> str:
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _render_toolpath(polylines, bed_w: float, bed_h: float,
                     canvas_px: int = 600) -> str:
    scale = canvas_px / max(bed_w, bed_h)
    img = np.ones((canvas_px, canvas_px, 3), dtype=np.uint8) * 245

    prev_end = None
    for poly in polylines:
        if len(poly) < 2:
            continue
        start = poly[0]
        if prev_end is not None:
            p1 = _mm_to_px(prev_end, scale, canvas_px, bed_h)
            p2 = _mm_to_px(start,    scale, canvas_px, bed_h)
            cv2.line(img, p1, p2, (210, 210, 210), 1, cv2.LINE_AA)
        pts_px = [_mm_to_px(pt, scale, canvas_px, bed_h) for pt in poly]
        for i in range(1, len(pts_px)):
            cv2.line(img, pts_px[i-1], pts_px[i], (30, 100, 200), 1, cv2.LINE_AA)
        prev_end = poly[-1]

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    return _pil_to_b64(pil, max_side=canvas_px)


def _mm_to_px(pt, scale, canvas_px, bed_h):
    x = max(0, min(canvas_px - 1, int(pt[0] * scale)))
    y = max(0, min(canvas_px - 1, int((bed_h - pt[1]) * scale)))
    return (x, y)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
