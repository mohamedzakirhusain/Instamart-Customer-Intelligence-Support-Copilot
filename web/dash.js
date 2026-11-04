/* dash.js -- navigation + dashboard views (Overview, Customers, Support triage, Refund agent, Quality checks).
   Uses helpers from app.js ($, el, render, toast, store). Charts are plain SVG/CSS: no libraries, works offline. */
"use strict";

const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const inr = n => "INR " + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = n => "INR " + Math.round(n).toLocaleString("en-IN");
const int = n => Number(n).toLocaleString("en-IN");
const short = n => n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e5 ? 0 : 1) + "K" : String(Math.round(n));
const segColor = i => `var(--c${i % 6})`;
const ACTIONS = {
  "Premium Big Spenders": "Early access to electronics offers and priority support",
  "Loyal Regulars": "Loyalty points and a subscription for daily staples",
  "Occasional Buyers": "Bundle and free-delivery nudges to raise order frequency",
  "Lapsing Customers": "Win-back coupon before they are lost"
};
const ICON = {
  overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM13 3v6h8V3zM3 21h8v-6H3z"/>',
  customers: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.4 3.4 0 0 1 0 6.3M18 14.8c1.9.7 3.2 2.4 3.5 5.2"/>',
  triage: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12.5h5"/>',
  agent: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 7V3M9 13h.01M15 13h.01M9 16.5h6"/>',
  quality: '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5L15.5 10"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>'
};
const PAGES = [
  { id:"chat",      label:"Copilot chat",   title:"Copilot chat",     sub:"Ask policies, refunds, customers and tickets", featured:true },
  { id:"overview",  label:"Overview",       title:"Overview",         sub:"Revenue, customers and support at a glance" },
  { id:"customers", label:"Customers",      title:"Customer intelligence", sub:"RFM segments, K-means and the lapse retention list" },
  { id:"triage",    label:"Support triage", title:"Support triage",   sub:"Privacy-safe ticket classification and routing" },
  { id:"agent",     label:"Refund agent",   title:"Refund agent",     sub:"ReAct runs, tool steps and the refund ledger" },
  { id:"quality",   label:"Quality checks", title:"Quality checks",   sub:"Every reference checkpoint from the brief, re-verified live" }
];

// ---- tooltip -----------------------------------------------------------------------------------------
const tipEl = el("div", "tip"); tipEl.setAttribute("role", "tooltip"); document.body.append(tipEl);
function showTip(html, x, y) {
  tipEl.innerHTML = html; tipEl.classList.add("on");
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  tipEl.style.left = Math.min(x + 14, innerWidth - w - 8) + "px"; tipEl.style.top = Math.max(8, Math.min(y - h - 10, innerHeight - h - 8)) + "px";
}
const hideTip = () => tipEl.classList.remove("on");

// ---- data ----------------------------------------------------------------------------------------------
let dashPromise = null;
function getDash(force) {
  if (!dashPromise || force) dashPromise = fetch("/api/dashboard" + (force ? "?refresh=1" : "")).then(async r => {
    const d = await r.json(); if (!r.ok) throw new Error(d.error || "Could not load dashboard data"); return d; });
  dashPromise.catch(() => { dashPromise = null; });
  return dashPromise;
}
let checksData = null;

