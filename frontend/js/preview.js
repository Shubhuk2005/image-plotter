/**
 * preview.js
 * ----------
 * Handles all preview rendering: image tabs, toolpath canvas animation,
 * G-code syntax highlighting, and stats display.
 */

// ── Tab switching ──────────────────────────────────────────────────────────────

export function initTabs() {
  // Each tab button targets a tab-content in the same card
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target  = btn.dataset.tab;
      // Scope to siblings within same preview-tabs container
      const group   = btn.closest(".preview-tabs") ?? btn.parentElement;
      const card    = group.closest(".card") ?? document.body;

      group.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      card.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      card.querySelector(`#${target}`)?.classList.add("active");
    });
  });
}

// ── Show image previews ────────────────────────────────────────────────────────

export function showPreviews({ preview_orig, preview_proc, preview_path }) {
  _setPreviewImg("preview-orig-img",    preview_orig, "Original image");
  _setPreviewImg("preview-proc-img",    preview_proc, "Processed binary image");
  _setPreviewImg("preview-toolpath-img", preview_path, "Toolpath visualisation");
}

function _setPreviewImg(id, b64, alt) {
  const el = document.getElementById(id);
  if (!el) return;
  if (b64) {
    el.src = `data:image/png;base64,${b64}`;
    el.alt = alt;
    el.style.display = "block";
    el.closest(".preview-image-wrap")?.querySelector(".preview-empty")?.remove();
  }
}

// ── Stats bar ──────────────────────────────────────────────────────────────────

export function showStats({ paths, points, layers = 0, travel = 0, stlSize = 0 }) {
  const bar = document.getElementById("stats-bar");
  if (!bar) return;

  const lifts = Math.max(0, paths - 1);
  const stlStr = stlSize > 0 ? `${(stlSize / 1024).toFixed(0)} KB` : "—";

  bar.innerHTML = `
    <div class="stat-chip">Paths <strong>${paths}</strong></div>
    <div class="stat-chip">Points <strong>${points}</strong></div>
    <div class="stat-chip">Pen lifts <strong>${lifts}</strong></div>
    <div class="stat-chip">FDM layers <strong>${layers}</strong></div>
    <div class="stat-chip">Travel <strong>${travel} mm</strong></div>
    <div class="stat-chip">STL <strong>${stlStr}</strong></div>
  `;
}

// ── G-code viewer ──────────────────────────────────────────────────────────────

export function renderGcode(gcode, elementId = "gcode-view-pen", mode = "pen") {
  const el = document.getElementById(elementId);
  if (!el) return;

  const lines = gcode.split("\n").slice(0, 400).map((line) => {
    const safe = _escapeHtml(line);
    if (safe.trim().startsWith(";"))     return `<span class="gc-comment">${safe}</span>`;
    if (/\bM1[01][04]\b/i.test(safe))   return `<span class="gc-temp">${safe}</span>`;
    if (/\bE[\d.]+/i.test(safe))         return `<span class="gc-extruder">${safe}</span>`;
    if (/\bZ\b/i.test(safe))             return `<span class="gc-pen">${safe}</span>`;
    if (/\bG[01]\b/i.test(safe))         return `<span class="gc-move">${safe}</span>`;
    return safe;
  });

  el.innerHTML = lines.join("\n");
}

function _escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Animated toolpath canvas ───────────────────────────────────────────────────

let _animFrame = null;

