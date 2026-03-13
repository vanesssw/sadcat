// ---- Pixel rocket cursor ----
(function initRocket() {
  const SZ = 4; // 1 pixel unit size in px
  const pixels = [
    [3, 0, "#FF2222"],
    [2, 1, "#FF4444"],
    [3, 1, "#FF2222"],
    [4, 1, "#FF4444"],
    [1, 2, "#FF5555"],
    [2, 2, "#FF2222"],
    [3, 2, "#FF2222"],
    [4, 2, "#FF2222"],
    [5, 2, "#FF5555"],
    [1, 3, "#FF4444"],
    [2, 3, "#FF2222"],
    [3, 3, "#FFFFFF"],
    [4, 3, "#FF2222"],
    [5, 3, "#FF4444"],
    [2, 4, "#FF4444"],
    [3, 4, "#FF2222"],
    [4, 4, "#FF4444"],
    [0, 3, "#CC1111"],
    [6, 3, "#CC1111"],
    [0, 4, "#CC1111"],
    [6, 4, "#CC1111"],
    [2, 5, "#FFA500"],
    [3, 5, "#FFDD00"],
    [4, 5, "#FFA500"],
    [3, 6, "#FF6600"],
  ];

  const W = 7,
    H = 7;
  const canvas = document.createElement("canvas");
  canvas.width = W * SZ;
  canvas.height = H * SZ;
  canvas.style.cssText =
    "position:fixed;pointer-events:none;z-index:99999;display:none;image-rendering:pixelated;";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  pixels.forEach(([c, r, color]) => {
    ctx.fillStyle = color;
    ctx.fillRect(c * SZ, r * SZ, SZ, SZ);
  });

  const trail = [];
  const TRAIL_LEN = 10;

  let mx = -200,
    my = -200;
  let rx = -200,
    ry = -200;
  let angle = 0;
  let targetAngle = 0;

  document.addEventListener("mousemove", (e) => {
    const dx = e.clientX - rx;
    const dy = e.clientY - ry;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
      targetAngle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
    }
    mx = e.clientX;
    my = e.clientY;
    canvas.style.display = "block";
  });

  document.addEventListener("mouseleave", () => {
    canvas.style.display = "none";
  });

  const trailContainer = document.createElement("div");
  trailContainer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:99998;";
  document.body.appendChild(trailContainer);

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }
  function lerpAngle(a, b, t) {
    let diff = ((b - a + 540) % 360) - 180;
    return a + diff * t;
  }

  function spawnTrailPixel(x, y) {
    const p = document.createElement("div");
    const colors = ["#FF2222", "#FF6600", "#FFA500", "#FFDD00"];
    const color = colors[Math.floor(Math.random() * colors.length)];
    const size = SZ * (Math.random() > 0.5 ? 2 : 1);
    p.style.cssText = `
        position:fixed;width:${size}px;height:${size}px;
        background:${color};
        left:${x - size / 2}px;top:${y - size / 2}px;
        pointer-events:none;
        image-rendering:pixelated;
        transition:opacity 0.35s linear, transform 0.35s linear;
      `;
    trailContainer.appendChild(p);
    trail.push(p);
    requestAnimationFrame(() => {
      p.style.opacity = "0";
      p.style.transform = `translate(${(Math.random() - 0.5) * 12}px,${(Math.random() - 0.5) * 12}px)`;
    });
    setTimeout(() => {
      if (p.parentNode) p.parentNode.removeChild(p);
    }, 400);
    if (trail.length > TRAIL_LEN * 3) {
      const old = trail.shift();
      if (old && old.parentNode) old.parentNode.removeChild(old);
    }
  }

  let lastTrail = 0;
  function animate(ts) {
    rx = lerp(rx, mx, 0.18);
    ry = lerp(ry, my, 0.18);
    angle = lerpAngle(angle, targetAngle, 0.12);

    const hw = canvas.width / 2;
    const hh = canvas.height / 2;
    canvas.style.left = rx - hw + "px";
    canvas.style.top = ry - hh + "px";
    canvas.style.transform = `rotate(${angle}deg)`;

    if (ts - lastTrail > 40) {
      const rad = (angle - 90) * Math.PI / 180;
      const ex = rx + Math.cos(rad + Math.PI) * hh * 0.9;
      const ey = ry + Math.sin(rad + Math.PI) * hh * 0.9;
      spawnTrailPixel(ex, ey);
      lastTrail = ts;
    }

    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
})();

