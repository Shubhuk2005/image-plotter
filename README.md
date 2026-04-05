# Image Plotter: Image-to-Gcode Converter

A modern, full-stack web application that converts images into optimized G-code for 2D Pen Plotters and 3D Printers (FDM machines).

## Features

- **End-to-End Pipeline**: Image \u2192 Preprocess \u2192 SVG Trace \u2192 Polyline Optimization \u2192 Slicing \u2192 G-code & STL.
- **Hardware Agnostic**: 
  - Generates robust **Pen Plotter G-code** (with specific Z-up / Z-down movements, no extrusion).
  - Generates layered **FDM Sliced G-code** (directly from vector paths with accurate E-axis extrusion) for 3D printers simulating a plotter.
  - Generates **STL Meshes** to drop into standard slicers like Cura or PrusaSlicer.
- **Dynamic Frontend UI**: A dark-mode, glassmorphism interface with real-time feedback and animated upload states. No page reloads needed.
- **Format Agnostic Input**: Upload direct image files or paste remote image URLs.
- **Resilient File Handling**: Server-side conversion caches files to enforce pure 7-bit ASCII G-code downloads with correct filenames—bypassing typical browser Blob URL UUID issues.

## Tech Stack

- **Backend**: Python (Flask), OpenCV, Pillow, Trimesh, Shapely.
- **Frontend**: HTML5, CSS3, Vanilla ES Modules JavaScript.

## Local Installation & Development

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/image-plotter.git
cd image-plotter
```

### 2. Create a Virtual Environment (Optional but recommended)
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On MacOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
python backend/app.py
```
*The app will run at `http://localhost:5000`*

## Deployment

This app is ready to deploy to platforms like **Render**, **Railway**, **Fly.io**, or any Docker-compatible hosting environment. 

### Docker Deployment
A `Dockerfile` is included. It provisions the environment, installs system dependencies like `potrace` for ultra-smooth tracing, and runs the app securely via `gunicorn`:

```bash
docker build -t image-plotter .
docker run -p 5000:5000 image-plotter
```

### Hosting Environments (Render/Railway)
1. Link your GitHub repo to your hosting provider.
2. The platform should auto-detect the `Dockerfile`.
3. Set the build command (if not using Docker) to `pip install -r requirements.txt`.
4. Set the Start Command (if not using Docker) to `gunicorn --bind 0.0.0.0:$PORT backend.app:app`.

## Troubleshooting

- **Large Image Timeouts:** High-resolution images may take significant time to trace and convert. If deploying on platforms with strict 30-second HTTP timeouts (like Heroku), you may need to increase the timeout via `--timeout 120` in the Gunicorn start command (already applied in the Dockerfile).
- **STL Generation Errors:** If STL downloads are empty or error out, ensure `mapbox-earcut` is installed. It is required by `trimesh` to perform polygon triangulation on 2D layouts.

## License
MIT
