/**
 * main.js
 * -------
 * Full pipeline controller:
 *   Image → Preprocess → SVG Trace → Pen G-code → STL → FDM Slice → Auto-download
 */

import { convertImage, checkHealth, runDemo } from "./api.js";
import { initTabs, showPreviews, showStats, renderGcode, animateToolpath } from "./preview.js";

// ── State ──────────────────────────────────────────────────────────────────────
let selectedFile = null;
let _result      = null;   // last successful conversion result

// Pipeline stage IDs in order
const PIPE_STAGES = [
  "ps-input", "ps-preprocess", "ps-trace",
  "ps-gcode", "ps-stl", "ps-slice", "ps-done"
];

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  _initUploadZone();
  _initRangeSliders();
  _initCollapsibles();
  _initConvertBtn();
  _initDemoBtn();
  _initThresholdToggle();
  _pingBackend();
});

// ── Backend ping ───────────────────────────────────────────────────────────────
async function _pingBackend() {
  const ok = await checkHealth();
  const badge = document.getElementById("backend-badge");
  if (!badge) return;
  if (ok) {
    badge.textContent   = "⬤  Backend online";
    badge.style.color   = "var(--success)";
    badge.style.borderColor = "var(--success)";
  } else {
    badge.textContent   = "⬤  Backend offline";
    badge.style.color   = "var(--error)";
    badge.style.borderColor = "var(--error)";
  }
}