// ---- small builders --------------------------------------------------------------------------------------
function html(tag, cls, inner) { const e = el(tag, cls); e.innerHTML = inner; return e; }
function kpi(label, value, sub, color, sp) {
  return `<div class="kpi" style="--kc:${color}"><div class="lbl">${esc(label)}</div><div class="val">${value}</div><div class="sub">${sub}</div>${sp ? spark(sp) : ""}</div>`;
}
function smooth(v, n = 7) { return v.map((_, i) => { const s = v.slice(Math.max(0, i - n + 1), i + 1); return s.reduce((a, b) => a + b, 0) / s.length; }); }
function spark(v) {                                // tiny self-drawing trend line inside a KPI card
  const W = 96, H = 34, max = Math.max(...v), min = Math.min(...v);
  const pts = v.map((y, i) => `${(W * i / (v.length - 1)).toFixed(1)},${(H - 3 - (H - 6) * (y - min) / ((max - min) || 1)).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline class="draw" pathLength="1" points="${pts}" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="stroke:var(--kc)"/></svg>`;
}
let bootQueue = [];
const afterBoot = fn => document.body.classList.contains("booting") ? bootQueue.push(fn) : fn();
function panel(title, desc, body, extraHead) {
  return `<div class="panel"><div class="head"><div><h2>${esc(title)}</h2><div class="desc">${desc}</div></div>${extraHead || ""}</div>${body}</div>`;
}
function bars(items, fmt) {                       // horizontal bars: [{label, value, sub, color}]
  const max = Math.max(...items.map(i => i.value), 1);
  return items.map(i => `<div class="bar"><div class="top"><span>${esc(i.label)}</span><span class="muted">${fmt ? fmt(i.value) : int(i.value)}${i.sub ? " · " + esc(i.sub) : ""}</span></div>
    <div class="track"><div class="fill" style="--w:${(100 * i.value / max).toFixed(1)}%;--glowc:${i.color || "rgba(252,128,25,.5)"};background:${i.color || "linear-gradient(90deg,var(--accent),var(--accent2))"}"></div></div></div>`).join("");
}
function failure(box, err, retry) {
  box.innerHTML = `<div class="page"><div class="errbox"><b>Could not load this page.</b><br>${esc(err.message)}<br><br><button class="btn" id="retry">Try again</button></div></div>`;
  box.querySelector("#retry").onclick = retry;
}
function skeleton(box) { box.innerHTML = `<div class="page"><div class="kpis">${'<div class="skel"></div>'.repeat(6)}</div><div class="row r21"><div class="skel" style="height:320px"></div><div class="skel" style="height:320px"></div></div></div>`; }

// ---- charts ------------------------------------------------------------------------------------------------
function lineChart(host, days, series, opts = {}) {      // series: [{values, color, area}]
  const W = 780, H = 290, L = 58, R = 14, T = 12, B = 28, n = days.length;
  const vals = series[0].values, max = Math.max(...vals) * 1.08 || 1;
  const x = i => L + (W - L - R) * i / (n - 1), y = v => T + (H - T - B) * (1 - v / max);
  const gid = "g" + Math.random().toString(36).slice(2, 7);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "Line chart")}"><defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" style="stop-color:var(--accent);stop-opacity:.35"/><stop offset="1" style="stop-color:var(--accent);stop-opacity:0"/></linearGradient></defs>`;
  for (let k = 0; k <= 4; k++) { const v = max * k / 4; s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${short(v)}</text>`; }
  days.forEach((d, i) => { if (d.slice(8) === "01") s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(d.slice(0, 7))}</text>`; });
  const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  s += `<polygon class="area-in" points="${L},${H - B} ${pts} ${x(n - 1)},${H - B}" fill="url(#${gid})"/><polyline class="draw" pathLength="1" points="${pts}" fill="none" style="stroke:var(--accent);filter:drop-shadow(0 3px 8px var(--accent))" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
    <line id="${gid}v" class="axis" y1="${T}" y2="${H - B}" style="opacity:0"/><circle id="${gid}c" r="4.5" style="fill:var(--accent);stroke:var(--panel);stroke-width:2;opacity:0"/>
    <rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" id="${gid}r"/></svg>`;
  host.innerHTML = s;
  const svg = host.querySelector("svg"), r = svg.querySelector("#" + gid + "r"), vl = svg.querySelector("#" + gid + "v"), c = svg.querySelector("#" + gid + "c");
  r.addEventListener("mousemove", e => {
    const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W;
    const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
    vl.setAttribute("x1", x(i)); vl.setAttribute("x2", x(i)); vl.style.opacity = 1; c.setAttribute("cx", x(i)); c.setAttribute("cy", y(vals[i])); c.style.opacity = 1;
    showTip(`<b>${esc(days[i])}</b><br>${esc(opts.name || "Value")}: ${inr(vals[i])}`, e.clientX, e.clientY);
  });
  r.addEventListener("mouseleave", () => { vl.style.opacity = 0; c.style.opacity = 0; hideTip(); });
}
function donut(parts) {                          // [{label,value,color}]
  const total = parts.reduce((a, p) => a + p.value, 0), R = 54, C = 2 * Math.PI * R; let off = 0;
  let s = `<svg class="chart" viewBox="0 0 150 150" style="max-width:170px" role="img" aria-label="Donut chart"><circle cx="75" cy="75" r="${R}" fill="none" style="stroke:var(--inset)" stroke-width="18"/><g class="sweep">`;
  parts.forEach(p => { const len = C * p.value / total; s += `<circle cx="75" cy="75" r="${R}" fill="none" stroke-width="18" stroke-linecap="butt" style="stroke:${p.color}" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 75 75)"><title>${esc(p.label)}: ${int(p.value)}</title></circle>`; off += len; });
  return s + `</g><text x="75" y="72" text-anchor="middle" style="fill:var(--text);font-size:19px;font-weight:700">${int(total)}</text><text x="75" y="89" text-anchor="middle">orders</text></svg>`;
}
function scatter(host, pts, names, ratio) {
  const W = 640, H = 340, L = 44, B = 34, T = 10, R = 10;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = v => L + (W - L - R) * (v - x0) / (x1 - x0), Y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="PCA scatter of customers by segment">`;
  for (let k = 0; k <= 4; k++) { const gy = T + (H - T - B) * k / 4; s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${gy}" y2="${gy}"/>`; }
  pts.forEach((p, i) => { s += `<circle class="scatter-dot" cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="3.2" data-s="${p[2]}" style="--d:${i % 300};fill:${segColor(p[2])};opacity:.62"/>`; });
  s += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">PC1 · ${(ratio[0] * 100).toFixed(1)}% of variance</text>
        <text transform="translate(12 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">PC2 · ${(ratio[1] * 100).toFixed(1)}%</text></svg>`;
  host.innerHTML = s;
  host.querySelectorAll("circle").forEach(c => {
    c.addEventListener("mouseenter", e => { c.setAttribute("r", 6); c.style.opacity = 1; showTip(esc(names[c.dataset.s] || "Segment " + c.dataset.s), e.clientX, e.clientY); });
    c.addEventListener("mousemove", e => showTip(esc(names[c.dataset.s] || "Segment " + c.dataset.s), e.clientX, e.clientY));
    c.addEventListener("mouseleave", () => { c.setAttribute("r", 3.2); c.style.opacity = .62; hideTip(); });
  });
}
function heatmap(cells) {
  const cities = [...new Set(cells.map(c => c.city))].sort(), cats = [...new Set(cells.map(c => c.category))].sort();
  const get = (a, b) => (cells.find(c => c.city === a && c.category === b) || { order_amount: 0 }).order_amount;
  const max = Math.max(...cells.map(c => c.order_amount));
  let s = `<div class="heat" style="grid-template-columns:90px repeat(${cats.length},1fr)"><div></div>${cats.map(c => `<div class="h">${esc(c)}</div>`).join("")}`;
  let di = 0;
  cities.forEach(ci => { s += `<div class="rl">${esc(ci)}</div>`; cats.forEach(ca => { const v = get(ci, ca), p = Math.round(8 + 72 * v / max);
    s += `<div class="c" title="${esc(ci)} / ${esc(ca)}: ${inr(v)}" style="--d:${di++};background:color-mix(in srgb,var(--accent) ${p}%,transparent);${p > 55 ? "color:#fff;font-weight:600" : ""}">${short(v)}</div>`; }); });
  return s + "</div>";
}

