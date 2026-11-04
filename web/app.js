const TOOLS = {
  auto:     { label:"Auto",           hint:"Picks the tool for you" },
  segments: { label:"Customer segments", hint:"Counts, or look up C0082" },
  policy:   { label:"Policy question", hint:"Answers from policy documents" },
  refund:   { label:"Refund agent",    hint:"Give an order id" },
  classify: { label:"Classify ticket", hint:"Billing, delivery, technical, fraud" },
  redact:   { label:"Hide personal data", hint:"Emails, phones, order ids" }
};
const EXAMPLES = [
  ["How many customers are in each segment?", "Customer segments"],
  ["Show customer C0082", "Customer segments"],
  ["Who must approve a refund above INR 1000?", "Policy question"],
  ["Refund ORD-100048", "Refund agent"],
  ["There is an unauthorized transaction on my card. Call 9876543210.", "Classify ticket"]
];
const NEXT = {   // "Try next" suggestions after an answer, per tool
  segments: ["Show customer C0005", "Who must approve a refund above INR 1000?"],
  policy:   ["What is the delivery fee on small orders?", "Refund ORD-100048", "How fast must a fraud ticket reach the security team?"],
  refund:   ["Refund ORD-100145", "Refund ORD-100001", "Refund ORD-999999"],
  classify: ["Why was I charged twice?", "The app crashes every time I open the cart.", "How many customers are in each segment?"],
  redact:   ["Call me on 9562272031 or email user118@example.com about ORD-100816", "Show customer C0082"]
};
const VIEWS = { summary:"Summary only", full:"Show full details", private:"Hide sensitive data" };
const STALE = "⚠ The server is running an older version of the code. Stop it (Ctrl+C in its terminal), start it again with python app.py, then press Ctrl+F5 here.";

// Decide which tool a message belongs to (used in Auto mode). Pure function, easy to test.
// Order matters: the most specific signals come first.
function detect(text) {
  const t = text.trim(), has = re => re.test(t);
  const orderId = has(/ORD-\d{6}/i);
  const ticketWords = has(/\b(charged|double|twice|deducted|crash(es|ed|ing)?|freez\w*|rider|fraud|unauthori[sz]ed|hacked|stolen|login|otp|not (arrived|delivered|received)|never (received|arrived)|invoice|wrong amount)\b/i);
  if (has(/^(hi|hello|hey|help|thanks?|thank you|ok|okay|test|what can you do)\b[\s\w!.?]{0,20}$/i)) return "help";
  if (has(/^(redact|hide|mask|anonymi[sz]e|remove personal|strip personal)\b/i) || has(/\b(redact|mask)\b.*(:|this)/i)) return "redact";
  if (orderId && (has(/refund|money back|reimburs|return/i) || t.replace(/ORD-\d{6}/i, "").trim().length < 3)) return "refund";
  // A message that is only contact details ("Call me on 95... or email a@b.com about ORD-...") has no problem to
  // classify: offer to hide the personal details instead.
  if (has(/[\w.+-]+@[\w-]+\.[\w.]+|\b[6-9]\d{9}\b/) && !ticketWords) {
    const rest = t.replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, " ").replace(/\b[6-9]\d{9}\b/g, " ").replace(/ORD-\d{6}/gi, " ").trim();
    if (rest.split(/\s+/).filter(Boolean).length <= 8) return "redact";
  }
  if (has(/\bC\d{4}\b/i) && !orderId) return "segments";
  if (has(/\b(segments?|premium|loyal|lapsing|occasional)\b/i) || has(/(how many|number of|count of|list|show).{0,25}customers?/i)) return "segments";
  const questionForm = has(/\?\s*$/) || has(/^(who|what|when|where|which|why|how|can|could|is|are|does|do|did|will|should|tell me|explain)\b/i);
  // Ticket words ("fraud", "charged"...) also appear in questions about the rules, e.g. "How fast must a fraud
  // ticket reach the security team?". A general question without "I / my / me" is a policy question; a
  // first-person complaint ("Why was I charged twice?") is a ticket.
  const firstPerson = has(/\b(i|my|me|mine|we|our)\b/i);
  const policyStart = has(/^(how (many|long|fast|soon|much|often)|what (is|are|happens|time)|who (must|can|should|approves?)|when (are|is|do|will)|can i|do i)\b/i);
  if (ticketWords && (policyStart || (questionForm && !firstPerson))) return "policy";
  if (ticketWords) return "classify";
  const policyWords = has(/\b(policy|policies|fee|fees|eligible|eligibility|window|within|cash on delivery|cod|wallet|coupon|privacy|deleted|escalat\w*|approve[sd]?|approval|human|how long|how many days|rules?|terms|supported cit\w+|refundable)\b/i);
  if (questionForm || policyWords) return "policy";
  return "classify";
}

