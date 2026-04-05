# Pipeline package — full image-to-gcode pipeline
from .preprocessor import preprocess_image
from .tracer import trace_to_svg
from .optimizer import optimize_paths
from .gcode_generator import generate_gcode
from .stl_generator import polylines_to_stl, stl_available
from .slicer import slice_to_fdm_gcode, slicer_stats

__all__ = [
    "preprocess_image",
    "trace_to_svg",
    "optimize_paths",
    "generate_gcode",
    "polylines_to_stl",
    "stl_available",
    "slice_to_fdm_gcode",
    "slicer_stats",
]
