"use strict";
/* WhyItMatters web UI. No build step: plain DOM + canvas, fed by the Server-Sent Events stream. */

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const I18N = {
  en: {
    lang: "Language", mode: "Show me", club: "My club", player: "My player", none: "— none —",
    fan: "Plain words", focus: "Player focus", analyst: "The numbers", empty: "Nothing yet. Kick off the match.",
    full: "Full time", moments: "Moments that decided it", recap: "Recap", close: "Close", foryou: "for you",
    verified: "verified", kickoff: "Kick-off",
  },
  es: {
    lang: "Idioma", mode: "Quiero ver", club: "Mi club", player: "Mi jugador", none: "— ninguno —",
    fan: "En cristiano", focus: "Foco en un jugador", analyst: "Los números", empty: "Todavía nada. Empieza el partido.",
    full: "Final", moments: "Los momentos que decidieron", recap: "Resumen", close: "Cerrar", foryou: "para ti",
    verified: "verificado", kickoff: "Saque inicial",
  },
  ca: {
    lang: "Idioma", mode: "Vull veure", club: "El meu club", player: "El meu jugador", none: "— cap —",
    fan: "En paraules planes", focus: "Focus en un jugador", analyst: "Els números", empty: "Encara res. Comença el partit.",
    full: "Final", moments: "Els moments que ho van decidir", recap: "Resum", close: "Tanca", foryou: "per a tu",
    verified: "verificat", kickoff: "Servei inicial",
  },
};

const METRICS = {
  possession_share: "Possession", pass_completion: "Pass completion", field_tilt: "Field tilt",
  turnovers_per_min: "Turnovers per minute", window_minutes: "Window (minutes)", shot_xg: "Shot xG",
  score_home: "Home goals", score_away: "Away goals", player_completed_passes: "Completed passes",
  carry_speed_kmh: "Carry speed (km/h)", team_xg: "Team xG",
};
const KINDS = { goal: "goal", state_shift: "shift", big_chance: "chance", top_speed: "speed", pass_master: "passing" };

const S = {};
let es = null;
let personalToken = 0;
let drawQueued = false;

function reset() {
  Object.assign(S, {
    seed: 7, info: null, matchT: 0, events: [], pulses: [], transitions: [], cues: [], verdicts: [],
    trust: null, eval: S.eval || null, score: [0, 0], recap: null, personal: null, ended: false,
    viewer: S.viewer || { mode: "fan", lang: "en", club: "", player: "" },
  });
}
reset();

// ----------------------------------------------------------------------------- formatting
const pad = (n) => String(n).padStart(2, "0");
const clock = (t) => `${pad(Math.floor(t / 60))}:${pad(Math.floor(t % 60))}`;
function fmtVal(unit, v) {
  if (v == null) return "—";
  if (unit === "share") return `${Math.round(v * 100)}%`;
  if (unit === "xg") return v.toFixed(2);
  if (unit === "rate") return v.toFixed(1);
  return String(Math.round(v));
}
const T = () => I18N[S.viewer.lang] || I18N.en;
const teamName = (side) => (S.info ? S.info[side].name : side === "home" ? "Home" : "Away");

// ----------------------------------------------------------------------------- stream
function openStream() {
  const pace = $("pace").value;
  const faults = $("faults").checked ? 0.3 : 0;
  es = new EventSource(`/matches/${S.seed}/stream?duration=${pace}&faults=${faults}`);
  const on = (type, fn) =>
    es.addEventListener(type, (e) => {
      const m = JSON.parse(e.data);
      if (m.t > S.matchT) S.matchT = m.t;
      fn(m.data, m);
    });

  on("event", (d) => {
    S.events.push(d);
    if (S.events.length > 80) S.events.shift();
    S.score = [d.score_home, d.score_away];
    schedule();
  });
  on("pulse", (d) => { S.pulses.push(d); renderFan(); schedule(); });
  on("transition", (d) => { S.transitions.push(d); schedule(); });
  on("verdict", (d) => { S.verdicts.push(d); if (S.verdicts.length > 300) S.verdicts.shift(); renderVerdicts(); });
  on("cue", (d) => { S.cues.push(d); renderRail(); renderFan(); schedule(); });
  on("trust", (d) => { S.trust = d; renderTrust(); });
  on("recap", (d) => { S.recap = d; });
  on("end", () => {
    S.ended = true;
    es.close();
    renderScoreboards();
    renderFan();
    schedule();
    showRecap();
  });
  es.onerror = () => {
    // never let the browser auto-reconnect: that would replay the match from the start
    es.close();
    if (!S.ended) S.ended = true;
    renderScoreboards();
  };
}