const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
let mode = "auto", busy = false, fewShot = true, view = "summary";
let history = [];                       // saved conversation: {t:"user",...} and {t:"bot",...} entries
let recall = -1;                        // position while browsing earlier messages with the arrow keys

// ---- small helpers: storage, toast, clipboard -------------------------------------------------
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage may be blocked: ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }
};
let toastTimer;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 1600); }
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied"); return; } catch (e) { /* fall through */ }
  const ta = el("textarea"); ta.value = text; document.body.append(ta); ta.select();
  try { document.execCommand("copy"); toast("Copied"); } catch (e) { toast("Copy not available in this browser"); }
  ta.remove();
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t; store.set("ic.theme", t);
  $("theme").setAttribute("aria-label", t === "dark" ? "Switch to light theme" : "Switch to dark theme");
  document.dispatchEvent(new CustomEvent("themechange", { detail: t }));
}

// ---- sidebar, modes -----------------------------------------------------------------------------
function buildSide() {
  for (const [k, t] of Object.entries(TOOLS)) {
    const b = el("button", "tool"); b.id = "tool-" + k; b.append(t.label, el("small", "", t.hint)); b.onclick = () => { setMode(k); closeMenu(); }; $("tools").append(b);
    const p = el("button", "pill", t.label); p.id = "pill-" + k; p.onclick = () => setMode(k); $("modes").append(p);
  }
  const l = el("label", "few"); const c = el("input"); c.type = "checkbox"; c.id = "few"; c.checked = true; c.onchange = () => fewShot = c.checked;
  l.append(c, "few-shot prompt"); l.title = "Used when classifying tickets: more accurate, more tokens"; $("modes").append(l);
  const v = el("label", "few"); v.style.marginLeft = "12px"; const s = el("select", "sel"); s.id = "view"; s.setAttribute("aria-label", "Customer view");
  for (const [k, name] of Object.entries(VIEWS)) { const o = el("option", "", name); o.value = k; s.append(o); }
  s.onchange = () => view = s.value; v.append("Customer view: ", s); v.title = "How much of a customer's data to show"; $("modes").append(v);
}
function setMode(k) {
  mode = k;
  for (const key of Object.keys(TOOLS)) {
    $("tool-" + key).classList.toggle("active", key === k); $("pill-" + key).classList.toggle("active", key === k);
    $("pill-" + key).setAttribute("aria-pressed", String(key === k));
  }
  $("input").focus();
}
function renderRecent() {
  const seen = new Set(), items = [];
  for (let i = history.length - 1; i >= 0 && items.length < 8; i--) {
    const h = history[i]; if (h.t === "user" && !seen.has(h.src)) { seen.add(h.src); items.push(h.src); }
  }
  const box = $("recent"); box.replaceChildren();
  if (!items.length) { box.append(el("div", "none", "Your questions will appear here")); return; }
  items.forEach(txt => { const b = el("button", "recent", txt); b.title = txt; b.onclick = () => { closeMenu(); send(txt); }; box.append(b); });
}
function closeMenu() { $("side").classList.remove("open"); $("backdrop").classList.remove("open"); }

// ---- conversation rendering ---------------------------------------------------------------------
function nearBottom() { const c = $("chat"); return c.scrollHeight - c.scrollTop - c.clientHeight < 140; }
function scrollDown() { const c = $("chat"); c.scrollTop = c.scrollHeight; updateJump(); }
function updateJump() { $("jump").classList.toggle("show", !nearBottom()); }