export function animateToolpath(gcodeStr, canvasId = "toolpath-canvas") {
  if (_animFrame) cancelAnimationFrame(_animFrame);

  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx  = canvas.getContext("2d");
  const dpr  = window.devicePixelRatio || 1;
  const size = 560;
  canvas.width  = size * dpr;
  canvas.height = size * dpr;
  canvas.style.width  = size + "px";
  canvas.style.height = size + "px";
  ctx.scale(dpr, dpr);

  const { moves } = _parseGcode(gcodeStr);
  if (!moves.length) return;

  // Find bounds
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const m of moves) {
    if (m.x !== null) { minX = Math.min(minX, m.x); maxX = Math.max(maxX, m.x); }
    if (m.y !== null) { minY = Math.min(minY, m.y); maxY = Math.max(maxY, m.y); }
  }
  const pad   = 24;
  const scaleX = (size - pad * 2) / (maxX - minX || 1);
  const scaleY = (size - pad * 2) / (maxY - minY || 1);
  const sc     = Math.min(scaleX, scaleY);

  const toCanvasX = (x) => pad + (x - minX) * sc;
  const toCanvasY = (y) => size - pad - (y - minY) * sc;

  ctx.fillStyle = "#f0f4ff";
  ctx.fillRect(0, 0, size, size);

  // Pre-draw full toolpath faintly
  ctx.save();
  ctx.globalAlpha = 0.12;
  ctx.strokeStyle = "#4f7cff";
  ctx.lineWidth   = 1;
  ctx.beginPath();
  let penDown = false;
  let cx = 0, cy = 0;
  for (const m of moves) {
    const nx = m.x ?? cx;
    const ny = m.y ?? cy;
    if (m.penDown) {
      ctx.lineTo(toCanvasX(nx), toCanvasY(ny));
    } else {
      ctx.moveTo(toCanvasX(nx), toCanvasY(ny));
    }
    cx = nx; cy = ny;
  }
  ctx.stroke();
  ctx.restore();

  // Animated draw
  let idx    = 0;
  let curX   = 0;
  let curY   = 0;
  const STEPS_PER_FRAME = 6;

  ctx.lineWidth   = 1.4;
  ctx.lineCap     = "round";
  ctx.lineJoin    = "round";

  function frame() {
    for (let s = 0; s < STEPS_PER_FRAME && idx < moves.length; s++, idx++) {
      const m = moves[idx];
      const nx = m.x ?? curX;
      const ny = m.y ?? curY;

      if (m.penDown) {
        ctx.beginPath();
        ctx.moveTo(toCanvasX(curX), toCanvasY(curY));
        ctx.lineTo(toCanvasX(nx),   toCanvasY(ny));
        ctx.strokeStyle = "#1e3a8a";
        ctx.stroke();
      } else if (!m.penDown && (nx !== curX || ny !== curY)) {
        // travel — draw dotted faint line
        ctx.save();
        ctx.setLineDash([3, 6]);
        ctx.beginPath();
        ctx.moveTo(toCanvasX(curX), toCanvasY(curY));
        ctx.lineTo(toCanvasX(nx),   toCanvasY(ny));
        ctx.strokeStyle = "#c0c8e0";
        ctx.lineWidth   = 0.8;
        ctx.stroke();
        ctx.restore();
      }

      curX = nx;
      curY = ny;
    }

    if (idx < moves.length) {
      _animFrame = requestAnimationFrame(frame);
    }
  }

  _animFrame = requestAnimationFrame(frame);
}

// ── G-code parser (lightweight) ────────────────────────────────────────────────

function _parseGcode(gcode) {
  const lines = gcode.split("\n");
  const moves = [];
  let penDown  = false;
  let curX = 0, curY = 0, curZ = 5;

  for (const raw of lines) {
    const line = raw.split(";")[0].trim();   // strip comments
    if (!line) continue;

    const tokens = line.toUpperCase().split(/\s+/);
    const cmd    = tokens[0];

    let x = null, y = null, z = null;
    for (const tok of tokens.slice(1)) {
      if (tok.startsWith("X")) x = parseFloat(tok.slice(1));
      if (tok.startsWith("Y")) y = parseFloat(tok.slice(1));
      if (tok.startsWith("Z")) z = parseFloat(tok.slice(1));
    }

    if (cmd === "G0" || cmd === "G1") {
      if (z !== null) {
        curZ    = z;
        penDown = z <= 0.5;       // pen is down when Z is near 0
      }
      if (x !== null || y !== null) {
        moves.push({ x, y, penDown });
        if (x !== null) curX = x;
        if (y !== null) curY = y;
      }
    }
  }

  return { moves };
}