async function start() {
  if (es) es.close();
  const keep = S.viewer;
  reset();
  S.viewer = keep;
  S.seed = Math.max(0, Math.min(100000, parseInt($("seed").value, 10) || 0));
  $("seed").value = S.seed;
  $("recap").close?.();
  try {
    S.info = await (await fetch(`/matches/${S.seed}`)).json();
  } catch (e) {
    $("rail").innerHTML = `<div class="empty">Could not load the match: ${esc(e.message)}</div>`;
    return;
  }
  buildSelectors();
  renderScoreboards();
  renderRail();
  renderFan();
  renderTrust();
  renderVerdicts();
  loadEval();
  refreshPersonal();
  openStream();
  schedule();
}

async function loadEval() {
  if (S.eval) return;
  try {
    S.eval = await (await fetch("/eval?seeds=20")).json();
    renderTrust();
  } catch { /* the trust panel just shows a dash */ }
}

async function refreshPersonal() {
  const token = ++personalToken;
  const v = S.viewer;
  const q = new URLSearchParams({ mode: v.mode, lang: v.lang, faults: $("faults").checked ? 0.3 : 0 });
  if (v.club) q.set("club", v.club);
  if (v.player) q.set("player", v.player);
  try {
    const r = await fetch(`/matches/${S.seed}/personal?${q}`);
    const body = await r.json();
    if (token === personalToken && r.ok) { S.personal = body; renderFan(); }
  } catch { /* offline: fan view stays as is */ }
}

// ----------------------------------------------------------------------------- scoreboard
function scoreboardHtml(lang) {
  const t = I18N[lang] || I18N.en;
  const clk = S.ended ? t.full : S.matchT ? `${Math.floor(S.matchT / 60)}'` : t.kickoff;
  const btn = S.ended && S.recap ? `<button data-recap>${esc(t.recap)}</button>` : "";
  return `<span class="team"><span class="swatch home"></span>${esc(teamName("home"))}</span>
    <span class="score">${S.score[0]} – ${S.score[1]}</span>
    <span class="team">${esc(teamName("away"))}<span class="swatch away"></span></span>
    <span class="clock">${esc(clk)}</span>${btn}`;
}
function renderScoreboards() {
  $("scoreboard-studio").innerHTML = scoreboardHtml("en");
  $("scoreboard-fan").innerHTML = scoreboardHtml(S.viewer.lang);
}
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-recap]")) showRecap();
});

// ----------------------------------------------------------------------------- cue rail
function cueSideClass(c) {
  if (c.slots && c.slots.template === "shift_chaos") return "chaos";
  return c.side || "";
}
function renderRail() {
  const el = $("rail");
  if (!S.cues.length) { el.innerHTML = `<div class="empty">${esc(T().empty)}</div>`; return; }
  el.innerHTML = [...S.cues].reverse().map((c) => `
    <article class="cue ${cueSideClass(c)} ${c.kind === "goal" ? "goal" : ""}">
      <div class="meta"><span class="min">${c.minute}'</span>
        <span class="tag">${esc(KINDS[c.kind] || c.kind)}</span>
        <span class="tag ${c.why.verified ? "ok" : "bad"}">${c.why.verified ? "verified" : "unverified"}</span>
        <span class="tag">P${c.priority}</span>
        ${c.why.attempts > 1 ? `<span class="tag bad">${c.why.attempts} drafts</span>` : ""}</div>
      <h3>${esc(c.headline)}</h3><p>${esc(c.body)}</p>
      <button data-why="${esc(c.cue_id)}">Why?</button>
    </article>`).join("");
}
$("rail").addEventListener("click", (e) => {
  const b = e.target.closest("[data-why]");
  if (b) openWhy(b.dataset.why);
});