function userNode(e, restored) {
  const m = el("div", "msg user" + (restored ? " restored" : "")), b = el("div", "bubble");
  b.append(el("span", "tag-mode", e.label), document.createTextNode(e.display)); m.append(b); return m;
}
function botNode(e, restored) {
  const m = el("div", "msg bot" + (restored ? " restored" : "")), b = el("div", "bubble");
  b.append(render[e.key](e.data));
  const act = el("div", "actions");                                     // copy, ask again, response time
  const copy = el("button", "act", "⧉ Copy"); copy.setAttribute("aria-label", "Copy this answer"); copy.onclick = () => copyText(toText(e.key, e.data));
  act.append(copy);
  if (e.src && e.key !== "help" && e.key !== "error") {
    const again = el("button", "act", "↻ Ask again"); again.setAttribute("aria-label", "Ask again"); again.onclick = () => send(e.src, e.key, e.view); act.append(again);
  }
  if (e.ms !== undefined) act.append(el("span", "meta", `⏱ ${(e.ms / 1000).toFixed(2)} s`));
  b.append(act);
  const nxt = (NEXT[e.key] || []).filter(x => x !== e.src).slice(0, 3);
  if (nxt.length && e.key !== "error") {
    const row = el("div", "chips"); row.append(el("span", "muted", "Try next:"));
    nxt.forEach(x => { const c = el("button", "chip small", x.length > 44 ? x.slice(0, 42) + "…" : x); c.title = x; c.onclick = () => send(x); row.append(c); });
    b.append(row);
  }
  if (e.auto && e.src && e.key !== "help" && e.key !== "error") b.append(runAsChips(e.src, e.key));   // Auto can guess wrong
  m.append(el("div", "avatar", "IC"), b); return m;
}
function addUser(e) { $("log").append(userNode(e)); scrollDown(); }
function addBot(e) { const n = botNode(e); $("log").append(n); scrollDown(); return n; }
function typing() {
  const d = el("div", "typing"); d.append(el("span"), el("span"), el("span"));
  const m = el("div", "msg bot"), b = el("div", "bubble"); b.append(d);
  m.append(el("div", "avatar", "IC"), b); $("log").append(m); scrollDown(); return m;
}
function persist() { store.set("ic.chat", history.slice(-60)); renderRecent(); }

function welcome() {
  $("log").replaceChildren();
  const w = el("div"); w.append(el("div", "big", "Hi! What would you like to check?"),
    el("div", "muted", "Ask a policy question, request a refund, look up customers, classify a support ticket or hide personal details. In Auto mode I pick the tool from your message."));
  const chips = el("div", "chips");
  EXAMPLES.forEach(([q, t]) => { const c = el("button", "chip", q); c.append(el("small", "", t)); c.onclick = () => { setMode("auto"); send(q); }; chips.append(c); });
  w.append(chips);
  const m = el("div", "msg bot"), b = el("div", "bubble"); b.append(w); m.append(el("div", "avatar", "IC"), b); $("log").append(m);
}
function newChat() { history = []; store.del("ic.chat"); welcome(); renderRecent(); $("input").focus(); }