// ---- views --------------------------------------------------------------------------------------------------
const VIEW = {};

VIEW.overview = async box => {
  const d = await getDash(), k = d.kpi;
  const cancelRate = 100 * k.cancelled / k.orders;
  const best = d.heat.reduce((a, b) => b.order_amount > a.order_amount ? b : a);
  const topCity = d.cities.slice().sort((a, b) => b.sum - a.sum)[0], prem = d.segments.find(s => s.premium);
  const facts = [
    `Completed revenue <b>${inr0(k.revenue)}</b>`, `Largest cell <b>${esc(best.city)} · ${esc(best.category)}</b> ${inr0(best.order_amount)}`,
    `Top city <b>${esc(topCity.city)}</b> ${inr0(topCity.sum)}`, `Lapse rate <b>${k.lapse_rate.toFixed(2)}%</b> (${int(k.lapsed)} of ${int(k.cohort)})`,
    prem ? `Premium segment <b>${esc(prem.name)}</b> · ${int(prem.count)} customers` : "", `Median order <b>${inr(k.median_order)}</b> vs mean ${inr(k.aov)}`,
    `<b>${int(k.tickets)}</b> tickets triaged with PII masked`, `<b>${d.agent.filter(a => a.ok).length}/${d.agent.length}</b> refund-agent scenarios match the brief`
  ].filter(Boolean).map(t => `<span>${t}</span>`).join("");
  box.innerHTML = `<div class="page">
    <div class="ticker" aria-label="Key facts"><div class="tk">${facts}${facts}</div></div>
    <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))">
      ${kpi("Completed revenue", inr0(k.revenue), `${int(k.completed)} completed orders`, "var(--accent)")}
      ${kpi("Average order", inr(k.aov), `median ${inr(k.median_order)} · right-skewed`, "var(--blue)")}
      ${kpi("Cancel rate", cancelRate.toFixed(1) + "%", `${int(k.cancelled)} of ${int(k.orders)} clean orders`, "var(--bad)")}
      ${kpi("Customers", int(k.customers), `${int(k.cohort)} active before 1 Sep 2025`, "var(--teal)")}
      ${kpi("Lapse rate", k.lapse_rate.toFixed(2) + "%", `${int(k.lapsed)} of ${int(k.cohort)} lapsed in September`, "var(--violet)")}
      ${kpi("Support tickets", int(k.tickets), `${int(k.refunds_ledger)} refund actions in ledger`, "var(--ok)")}
    </div>
    <div class="row r21">
      ${panel("Revenue over time", "Completed orders, 1 Apr to 30 Sep 2025. Hover for the day.", `<div id="rev"></div>`,
        `<div class="seg" role="group" aria-label="Series"><button class="on" data-m="daily">Daily</button><button data-m="cumulative">Cumulative</button></div>`)}
      ${panel("Revenue by city", "Sum of completed order_amount", bars(d.cities.slice().sort((a, b) => b.sum - a.sum).map((c, i) => ({
        label: c.city, value: c.sum, sub: `avg ${inr0(c.mean)} · ${int(c.count)} orders`, color: segColor(i) })), inr0))}
    </div>
    <div class="row r21">
      ${panel("City × category revenue", "Darker = more revenue. Electronics in Bengaluru is the largest cell.", heatmap(d.heat))}
      ${panel("Order outcomes", "After de-duplication: one row per order_id.", `<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">${donut([
        { label:"Completed", value:k.completed, color:"var(--ok)" }, { label:"Cancelled", value:k.cancelled, color:"var(--bad)" }])}
        <div class="legend" style="flex-direction:column"><span><i style="background:var(--ok)"></i>Completed · ${int(k.completed)}</span><span><i style="background:var(--bad)"></i>Cancelled · ${int(k.cancelled)}</span></div></div>`)}
    </div></div>`;
  const draw = m => lineChart(box.querySelector("#rev"), d.daily.days, [{ values: m === "daily" ? d.daily.revenue : d.daily.cumulative }],
    { label: "Revenue chart", name: m === "daily" ? "Revenue that day" : "Cumulative revenue" });
  draw("daily");
  box.querySelectorAll(".seg button").forEach(b => b.onclick = () => {
    box.querySelectorAll(".seg button").forEach(x => x.classList.toggle("on", x === b)); draw(b.dataset.m); });
};