function openWhy(id) {
  const c = S.cues.find((x) => x.cue_id === id);
  if (!c) return;
  const w = c.why;
  const claims = w.claims.map((k) => `<tr>
      <td>${esc(METRICS[k.claim.metric] || k.claim.metric)}${k.claim.side ? ` (${esc(k.claim.side)})` : ""}</td>
      <td>${fmtVal(k.claim.unit, k.claim.value)}</td><td>${fmtVal(k.claim.unit, k.actual)}</td>
      <td class="${k.ok ? "ok" : "bad"}">${k.ok ? "✓" : "✗"}</td></tr>`).join("");
  const evidence = w.evidence.map((ev) => `<tr><td><code>${esc(ev.id)}</code></td><td>${Math.floor(ev.t / 60)}'</td>
      <td>${esc(ev.type)}</td><td>${esc(ev.player || teamName(ev.side))}</td>
      <td>${esc(ev.outcome || "")}${ev.xg != null ? ` · ${ev.xg.toFixed(2)} xG` : ""}</td></tr>`).join("");
  const history = w.history.map((h) => `<li>Draft ${h.attempt}: ${h.ok
      ? '<b style="color:var(--ok)">verified</b>'
      : `<b style="color:var(--bad)">rejected</b> — ${esc([...h.failures, ...h.unsupported_numbers.map((n) => `unsupported number ${n}`)].join("; "))}`}</li>`).join("");
  $("why-body").innerHTML = `
    <button class="close" data-close>Close</button>
    <h2>${c.minute}' · ${esc(KINDS[c.kind] || c.kind)}</h2>
    <h3 style="margin:6px 0">${esc(c.headline)}</h3><p>${esc(c.body)}</p>
    <h2>What the Verifier checked</h2>
    <table><tr><th>Claim</th><th>Stated</th><th>Match state</th><th></th></tr>${claims}</table>
    <h2>Evidence</h2>
    <table><tr><th>Event</th><th>Min</th><th>Type</th><th>Who</th><th>Result</th></tr>${evidence}</table>
    <h2>Drafting</h2><ul>${history}</ul>
    <p class="legend">Recomputed from the raw event stream · ${w.attempts} draft${w.attempts > 1 ? "s" : ""} · ${w.latency_ms.toFixed(1)} ms to verify and publish · on screen ${clock(c.t_in)}–${clock(c.t_out)}</p>`;
  $("why").showModal();
}
document.addEventListener("click", (e) => {
  const d = e.target.closest("[data-close]");
  if (d) d.closest("dialog").close();
});

// ----------------------------------------------------------------------------- fan view
const MODES = ["fan", "player_focus", "analyst"];
function buildSelectors() {
  const v = S.viewer;
  const t = T();
  $("l-lang").textContent = t.lang; $("l-mode").textContent = t.mode;
  $("l-club").textContent = t.club; $("l-player").textContent = t.player;
  $("f-lang").value = v.lang;
  $("f-mode").innerHTML = MODES.map((m) => `<option value="${m}">${esc({ fan: t.fan, player_focus: t.focus, analyst: t.analyst }[m])}</option>`).join("");
  $("f-mode").value = v.mode;
  const clubs = [`<option value="">${esc(t.none)}</option>`];
  if (S.info) for (const s of ["home", "away"]) clubs.push(`<option value="${s}">${esc(S.info[s].name)}</option>`);
  $("f-club").innerHTML = clubs.join("");
  $("f-club").value = v.club;
  const players = [`<option value="">${esc(t.none)}</option>`];
  if (S.info) {
    for (const s of ["home", "away"]) {
      players.push(`<optgroup label="${esc(S.info[s].name)}">${S.info[s].players
        .map((p) => `<option value="${esc(p.id)}">${p.number} ${esc(p.name)}</option>`).join("")}</optgroup>`);
    }
  }
  $("f-player").innerHTML = players.join("");
  $("f-player").value = v.player;
}
function onViewerChange() {
  S.viewer = { mode: $("f-mode").value, lang: $("f-lang").value, club: $("f-club").value, player: $("f-player").value };
  if (S.viewer.mode === "player_focus" && !S.viewer.player && S.info) {
    // player focus needs a player: default to the first outfield player of the favourite club
    const side = S.viewer.club || "home";
    S.viewer.player = (S.info[side].players[9] || S.info[side].players[0]).id;
  }
  const keep = S.viewer;
  buildSelectors();
  S.viewer = keep;
  document.documentElement.lang = S.viewer.lang;
  renderScoreboards();
  renderFan();
  refreshPersonal();
}
["f-lang", "f-mode", "f-club", "f-player"].forEach((id) => $(id).addEventListener("change", onViewerChange));