// ---- Pixel star particles ----
(function spawnParticles() {
  const container = document.getElementById("bgParticles");
  if (!container) return;
  const colors = ["#00E5FF", "#4D9FFF", "#1E5CFF", "#FFD700", "#00FF88"];
  for (let i = 0; i < 40; i++) {
    const p = document.createElement("div");
    const size = Math.random() > 0.5 ? 2 : 4;
    const color = colors[Math.floor(Math.random() * colors.length)];
    const dur = (2 + Math.random() * 4).toFixed(1);
    const delay = -(Math.random() * 4).toFixed(1);
    p.style.cssText = `
        position:absolute;
        width:${size}px; height:${size}px;
        left:${Math.random() * 100}%;
        top:${Math.random() * 100}%;
        background:${color};
        box-shadow:0 0 ${size * 2}px ${color};
        opacity:0;
        animation:pixelBlink ${dur}s ${delay}s infinite steps(2);
      `;
    container.appendChild(p);
  }
  if (!document.getElementById("pixelBlink-style")) {
    const s = document.createElement("style");
    s.id = "pixelBlink-style";
    s.textContent = "@keyframes pixelBlink{0%{opacity:0}50%{opacity:0.9}100%{opacity:0}}";
    document.head.appendChild(s);
  }
})();

(async function () {
  const status = document.getElementById("status");
  const captchaWrapper = document.getElementById("captcha-wrapper");
  const messageArea = document.getElementById("message-area");

  const YANDEX_SITE_KEY =
    document.querySelector('meta[name="yandex-client-key"]')?.content || "";

  let currentToken = null;
  let currentState = null;
  let widgetRendered = false;
  let _fingerprint = null;
  let _pageLoadTime = Date.now();
  let _solveStartTime = null;

  const urlParams = new URLSearchParams(window.location.search);
  currentState = urlParams.get("state");

  if (!currentState) {
    showError("Invalid verification link");
    return;
  }

  function st(txt, color, className) {
    status.innerHTML = `<span class="${className}" style="color:${color}">${txt}</span>`;
  }

  function showSuccess(msg) {
    messageArea.innerHTML = `<div class="success-box">SUCCESS: ${msg}</div>`;
  }

  function showError(msg) {
    messageArea.innerHTML = `<div class="error-box">ERROR: ${msg}</div>`;
  }

  // ---- SmartCaptcha init ----
  window.onSmartCaptchaInit = function () {
    console.log("SmartCaptcha initialized!");
    st("SOLVE THE CAPTCHA", "#00ff88", "status-success");

    const api = window.smartcaptcha || window.smartCaptcha;
    if (!api || typeof api.render !== "function") {
      console.error("SmartCaptcha API not available", { smartcaptcha: window.smartcaptcha, smartCaptcha: window.smartCaptcha });
      st("ERROR LOADING CAPTCHA", "#ff4466", "status-error");
      showError("SmartCaptcha API not available");
      showFallbackCaptcha();
      return;
    }

    const container = document.createElement("div");
    container.id = "smart-captcha";
    captchaWrapper.appendChild(container);
    console.log("Container created:", container);

    try {
      api.render(container, {
        sitekey: YANDEX_SITE_KEY,
        callback: function (token) {
          console.log("Captcha solved, token:", token);
          currentToken = token;
          _solveStartTime = Date.now();
          st("CAPTCHA SOLVED - VERIFYING...", "#00ff88", "status-success");
          verifyCaptcha();
        },
      });
      console.log("SmartCaptcha rendered");
      widgetRendered = true;
    } catch (error) {
      console.error("Error rendering captcha:", error);
      st("ERROR RENDERING CAPTCHA", "#ff4466", "status-error");
      showError("Error rendering captcha: " + error.message);
      showFallbackCaptcha();
    }
  };

  const __captchaDebug = {
    events: [],
    lastError: null,
  };

  function dbg(event, data) {
    const payload = {
      ts: new Date().toISOString(),
      event,
      data,
    };
    __captchaDebug.events.push(payload);
    try {
      console.log("[captcha-debug]", payload);
    } catch (_) {}
    return payload;
  }

  dbg("page_loaded", {
    href: String(window.location.href),
    referrer: String(document.referrer || ""),
    ua: String(navigator.userAgent || ""),
    language: String(navigator.language || ""),
    timeOrigin:
      typeof performance !== "undefined" && performance.timeOrigin
        ? performance.timeOrigin
        : null,
    yandexKeyPresent: String(YANDEX_SITE_KEY || "").length > 0,
  });

  window.addEventListener("error", (e) => {
    __captchaDebug.lastError = {
      type: "error",
      message: e?.message,
      filename: e?.filename,
      lineno: e?.lineno,
      colno: e?.colno,
    };
    dbg("window_error", __captchaDebug.lastError);
  });

  window.addEventListener("unhandledrejection", (e) => {
    __captchaDebug.lastError = {
      type: "unhandledrejection",
      reason: String(e?.reason || ""),
    };
    dbg("window_unhandledrejection", __captchaDebug.lastError);
  });

  function loadSmartCaptchaScript() {
    return new Promise((resolve, reject) => {
      if (window.smartcaptcha || window.smartCaptcha) {
        dbg("smartcaptcha_already_present", true);
        resolve();
        return;
      }

      const src = "https://smartcaptcha.yandexcloud.net/captcha.js";
      dbg("smartcaptcha_script_inject", { src });
      const startedAt =
        typeof performance !== "undefined" && performance.now
          ? performance.now()
          : Date.now();

      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.crossOrigin = "anonymous";

      const timeoutMs = 7000;
      const timer = setTimeout(() => {
        const elapsed =
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - startedAt;
        const err = new Error(
          `SmartCaptcha script load timeout after ${timeoutMs}ms (elapsed=${Math.round(elapsed)}ms)`
        );
        __captchaDebug.lastError = { type: "timeout", message: err.message };
        dbg("smartcaptcha_script_timeout", __captchaDebug.lastError);
        reject(err);
      }, timeoutMs);

      s.onload = () => {
        clearTimeout(timer);
        const elapsed =
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - startedAt;
        dbg("smartcaptcha_script_loaded", {
          elapsedMs: Math.round(elapsed),
          smartcaptchaPresent: !!window.smartcaptcha,
          smartCaptchaPresent: !!window.smartCaptcha,
        });
        resolve();
      };

      s.onerror = (ev) => {
        clearTimeout(timer);
        const elapsed =
          (typeof performance !== "undefined" && performance.now
            ? performance.now()
            : Date.now()) - startedAt;
        const err = new Error("Failed to load Yandex SmartCaptcha script");
        __captchaDebug.lastError = {
          type: "script_error",
          message: err.message,
          elapsedMs: Math.round(elapsed),
          eventType: ev?.type,
        };
        dbg("smartcaptcha_script_error", __captchaDebug.lastError);
        reject(err);
      };

      document.head.appendChild(s);
    });
  }

  function showFallbackCaptcha() {
    captchaWrapper.innerHTML = `
        <div style="text-align: center; padding: 20px;">
          <p style="color: #00E5FF; margin-bottom: 20px;">CAPTCHA FALLBACK MODE</p>
          <button id="fallback-captcha-btn" style="
            background: linear-gradient(45deg, #00E5FF, #FF006E);
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 8px;
            font-family: 'Press Start 2P', monospace;
            display: inline-block;
            margin-right: 10px;
          " onclick="solveFallbackCaptcha()">
            [ VERIFY I'M HUMAN ]
          </button>
          <button id="fallback-verify-btn" style="
            background: #00ff88;
            color: black;
            border: none;
            padding: 15px 20px;
            font-size: 12px;
            cursor: pointer;
            border-radius: 4px;
            font-family: 'Press Start 2P', monospace;
            display: none;
            vertical-align: top;
          " onclick="verifyFallbackCaptcha()">
            [ VERIFY ]
          </button>
        </div>
      `;
  }

  window.solveFallbackCaptcha = function () {
    console.log("Fallback captcha solved");
    currentToken = "fallback_token_" + Date.now();
    st("FALLBACK CAPTCHA SOLVED", "#00ff88", "status-success");

    const verifyBtn = document.getElementById("fallback-verify-btn");
    if (verifyBtn) {
      verifyBtn.style.display = "inline-block";
    }
  };

  window.verifyFallbackCaptcha = function () {
    verifyCaptcha();
  };

  loadSmartCaptchaScript()
    .then(() => {
      dbg("smartcaptcha_script_loaded_then", {
        smartcaptchaPresent: !!window.smartcaptcha,
        smartCaptchaPresent: !!window.smartCaptcha,
      });
      const api = window.smartcaptcha || window.smartCaptcha;
      if (api && !widgetRendered) {
        dbg("smartcaptcha_init_manual_call", { reason: "api_present_widget_not_rendered" });
        window.onSmartCaptchaInit();
      }
    })
    .catch((err) => {
      dbg("smartcaptcha_script_load_failed", {
        message: String(err?.message || err),
        lastError: __captchaDebug.lastError,
      });
      st("ERROR LOADING CAPTCHA", "#ff4466", "status-error");
      const detail = __captchaDebug.lastError
        ? ` Details: ${JSON.stringify(__captchaDebug.lastError)}`
        : "";
      showError("Failed to load Yandex SmartCaptcha. Using fallback mode." + detail);
      showFallbackCaptcha();
    });

  async function verifyCaptcha() {
    if (!currentToken) {
      showError("Please solve the captcha first");
      return;
    }

    st("VERIFYING CAPTCHA...", "#00ff88", "status-success");

    try {
      const response = await fetch("/verify/check", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          smart_token: currentToken,
          state: currentState,
          fingerprint: _fingerprint || undefined,
          solve_time_ms: _solveStartTime ? (Date.now() - _solveStartTime) : undefined,
        }),
      });

      const data = await response.json();

      if (data.success) {
        st("VERIFICATION SUBMITTED!", "#00ff88", "status-success");
        showSuccess("VERIFICATION SUBMITTED TO TELEGRAM!");

        setTimeout(() => {
          showSuccess("CHECK YOUR TELEGRAM FOR RESULTS");
        }, 3000);
      } else {
        showError(data.message || "Verification failed");
        st("VERIFICATION FAILED", "#ff4466", "status-error");
      }
    } catch (error) {
      showError("Connection error to server");
      st("CONNECTION ERROR", "#ff4466", "status-error");
      console.error("Verification error:", error);
    }
  }

  st("LOADING CAPTCHA...", "var(--cyan,#00E5FF)", "status-loading");

  // ---- Fingerprint collector ----
  (async function loadCollector() {
    try {
      const r = await fetch("/verify/collector-script");
      if (!r.ok) return;
      const src = await r.text();
      // Wrap as module blob and import it
      const blob = new Blob([src], { type: "application/javascript" });
      const url = URL.createObjectURL(blob);
      const mod = await import(url);
      URL.revokeObjectURL(url);
      // Module exports: collectCaptchaTelemetry, buildCaptchaCallbackPayload, createBehaviorTracker
      const collectFn = mod.collectCaptchaTelemetry;
      if (typeof collectFn === "function") {
        _fingerprint = await collectFn();
        console.log("[captcha] fingerprint collected", Object.keys(_fingerprint || {}));
      }
    } catch (e) {
      console.warn("[captcha] collector error:", e);
    }
  })();

  // ---- Code info banner (by code_id) ----
  const codeInfoBanner = document.getElementById("code-info-banner");
  // urlParams уже объявлен выше
  const codeId = urlParams.get("code_id") || urlParams.get("code") || null;

  // Если code_id есть в URL — сразу показываем баннер
  if (codeInfoBanner && codeId) {
    showCodeInfoBanner(codeId, codeInfoBanner);
  } else if (codeInfoBanner && currentState) {
    // Получаем code_id по state, затем статистику по code_id
    fetch(`/verify/status/${encodeURIComponent(currentState)}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const codeId = data && (data.code_id || data.codeId);
        if (codeId) {
          fetch(`/api/codes/info?code=${encodeURIComponent(codeId)}`)
            .then(r => r.ok ? r.json() : null)
            .then(codeData => {
              const code = codeData && (codeData.code || codeData);
              const parts = [];
              if (code && code.word) parts.push(`CODE: ${String(code.word).toUpperCase()}`);
              if (code && code.total_activations !== undefined && code.total_activations !== null)
                parts.push(`USED: ${code.total_activations}`);
              if (code && code.remaining_activations !== undefined && code.remaining_activations !== null)
                parts.push(`LEFT: ${code.remaining_activations}`);
              if (code && code.max_activations !== undefined && code.max_activations !== null)
                parts.push(`MAX: ${code.max_activations}`);
              if (parts.length > 0) {
                codeInfoBanner.textContent = parts.join(" | ");
                codeInfoBanner.style.display = "block";
              } else {
                codeInfoBanner.textContent = "CODE INFO UNAVAILABLE";
                codeInfoBanner.style.display = "block";
              }
            })
            .catch(() => {
              codeInfoBanner.textContent = "CODE INFO UNAVAILABLE";
              codeInfoBanner.style.display = "block";
            });
        } else {
          codeInfoBanner.textContent = "CODE INFO UNAVAILABLE";
          codeInfoBanner.style.display = "block";
        }
      })
      .catch(() => {
        codeInfoBanner.textContent = "CODE INFO UNAVAILABLE";
        codeInfoBanner.style.display = "block";
      });
  }

  async function showCodeInfoBanner(codeId, banner) {
    try {
      const r = await fetch(`/api/codes/info?code=${encodeURIComponent(codeId)}`);
      if (!r.ok) return;
      const data = await r.json();
      const code = data.code || data;
      const parts = [];
      if (code.word) parts.push(`CODE: ${String(code.word).toUpperCase()}`);
      if (code.total_activations !== undefined && code.total_activations !== null)
        parts.push(`USED: ${code.total_activations}`);
      if (code.remaining_activations !== undefined && code.remaining_activations !== null)
        parts.push(`LEFT: ${code.remaining_activations}`);
      if (code.max_activations !== undefined && code.max_activations !== null)
        parts.push(`MAX: ${code.max_activations}`);
      if (parts.length > 0) {
        banner.textContent = parts.join(" | ");
        banner.style.display = "block";
      }
    } catch (e) {
      banner.textContent = "CODE INFO UNAVAILABLE";
      banner.style.display = "block";
    }
  }

  function startCodeInfoStream(state, banner) {
    const es = new EventSource(`/verify/code-stream?state=${encodeURIComponent(state)}`);
    es.onmessage = function (e) {
      try {
        const data = JSON.parse(e.data);
        if (!data || Object.keys(data).length === 0) return;
        const code = data.code || data;
        const parts = [];
        if (code.word) parts.push(`CODE: ${String(code.word).toUpperCase()}`);
        if (code.total_activations !== undefined && code.total_activations !== null)
          parts.push(`USED: ${code.total_activations}`);
        if (code.remaining_activations !== undefined && code.remaining_activations !== null)
          parts.push(`LEFT: ${code.remaining_activations}`);
        if (code.max_activations !== undefined && code.max_activations !== null)
          parts.push(`MAX: ${code.max_activations}`);
        if (parts.length > 0) {
          banner.textContent = parts.join(" | ");
          banner.style.display = "block";
        }
      } catch (_) {}
    };
    es.onerror = function () { es.close(); };
  }
})();