// ---- sending -------------------------------------------------------------------------------------
// forcedKey: run a specific tool (used by the "Run as" and "Ask again" buttons); viewArg: customer detail level.
async function send(textArg, forcedKey, viewArg) {
  const text = (textArg ?? $("input").value).trim();
  if (!text || busy) return;
  busy = true; $("send").disabled = true; $("input").value = ""; resize(); recall = -1;
  if (!history.length) $("log").replaceChildren();              // the welcome card is not part of the saved chat
  const auto = !forcedKey && mode === "auto";
  const key = forcedKey || (auto ? detect(text) : mode);
  const useView = viewArg || view;
  const name = key === "help" ? "Help" : TOOLS[key].label;
  const isCustomer = key === "segments" && /\bC\d{4}\b/i.test(text);
  const u = { t:"user", src:text, display: text + (isCustomer ? `  ·  ${VIEWS[useView]}` : ""), label: name + (auto ? " (auto)" : "") };
  history.push(u); addUser(u);
  if (key === "help") {
    const h = { t:"bot", key:"help", data:{}, src:text }; history.push(h); addBot(h); persist();
    busy = false; $("send").disabled = false; $("input").focus(); return;
  }
  const wait = typing(), t0 = performance.now();
  let entry;
  try {
    let resp;
    if (key === "segments") {
      const id = (text.match(/\bC\d{4}\b/i) || [""])[0];
      resp = await fetch("/api/segments?customer_id=" + encodeURIComponent(id) + "&view=" + useView);
    } else {
      const body = { text, question: text, few_shot: fewShot, order_id: (text.match(/ORD-\d{6}/i) || [text])[0] };
      resp = await fetch("/api/" + key, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body) });
    }
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Request failed");
    entry = { t:"bot", key, data, src:text, auto, view: key === "segments" ? useView : undefined, ms: performance.now() - t0 };
  } catch (err) { entry = { t:"bot", key:"error", data:{ message: err.message }, src:text }; }
  wait.remove(); history.push(entry); addBot(entry); persist();
  busy = false; $("send").disabled = false; $("input").focus();
}

function runAsChips(text, usedKey) {
  const row = el("div", "chips"); row.append(el("span", "muted", "Not what you wanted? Run as:"));
  for (const k of Object.keys(TOOLS)) if (k !== "auto" && k !== usedKey) {
    const c = el("button", "chip small", TOOLS[k].label); c.onclick = () => send(text, k); row.append(c);
  }
  return row;
}

// ---- plain-text version of an answer (Copy button and Export) ------------------------------------------
function toText(key, d) {
  switch (key) {
    case "redact": return d.redacted;
    case "policy": return `${d.answer}\n(Searched: ${d.sources.join(", ")})`;
    case "classify": return d.category ? `Category: ${d.category} (${d.status})` : `Needs human review (${d.status})`;
    case "refund": return d.error ? d.error : `${d.status}: ${d.final_answer}` + (d.refund_inr ? ` INR ${d.refund_inr.toFixed(2)}` : "") +
        "\n" + d.steps.map((s, i) => `${i + 1}. ${s.tool} ${JSON.stringify(s.observation)}`).join("\n");
    case "segments": {
      let s = d.segments.map(x => `${x.name}: ${x.count} customers`).join("\n") + `\nTotal: ${d.total}`;
      if (d.customer && d.customer.fields) s += `\n\n${d.customer.customer_id} - ${d.customer.segment}\n` + d.customer.fields.map(([k, v]) => `${k}: ${v}`).join("\n");
      return s;
    }
    case "error": return "Error: " + d.message;
    default: return "Instamart Customer Intelligence Copilot";
  }
}