function renderFan() {
  const el = $("fan-feed");
  const t = T();
  const cues = S.personal ? S.personal.cues.filter((c) => S.ended || c.t_in <= S.matchT) : [];
  if (!cues.length) { el.innerHTML = `<div class="empty">${esc(t.empty)}</div>`; return; }
  el.innerHTML = [...cues].reverse().map((c) => `
    <article class="cue ${c.kind === "goal" ? "goal" : ""} ${c.for_you ? "you" : ""}">
      <div class="meta"><span class="min">${c.minute}'</span>
        ${c.for_you ? `<span class="tag ok">${esc(t.foryou)}</span>` : ""}
        <span class="tag">${esc(t.verified)}</span></div>
      <h3>${esc(c.headline)}</h3><p>${esc(c.body)}</p></article>`).join("");
}

// ----------------------------------------------------------------------------- trust panel
function stat(label, value, note = "", good = false) {
  return `<div class="stat ${good ? "good" : ""}"><div class="l">${esc(label)}</div><div class="v">${esc(value)}</div><div class="n">${esc(note)}</div></div>`;
}
function renderTrust() {
  const tr = S.trust || { truth_score: 1, claims_generated: 0, claims_verified: 0, claims_rejected: 0, retries: 0, dropped: 0, first_draft_accuracy: 1, latency_ms_mean: 0, latency_ms_p95: 0, insights: 0, cues: 0 };
  const pct = (v) => `${(v * 100).toFixed(v >= 0.995 || v === 0 ? 0 : 1)}%`;
  $("badge-score").textContent = pct(tr.truth_score);
  $("badge").querySelector(".dot").style.background = tr.truth_score >= 0.95 ? "var(--ok)" : tr.truth_score >= 0.85 ? "var(--away)" : "var(--bad)";
  const ev = S.eval;
  $("trust-grid").innerHTML = [
    stat("Truth Score", pct(tr.truth_score), `${tr.claims_verified} of ${tr.claims_generated} generated claims matched`, tr.truth_score >= 0.95),
    stat("On-air accuracy", pct(tr.on_air_accuracy ?? 1), "audited against the final match state", true),
    stat("Claims rejected", tr.claims_rejected, "caught before air"),
    stat("Retried drafts", tr.retries, `first-draft accuracy ${pct(tr.first_draft_accuracy)}`),
    stat("Dropped", tr.dropped, "never passed verification"),
    stat("Insight latency", `${tr.latency_ms_mean.toFixed(1)} ms`, `p95 ${tr.latency_ms_p95.toFixed(1)} ms`),
    stat("Insights → cues", `${tr.insights} → ${tr.cues}`, "on-air budget: 3 per 5 min, goals always air"),
    stat("Shift recall", ev ? pct(ev.recall) : "—", "vs planted ground truth (20 held-out matches)"),
    stat("Shift precision", ev ? pct(ev.precision) : "—", "±4 min, correct new state"),
    stat("Timeline accuracy", ev ? pct(ev.timeline_accuracy) : "—", ev ? `detection lag ${ev.mean_detection_lag_min} min` : ""),
  ].join("");
}
function renderVerdicts() {
  const rows = S.verdicts.filter((v) => !v.ok).slice(-12).reverse();
  $("verdicts").innerHTML = rows.length
    ? rows.map((v) => `<div class="verdict bad"><b>${esc(v.kind)}</b> draft ${v.attempt} rejected: ${esc([...v.failures, ...v.unsupported_numbers.map((n) => `unsupported number ${n}`)].join("; "))}</div>`).join("")
    : `<div class="empty">No draft has been rejected. Tick “Unreliable model” and kick off again to watch the Verifier work.</div>`;
}