VIEW.customers = async box => {
  const d = await getDash(), segs = d.segments, total = d.segments.reduce((a, s) => a + s.count, 0);
  const idOf = name => Object.keys(d.segment_names).find(k => d.segment_names[k] === name);
  const maxIn = Math.max(...d.kmeans.map(r => r.inertia));
  box.innerHTML = `<div class="page">
    <div class="segcards">${segs.map(s => `<div class="segcard" style="--sc:${segColor(+idOf(s.name))}">
      <h3><span>${esc(s.name)}</span>${s.premium ? '<span class="badge b-info">★ Premium</span>' : ""}</h3>
      <div class="share">${(100 * s.count / total).toFixed(1)}%</div><div class="muted">${int(s.count)} customers</div>
      <div class="mini"><div>Recency<b>${s.mean_recency}d</b></div><div>Orders<b>${s.mean_frequency}</b></div><div>Spend<b>${short(s.mean_monetary)}</b></div></div>
      <div class="act2"><b>Action:</b> ${esc(ACTIONS[s.name] || "")}</div></div>`).join("")}</div>
    <div class="row r21">
      ${panel("Segment map (PCA)", `Each dot is a customer. Two components keep ${((d.pca[0] + d.pca[1]) * 100).toFixed(1)}% of the RFM variance. Cluster numbers are only labels.`, `<div id="pca"></div>
        <div class="legend">${Object.entries(d.segment_names).map(([i, n]) => `<span><i style="background:${segColor(+i)}"></i>${esc(n)}</span>`).join("")}</div>`)}
      ${panel("Choosing K", "Elbow and silhouette for K = 2 to 8. K = 4 has the best silhouette and a clear business story.",
        `<table class="t"><thead><tr><th>K</th><th>Inertia</th><th class="num">Silhouette</th></tr></thead><tbody>${d.kmeans.map(r => `<tr style="${r.chosen ? "background:rgba(252,128,25,.1)" : ""}">
          <td>${r.k}${r.chosen ? ' <span class="badge b-info">chosen</span>' : ""}</td>
          <td style="min-width:120px"><div class="track" style="height:8px;background:var(--inset);border-radius:99px"><div style="height:100%;width:${(100 * r.inertia / maxIn).toFixed(0)}%;border-radius:99px;background:${r.chosen ? "var(--accent)" : "var(--blue)"}"></div></div><span class="muted">${r.inertia}</span></td>
          <td class="num">${r.silhouette.toFixed(3)}</td></tr>`).join("")}</tbody></table>`)}
    </div>
    <div class="row r2">
      ${panel("Customer lookup", "Type a customer id such as C0082. The private view hides personal fields.",
        `<div class="toolbar"><input class="input" id="cid" placeholder="C0082" maxlength="5" aria-label="Customer id" style="width:110px">
          <select class="input" id="cview" aria-label="Detail level"><option value="summary">Summary</option><option value="full">Full details</option><option value="private">Hide sensitive data</option></select>
          <button class="btn primary" id="lookup">Look up</button></div><div id="lookres" class="muted">Result appears here.</div>`)}
      ${panel("Retention list (illustrative)", `Top Premium test-set customers by predicted lapse probability. Premium is a post-hoc whole-window label, so this is <b>not</b> a leakage-free evaluation. ${d.retention.filter(r => r.actually_lapsed).length} of ${d.retention.length} truly lapsed.`,
        `<div class="scroll"><table class="t"><thead><tr><th>Customer</th><th class="num">Lapse probability</th><th>Actually lapsed</th></tr></thead><tbody>${d.retention.map(r => `<tr><td>${esc(r.customer_id)}</td>
          <td class="num"><span style="display:inline-block;width:${Math.round(r.lapse_probability * 90)}px;height:6px;border-radius:9px;background:var(--accent);margin-right:8px;vertical-align:middle"></span>${(r.lapse_probability * 100).toFixed(1)}%</td>
          <td>${r.actually_lapsed ? '<span class="badge b-bad">yes</span>' : '<span class="badge b-ok">no</span>'}</td></tr>`).join("")}</tbody></table></div>`)}
    </div></div>`;
  scatter(box.querySelector("#pca"), d.scatter, d.segment_names, d.pca);
  const go = async () => {
    const id = box.querySelector("#cid").value.trim().toUpperCase(), out = box.querySelector("#lookres");
    if (!/^C\d{4}$/.test(id)) { out.textContent = "A customer id looks like C0082."; return; }
    out.textContent = "Loading…";
    try {
      const r = await fetch(`/api/segments?customer_id=${id}&view=${box.querySelector("#cview").value}`), j = await r.json();
      if (!r.ok) throw new Error(j.error); out.replaceChildren(render.segments(j));
    } catch (e) { out.textContent = e.message; }
  };
  box.querySelector("#lookup").onclick = go; box.querySelector("#cid").addEventListener("keydown", e => { if (e.key === "Enter") go(); });
};

