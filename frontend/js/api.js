/**
 * api.js
 * ------
 * Handles all communication with the Flask backend.
 */

// When served by Flask at the same origin, use relative paths.
// Override with a full URL only if running the frontend separately.
const API_BASE = window.location.hostname === "localhost" && window.location.port !== "5000"
  ? "http://localhost:5000"
  : "";

/**
 * Send an image (file or URL) plus settings to the backend.
 *
 * @param {Object} params
 * @param {File|null}   params.file        - Uploaded file object
 * @param {string}      params.url         - Image URL (used if file is null)
 * @param {Object}      params.settings    - User-defined settings
 * @param {Function}    params.onProgress  - Optional progress callback (0–100)
 * @returns {Promise<Object>} Parsed JSON response from server
 */
export async function convertImage({ file, url, settings, onProgress }) {
  const form = new FormData();

  if (file) {
    form.append("file", file);
  } else if (url) {
    form.append("url", url);
  } else {
    throw new Error("No image source provided.");
  }

  // Append all settings
  for (const [key, value] of Object.entries(settings)) {
    form.append(key, value);
  }

  // Use XHR for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.error || `Server error ${xhr.status}`));
        }
      } catch {
        reject(new Error("Invalid JSON response from server"));
      }
    });

    xhr.addEventListener("error",   () => reject(new Error("Network error — is the backend running?")));
    xhr.addEventListener("timeout", () => reject(new Error("Request timed out")));

    xhr.open("POST", `${API_BASE}/api/convert`);
    xhr.timeout = 120_000; // 2 min
    xhr.send(form);
  });
}

/**
 * Check if the backend is reachable.
 * @returns {Promise<boolean>}
 */
export async function checkHealth() {
  try {
    const resp = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
    return resp.ok;
  } catch {
    return false;
  }
}

/**
 * Run the full pipeline on a built-in demo image (no upload required).
 * @param {Object} settings - User-defined settings
 * @returns {Promise<Object>} Same JSON shape as convertImage
 */
export async function runDemo(settings) {
  const form = new FormData();
  for (const [key, value] of Object.entries(settings)) {
    form.append(key, value);
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.error || `Server error ${xhr.status}`));
        }
      } catch {
        reject(new Error("Invalid JSON response from server"));
      }
    });
    xhr.addEventListener("error",   () => reject(new Error("Network error — is the backend running?")));
    xhr.addEventListener("timeout", () => reject(new Error("Request timed out")));
    xhr.open("POST", `${API_BASE}/api/demo`);
    xhr.timeout = 120_000;
    xhr.send(form);
  });
}

