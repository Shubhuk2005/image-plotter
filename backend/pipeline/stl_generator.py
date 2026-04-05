"""
stl_generator.py
----------------
Converts optimised polylines (mm coordinates) into a 3D STL mesh.

Each pen path is "extruded" into a thin rectangular solid — representing
the raised ink trace if the drawing were physically 3D printed.

Dependencies: trimesh, shapely
"""

import io
import math
from typing import List, Tuple, Optional

Point = Tuple[float, float]
Polyline = List[Point]

try:
    import trimesh
    import numpy as np
    from shapely.geometry import LineString, MultiPolygon, Polygon
    from shapely.ops import unary_union
    _HAS_MESH = True
except ImportError:
    _HAS_MESH = False


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def polylines_to_stl(
    polylines: List[Polyline],
    pen_width: float = 0.5,           # mm — width of each extruded trace
    trace_height: float = 2.0,        # mm — extrusion height of traces
    base_thickness: float = 0.0,      # mm — flat base plate (0 = none)
    bed_width: float = 220.0,
    bed_height: float = 220.0,
) -> Optional[bytes]:
    """
    Convert 2D polylines into a 3D STL mesh (binary format).

    Returns STL bytes, or None if mesh libraries are unavailable.
    """
    if not _HAS_MESH:
        return None
    if not polylines:
        return None

    print(f"[stl_generator] Building STL from {len(polylines)} paths ...")

    # ── Buffer each polyline into a 2D filled polygon ─────────────────────────
    shapes = []
    for poly in polylines:
        if len(poly) < 2:
            continue
        try:
            ls = LineString(poly)
            buffered = ls.buffer(
                pen_width / 2,
                cap_style=2,       # square caps
                join_style=2,      # mitre joins
                mitre_limit=3.0,
                resolution=2,      # keep low for speed
            )
            if buffered.is_valid and not buffered.is_empty and buffered.area > 1e-6:
                shapes.append(buffered)
        except Exception as e:
            print(f"[stl_generator] Buffer error: {e}")
            continue

    if not shapes:
        print("[stl_generator] No valid shapes to extrude")
        return None

    # ── Union overlapping shapes ──────────────────────────────────────────────
    try:
        combined = unary_union(shapes)
    except Exception as e:
        print(f"[stl_generator] Union error: {e}")
        return None

    # ── Collect individual polygons ───────────────────────────────────────────
    if combined.geom_type == "MultiPolygon":
        geoms = list(combined.geoms)
    elif combined.geom_type == "Polygon":
        geoms = [combined]
    elif combined.geom_type == "GeometryCollection":
        geoms = [g for g in combined.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
    else:
        print(f"[stl_generator] Unexpected geometry type: {combined.geom_type}")
        return None

    meshes = []

    # ── Optional flat base plate ──────────────────────────────────────────────
    if base_thickness > 0:
        base_poly = Polygon([
            (0, 0), (bed_width, 0),
            (bed_width, bed_height), (0, bed_height),
        ])
        try:
            base_mesh = trimesh.creation.extrude_polygon(base_poly, height=base_thickness)
            meshes.append(base_mesh)
        except Exception as e:
            print(f"[stl_generator] Base plate error: {e}")

    # ── Extrude each trace polygon ────────────────────────────────────────────
    base_z = base_thickness
    success_count = 0

    for geom in geoms:
        if geom.geom_type == "MultiPolygon":
            sub_geoms = list(geom.geoms)
        else:
            sub_geoms = [geom]

        for g in sub_geoms:
            if not (g.is_valid and not g.is_empty and g.area > 1e-6):
                continue
            try:
                m = trimesh.creation.extrude_polygon(g, height=trace_height)
                if base_z > 0:
                    m.apply_translation([0, 0, base_z])
                meshes.append(m)
                success_count += 1
            except Exception as e:
                print(f"[stl_generator] Extrude error: {e}")
                continue

    print(f"[stl_generator] Extruded {success_count} polygons")

    if not meshes:
        return None

    # ── Concatenate and export ────────────────────────────────────────────────
    try:
        final_mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]

        # Export as binary STL (compact)
        stl_bytes = final_mesh.export(file_type="stl")
        if isinstance(stl_bytes, str):
            stl_bytes = stl_bytes.encode("utf-8")

        print(f"[stl_generator] STL generated: {len(stl_bytes):,} bytes")
        return stl_bytes

    except Exception as e:
        print(f"[stl_generator] Export error: {e}")
        return None


def stl_available() -> bool:
    """Return True if trimesh and shapely are importable."""
    return _HAS_MESH
