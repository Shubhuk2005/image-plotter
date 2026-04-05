"""
test_full_pipeline.py
---------------------
Complete end-to-end pipeline test:
  Image -> Preprocess -> Trace -> Optimize -> Pen G-code -> STL -> FDM Slice
Saves all output files to the user's Downloads folder.
"""
import sys, io, os
sys.path.insert(0, '.')

from PIL import Image, ImageDraw
from pipeline.preprocessor import preprocess_image
from pipeline.tracer import trace_to_svg
from pipeline.optimizer import optimize_paths
from pipeline.gcode_generator import generate_gcode
from pipeline.stl_generator import polylines_to_stl, stl_available
from pipeline.slicer import slice_to_fdm_gcode, slicer_stats
from utils.svg_utils import scale_polylines

# ── Create test image (apple-like silhouette) ──────────────────────────────────
img = Image.new('RGB', (512, 512), 'white')
draw = ImageDraw.Draw(img)
draw.ellipse([80, 60, 430, 450], fill='black')   # apple body
draw.rectangle([230, 15, 270, 70], fill='black') # stem
draw.ellipse([260, 8, 360, 65], fill='black')    # leaf
buf = io.BytesIO()
img.save(buf, 'PNG')
src = buf.getvalue()

print("Step 1: Preprocess...")
binary = preprocess_image(src, max_dimension=512, blur_radius=1, threshold_mode='auto')

print("Step 2: Trace (OpenCV)...")
polylines = trace_to_svg(binary, backend='opencv', min_area=20)

print("Step 3: Scale to 220x220mm bed...")
scaled = scale_polylines(polylines, bed_width=220, bed_height=220, margin=5)

print("Step 4: Optimize paths (nearest-neighbour)...")
optimized = optimize_paths(scaled)

print("Step 5: Generate pen G-code (Z-axis pen, no E-axis)...")
pen_gcode = generate_gcode(optimized, feed_rate=3000, pen_up_z=5.0, pen_down_z=0.0)

print("Step 6: FDM slice (layer-by-layer extrusion)...")
fdm_gcode = slice_to_fdm_gcode(
    optimized, layer_height=0.2, trace_height=2.0,
    pen_width=0.5, hotend_temp=200.0, bed_temp=60.0,
    print_speed=1800, travel_speed=6000
)
sl = slicer_stats(optimized, 0.2, 2.0)

print("Step 7: Generate STL mesh...")
stl_bytes = polylines_to_stl(optimized, pen_width=0.5, trace_height=2.0) if stl_available() else None

# ── Print results ──────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("PIPELINE RESULTS")
print("=" * 50)
print(f"  Paths     : {len(optimized)}")
print(f"  Points    : {sum(len(p) for p in optimized)}")
print(f"  Pen lifts : {max(0, len(optimized) - 1)}")
print(f"  Pen G-code: {len(pen_gcode.splitlines())} lines")
print(f"  FDM G-code: {len(fdm_gcode.splitlines())} lines  |  {sl['layers']} layers")
if stl_bytes:
    print(f"  STL       : {len(stl_bytes):,} bytes  ({len(stl_bytes)/1024:.1f} KB)")
else:
    print(f"  STL       : FAILED (install mapbox-earcut)")
print()

# ── Save to Downloads ──────────────────────────────────────────────────────────
downloads = os.path.expanduser('~/Downloads')
pen_path = os.path.join(downloads, 'plotter_pen.gcode')
fdm_path = os.path.join(downloads, 'plotter_fdm_sliced.gcode')
stl_path = os.path.join(downloads, 'plotter.stl')

with open(pen_path, 'w') as f:
    f.write(pen_gcode)
print(f"  Saved: {pen_path}")

with open(fdm_path, 'w') as f:
    f.write(fdm_gcode)
print(f"  Saved: {fdm_path}")

if stl_bytes:
    with open(stl_path, 'wb') as f:
        f.write(stl_bytes)
    print(f"  Saved: {stl_path}")
else:
    print(f"  STL skipped (trimesh triangulation not available)")

print()
print("=== First 20 lines of pen G-code ===")
for line in pen_gcode.splitlines()[:20]:
    print(f"  {line}")

print()
print("SUCCESS — Image → SVG → G-code → STL → FDM Slice pipeline complete!")