// ----------------------------------------------------------------------------- recap
function showRecap() {
  const fan = $("view-fan").classList.contains("active") && S.personal;
  const r = fan ? S.personal.recap : S.recap;
  if (!r) return;
  const t = fan ? T() : I18N.en;
  $("recap-body").innerHTML = `
    <button class="close" data-close>${esc(t.close)}</button>
    <h2>${esc(t.full)}</h2>
    <div class="final">${esc(teamName("home"))} ${r.score_home} – ${r.score_away} ${esc(teamName("away"))}</div>
    <p><b>${esc(r.headline)}</b></p><p>${esc(r.summary)}</p>
    <h2>${esc(t.moments)}</h2>
    <ol>${r.moments.map((m) => `<li><b>${m.minute}'</b> ${esc(m.headline)}<br><span class="legend">${esc(m.body)}</span></li>`).join("")}</ol>`;
  if (!$("recap").open) $("recap").showModal();
}

// ----------------------------------------------------------------------------- canvases
function fit(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return [canvas.getContext("2d"), w, h, dpr];
}
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function drawPitch() {
  const [ctx, W, H, dpr] = fit($("pitch"));
  ctx.clearRect(0, 0, W, H);
  const sx = W / 105, sy = H / 68;
  ctx.strokeStyle = css("--pitch-line"); ctx.lineWidth = 1.5 * dpr;
  const rect = (x, y, w, h) => ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
  rect(0.5, 0.5, 104, 67);
  ctx.beginPath(); ctx.moveTo(52.5 * sx, 0); ctx.lineTo(52.5 * sx, H); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(52.5 * sx, 34 * sy, 9.15 * sx, 9.15 * sy, 0, 0, 7); ctx.stroke();
  rect(0.5, 13.85, 16.5, 40.3); rect(88.5, 13.85, 16, 40.3);
  rect(0.5, 24.85, 5.5, 18.3); rect(99, 24.85, 5.5, 18.3);

  const home = css("--home"), away = css("--away");
  const at = (ev, x, y) => (ev.side === "away" ? [(105 - x) * sx, (68 - y) * sy] : [x * sx, y * sy]);
  const recent = S.events.filter((e) => !["kick_off", "half_end"].includes(e.type)).slice(-14);
  recent.forEach((ev, i) => {
    const a = (i + 1) / recent.length;
    const col = ev.side === "home" ? home : away;
    ctx.globalAlpha = 0.2 + 0.8 * a; ctx.fillStyle = col; ctx.strokeStyle = col;
    const [x, y] = at(ev, ev.x, ev.y);
    if (ev.end_x != null && (ev.type === "pass" || ev.type === "carry")) {
      const [x2, y2] = at(ev, ev.end_x, ev.end_y);
      ctx.lineWidth = (ev.type === "pass" ? 2 : 3) * dpr;
      ctx.setLineDash(ev.type === "carry" ? [6 * dpr, 4 * dpr] : []);
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
    }
    const r = (ev.type === "shot" ? 7 : 4) * dpr;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
    if (ev.outcome === "goal") {
      ctx.lineWidth = 3 * dpr; ctx.strokeStyle = "#fff";
      ctx.beginPath(); ctx.arc(x, y, r + 5 * dpr, 0, 7); ctx.stroke();
    }
    if (ev.outcome === "incomplete" || ev.outcome === "lost") {
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath(); ctx.moveTo(x - 3 * dpr, y - 3 * dpr); ctx.lineTo(x + 3 * dpr, y + 3 * dpr); ctx.stroke();
    }
  });
  ctx.globalAlpha = 1;
  $("pitch-legend").innerHTML = `<span><span class="swatch home"></span> ${esc(teamName("home"))} attacks →</span>
    <span><span class="swatch away"></span> ← ${esc(teamName("away"))} attacks</span><span>line = pass · dashed = carry · ring = goal</span>`;
}

