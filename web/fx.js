/* fx.js -- motion + depth effects: particle network, cursor light and 3D tilt on cards, animated number count-up.
   Pure canvas / DOM, no libraries. Respects prefers-reduced-motion. Exposes window.FX.countUp(root). */
"use strict";
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  // ---- particle network behind everything ---------------------------------------------------------------
  const cv = document.getElementById("bg"), ctx = cv.getContext("2d");
  let W = 0, H = 0, rgb = "252,128,25";
  const P = [], mouse = { x: -999, y: -999 };
  function readColour() {
    const m = /^#([0-9a-f]{6})$/i.exec(getComputedStyle(root).getPropertyValue("--accent").trim());
    if (m) { const n = parseInt(m[1], 16); rgb = `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`; }
  }
  function resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(80, (W * H) / 20000));
    while (P.length < n) P.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .28, vy: (Math.random() - .5) * .28, r: Math.random() * 1.5 + .7 });
    P.length = n;
  }
  function frame() {
    ctx.clearRect(0, 0, W, H);
    const k = root.dataset.theme === "light" ? .55 : 1;
    for (const p of P) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
      const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
      if (d > 0 && d < 140) { p.x += (dx / d) * .7; p.y += (dy / d) * .7; }          // particles drift away from the cursor
    }
    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        const d = Math.hypot(P[i].x - P[j].x, P[i].y - P[j].y);
        if (d < 130) { ctx.strokeStyle = `rgba(${rgb},${(1 - d / 130) * .2 * k})`; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(P[i].x, P[i].y); ctx.lineTo(P[j].x, P[j].y); ctx.stroke(); }
      }
      ctx.fillStyle = `rgba(${rgb},${.55 * k})`; ctx.beginPath(); ctx.arc(P[i].x, P[i].y, P[i].r, 0, 6.2832); ctx.fill();
    }
    if (!reduce) requestAnimationFrame(frame);
  }
  readColour(); resize(); frame();
  addEventListener("resize", () => { resize(); if (reduce) frame(); });
  document.addEventListener("themechange", () => { readColour(); if (reduce) frame(); });

  // ---- cursor light on every card, 3D tilt on the small ones ------------------------------------------------
  const LIGHT = ".kpi,.segcard,.partcard,.panel,.card,.banner", TILT = ".kpi,.segcard,.partcard";
  let last = null, pending = false, ev = null;
  const clear = el => { if (el) el.style.transform = ""; };
  document.addEventListener("pointermove", e => {
    mouse.x = e.clientX; mouse.y = e.clientY; ev = e;
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const t = ev.target.closest ? ev.target.closest(LIGHT) : null;
      if (last && last !== t) clear(last);
      last = t;
      if (!t) return;
      const r = t.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
      t.style.setProperty("--mx", x + "px"); t.style.setProperty("--my", y + "px");
      if (!reduce && t.matches(TILT)) {
        const rx = (y / r.height - .5) * -9, ry = (x / r.width - .5) * 9;
        t.style.transform = `perspective(900px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateY(-3px)`;
      }
    });
  });
  root.addEventListener("mouseleave", () => { mouse.x = mouse.y = -999; clear(last); last = null; });

  // ---- number count-up ---------------------------------------------------------------------------------------------
  // Animates the first number found in each KPI value / segment share, keeping prefix, suffix and Indian digit grouping.
  function countUp(scope) {
    if (reduce) return;
    scope.querySelectorAll(".kpi .val, .segcard .share").forEach(node => {
      const txt = node.textContent, m = /\d[\d,]*\.?\d*/.exec(txt);
      if (!m) return;
      const target = parseFloat(m[0].replace(/,/g, ""));
      if (!isFinite(target) || target === 0) return;
      const dec = (m[0].split(".")[1] || "").length, pre = txt.slice(0, m.index), post = txt.slice(m.index + m[0].length);
      const fmt = v => v.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec });
      const t0 = performance.now(), dur = 1500;
      (function step(now) {
        const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 4);
        node.textContent = k < 1 ? pre + fmt(target * e) + post : txt;
        if (k < 1) requestAnimationFrame(step);
      })(t0);
    });
  }
  window.FX = { countUp };
})();
