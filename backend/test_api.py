"""
test_api.py — Tests the full /api/convert pipeline via HTTP
"""
import io, sys
sys.path.insert(0, '.')
import requests
from PIL import Image, ImageDraw

# ── Create synthetic apple-like test image ────────────────────────────────────
img = Image.new("RGB", (512, 512), "white")
draw = ImageDraw.Draw(img)
draw.ellipse([100, 60, 420, 420], fill="black")   # apple body
draw.rectangle([240, 20, 270, 70], fill="black")  # stem
draw.ellipse([260, 10, 340, 60], fill="black")    # leaf

buf = io.BytesIO()
img.save(buf, "PNG")
buf.seek(0)

# ── POST to the conversion API ────────────────────────────────────────────────
print("Posting to http://localhost:5000/api/convert ...")
resp = requests.post(
    "http://localhost:5000/api/convert",
    files={"file": ("apple_test.png", buf, "image/png")},
    data={
        "bed_width": "220",
        "bed_height": "220",
        "feed_rate": "3000",
        "travel_rate": "6000",
        "pen_up_z": "5",
        "pen_down_z": "0",
        "threshold": "auto",
        "blur": "1",
        "invert": "0",
        "backend": "opencv",
        "min_area": "10",
        "max_dim": "512",
        "margin": "5",
    },
    timeout=60,
)

print(f"HTTP Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    stats     = data["stats"]
    pen_gcode = data["pen_gcode"]
    fdm_gcode = data["fdm_gcode"]
    stl_b64   = data.get("stl_b64")

    pen_lines = pen_gcode.split("\n")
    fdm_lines = fdm_gcode.split("\n")

    print(f"\nSTATS")
    print(f"  Paths         : {stats['paths']}")
    print(f"  Points        : {stats['points']}")
    print(f"  Pen G-code L  : {len(pen_lines)}")
    print(f"  FDM layers    : {stats.get('slicer_layers','?')}")
    print(f"  FDM G-code L  : {len(fdm_lines)}")
    print(f"  STL b64 size  : {len(stl_b64) if stl_b64 else 0} chars")
    print(f"  STL bytes     : {data.get('stl_size_bytes', 0):,}")
    print(f"  Preview orig  : {len(data.get('preview_orig',''))} chars (b64)")

    print("\n=== First 20 lines of Pen G-code ===")
    for ln in pen_lines[:20]: print(ln)

    print("\n=== First 20 lines of FDM G-code ===")
    for ln in fdm_lines[:20]: print(ln)
    print("...")
    for ln in fdm_lines[-5:]: print(ln)

    # Save both G-code files
    pen_out = r"C:\Users\Shubh\Desktop\image plotter\apple_pen.gcode"
    fdm_out = r"C:\Users\Shubh\Desktop\image plotter\apple_fdm.gcode"
    with open(pen_out, "w") as f: f.write(pen_gcode)
    with open(fdm_out, "w") as f: f.write(fdm_gcode)
    print(f"\nPen G-code saved to: {pen_out}")
    print(f"FDM G-code saved to: {fdm_out}")

    if stl_b64:
        import base64
        stl_bytes = base64.b64decode(stl_b64)
        stl_out = r"C:\Users\Shubh\Desktop\image plotter\apple.stl"
        with open(stl_out, "wb") as f: f.write(stl_bytes)
        print(f"STL saved to: {stl_out}")

    print("\n✓ FULL PIPELINE COMPLETE")
else:
    print("ERROR:", resp.text[:2000])