// ── Upload zone ────────────────────────────────────────────────────────────────
function _initUploadZone() {
  const zone   = document.getElementById("upload-zone");
  const fileIn = document.getElementById("file-input");

  zone.addEventListener("click",     () => fileIn.click());
  fileIn.addEventListener("change",  () => { if (fileIn.files[0]) _handleFile(fileIn.files[0]); });
  zone.addEventListener("dragover",  (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag-over"));
  zone.addEventListener("drop",      (e) => {
    e.preventDefault(); zone.classList.remove("drag-over");
    const f = e.dataTransfer.files[0];
    if (f) _handleFile(f);
  });
  document.addEventListener("paste", (e) => {
    for (const item of (e.clipboardData?.items ?? [])) {
      if (item.type.startsWith("image/")) { _handleFile(item.getAsFile()); break; }
    }
  });
}

function _handleFile(file) {
  const allowed = ["image/png","image/jpeg","image/gif","image/bmp","image/webp","image/tiff"];
  if (!allowed.includes(file.type)) { _toast("Unsupported file type: " + file.type, "error"); return; }

  selectedFile = file;
  document.getElementById("url-input").value = "";

  const reader = new FileReader();
  reader.onload = (e) => {
    const zone = document.getElementById("upload-zone");
    zone.innerHTML = `
      <img src="${e.target.result}" alt="Selected"
           style="max-height:150px;border-radius:8px;object-fit:contain;max-width:100%"/>
      <p style="margin-top:10px;font-size:0.8rem;color:var(--text-muted)">
        ${file.name} · ${_fmtBytes(file.size)}
        <span style="color:var(--accent-light)">— Click to change</span>
      </p>`;
    zone.onclick = () => document.getElementById("file-input").click();
  };
  reader.readAsDataURL(file);

  // Mark input stage done
  _stageComplete("ps-input");
  _toast(`Loaded: ${file.name}`, "info");
}

// ── Range sliders ──────────────────────────────────────────────────────────────
function _initRangeSliders() {
  document.querySelectorAll("input[type=range]").forEach((r) => {
    const el = document.getElementById(r.id + "-val");
    if (el) el.textContent = r.value;
    r.addEventListener("input", () => { if (el) el.textContent = r.value; });
  });
}

// ── Collapsibles ───────────────────────────────────────────────────────────────
function _initCollapsibles() {
  document.querySelectorAll(".collapsible-header").forEach((hdr) => {
    const body = document.getElementById(hdr.dataset.target);
    if (!body) return;
    body.style.maxHeight = "0px";
    hdr.addEventListener("click", () => {
      const open = hdr.classList.toggle("open");
      body.style.maxHeight = open ? body.scrollHeight + "px" : "0px";
    });
  });
}

// ── Threshold mode toggle ──────────────────────────────────────────────────────
function _initThresholdToggle() {
  document.getElementById("threshold-mode")?.addEventListener("change", (e) => {
    const canny = document.getElementById("canny-options");
    if (canny) canny.style.display = e.target.value === "canny" ? "grid" : "none";
  });
}

// ── Convert button ─────────────────────────────────────────────────────────────
function _initConvertBtn() {
  document.getElementById("convert-btn")?.addEventListener("click", _runPipeline);
}

// ── Demo button ────────────────────────────────────────────────────────────────
function _initDemoBtn() {
  document.getElementById("demo-btn")?.addEventListener("click", async () => {
    _resetPipeline();
    _showLoader(true, "Running demo pipeline…");
    document.getElementById("demo-btn").disabled = true;
    try {
      const settings = _collectSettings();
      const steps = [
        { stage: "ps-input",      msg: "Loading demo image…",    sub: "Built-in test shape" },
        { stage: "ps-preprocess", msg: "Preprocessing…",         sub: "Resize · Blur · Binarise" },
        { stage: "ps-trace",      msg: "Tracing SVG paths…",     sub: "OpenCV contours" },
        { stage: "ps-gcode",      msg: "Pen G-code…",            sub: "Z-axis pen control" },
        { stage: "ps-stl",        msg: "Building STL mesh…",     sub: "Extruding polylines" },
        { stage: "ps-slice",      msg: "FDM slicing…",           sub: "Layer-by-layer" },
        { stage: "ps-done",       msg: "Finalising…",            sub: "Preparing downloads" },
      ];
      let stepIdx = 0;
      const stepTimer = setInterval(() => {
        if (stepIdx < steps.length) { _setStageActive(steps[stepIdx].stage); _updateLoader(steps[stepIdx].msg, steps[stepIdx].sub); stepIdx++; }
      }, 700);

      const result = await runDemo(settings);
      clearInterval(stepTimer);
      PIPE_STAGES.forEach((id) => _stageComplete(id));
      _result = result;
      _processResult(result);
      _toast("Demo complete — download files below!", "success");
    } catch (err) {
      _toast(err.message, "error");
      _resetPipeline();
    } finally {
      _showLoader(false);
      document.getElementById("demo-btn").disabled = false;
    }
  });
}

async function _runPipeline() {
  const url = document.getElementById("url-input").value.trim();
  if (!selectedFile && !url) {
    _toast("Please upload an image or provide a URL", "error");
    return;
  }

  const settings = _collectSettings();

  _resetPipeline();
  _showLoader(true, "Starting pipeline…");
  _setConvertBtn(true);

  try {
    // Step labels for the loader
    const steps = [
      { stage: "ps-input",     msg: "Loading image…",         sub: "Reading source…" },
      { stage: "ps-preprocess",msg: "Preprocessing…",         sub: "Resize · Blur · Binarise" },
      { stage: "ps-trace",     msg: "Tracing SVG paths…",     sub: "Potrace / OpenCV contours" },
      { stage: "ps-gcode",     msg: "Generating pen G-code…", sub: "Z-axis pen control" },
      { stage: "ps-stl",       msg: "Building STL mesh…",     sub: "Extruding polylines → 3D" },
      { stage: "ps-slice",     msg: "FDM slicing…",           sub: "Layer-by-layer extrusion" },
      { stage: "ps-done",      msg: "Finalising…",            sub: "Preparing downloads" },
    ];

    // Animate loader steps while waiting
    let stepIdx   = 0;
    const stepTimer = setInterval(() => {
      if (stepIdx < steps.length) {
        const s = steps[stepIdx];
        _setStageActive(s.stage);
        _updateLoader(s.msg, s.sub);
        stepIdx++;
      }
    }, 900);

    const result = await convertImage({
      file: selectedFile,
      url:  selectedFile ? null : url,
      settings,
      onProgress: (pct) => _updateLoader(`Uploading… ${pct}%`, ""),
    });

    clearInterval(stepTimer);

    // All stages complete
    PIPE_STAGES.forEach((id) => _stageComplete(id));

    _result = result;
    _processResult(result);

  } catch (err) {
    _toast(err.message, "error");
    console.error(err);
    _resetPipeline();
  } finally {
    _showLoader(false);
    _setConvertBtn(false);
  }
}

// ── Shared result processor ────────────────────────────────────────────────────
function _processResult(result) {
  showPreviews({
    preview_orig: result.preview_orig,
    preview_proc: result.preview_proc,
    preview_path: result.preview_path,
  });
  showStats({
    paths:   result.stats.paths,
    points:  result.stats.points,
    layers:  result.stats.slicer_layers,
    travel:  result.stats.slicer_travel_mm,
    stlSize: result.stl_size_bytes,
  });
  renderGcode(result.pen_gcode, "gcode-view-pen", "pen");
  renderGcode(result.fdm_gcode, "gcode-view-fdm", "fdm");
  animateToolpath(result.pen_gcode);

  // ── Wire download buttons to /api/download/* server endpoints ──────────────
  // The server sets Content-Disposition: attachment; filename="xxx.gcode"
  // so the browser always saves with the correct filename (no UUID blob names).
  _setupServerDownload("dl-pen-btn", "dl-meta-pen", "pen_gcode",
                       "plotter_pen.gcode", _fmtBytes(result.pen_gcode.length), "dl-pen");
  _setupServerDownload("dl-fdm-btn", "dl-meta-fdm", "fdm_gcode",
                       "plotter_fdm_sliced.gcode", _fmtBytes(result.fdm_gcode.length), "dl-fdm");
  if (result.stl_b64) {
    _setupServerDownload("dl-stl-btn", "dl-meta-stl", "stl",
                         "plotter.stl", _fmtBytes(result.stl_size_bytes), "dl-stl");
  }

  _toast(`✓ Pipeline complete — ${result.stats.paths} paths · ${result.stats.slicer_layers} FDM layers`, "success");
  document.querySelector("[data-tab='tab-pen-gcode']")?.click();
}

// ── Settings collection ────────────────────────────────────────────────────────
function _collectSettings() {
  const v = (id, def = "") => document.getElementById(id)?.value ?? def;
  return {
    bed_width:     v("bed-width"),
    bed_height:    v("bed-height"),
    feed_rate:     v("feed-rate"),
    travel_rate:   v("travel-rate"),
    pen_up_z:      v("pen-up-z"),
    pen_down_z:    v("pen-down-z"),
    threshold:     v("threshold-mode"),
    canny_low:     v("canny-low"),
    canny_high:    v("canny-high"),
    blur:          v("blur-radius"),
    invert:        document.getElementById("invert-img")?.checked ? 1 : 0,
    backend:       v("backend-mode"),
    min_area:      v("min-area"),
    max_dim:       v("max-dim"),
    margin:        v("margin"),
    layer_height:  v("layer-height"),
    trace_height:  v("trace-height"),
    pen_width_mm:  v("pen-width-mm"),
    hotend_temp:   v("hotend-temp"),
    bed_temp:      v("bed-temp-fdm"),
    generate_stl:  document.getElementById("gen-stl")?.checked ? 1 : 0,
  };
}

// ── Pipeline stage helpers ─────────────────────────────────────────────────────
function _resetPipeline() {
  PIPE_STAGES.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.className = "pipe-stage";
  });
}