// ---- answer cards ---------------------------------------------------------------------------------------
const card = (...kids) => { const c = el("div", "card"); c.append(...kids); return c; };
const tagged = (text, box) => text.split(/(\[EMAIL\]|\[PHONE\]|\[ORDER_ID\])/).forEach(p => box.append(/^\[/.test(p) ? el("span", "tag", p) : document.createTextNode(p)));
const render = {
  error(d) { return card(el("span", "badge b-bad", "Error"), el("div", "", d.message)); },
  redact(d) {
    const box = el("div", "redacted"); tagged(d.redacted, box);
    const c = d.counts || { EMAIL: 0, PHONE: 0, ORDER_ID: 0 };
    return card(el("div", "muted", "Personal details hidden:"), box, el("div", "muted", `${c.EMAIL} email · ${c.PHONE} phone · ${c.ORDER_ID} order id`));
  },
  classify(d) {
    const parts = [el("span", "badge " + (d.human_review ? "b-warn" : "b-ok"), d.status)];
    // Where the pipeline would send this ticket (same rules as outputs/triage_results.csv; a lookup by customer
    // is not possible here, so a Premium customer's ticket would go to the premium desk instead of the queue).
    if (d.category) {
      const route = d.category === "fraud" ? "security team, HIGH priority" : "support queue, NORMAL priority (premium customers: premium desk, HIGH)";
      parts.push(el("div", "big", "Category: " + d.category), el("div", "muted", `${d.prompt} prompt · ${d.tokens} tokens`), el("div", "muted", "Route: " + route));
    } else {
      parts.push(el("div", "big", "Needs human review"), el("div", "muted", "Route: human review (" + d.status + "). No valid category was accepted, so a person should read this ticket."));
    }
    const stale = d.redacted === undefined;     // an older server does not send counts/redacted
    if (stale) parts.push(el("div", "lock", STALE));
    const counts = d.counts || { EMAIL: 0, PHONE: 0, ORDER_ID: 0 }, red = d.redacted || "";
    const n = counts.EMAIL + counts.PHONE + counts.ORDER_ID;
    if (n) { const box = el("div", "redacted"); tagged(red, box);
      parts.push(el("div", "muted", "🔒 What the model actually saw (" + n + " personal detail" + (n > 1 ? "s" : "") + " hidden):"), box); }
    const KEYWORDS = /\b(charged|invoice|bill|refund|deducted|payment|unauthorized|fraud|hacked|stolen|arrived|rider|delivery|delivered|late|app|crash|login|otp|error|freezes)\b/i;
    if (d.category && !stale && !KEYWORDS.test(red))
      parts.push(el("div", "lock", "No clear keyword was found in this text, so the offline mock model fell back to its default category. A real model would judge by meaning."));
    return card(...parts);
  },
  policy(d) {
    return card(el("span", "badge " + (d.found ? "b-ok" : "b-warn"), d.found ? "Found in policy" : "Not covered by the policies"),
      el("div", "big", d.answer), el("div", "muted", "Searched: " + d.sources.join(", ")));
  },
  refund(d) {
    if (d.error) return card(el("span", "badge b-bad", "Check input"), el("div", "", d.error));
    const cls = { REFUND:"b-ok", ESCALATE:"b-warn", DENIED:"b-bad", NOT_FOUND:"b-bad" }[d.status] || "b-info";
    const ul = el("ul", "steps");
    d.steps.forEach(s => { const li = el("li"); li.append(el("code", "", s.tool), el("pre", "", JSON.stringify(s.observation))); ul.append(li); });
    return card(el("span", "badge " + cls, d.status), el("div", "big", d.final_answer),
      el("div", "muted", `${d.model_calls} model calls · ${d.tokens} tokens` + (d.refund_inr ? ` · INR ${d.refund_inr.toFixed(2)}` : "")), ul);
  },
  segments(d) {
    const max = Math.max(...d.segments.map(s => s.count)), kids = [], fills = [];
    d.segments.forEach(s => { const b = el("div", "bar"), top = el("div", "top");
      top.append(el("span", "", s.name + (s.premium ? " ★ Premium" : "")), el("span", "muted", `${s.count} customers`));
      const track = el("div", "track"), fill = el("div", "fill"); fill.dataset.w = (100 * s.count / max) + "%"; fills.push(fill); track.append(fill);
      b.append(top, track, el("div", "muted", `avg spend INR ${s.mean_monetary.toLocaleString()} · ${s.mean_frequency} orders · last order ${s.mean_recency} days ago`)); kids.push(b); });
    requestAnimationFrame(() => requestAnimationFrame(() => fills.forEach(f => f.style.width = f.dataset.w)));   // animate the bars in
    kids.push(el("div", "muted", `Total: ${d.total} customers with at least one completed order.`));
    if ("customer" in d) { const c = d.customer;
      if (!c) kids.push(el("hr", "sep"), el("div", "big", "No segment"), el("div", "muted", `${d.requested_id} has no completed order, or does not exist.`));
      else if (!c.fields) kids.push(el("hr", "sep"), el("div", "lock", STALE));
      else {
        kids.push(el("hr", "sep"), el("span", "badge b-info", VIEWS[c.view]),
          el("div", "big", `${c.customer_id}: ${c.segment}${c.premium ? " ★" : ""}`), el("div", "muted", "Suggested action: " + c.action));
        const g = el("div", "grid"); kids.push(g);
        c.fields.forEach(([k, v]) => { const s = el("div", "stat", k); s.append(el("b", "", String(v))); g.append(s); });
        if (c.hidden.length) kids.push(el("div", "lock", "🔒 Withheld: " + c.hidden.join(", ")));
        const row = el("div", "chips"); row.append(el("span", "muted", "Show this customer as:"));
        for (const [k, name] of Object.entries(VIEWS)) if (k !== c.view) {
          const b = el("button", "chip small", name); b.onclick = () => send(d.requested_id, "segments", k); row.append(b); }
        kids.push(row); } }
    return card(...kids);
  },
  help() {
    const c = el("div"); c.append(el("div", "big", "Here is what I can do"));
    [["Customer segments", "how many customers are in each segment? · C0082"], ["Policy question", "Who must approve a refund above INR 1000?"],
     ["Refund agent", "Refund ORD-100048"], ["Classify a ticket", "There is an unauthorized transaction on my card"],
     ["Hide personal data", "hide: call 9123456789 or mail a@b.com"]].forEach(([k, ex]) => {
      const p = el("div", "muted"); p.append(el("b", "", k + ": "), ex); c.append(p); });
    c.append(el("div", "muted", "Auto mode picks the tool from your message. If it picks wrong, use the \"Run as\" buttons under the answer."));
    return card(...c.childNodes);
  }
};

// ---- export ---------------------------------------------------------------------------------------------
function exportChat() {
  if (!history.length) { toast("Nothing to export yet"); return; }
  const lines = history.map(h => h.t === "user" ? `YOU (${h.label}): ${h.display}` : `COPILOT:\n${toText(h.key, h.data)}`);
  const blob = new Blob([lines.join("\n\n") + "\n"], { type:"text/plain" });
  const a = el("a"); a.href = URL.createObjectURL(blob); a.download = "copilot-chat.txt"; document.body.append(a); a.click(); a.remove(); toast("Chat exported");
}

// ---- input behaviour -------------------------------------------------------------------------------------
function resize() { const i = $("input"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 160) + "px"; }
function userTexts() { return history.filter(h => h.t === "user").map(h => h.src); }
$("input").addEventListener("input", resize);
$("input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); return; }
  const i = $("input"), past = userTexts();
  if (e.key === "ArrowUp" && past.length && (i.value === "" || recall >= 0)) {          // browse earlier messages
    e.preventDefault(); recall = recall < 0 ? past.length - 1 : Math.max(0, recall - 1); i.value = past[recall]; resize();
  } else if (e.key === "ArrowDown" && recall >= 0) {
    e.preventDefault(); recall++;
    if (recall >= past.length) { recall = -1; i.value = ""; } else i.value = past[recall];
    resize();
  } else if (e.key === "Escape") { i.value = ""; recall = -1; resize(); }
});
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); newChat(); return; }
  const tag = (document.activeElement || {}).tagName;
  if (e.key === "/" && tag !== "TEXTAREA" && tag !== "INPUT" && tag !== "SELECT") { e.preventDefault(); $("input").focus(); }
});
$("send").onclick = () => send();
$("newchat").onclick = newChat;
$("theme").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
$("export").onclick = exportChat;
$("jump").onclick = scrollDown;
$("chat").addEventListener("scroll", updateJump);
$("menu").onclick = () => { $("side").classList.add("open"); $("backdrop").classList.add("open"); };
$("backdrop").onclick = closeMenu;

// ---- start-up: theme, sidebar, and the saved conversation ------------------------------------------------
applyTheme(store.get("ic.theme", window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
buildSide(); setMode("auto");
history = store.get("ic.chat", []).filter(h => h && (h.t === "user" || (h.t === "bot" && render[h.key])));
if (history.length) {
  history.forEach(h => $("log").append(h.t === "user" ? userNode(h, true) : botNode(h, true)));
  $("chat").style.scrollBehavior = "auto"; scrollDown(); $("chat").style.scrollBehavior = "";
} else welcome();
renderRecent();