function drawPulse() {
  const [ctx, W, H, dpr] = fit($("pulse"));
  ctx.clearRect(0, 0, W, H);
  const mid = H / 2;
  const maxMin = Math.max(90, ...S.pulses.map((p) => p.minute + 1));
  const X = (m) => (m / maxMin) * W;
  ctx.strokeStyle = css("--line"); ctx.lineWidth = dpr;
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(W, mid); ctx.stroke();
  for (let m = 15; m < maxMin; m += 15) { ctx.beginPath(); ctx.moveTo(X(m), 0); ctx.lineTo(X(m), H); ctx.stroke(); }
  ctx.fillStyle = css("--muted"); ctx.font = `${11 * dpr}px system-ui`;
  for (let m = 0; m <= maxMin; m += 15) ctx.fillText(`${m}'`, Math.min(X(m) + 3 * dpr, W - 22 * dpr), H - 4 * dpr);

  const pts = S.pulses.map((p) => [X(p.minute + 1), mid - p.dominance * mid * 0.9]);
  if (pts.length) {
    const area = (clipTop, color) => {
      ctx.save(); ctx.beginPath(); ctx.rect(0, clipTop ? 0 : mid, W, clipTop ? mid : H - mid); ctx.clip();
      ctx.beginPath(); ctx.moveTo(pts[0][0], mid);
      pts.forEach(([x, y]) => ctx.lineTo(x, y)); ctx.lineTo(pts[pts.length - 1][0], mid); ctx.closePath();
      ctx.globalAlpha = 0.45; ctx.fillStyle = color; ctx.fill(); ctx.restore();
    };
    area(true, css("--home")); area(false, css("--away"));
    ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1.5 * dpr; ctx.stroke();
    ctx.beginPath();
    S.pulses.forEach((p, i) => { const x = X(p.minute + 1), y = H - 14 * dpr - p.chaos * (H - 30 * dpr); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = css("--chaos"); ctx.lineWidth = 2 * dpr; ctx.stroke();
  }
  ctx.setLineDash([4 * dpr, 4 * dpr]); ctx.strokeStyle = css("--muted"); ctx.lineWidth = dpr;
  for (const t of S.transitions) { const x = X(t.estimated_minute); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H - 14 * dpr); ctx.stroke(); }
  ctx.setLineDash([]);
  for (const c of S.cues.filter((q) => q.kind === "goal")) {
    ctx.fillStyle = c.side === "home" ? css("--home") : css("--away");
    ctx.beginPath(); ctx.arc(X(c.minute), mid, 6 * dpr, 0, 7); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2 * dpr; ctx.stroke();
  }
  const nowX = X(S.matchT / 60);
  ctx.strokeStyle = css("--ink"); ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(nowX, 0); ctx.lineTo(nowX, H); ctx.stroke();
  $("pulse-legend").innerHTML = `<span><span class="swatch home"></span> ${esc(teamName("home"))} in control ↑</span>
    <span><span class="swatch away"></span> ${esc(teamName("away"))} in control ↓</span>
    <span><span class="swatch" style="background:var(--chaos)"></span> chaos</span><span>dashed = shift confirmed (back-dated) · dot = goal</span>`;
}

function schedule() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => {
    drawQueued = false;
    renderScoreboards();
    if ($("view-studio").classList.contains("active")) { drawPitch(); drawPulse(); }
  });
}

// ----------------------------------------------------------------------------- tabs, boot
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${tab.dataset.view}`));
    if (tab.dataset.view === "studio") schedule();
    if (tab.dataset.view === "trust") { renderTrust(); renderVerdicts(); }
    if (tab.dataset.view === "fan") renderFan();
  }));
$("start").addEventListener("click", start);
$("seed").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
window.addEventListener("resize", schedule);
start();
