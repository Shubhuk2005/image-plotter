"""
test_api_upload.py — Tests the Flask API by uploading a generated test image file
and verifies pen G-code, FDM G-code, and STL are returned.
Also auto-saves files to Downloads.
"""
import io, os, requests
from PIL import Image, ImageDraw

# Make test image
img = Image.new('RGB', (512, 512), 'white')
draw = ImageDraw.Draw(img)
draw.ellipse([80, 60, 430, 450], fill='black')
draw.rectangle([230, 15, 270, 70], fill='black')
draw.ellipse([260, 8, 360, 65], fill='black')
buf = io.BytesIO()
img.save(buf, 'PNG')
buf.seek(0)

data = {
    'bed_width': '220', 'bed_height': '220',
    'feed_rate': '3000', 'travel_rate': '6000',
    'pen_up_z': '5', 'pen_down_z': '0',
    'threshold': 'auto', 'blur': '1', 'invert': '0',
    'backend': 'opencv', 'min_area': '10',
    'max_dim': '512', 'margin': '5',
    'layer_height': '0.2', 'trace_height': '2.0',
    'pen_width_mm': '0.5', 'hotend_temp': '200', 'bed_temp': '60',
    'generate_stl': '1',
}

print("POSTing to http://localhost:5000/api/convert ...")
resp = requests.post(
    'http://localhost:5000/api/convert',
    files={'file': ('test_apple.png', buf, 'image/png')},
    data=data,
    timeout=120,
)
print(f"HTTP Status: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()
    stats = result['stats']
    pen_gcode = result['pen_gcode']
    fdm_gcode = result['fdm_gcode']
    stl_b64 = result.get('stl_b64')

    print()
    print("=== STATS ===")
    print(f"  Paths       : {stats['paths']}")
    print(f"  Points      : {stats['points']}")
    print(f"  Pen lifts   : {stats['pen_lifts']}")
    print(f"  FDM layers  : {stats['slicer_layers']}")
    print(f"  STL bytes   : {stats.get('stl_bytes', 0)}")
    print(f"  Total travel: {stats['slicer_travel_mm']} mm")
    print()
    print(f"Pen G-code:  {len(pen_gcode.splitlines())} lines")
    print(f"FDM G-code:  {len(fdm_gcode.splitlines())} lines")
    print(f"STL b64:     {'YES (' + str(len(stl_b64)) + ' chars)' if stl_b64 else 'NO'}")

    # Save to Downloads
    import base64
    dl = os.path.expanduser('~/Downloads')
    with open(os.path.join(dl, 'plotter_pen.gcode'), 'w') as f:
        f.write(pen_gcode)
    with open(os.path.join(dl, 'plotter_fdm_sliced.gcode'), 'w') as f:
        f.write(fdm_gcode)
    if stl_b64:
        stl_bytes = base64.b64decode(stl_b64)
        with open(os.path.join(dl, 'plotter.stl'), 'wb') as f:
            f.write(stl_bytes)
        print(f"STL file    : plotter.stl ({len(stl_bytes):,} bytes)")

    print()
    print("All files saved to Downloads folder!")
    print()
    print("=== Pen G-code (first 25 lines) ===")
    for line in pen_gcode.splitlines()[:25]:
        print(f"  {line}")
    print()
    print("=== FDM G-code (first 15 lines) ===")
    for line in fdm_gcode.splitlines()[:15]:
        print(f"  {line}")
    print()
    print("SUCCESS - Full API pipeline test passed!")

else:
    print(f"ERROR: {resp.text[:2000]}")