VIEW.triage = async box => {
  const d = await getDash(), T = d.tickets;
  const cnt = (f) => T.reduce((m, t) => (m[f(t)] = (m[f(t)] || 0) + 1, m), {});
  const routes = cnt(t => t.route), statuses = cnt(t => t.status);
  const classified = T.filter(t => t.category), correct = classified.filter(t => t.category === t.true).length;
  const human = T.filter(t => t.route === "human_review").length, high = T.filter(t => t.priority === "HIGH").length;
  const tokens = T.reduce((a, t) => a + t.tokens, 0);
  const cats = ["billing", "delivery", "technical", "fraud"];
  const rcol = { security_team:"var(--bad)", premium_desk:"var(--accent)", support_queue:"var(--blue)", human_review:"var(--warn)" };
  box.innerHTML = `<div class="page">
    <div class="kpis">
      ${kpi("Tickets processed", int(T.length), "in file order, one model call each", "var(--accent)")}
      ${kpi("Auto-classified", int(classified.length), `${correct} correct · ${(100 * correct / classified.length).toFixed(1)}% accuracy`, "var(--ok)")}
      ${kpi("Sent to humans", int(human), "empty, too long or invalid output", "var(--warn)")}
      ${kpi("High priority", int(high), "fraud + premium customers", "var(--bad)")}
      ${kpi("Tokens used", int(tokens), `${(tokens / classified.length).toFixed(0)} per classified ticket (few-shot)`, "var(--violet)")}
    </div>
    <div class="row r3">
      ${panel("Routing", "Where each ticket goes", bars(Object.entries(routes).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v, color: rcol[k] }))))}
      ${panel("Pipeline status", "Input guardrails and output validation", bars(Object.entries(statuses).sort((a, b) => b[1] - a[1]).map(([k, v], i) => ({ label: k, value: v, color: segColor(i) }))))}
      ${panel("Confusion matrix", "True category (rows) vs predicted (columns), few-shot run", `<div class="heat" style="grid-template-columns:70px repeat(4,1fr)"><div></div>${cats.map(c => `<div class="h">${c}</div>`).join("")}
        ${cats.map(a => `<div class="rl">${a}</div>` + cats.map(b => { const v = (d.confusion[a] || {})[b] || 0, diag = a === b;
          return `<div class="c" style="background:${v ? `color-mix(in srgb,${diag ? "var(--ok)" : "var(--bad)"} ${diag ? 55 : 80}%,transparent)` : "var(--inset)"}">${v}</div>`; }).join("")).join("")}</div>`)}
    </div>
    ${panel("Tickets", "Text shown is exactly what the model saw: emails, phones and order ids are replaced by placeholders.", `
      <div class="toolbar"><input class="input" id="q" placeholder="Search text, ticket or customer…" aria-label="Search tickets" style="min-width:240px">
        <select class="input" id="fr" aria-label="Route"><option value="">All routes</option>${Object.keys(routes).map(r => `<option>${r}</option>`).join("")}</select>
        <select class="input" id="fs" aria-label="Status"><option value="">All statuses</option>${Object.keys(statuses).map(r => `<option>${r}</option>`).join("")}</select>
        <span class="muted" id="cnt"></span></div>
      <div class="scroll" style="max-height:520px"><table class="t"><thead><tr><th>Ticket</th><th>Customer / segment</th><th>Status</th><th>Category</th><th>Route</th><th>Priority</th><th>What the model saw</th></tr></thead><tbody id="tb"></tbody></table></div>`)}
  </div>`;
  const tag = s => esc(s).replace(/\[(EMAIL|PHONE|ORDER_ID)\]/g, '<span class="tag">[$1]</span>');
  const draw = () => {
    const q = box.querySelector("#q").value.toLowerCase(), fr = box.querySelector("#fr").value, fs = box.querySelector("#fs").value;
    const rows = T.filter(t => (!fr || t.route === fr) && (!fs || t.status === fs) && (!q || (t.id + t.customer + t.text + t.category).toLowerCase().includes(q)));
    box.querySelector("#cnt").textContent = `${rows.length} of ${T.length}`;
    box.querySelector("#tb").innerHTML = rows.map(t => `<tr><td class="mono">${esc(t.id)}</td><td>${esc(t.customer)}<div class="muted" style="font-size:11px">${esc(t.segment || "no segment")}</div></td>
      <td><span class="badge ${t.status.startsWith("classified") ? "b-ok" : "b-warn"}">${esc(t.status)}</span></td>
      <td>${t.category ? `${esc(t.category)} ${t.category === t.true ? '<span style="color:var(--ok)" title="matches true label">✓</span>' : '<span style="color:var(--bad)" title="differs from true label">✗</span>'}` : '<span class="muted">none</span>'}</td>
      <td><span class="badge" style="background:color-mix(in srgb,${rcol[t.route]} 18%,transparent);color:${rcol[t.route]}">${esc(t.route)}</span></td>
      <td>${t.priority === "HIGH" ? '<span class="badge b-bad">HIGH</span>' : '<span class="muted">NORMAL</span>'}</td>
      <td style="max-width:420px">${t.text ? tag(t.text.length > 150 ? t.text.slice(0, 150) + "…" : t.text) : '<span class="muted">(empty)</span>'}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No tickets match.</td></tr>`;
  };
  ["q", "fr", "fs"].forEach(i => box.querySelector("#" + i).addEventListener("input", draw)); draw();
};

VIEW.agent = async box => {
  const d = await getDash(), A = d.agent, ok = A.filter(a => a.ok).length;
  box.innerHTML = `<div class="page">
    <div class="kpis">
      ${kpi("Scenarios matching brief", `${ok} / ${A.length}`, "status and refund amount", ok === A.length ? "var(--ok)" : "var(--bad)")}
      ${kpi("Model calls", int(A.reduce((a, r) => a + r.calls, 0)), "across all seven runs", "var(--blue)")}
      ${kpi("Tokens", int(A.reduce((a, r) => a + r.tokens, 0)), "estimated, mock model", "var(--violet)")}
      ${kpi("Ledger actions", int(d.ledger.length), "issued or escalated refunds", "var(--accent)")}
    </div>
    ${panel("Scenario results", "Click a row to see the tool steps the agent took. Limits: 6 model calls, 6000 tokens, 10 seconds.", `
      <div class="scroll" style="max-height:none"><table class="t"><thead><tr><th>Scenario</th><th>Request</th><th>Status</th><th class="num">Refund</th><th class="num">Calls</th><th class="num">Tokens</th><th>Brief</th></tr></thead><tbody>
      ${A.map((a, i) => `<tr data-i="${i}" style="cursor:pointer"><td><b>${esc(a.id)}</b></td><td style="max-width:340px">${esc(a.message)}</td>
        <td><span class="badge ${{ REFUND:"b-ok", ESCALATE:"b-warn", DENIED:"b-bad", NOT_FOUND:"b-bad" }[a.status] || "b-info"}">${esc(a.status)}</span></td>
        <td class="num">${a.refund ? inr(a.refund) : "—"}</td><td class="num">${a.calls}</td><td class="num">${int(a.tokens)}</td>
        <td>${a.ok ? '<span class="badge b-ok">✓ match</span>' : '<span class="badge b-bad">✗ differs</span>'}</td></tr>
        <tr hidden id="st${i}"><td colspan="7"><div class="muted">${esc(a.answer)}</div><ul class="timeline">${a.steps.map(s => `<li><code>${esc(s.tool)}</code> <span class="muted mono">${esc(JSON.stringify(s.args))}</span><pre>→ ${esc(JSON.stringify(s.obs))}</pre></li>`).join("") || '<li class="muted">No tool was called.</li>'}</ul></td></tr>`).join("")}
      </tbody></table></div>`)}
    <div class="row r2">
      ${panel("Safe stopping", "Three limits protect against runaway agents. Demo statuses are recorded in the README.", `
        <table class="t"><tbody><tr><td>Max iterations (S7 loop)</td><td><span class="badge b-warn">FALLBACK_MAX_ITERATIONS</span></td></tr>
        <tr><td>Token limit 200 (S1)</td><td><span class="badge b-warn">FALLBACK_TOKEN_LIMIT</span></td></tr>
        <tr><td>Time limit 0 s (S1)</td><td><span class="badge b-warn">FALLBACK_TIMEOUT</span></td></tr>
        <tr><td>Crash after tool 2, then resume</td><td><span class="badge b-ok">REFUND 128.25 · 4 tools, no repeats</span></td></tr></tbody></table>`)}
      ${panel("Refund ledger", "Every money-moving tool call is appended here (outputs/refund_ledger.jsonl).", `<div class="scroll"><table class="t"><thead><tr><th>Time</th><th>Tool</th><th>Order</th><th class="num">Amount</th></tr></thead><tbody>
        ${d.ledger.map(l => `<tr><td class="mono">${esc((l.timestamp || "").replace("T", " "))}</td><td><span class="badge ${l.tool === "issue_refund" ? "b-ok" : "b-warn"}">${esc(l.tool)}</span></td><td class="mono">${esc(l.order_id)}</td><td class="num">${inr(l.refund_inr)}</td></tr>`).join("") || '<tr><td colspan="4" class="empty">No entries.</td></tr>'}</tbody></table></div>`)}
    </div></div>`;
  box.querySelectorAll("tr[data-i]").forEach(tr => tr.onclick = () => { const r = box.querySelector("#st" + tr.dataset.i); r.hidden = !r.hidden; });
};

VIEW.quality = async (box, force) => {
  box.innerHTML = `<div class="page"><div class="skel" style="height:110px"></div><div class="skel" style="height:300px"></div></div>`;
  const r = await fetch("/api/checks" + (force ? "?refresh=1" : "")), c = await r.json();
  if (!r.ok) throw new Error(c.error || "Checks failed to run");
  checksData = c; updateBadge();
  const allOk = c.passed === c.total, parts = Object.entries(c.summary);
  const NAMES = { A:"Part A · Data", B:"Part B · Models", C:"Part C · Triage", D:"Part D · RAG & agent", Repo:"Repository" };
  box.innerHTML = `<div class="page">
    <div class="banner ${allOk ? "" : "bad"}"><div class="ring" style="--p:${100 * c.passed / c.total};--rc:${allOk ? "var(--ok)" : "var(--bad)"}"><span>${Math.round(100 * c.passed / c.total)}%</span></div>
      <div><h2>${allOk ? "All checkpoints passed" : `${c.total - c.passed} checkpoint(s) failing`}</h2><p>${c.passed} of ${c.total} checks · re-derived from the generated files in ${c.seconds}s</p></div>
      <span class="spacer"></span><button class="btn primary" id="rerun">Re-run checks</button></div>
    <div class="partcards">${parts.map(([p, s]) => `<button class="partcard" data-p="${p}"><div class="ring" style="--p:${100 * s.passed / s.total};--rc:${s.passed === s.total ? "var(--ok)" : "var(--bad)"}"><span>${s.passed}/${s.total}</span></div>
      <div><b>${NAMES[p] || p}</b><small>${s.passed === s.total ? "all passing" : (s.total - s.passed) + " failing"}</small></div></button>`).join("")}</div>
    ${panel("Checks", "Filter by part, or show only failures.", `<div class="toolbar"><input class="input" id="cq" placeholder="Search checks…" aria-label="Search checks" style="min-width:220px">
        <div class="seg" role="group" aria-label="Filter"><button class="on" data-f="all">All</button><button data-f="fail">Failing</button></div><span class="muted" id="ccnt"></span></div>
      <div class="scroll" style="max-height:560px"><table class="t"><thead><tr><th style="width:26px"></th><th>Part</th><th>Check</th><th>Expected</th><th>Actual</th></tr></thead><tbody id="ctb"></tbody></table></div>`)}</div>`;
  let part = "", filt = "all";
  const draw = () => {
    const q = box.querySelector("#cq").value.toLowerCase();
    const rows = c.rows.filter(x => (!part || x.part === part) && (filt === "all" || !x.passed) && (!q || (x.name + x.expected + x.actual).toLowerCase().includes(q)));
    box.querySelector("#ccnt").textContent = `${rows.length} shown`;
    box.querySelector("#ctb").innerHTML = rows.map(x => `<tr><td><span class="dot ${x.passed ? "p" : "f"}" title="${x.passed ? "pass" : "fail"}"></span></td><td>${esc(x.part)}</td><td>${esc(x.name)}</td>
      <td class="mono muted" style="max-width:260px;word-break:break-word">${esc(x.expected)}</td><td class="mono" style="max-width:260px;word-break:break-word;color:${x.passed ? "inherit" : "var(--bad)"}">${esc(x.actual)}</td></tr>`).join("") || '<tr><td colspan="5" class="empty">Nothing to show.</td></tr>';
  };
  box.querySelector("#cq").addEventListener("input", draw);
  box.querySelectorAll(".seg button").forEach(b => b.onclick = () => { filt = b.dataset.f; box.querySelectorAll(".seg button").forEach(x => x.classList.toggle("on", x === b)); draw(); });
  box.querySelectorAll(".partcard").forEach(b => b.onclick = () => { part = part === b.dataset.p ? "" : b.dataset.p; box.querySelectorAll(".partcard").forEach(x => x.classList.toggle("on", x.dataset.p === part)); draw(); });
  box.querySelector("#rerun").onclick = e => { e.target.disabled = true; e.target.textContent = "Running…"; show("quality", true); };
  draw();
};

// ---- navigation ------------------------------------------------------------------------------------------------
function updateBadge() {
  const b = document.querySelector("#nav-quality .count"); if (!b || !checksData) return;
  b.textContent = checksData.passed === checksData.total ? "✓ " + checksData.total : `${checksData.total - checksData.passed} ✗`;
  b.className = "count " + (checksData.passed === checksData.total ? "good" : "badc");
}
function buildNav() {
  PAGES.forEach(p => {
    const b = el("button", "navlink" + (p.featured ? " featured" : "")); b.id = "nav-" + p.id; b.dataset.page = p.id;
    b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[p.id === "chat" ? "chat" : p.id]}</svg><span>${p.label}</span>` +
      (p.featured ? '<em class="aitag">AI</em>' : "") + (p.id === "quality" ? '<span class="count"></span>' : "");
    b.onclick = () => { location.hash = "#/" + p.id; closeMenu(); };
    $("nav").append(b);
    if (p.featured) $("nav").append(el("div", "navsep"));
  });
  // floating shortcut to the chat, visible on every dashboard page
  const fab = el("button", "fab"); fab.id = "fab"; fab.type = "button"; fab.setAttribute("aria-label", "Ask Copilot");
  fab.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg><span>Ask Copilot</span>';
  fab.onclick = () => { location.hash = "#/chat"; };
  document.body.append(fab);
}
async function show(id, force) {
  const page = PAGES.find(p => p.id === id) || PAGES.find(p => p.id === "overview");
  $("fab").hidden = page.id === "chat";
  PAGES.forEach(p => { $("view-" + p.id).hidden = p.id !== page.id; $("nav-" + p.id).classList.toggle("active", p.id === page.id);
    $("nav-" + p.id).setAttribute("aria-current", p.id === page.id ? "page" : "false"); });
  $("title").textContent = page.title; $("subtitle").textContent = page.sub; document.title = page.title + " · Instamart Copilot";
  $("chatside").hidden = page.id !== "chat"; hideTip(); store.set("ic.page", page.id);
  if (page.id === "chat") { scrollDown(); $("input").focus(); return; }
  const box = $("view-" + page.id);
  skeleton(box);                       // always re-render so every visit replays its entrance animation
  try {
    await VIEW[page.id](box, force);
    box.querySelectorAll("table.t tbody").forEach(tb => [...tb.rows].slice(0, 40).forEach((r, i) => r.style.setProperty("--r", i)));
    afterBoot(() => { if (window.FX) FX.countUp(box); });      // effects are optional: never let them break a page
  } catch (e) { failure(box, e, () => show(id, true)); }
}
buildNav();
window.addEventListener("hashchange", () => show((location.hash.match(/#\/(\w+)/) || [])[1] || "overview"));
document.addEventListener("keydown", e => {                       // g then a letter: quick page switch
  if (e.target.matches("input, textarea, select") || e.ctrlKey || e.metaKey) return;
  if (e.key === "g") { window._g = Date.now(); return; }
  if (Date.now() - (window._g || 0) < 900) { const m = { o:"overview", c:"customers", t:"triage", a:"agent", q:"quality", m:"chat" }[e.key]; if (m) location.hash = "#/" + m; window._g = 0; }
});
// ---- landing: every load/refresh plays the logo intro, then opens the Overview -----------------------------------------
const splash = $("splash"), reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
window.history.replaceState(null, "", location.pathname + "#/overview");   // (app.js has its own global `history` array, so use window.history)        // ignore any saved page or #hash: Overview is always the landing page
const firstPage = show("overview");                                      // loads data while the intro plays
let skipIntro = () => {};
const minIntro = new Promise(res => { const t = setTimeout(res, reduceMotion ? 400 : 3600); skipIntro = () => { clearTimeout(t); res(); }; });
const msgs = [[0, "Warming up the models…"], [1300, "Loading segments and orders…"], [2500, "Checking the dashboards…"], [3300, "Ready"]];
msgs.forEach(([ms, text]) => setTimeout(() => { const s = $("spstatus"); if (s) s.textContent = text; }, ms));
$("spskip").onclick = () => skipIntro();
document.addEventListener("keydown", e => { if ($("splash") && (e.key === "Escape" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); skipIntro(); } });
function endIntro() {
  if (!splash.isConnected) return;
  splash.classList.add("out");
  document.body.classList.remove("booting");                              // releases all paused entrance animations
  bootQueue.splice(0).forEach(fn => fn());
  setTimeout(() => splash.remove(), 1100);
}
Promise.race([Promise.all([minIntro, firstPage.catch(() => {})]), new Promise(r => setTimeout(r, 9000))]).then(endIntro);