function _setStageActive(id) {
  // Mark all previous stages as done
  const idx = PIPE_STAGES.indexOf(id);
  PIPE_STAGES.forEach((sid, i) => {
    const el = document.getElementById(sid);
    if (!el) return;
    if (i < idx)       el.className = "pipe-stage done";
    else if (i === idx) el.className = "pipe-stage active";
    else                el.className = "pipe-stage";
  });
}

function _stageComplete(id) {
  const el = document.getElementById(id);
  if (el) el.className = "pipe-stage done";
}

// ── Download helpers ───────────────────────────────────────────────────────────
/**
 * Wire a download button to a server-side /api/download/<filetype> endpoint.
 * The server sets Content-Disposition: attachment; filename="..."
 * so browsers always save with the correct filename (no UUID blob names).
 */
function _setupServerDownload(btnId, metaId, filetype, filename, sizeStr, itemId) {
  const btn  = document.getElementById(btnId);
  const meta = document.getElementById(metaId);
  if (!btn) return;

  // Make the anchor functional
  btn.href = `/api/download/${filetype}`;
  btn.download = filename;
  btn.removeAttribute("aria-disabled");
  btn.classList.remove("disabled"); // In case CSS uses this
  
  if (meta) meta.textContent = `${filename} · ${sizeStr}`;
  if (itemId) document.getElementById(itemId)?.classList.add("ready");

  btn.onclick = () => {
    _toast(`Downloading ${filename}…`, "success");
  };
}

function _b64ToBlob(b64, type) {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Blob([buf], { type });
}

// ── UI helpers ─────────────────────────────────────────────────────────────────
function _showLoader(show, msg = "") {
  const el = document.getElementById("loader-overlay");
  el?.classList.toggle("active", show);
  if (msg) _updateLoader(msg, "");
}

function _updateLoader(msg, sub = "") {
  const t = document.getElementById("loader-text");
  const s = document.getElementById("loader-sub");
  if (t) t.textContent = msg;
  if (s) s.textContent = sub;
}

function _setConvertBtn(loading) {
  const btn = document.getElementById("convert-btn");
  if (!btn) return;
  btn.disabled    = loading;
  btn.textContent = loading ? "Running pipeline…" : "⚡ Run Full Pipeline";
}

function _fmtBytes(n) {
  if (n < 1024)         return n + " B";
  if (n < 1024 * 1024)  return (n / 1024).toFixed(1) + " KB";
  return (n / (1024 * 1024)).toFixed(2) + " MB";
}

function _toast(msg, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const icon = type === "success" ? "✓" : type === "error" ? "✕" : "ℹ";
  const el   = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = "fadeOut 0.3s ease forwards";
    setTimeout(() => el.remove(), 300);
  }, 4500);
}
