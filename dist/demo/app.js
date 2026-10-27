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
    coach: "Coach view", metric: "My metric", all: "Everything",
    st_wait: "Waiting for kick-off", st_chaos: "Broken game", st_control: "{team} in control", st_balanced: "Evenly matched",
    first: "1st half", second: "2nd half", with_ball: "With the ball", shots: "Shots", poss: "Possession",
    m: { pressing: "Pressing", duels: "Duels", possession: "Possession", xg: "xG (chances)", pass_quality: "Pass quality", speed: "Speed", threat: "Threat (xT)", shape: "Team shape" },
  },
  es: {
    lang: "Idioma", mode: "Quiero ver", club: "Mi club", player: "Mi jugador", none: "— ninguno —",
    fan: "En cristiano", focus: "Foco en un jugador", analyst: "Los números", empty: "Todavía nada. Empieza el partido.",
    full: "Final", moments: "Los momentos que decidieron", recap: "Resumen", close: "Cerrar", foryou: "para ti",
    verified: "verificado", kickoff: "Saque inicial",
    coach: "Vista de entrenador", metric: "Mi métrica", all: "Todo",
    st_wait: "Esperando el saque", st_chaos: "Partido roto", st_control: "Manda {team}", st_balanced: "Igualado",
    first: "1ª parte", second: "2ª parte", with_ball: "Con balón", shots: "Tiros", poss: "Posesión",
    m: { pressing: "Presión", duels: "Duelos", possession: "Posesión", xg: "xG (ocasiones)", pass_quality: "Calidad de pase", speed: "Velocidad", threat: "Amenaza (xT)", shape: "Dibujo" },
  },
  ca: {
    lang: "Idioma", mode: "Vull veure", club: "El meu club", player: "El meu jugador", none: "— cap —",
    fan: "En paraules planes", focus: "Focus en un jugador", analyst: "Els números", empty: "Encara res. Comença el partit.",
    full: "Final", moments: "Els moments que ho van decidir", recap: "Resum", close: "Tanca", foryou: "per a tu",
    verified: "verificat", kickoff: "Servei inicial",
    coach: "Vista d'entrenador", metric: "La meva mètrica", all: "Tot",
    st_wait: "Esperant el servei", st_chaos: "Partit trencat", st_control: "Mana {team}", st_balanced: "Igualat",
    first: "1a part", second: "2a part", with_ball: "Amb pilota", shots: "Xuts", poss: "Possessió",
    m: { pressing: "Pressió", duels: "Duels", possession: "Possessió", xg: "xG (ocasions)", pass_quality: "Qualitat de passada", speed: "Velocitat", threat: "Amenaça (xT)", shape: "Dibuix" },
  },
};

const METRICS = {
  possession_share: "Possession", pass_completion: "Pass completion", field_tilt: "Field tilt",
  turnovers_per_min: "Turnovers per minute", window_minutes: "Window (minutes)", shot_xg: "Shot xG",
  score_home: "Score (home)", score_away: "Score (away)", player_completed_passes: "Completed passes",
  carry_speed_kmh: "Carry speed (km/h)", team_xg: "Team xG",
  duel_share_def: "Duels won, own third", duel_share_mid: "Duels won, midfield", duel_share_att: "Duels won, final third",
  duels_won_mid: "Midfield duels won", high_recoveries: "High recoveries", final_third_recoveries: "Final-third recoveries",
  counter_press: "Counter-press recoveries", own_half_losses: "Losses in own half", progressive_passes: "Progressive passes",
  long_ball_share: "Long-ball share", central_buildup_share: "Central build-up share", ppda: "Passes per defensive action",
  pressures: "Pressures", pass_difficulty: "Pass difficulty", shot_speed_kmh: "Shot speed (km/h)",
  buildup_seconds: "Seconds from winning the ball to the shot", counter_press_in_move: "Move began with a counter-press",
  long_balls_in_move: "Long balls in the move",
  xt: "Expected threat (xT)", formation_in: "Shape in possession", formation_out: "Shape out of possession",
  gap_def_mid: "Gap, defence to midfield", team_length: "Team length", line_height: "Back-line height",
  line_breaks: "Line-breaking passes", packing: "Opponents bypassed", between_lines: "Received between the lines",
  line_breaks_back: "Passes beating the defence", line_breaks_mid: "Passes beating midfield", line_breaks_fwd: "Passes beating the forward line",
  between_mid_def: "Received between midfield and defence", between_fwd_mid: "Received between forwards and midfield",
  box_entries: "Box entries", zone14_entries: "Zone 14 entries", halfspace_entries: "Half-space entries",
  xt_share_left: "Threat down the left", xt_share_centre: "Threat through the middle", xt_share_right: "Threat down the right",
  pass_xt_added: "xT added by the pass", pass_packing: "Opponents the pass bypassed",
};
const LINE_NAMES = { back: "defence", midfield: "midfield", forward: "forwards" };
const UNITS = {
  possession_share: "share", pass_completion: "share", field_tilt: "share", turnovers_per_min: "rate",
  window_minutes: "minutes", shot_xg: "xg", team_xg: "xg", score_home: "count", score_away: "count",
  player_completed_passes: "count", carry_speed_kmh: "kmh",
  duel_share_def: "share", duel_share_mid: "share", duel_share_att: "share", duels_won_mid: "count",
  high_recoveries: "count", final_third_recoveries: "count", counter_press: "count", own_half_losses: "count",
  progressive_passes: "count", long_ball_share: "share", central_buildup_share: "share", ppda: "rate",
  pressures: "count", pass_difficulty: "index", shot_speed_kmh: "kmh", buildup_seconds: "seconds",
  counter_press_in_move: "count", long_balls_in_move: "count",
  xt: "xg", formation_in: "formation", formation_out: "formation", gap_def_mid: "metres", team_length: "metres",
  line_height: "metres", line_breaks: "count", packing: "count", between_lines: "count", box_entries: "count",
  line_breaks_back: "count", line_breaks_mid: "count", line_breaks_fwd: "count", between_mid_def: "count", between_fwd_mid: "count",
  zone14_entries: "count", halfspace_entries: "count", xt_share_left: "share", xt_share_centre: "share",
  xt_share_right: "share", pass_xt_added: "xg", pass_packing: "count",
};
const KINDS = {
  goal: "Goal", state_shift: "Control shift", big_chance: "Big chance", top_speed: "Top speed", pass_master: "Passing",
  press_surge: "Pressing", midfield_battle: "Midfield battle", danger_turnovers: "Dangerous losses", direct_switch: "Going long",
  pass_difficulty: "Hardest pass", shot_speed: "Fastest shot", line_breakers: "Through the lines", zone_damage: "Danger zone",
  momentum_swing: "Momentum", shape_change: "Change of shape", lines_stretched: "Stretched lines", most_dangerous_pass: "Killer pass",
};

const S = {};
let es = null;
let startSeq = 0;      // bumps on every Kick off: late answers from an older start are ignored
let gotRecord = false; // true once the current match has delivered its first record
let seedNote = "";     // the standing note about the seed (clamped, or not recorded)
let STATIC = false; // no backend: replay the pre-recorded files under data/
let MANIFEST = null; // data/index.json
let replayToken = 0;
let personalToken = 0;
let drawQueued = false;

function reset() {
  Object.assign(S, {
    seed: 7, info: null, matchT: 0, events: [], pulses: [], transitions: [], cues: [], verdicts: [],
    trust: null, eval: S.eval || null, score: [0, 0], recap: null, personal: null, ended: false,
    shots: [], hurt: [], live: null, // every shot; the passes that added most threat; the latest frame of all 22
    pl: {}, plSort: S.plSort ?? 1, plTeam: S.plTeam || "both",
    railAll: false, layer: S.layer || "live", layerTeam: S.layerTeam || "home", h2hScope: S.h2hScope || "window",
    viewer: S.viewer || { mode: "fan", lang: "en", club: "", player: "", metric: "" },
  });
}
reset();

// ----------------------------------------------------------------------------- formatting
const pad = (n) => String(n).padStart(2, "0");
const clock = (t) => `${pad(Math.floor(t / 60))}:${pad(Math.floor(t % 60))}`;
function fmtVal(unit, v) {
  if (v == null) return "—";
  if (unit === "share") return `${Math.round(v * 100)}%`;
  if (unit === "xg" || unit === "index") return v.toFixed(2);
  if (unit === "rate") return v.toFixed(1);
  if (unit === "xt") return v.toFixed(2);
  if (unit === "formation") return String(Math.round(v)).split("").join("-");
  if (unit === "metres") return `${Math.round(v)} m`;
  return String(Math.round(v));
}
const baseLang = (lang) => String(lang || "en").split("-")[0].toLowerCase();
const T = () => I18N[baseLang(S.viewer.lang)] || I18N.en;
const teamName = (side) => (S.info ? S.info[side].name : side === "home" ? "Home" : "Away");
const teamShort = (side) => (S.info ? S.info[side].short_name || S.info[side].name : side === "home" ? "HOM" : "AWY");

// "turnovers_per_min stated 4.7 but match state says 3.2" -> "Turnovers per minute: stated 4.7, match state 3.2"
function humanReason(r) {
  const m = /^(\w+) stated (-?[\d.]+) but match state says (-?[\d.]+)$/.exec(r);
  if (!m) return r;
  const unit = UNITS[m[1]];
  return `${METRICS[m[1]] || m[1]}: stated ${fmtVal(unit, +m[2])}, match state ${fmtVal(unit, +m[3])}`;
}
const failureList = (v) => [
  ...v.failures.map(humanReason),
  ...v.unsupported_numbers.map((n) => `unsupported number ${n}`),
  ...(v.unsupported_names || []).map((n) => `mentions ${n}, who is not in the brief`),
].join("; ");

// ----------------------------------------------------------------------------- stream
// One handler per message type; the live SSE stream and the static replay both feed them.
const handlers = {
  event: (d) => {
    S.events.push(d);
    if (S.events.length > 80) S.events.shift();
    S.score = [d.score_home, d.score_away];
    if (d.fz) S.live = d;
    tallyPlayer(d);
    if (d.type === "shot") S.shots.push(d);
    if (d.type === "pass" && d.xt >= 0.03) {
      S.hurt.push(d);
      S.hurt.sort((p, q) => q.xt - p.xt);
      if (S.hurt.length > 10) S.hurt.length = 10;
    }
    schedule();
  },
  pulse: (d) => { S.pulses.push(d); renderFan(); renderH2H(); schedule(); },
  transition: (d) => { S.transitions.push(d); schedule(); },
  verdict: (d) => { S.verdicts.push(d); if (S.verdicts.length > 300) S.verdicts.shift(); renderVerdicts(); },
  cue: (d) => { S.cues.push(d); renderRail(); renderFan(); if ($("view-trust").classList.contains("active")) renderLedger(); schedule(); },
  trust: (d) => { S.trust = d; renderTrust(); },
  recap: (d) => { S.recap = d; },
  end: () => {
    S.ended = true;
    renderPlayers();
    if (es) es.close();
    renderScoreboards();
    renderFan();
    schedule();
    showRecap();
  },
};
// A one-line status above the views: "Preparing match…", a clamped seed, a missing recording.
function setNote(msg) {
  const n = $("start-notice");
  n.textContent = msg || "";
  n.hidden = !msg;
}
function closeDialogs() {
  for (const id of ["recap", "why"]) { const d = $(id); if (d.open) d.close(); }
}
function showStartError(msg) {
  S.ended = true;
  setNote(seedNote);
  $("rail").innerHTML = `<div class="empty">${esc(msg)} <button type="button" data-retry>Retry</button></div>`;
  renderScoreboards();
}
function dispatch(type, m) {
  const fn = handlers[type];
  if (!fn) return;
  if (!gotRecord) { gotRecord = true; setNote(seedNote); }
  if (m.t > S.matchT) S.matchT = m.t;
  fn(m.data, m);
}

// Static mode: replay a pre-recorded bus (data/<seed>/stream-*.json) with the same pacing as the API.
async function openStaticStream(pace, faults) {
  const token = ++replayToken;
  let feed;
  try {
    const r = await fetch(`data/${S.seed}/stream-${faults ? "faults" : "clean"}.json`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    feed = await r.json();
  } catch (e) {
    if (token === replayToken) showStartError(`Could not load the recording (${e.message}).`);
    return;
  }
  if (token !== replayToken) return;
  const total = feed.reduce((m, r) => Math.max(m, r.t), 0) || 1;
  const speed = pace > 0 ? total / pace : 0; // match seconds per real second; 0 = as fast as possible
  const t0 = performance.now();
  let i = 0;
  const step = () => {
    if (token !== replayToken) return;
    const now = speed ? ((performance.now() - t0) / 1000) * speed : Infinity;
    const stop = i + 300; // instant pace still yields to the UI every 300 records
    while (i < feed.length && feed[i].t <= now && (speed || i < stop)) { dispatch(feed[i].type, feed[i]); i++; }
    if (i < feed.length) setTimeout(step, speed ? 40 : 0);
    else dispatch("end", { t: total, data: {} });
  };
  step();
}

function openStream() {
  const pace = parseFloat($("pace").value);
  const faults = $("faults").checked ? 0.3 : 0;
  if (STATIC) { openStaticStream(pace, faults); return; }
  const mine = es = new EventSource(`matches/${S.seed}/stream?duration=${pace}&faults=${faults}`);
  for (const type of Object.keys(handlers)) {
    mine.addEventListener(type, (e) => { if (es === mine) dispatch(type, JSON.parse(e.data)); });
  }
  mine.onerror = () => {
    // never let the browser auto-reconnect: that would replay the match from the start
    mine.close();
    if (es !== mine || S.ended) return;
    if (!gotRecord) showStartError("The match stream failed before it started.");
    else { S.ended = true; renderScoreboards(); }
  };
}

// The seed box: empty, negative, too large or not a number never leaves a blank screen.
let pendingSeed = null; // ?seed=N from the address bar, used once by the first Kick off
function readSeed() {
  const raw = (pendingSeed ?? $("seed").value).trim();
  pendingSeed = null;
  const n = Number(raw);
  if (STATIC) {
    const ok = MANIFEST.seeds[raw];
    if (ok) return { seed: +raw, note: "" };
    const first = +Object.keys(MANIFEST.seeds)[0];
    return { seed: first, note: `Match ${raw || "?"} is not in the recorded set (${Object.keys(MANIFEST.seeds).join(", ")}); showing ${first}.` };
  }
  if (raw === "" || !Number.isFinite(n)) return { seed: 7, note: `"${raw}" is not a match number; showing match 7.` };
  const seed = Math.max(0, Math.min(100000, Math.round(n)));
  return { seed, note: seed === n ? "" : `Match numbers run from 0 to 100000; showing match ${seed}.` };
}

async function start() {
  const mine = ++startSeq;
  if (es) es.close();
  es = null;
  replayToken++;
  personalToken++;
  closeDialogs();
  const keep = S.viewer;
  reset();
  S.viewer = keep;
  gotRecord = false;
  const picked = readSeed();
  S.seed = picked.seed;
  seedNote = picked.note;
  $("seed").value = S.seed;
  setNote(`${seedNote} Preparing match…`.trim());
  renderRail();
  try {
    const r = await fetch(STATIC ? `data/${S.seed}/info.json` : `matches/${S.seed}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const info = await r.json();
    if (mine !== startSeq) return; // a newer Kick off took over while this one was loading
    S.info = info;
  } catch (e) {
    if (mine === startSeq) showStartError(`Could not load the match (${e.message}).`);
    return;
  }
  buildSelectors();
  renderScoreboards();
  renderRail();
  renderH2H();
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
    S.eval = await (await fetch(STATIC ? "data/eval.json" : "eval?seeds=20")).json();
    renderTrust();
  } catch { /* the trust panel just shows a dash */ }
}

async function refreshPersonal() {
  const token = ++personalToken;
  const v = S.viewer;
  if (STATIC) return refreshPersonalStatic(token);
  const q = new URLSearchParams({ mode: v.mode, lang: v.lang, faults: $("faults").checked ? 0.3 : 0 });
  if (v.club) q.set("club", v.club);
  if (v.player) q.set("player", v.player);
  if (v.metric) q.set("metric", v.metric);
  try {
    const r = await fetch(`matches/${S.seed}/personal?${q}`);
    const body = await r.json();
    if (token === personalToken && r.ok) { S.personal = body; renderFan(); }
  } catch { /* offline: fan view stays as is */ }
}

// Static mode: mode x lang files; favourite club and player only change `for_you`, applied here.
const focusPlayers = () => (MANIFEST.seeds[S.seed] || { focus_players: [] }).focus_players;
async function refreshPersonalStatic(token) {
  const v = S.viewer;
  const recorded = ["en", "es", "ca"].includes(baseLang(v.lang));
  const lang = recorded ? baseLang(v.lang) : "en"; // only these three were pre-recorded
  const name = v.mode === "player_focus"
    ? `player_focus-${focusPlayers().includes(v.player) ? v.player : focusPlayers()[0]}-${lang}`
    : `${v.mode}-${lang}`;
  try {
    const body = await (await fetch(`data/${S.seed}/personal-${name}.json`)).json();
    if (!recorded) {
      body.cues.forEach((c) => { c.translation_unavailable = true; });
      body.recap.translation_unavailable = true;
    }
    body.cues.forEach((c) => { c.for_you = (!!v.club && c.side === v.club) || (!!v.player && c.player_id === v.player); });
    // "My metric" is applied here, like the API does: one thread only, goals always show
    if (v.metric) body.cues = body.cues.filter((c) => c.kind === "goal" || (c.tags || []).includes(v.metric));
    if (token === personalToken) { S.personal = body; renderFan(); }
  } catch { /* missing file: fan view stays as is */ }
}

// ----------------------------------------------------------------------------- scorebug
function crest(side) {
  // a generated shield with the club's initials; fictional clubs, no real marks
  const col = side === "home" ? "var(--home)" : "var(--away)";
  const ink = side === "home" ? "var(--on-home)" : "var(--on-away)";
  const ini = esc((S.info ? S.info[side].short_name : side).slice(0, 3));
  return `<svg class="crest" viewBox="0 0 46 52" aria-hidden="true">
    <path d="M23 1 L44 7 V24 C44 37 35 46 23 51 C11 46 2 37 2 24 V7 Z" fill="var(--purple)" stroke="${col}" stroke-width="2.5"/>
    <path d="M8 12 L23 8 L38 12 V22 H8 Z" fill="${col}"/>
    <text x="23" y="19.5" text-anchor="middle" font-family="Saira Condensed, sans-serif" font-weight="800" font-size="10" fill="${ink}">${ini}</text>
    <text x="23" y="38" text-anchor="middle" font-family="Saira Condensed, sans-serif" font-weight="800" font-size="13" fill="#fff">${ini.slice(0, 1)}</text>
  </svg>`;
}
const lastPulse = () => S.pulses[S.pulses.length - 1];
const formationLabel = (code) => (code ? String(Math.round(code)).split("").join("-") : null);
function stateChip(lang) {
  const p = lastPulse();
  const t = I18N[lang] || I18N.en;
  if (!p) return `<span class="chip"><i></i>${esc(t.st_wait)}</span>`;
  if (p.state === "chaos") return `<span class="chip chaos"><i></i>${esc(t.st_chaos)}</span>`;
  if (p.state === "home_control" || p.state === "away_control") {
    const side = p.state === "home_control" ? "home" : "away";
    return `<span class="chip ${side}"><i></i>${esc(t.st_control.replace("{team}", teamShort(side)))}</span>`;
  }
  return `<span class="chip"><i></i>${esc(t.st_balanced)}</span>`;
}
function scoreboardHtml(lang) {
  const t = I18N[lang] || I18N.en;
  const mins = Math.floor(S.matchT / 60);
  const clk = S.ended ? t.full : S.matchT ? `<span class="live">●</span> ${mins}'${mins >= 45 ? ` · ${t.second}` : ` · ${t.first}`}` : t.kickoff;
  const p = lastPulse();
  const m = p && p.match;
  const shape = (side) => {
    const f = p && formationLabel(p[side].formation_in); // the last 5 minutes: a match average blurs changes
    return f ? `${t.with_ball} ${f}` : esc(S.info ? S.info[side].formation : "");
  };
  const nm = (side) => `<div class="sb-name"><b><span class="full">${esc(teamName(side))}</span><span class="short">${esc(teamShort(side))}</span></b><small>${shape(side)}</small></div>`;
  const foot = m
    ? `<span>xG <b>${m.home.xg.toFixed(2)}</b> – <b>${m.away.xg.toFixed(2)}</b></span>
       <span>${esc(t.shots)} <b>${m.home.shots}</b> – <b>${m.away.shots}</b></span>
       <span>${esc(t.poss)} <b>${Math.round(m.home.possession_share * 100)}%</b> – <b>${Math.round(m.away.possession_share * 100)}%</b></span>`
    : "";
  const btn = S.ended && S.recap ? `<button data-recap>${esc(t.recap)}</button>` : "";
  return `<div class="sb-team home">${crest("home")}${nm("home")}</div>
    <div class="sb-center"><div class="sb-score"><span>${S.score[0]}</span><span class="dash">–</span><span>${S.score[1]}</span></div>
      <div class="sb-clock">${clk}</div></div>
    <div class="sb-team away">${crest("away")}${nm("away")}</div>
    <div class="sb-foot">${stateChip(lang)}${foot}${btn}</div>`;
}
function renderScoreboards() {
  $("scoreboard-studio").innerHTML = scoreboardHtml("en");
  $("scoreboard-fan").innerHTML = scoreboardHtml(baseLang(S.viewer.lang));
}
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-recap]")) showRecap();
});

// ----------------------------------------------------------------------------- head to head
// [label, key, unit, plain-words explanation, lower is better]
const H2H = [
  ["Possession", "possession_share", "share", "Share of the time each team had the ball."],
  ["xG", "xg", "xg", "Expected goals: how many goals the chances were worth, from where each shot was taken."],
  ["Expected threat (xT)", "xt", "xg", "How much closer to scoring each team moved the ball with passes and carries."],
  ["Shots", "shots", "count", "Shots on, off and blocked."],
  ["Line-breaking passes", "line_breaks", "count", "Completed passes that crossed a line of opponents through its span, not round the side."],
  ["Received between the lines", "between_lines", "count", "Passes received in the space between any two lines of the opponent, at least 3 m from every opponent."],
  ["Box entries", "box_entries", "count", "Passes and carries that reached the penalty area."],
  ["Progressive passes", "progressive_passes", "count", "Completed passes that moved the ball at least 10 m towards goal."],
  ["High recoveries", "high_recoveries", "count", "Times the ball was won back in the opponent's half."],
  ["Passes allowed per defensive action", "ppda", "rate", "PPDA: how many passes a team lets the opponent make before it challenges. Lower means a harder press.", true],
  ["Midfield duels won", "duel_share_mid", "share", "Share of the tackles and interceptions in midfield each team won."],
  ["Shape with the ball", "formation_in", "formation", "How the team lines up when it has the ball, read from player positions."],
  ["Shape without the ball", "formation_out", "formation", "How the team lines up when defending."],
  ["Back-line height", "line_height", "metres", "How far from its own goal the defence stands without the ball."],
];
function renderH2H() {
  const el = $("h2h");
  const p = lastPulse();
  if (!p) { el.innerHTML = `<div class="empty">${esc(T().empty)}</div>`; return; }
  const src = S.h2hScope === "match" ? p.match : p;
  const h = src.home, a = src.away;
  el.innerHTML = `<div class="h2h-head"><span>${esc(teamShort("home"))}</span><span></span><span>${esc(teamShort("away"))}</span></div>` +
    H2H.map(([label, key, unit, why, lowerBetter]) => {
      const hv = h[key], av = a[key];
      if (unit === "formation" || unit === "metres") {
        const f = (v) => (v == null ? "—" : unit === "formation" ? formationLabel(v) : `${Math.round(v)} m`);
        return `<div class="row text" title="${esc(why)}"><span class="v">${f(hv)}</span><span class="mid">${esc(label)}</span><span class="v r">${f(av)}</span></div>`;
      }
      const x = hv ?? 0, y = av ?? 0;
      let hs = x + y > 0 ? x / (x + y) : 0.5;
      if (lowerBetter && x > 0 && y > 0) hs = (1 / x) / (1 / x + 1 / y);
      const lead = hs > 0.5 ? "h" : hs < 0.5 ? "a" : "";
      return `<div class="row" title="${esc(why)}">
        <span class="lab">${esc(label)}</span>
        <span class="v ${lead === "a" ? "trail" : "lead"}">${fmtVal(unit, hv)}</span>
        <span class="bars"><span class="h" style="flex:${hs.toFixed(3)}"></span><span class="a" style="flex:${(1 - hs).toFixed(3)}"></span></span>
        <span class="v r ${lead === "h" ? "trail" : "lead"}">${fmtVal(unit, av)}</span></div>`;
    }).join("");
}
document.querySelectorAll("#h2h-scope button").forEach((b) => b.addEventListener("click", () => {
  S.h2hScope = b.dataset.scope;
  document.querySelectorAll("#h2h-scope button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderH2H();
}));

// ----------------------------------------------------------------------------- cue rail
function cueSideClass(c) {
  if (c.slots && c.slots.template === "shift_chaos") return "chaos";
  return c.side || "";
}
function renderRail() {
  const el = $("rail");
  if (!S.cues.length) { el.innerHTML = `<div class="empty">${esc(T().empty)}</div>`; return; }
  const all = [...S.cues].reverse();
  const shown = S.railAll ? all : all.slice(0, 6);
  const more = all.length > shown.length ? `<button class="more" data-more>Show all ${all.length} moments</button>` : "";
  el.innerHTML = shown.map((c) => `
    <article class="cue ${cueSideClass(c)} ${c.kind === "goal" ? "goal" : ""}">
      <div class="meta"><span class="min">${c.minute}'</span>
        <span class="kind">${esc(KINDS[c.kind] || c.kind)}</span>
        <span class="${c.why.verified ? "ok" : "bad"}">${c.why.verified ? "✓ verified" : "unverified"}</span>
        ${c.why.attempts > 1 ? `<span class="bad">${c.why.attempts} drafts</span>` : ""}</div>
      <h3>${esc(c.headline)}</h3><p>${esc(c.body)}</p>
      <button data-why="${esc(c.cue_id)}">Show the proof</button>
    </article>`).join("") + more;
}
$("rail").addEventListener("click", (e) => {
  if (e.target.closest("[data-more]")) { S.railAll = true; renderRail(); return; }
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
      <td>${esc(ev.outcome || "")}${ev.xg != null ? ` · ${ev.xg.toFixed(2)} xG` : ""}${ev.lbl && ev.lbl.length ? ` · beat ${esc(ev.lbl.map((l) => LINE_NAMES[l] || l).join(" + "))}` : ""}</td></tr>`).join("");
  const history = w.history.map((h) => `<li>Draft ${h.attempt}: ${h.ok
      ? '<b style="color:var(--ok-ink)">verified</b>'
      : `<b style="color:var(--bad)">rejected</b> — ${esc(failureList(h))}`}</li>`).join("");
  $("why-body").innerHTML = `
    <button class="close" data-close>Close</button>
    <h2>${c.minute}' · ${esc(KINDS[c.kind] || c.kind)}</h2>
    <h3 style="margin:6px 0">${esc(c.headline)}</h3><p>${esc(c.body)}</p>
    <h2>What the Verifier checked</h2>
    <table><tr><th>Claim</th><th>Stated</th><th>Match state</th><th></th></tr>${claims}</table>
    <h2>Key events in this window</h2>
    <table><tr><th>Event</th><th>Min</th><th>Type</th><th>Who</th><th>Result</th></tr>${evidence}</table>
    <h2>Drafting</h2><ul>${history}</ul>
    <p class="legend">Written by: ${esc(WRITTEN_BY[c.slots && c.slots.written_by] || "template")} · Recomputed from the raw event stream · ${w.attempts} draft${w.attempts > 1 ? "s" : ""} · ${w.latency_ms.toFixed(1)} ms to verify and publish · on screen ${clock(c.t_in)}–${clock(c.t_out)}</p>`;
  $("why").showModal();
}
document.addEventListener("click", (e) => {
  const d = e.target.closest("[data-close]");
  if (d) d.closest("dialog").close();
  if (e.target.closest("[data-retry]")) start();
  if (e.target === $("why")) $("why").close(); // a click on the backdrop
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("recap").open) $("recap").close(); // non-modal dialogs ignore Esc on their own
});
// Changing the match or the pace leaves the old recap behind; both apply on the next Kick off.
for (const id of ["pace", "faults"]) $(id).addEventListener("change", () => $("recap").close());
$("seed").addEventListener("change", () => $("recap").close());

// ----------------------------------------------------------------------------- fan view
const MODES = ["fan", "player_focus", "analyst", "coach"];
const METRIC_KEYS = ["pressing", "duels", "possession", "xg", "pass_quality", "speed", "threat", "shape"];
function buildSelectors() {
  const v = S.viewer;
  const t = T();
  $("l-lang").textContent = t.lang; $("l-mode").textContent = t.mode;
  $("l-club").textContent = t.club; $("l-player").textContent = t.player;
  $("l-metric").textContent = t.metric;
  const listed = [...$("f-lang").options].some((o) => o.value === v.lang && o.value !== "other");
  $("f-lang").value = listed ? v.lang : "other";
  $("f-lang-other").hidden = listed;
  $("f-lang-other").value = listed ? "" : v.lang;
  $("f-mode").innerHTML = MODES.map((m) => `<option value="${m}">${esc({ fan: t.fan, player_focus: t.focus, analyst: t.analyst, coach: t.coach }[m])}</option>`).join("");
  $("f-mode").value = v.mode;
  $("f-metric").innerHTML = [`<option value="">${esc(t.all)}</option>`,
    ...METRIC_KEYS.map((k) => `<option value="${k}">${esc(t.m[k])}</option>`)].join("");
  $("f-metric").value = v.metric || "";
  const clubs = [`<option value="">${esc(t.none)}</option>`];
  if (S.info) for (const s of ["home", "away"]) clubs.push(`<option value="${s}">${esc(S.info[s].name)}</option>`);
  $("f-club").innerHTML = clubs.join("");
  $("f-club").value = v.club;
  const players = [`<option value="">${esc(t.none)}</option>`];
  if (S.info) {
    for (const s of ["home", "away"]) {
      players.push(`<optgroup label="${esc(S.info[s].name)}">${S.info[s].players
        .map((p) => `<option value="${esc(p.id)}">${p.number} ${esc(p.name)}${STATIC && focusPlayers().includes(p.id) ? " ★" : ""}</option>`).join("")}</optgroup>`);
    }
  }
  $("f-player").innerHTML = players.join("");
  $("f-player").value = v.player;
}
const LANG_RE = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$/;
function pickedLang() {
  const sel = $("f-lang").value;
  if (sel !== "other") return sel;
  const typed = $("f-lang-other").value.trim();
  return LANG_RE.test(typed) ? typed : (S.viewer.lang || "en"); // not a language code: keep the last good one
}
function onViewerChange() {
  S.viewer = {
    mode: $("f-mode").value, lang: pickedLang(), club: $("f-club").value,
    player: $("f-player").value, metric: $("f-metric").value,
  };
  $("f-lang-other").hidden = $("f-lang").value !== "other";
  if (S.viewer.mode === "player_focus" && !S.viewer.player && S.info) {
    // player focus needs a player: default to the first outfield player of the favourite club
    const side = S.viewer.club || "home";
    S.viewer.player = (S.info[side].players[9] || S.info[side].players[0]).id;
  }
  // static demo: player focus is pre-recorded for the starred players only
  if (STATIC && S.viewer.mode === "player_focus" && !focusPlayers().includes(S.viewer.player)) S.viewer.player = focusPlayers()[0];
  const keep = S.viewer;
  buildSelectors();
  S.viewer = keep;
  document.documentElement.lang = S.viewer.lang;
  $("fan-feed").dir = ["ar", "he", "fa", "ur"].includes(baseLang(S.viewer.lang)) ? "rtl" : "ltr";
  renderScoreboards();
  renderFan();
  refreshPersonal();
}
["f-lang", "f-lang-other", "f-mode", "f-club", "f-player", "f-metric"].forEach((id) => $(id).addEventListener("change", onViewerChange));

const WRITTEN_BY = { model: "model", template: "template", template_fallback: "template fallback", other: "custom" };
function renderFan() {
  const el = $("fan-feed");
  const t = T();
  const p = S.personal;
  const flagged = p && (p.cues.some((c) => c.translation_unavailable) || (p.recap && p.recap.translation_unavailable));
  $("fan-notice").hidden = !flagged;
  if (flagged) {
    $("fan-notice").textContent = STATIC
      ? `No pre-recorded text in “${S.viewer.lang}”: showing English. The static demo has English, Spanish and Catalan; run the API with WIM_GENERATOR=llm for any other language.`
      : `Translation unavailable for “${S.viewer.lang}”: showing English. The offline writer covers English, Spanish and Catalan; start the API with WIM_GENERATOR=llm (docs/LLM.md) to write in any language.`;
  }
  const cues = p ? p.cues.filter((c) => S.ended || c.t_in <= S.matchT) : [];
  if (!cues.length) { el.innerHTML = `<div class="empty">${esc(t.empty)}</div>`; return; }
  el.innerHTML = [...cues].reverse().map((c) => `
    <article class="cue ${c.side || ""} ${c.kind === "goal" ? "goal" : ""} ${c.for_you ? "you" : ""}">
      <div class="meta"><span class="min">${c.minute}'</span>
        ${c.for_you ? `<span class="tag ok">${esc(t.foryou)}</span>` : ""}
        <span class="tag">${esc(t.verified)}</span>
        ${c.written_by === "model" ? `<span class="tag ok" title="written by the model, checked before airing">model</span>` : ""}
        ${c.written_by === "template_fallback" ? `<span class="tag bad" title="the model's text was rejected">template fallback</span>` : ""}</div>
      <h3>${esc(c.headline)}</h3><p>${esc(c.body)}</p></article>`).join("");
}

// ----------------------------------------------------------------------------- trust panel
const BENCH = "Benchmark: 20 held-out matches";
function stat(label, value, note = "", good = false, bench = "") {
  return `<div class="stat ${good ? "good" : ""}">${bench ? `<div class="bench">${esc(bench)}</div>` : ""}<div class="l">${esc(label)}</div><div class="v">${esc(value)}</div><div class="n">${esc(note)}</div></div>`;
}
function renderTrust() {
  const tr = S.trust || { truth_score: 1, claims_generated: 0, claims_verified: 0, claims_rejected: 0, retries: 0, dropped: 0, first_draft_accuracy: 1, latency_ms_mean: 0, latency_ms_p95: 0, insights: 0, cues: 0 };
  const pct = (v) => `${(v * 100).toFixed(v >= 0.995 || v === 0 ? 0 : 1)}%`;
  $("badge-score").textContent = pct(tr.truth_score);
  $("badge").querySelector(".dot").style.background = tr.truth_score >= 0.95 ? "var(--ok)" : tr.truth_score >= 0.85 ? "var(--away)" : "var(--bad)";
  const drafts = S.verdicts.length, rejected = S.verdicts.filter((v) => !v.ok).length;
  const step = (who, n, d, bad = false) => `<li><div class="who">${esc(who)}</div><div class="n ${bad ? "bad" : ""}">${esc(n)}</div><div class="d">${esc(d)}</div></li>`;
  $("flow-engine").textContent = tr.engine === "agent_framework"
    ? "Live counts for this match · runs as a Microsoft Agent Framework workflow"
    : "Live counts for this match";
  $("flow").innerHTML = [
    step("Match Pulse", S.pulses.length, `minutes read · ${S.transitions.length} changes of control confirmed`),
    step("Analyst", tr.insights, "moments worth explaining (shifts, tactics, chances, records)"),
    step("Explainer", drafts, `drafts written, ${tr.claims_generated} numbers stated as claims`),
    step("Verifier", rejected, `drafts rejected and rewritten · every number recomputed from the raw events`, rejected > 0),
    step("Producer", S.cues.length, "put on air, at most 3 every 5 minutes; goals always"),
    step("Personalizer", "4 × any", "views (fan, player, analyst, coach) in any language, re-checked"),
  ].join("");
  $("trust-grid").innerHTML = [
    stat("Truth Score", pct(tr.truth_score), `${tr.claims_verified} of ${tr.claims_generated} generated claims matched`, tr.truth_score >= 0.95),
    stat("On-air accuracy", pct(tr.on_air_accuracy ?? 1), "audited against the final match state", true),
    stat("Claims rejected", tr.claims_rejected, "caught before air"),
    stat("Retried drafts", tr.retries, `first-draft accuracy ${pct(tr.first_draft_accuracy)}`),
    stat("Written by", `${tr.written_by_model ?? 0} model`,
      `${tr.written_by_fallback ?? 0} template fallback · ${tr.written_by_template ?? 0} template`),
    stat("Insight latency", `${tr.latency_ms_mean.toFixed(1)} ms`, `p95 ${tr.latency_ms_p95.toFixed(1)} ms`),
  ].join("");
  const ev = S.eval;
  $("bench-grid").innerHTML = [
    stat("Shift recall", ev ? pct(ev.recall) : "—", "changes of control found, ±4 min", false, BENCH),
    stat("Shift precision", ev ? pct(ev.precision) : "—", "found changes that really happened", false, BENCH),
    stat("Timeline accuracy", ev ? pct(ev.timeline_accuracy) : "—", ev ? `detection lag ${ev.mean_detection_lag_min} min` : "", false, BENCH),
    stat("Shape with the ball", ev && ev.formation_in_accuracy != null ? pct(ev.formation_in_accuracy) : "—", "formation read from positions", false, BENCH),
    stat("Shape without the ball", ev && ev.formation_out_accuracy != null ? pct(ev.formation_out_accuracy) : "—", "defending shape", false, BENCH),
    stat("Block height", ev && ev.block_accuracy != null ? pct(ev.block_accuracy) : "—", "high / mid / low block", false, BENCH),
  ].join("");
  renderLedger();
}
function renderLedger() {
  const rows = [];
  for (const c of [...S.cues].reverse()) {
    for (const k of c.why.claims) {
      if (k.claim.metric === "window_minutes") continue;
      rows.push(`<tr><td>${c.minute}'</td><td class="what">${esc(c.headline)}</td>
        <td>${esc(METRICS[k.claim.metric] || k.claim.metric)}${k.claim.side ? ` · ${esc(teamShort(k.claim.side))}` : ""}${k.claim.window ? ` <span class="hint">${k.claim.window[0]}–${k.claim.window[1]}'</span>` : ""}</td>
        <td>${fmtVal(k.claim.unit, k.claim.value)}</td><td>${fmtVal(k.claim.unit, k.actual)}</td>
        <td class="${k.ok ? "ok" : "bad"}">${k.ok ? "✓" : "✗"}</td></tr>`);
    }
  }
  $("ledger-count").textContent = rows.length ? `${rows.length} numbers on air, each recomputed` : "";
  $("ledger").innerHTML = rows.length
    ? `<thead><tr><th>Min</th><th>On air</th><th>Number</th><th>Stated</th><th>Recomputed</th><th></th></tr></thead><tbody>${rows.slice(0, 60).join("")}</tbody>`
    : `<tbody><tr><td class="empty">Numbers appear here as cues go on air.</td></tr></tbody>`;
}
function renderVerdicts() {
  const rows = S.verdicts.filter((v) => !v.ok).slice(-12).reverse();
  $("verdicts").innerHTML = rows.length
    ? rows.map((v) => `<div class="verdict bad"><b>${esc(KINDS[v.kind] || v.kind)}</b>, draft ${v.attempt} rejected: ${esc(failureList(v))}</div>`).join("")
    : `<div class="empty">No draft has been rejected. Tick “Unreliable model” and kick off again to watch the Verifier catch wrong numbers.</div>`;
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
    <p>${esc(r.summary)}</p>
    <h2>${esc(t.moments)}</h2>
    <ol>${r.moments.map((m) => `<li><b>${m.minute}'</b> ${esc(m.headline)}<br><span class="legend">${esc(m.body)}</span></li>`).join("")}</ol>`;
  // non-modal: the header controls stay clickable while the recap is open
  if (!$("recap").open) $("recap").show();
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

// The pitch: one shared picture, the home team attacks left to right.
function pitchBase(ctx, W, H, dpr) {
  const sx = W / 105, sy = H / 68;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = css("--pitch-stripe");
  for (let i = 0; i < 12; i += 2) ctx.fillRect((i * 105 / 12) * sx, 0, (105 / 12) * sx, H);
  ctx.strokeStyle = css("--pitch-line"); ctx.lineWidth = 1.3 * dpr;
  const rect = (x, y, w, h) => ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
  rect(0.5, 0.5, 104, 67);
  ctx.beginPath(); ctx.moveTo(52.5 * sx, 0); ctx.lineTo(52.5 * sx, H); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(52.5 * sx, 34 * sy, 9.15 * sx, 9.15 * sy, 0, 0, 7); ctx.stroke();
  rect(0.5, 13.85, 16.5, 40.3); rect(88.5, 13.85, 16, 40.3);
  rect(0.5, 24.85, 5.5, 18.3); rect(99, 24.85, 5.5, 18.3);
  ctx.fillStyle = css("--pitch-line");
  for (const x of [11, 94]) { ctx.beginPath(); ctx.arc(x * sx, 34 * sy, 1.8 * dpr, 0, 7); ctx.fill(); }
  return [sx, sy];
}
// an event's own coordinates -> the shared picture
const abs = (side, x, y) => (side === "away" ? [105 - x, 68 - y] : [x, y]);
const teamCol = (side) => css(side === "home" ? "--home" : "--away");
const playerById = (id) => {
  if (!S.info || !id) return null;
  for (const s of ["home", "away"]) { const p = S.info[s].players.find((q) => q.id === id); if (p) return p; }
  return null;
};
const surname = (id) => { const p = playerById(id); return p ? p.name.split(" ").slice(-1)[0] : ""; };

function arrow(ctx, x1, y1, x2, y2, head) {
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  const a = Math.atan2(y2 - y1, x2 - x1);
  ctx.beginPath(); ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - head * Math.cos(a - 0.45), y2 - head * Math.sin(a - 0.45));
  ctx.lineTo(x2 - head * Math.cos(a + 0.45), y2 - head * Math.sin(a + 0.45));
  ctx.closePath(); ctx.fill();
}
function dot(ctx, x, y, r, fill, stroke, lw) {
  ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
}

const LAYERS = {
  live: {
    caption: () => "Where all 22 players stand at the latest action, and the last few moves of the ball. Numbers are shirt numbers.",
    legend: () => `<span><span class="swatch home"></span>${esc(teamName("home"))} attacks →</span><span><span class="swatch away"></span>← ${esc(teamName("away"))} attacks</span><span>white = the ball</span>`,
    draw(ctx, sx, sy, dpr) {
      const trail = S.events.filter((e) => !["kick_off", "half_end", "pressure"].includes(e.type)).slice(-7);
      trail.forEach((ev, i) => {
        if (ev.end_x == null || !["pass", "carry"].includes(ev.type)) return;
        const [x1, y1] = abs(ev.side, ev.x, ev.y), [x2, y2] = abs(ev.side, ev.end_x, ev.end_y);
        ctx.globalAlpha = 0.25 + (0.6 * (i + 1)) / trail.length;
        ctx.strokeStyle = teamCol(ev.side); ctx.fillStyle = teamCol(ev.side); ctx.lineWidth = 2 * dpr;
        ctx.setLineDash(ev.type === "carry" ? [5 * dpr, 4 * dpr] : []);
        arrow(ctx, x1 * sx, y1 * sy, x2 * sx, y2 * sy, 7 * dpr);
        ctx.setLineDash([]);
      });
      ctx.globalAlpha = 1;
      const ev = S.live;
      if (!ev) return;
      const r = Math.max(8 * dpr, sx * 1.15);
      ctx.font = `700 ${Math.round(r * 1.15)}px "Saira Condensed", sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (const [side, off] of [["home", 0], ["away", 22]]) {
        const players = S.info ? S.info[side].players : [];
        for (let i = 0; i < 11; i++) {
          const x = ev.fz[off + 2 * i] * sx, y = ev.fz[off + 2 * i + 1] * sy;
          dot(ctx, x, y, r, teamCol(side), css("--pitch"), 1.5 * dpr);
          ctx.fillStyle = side === "home" ? css("--on-home") : css("--on-away");
          ctx.fillText(players[i] ? players[i].number : "", x, y + 0.5 * dpr);
        }
      }
      const [bx, by] = abs(ev.side, ev.end_x ?? ev.x, ev.end_y ?? ev.y);
      dot(ctx, bx * sx, by * sy, 4.5 * dpr, "#fff", "#000", 1.2 * dpr);
    },
  },
  shape: {
    team: true,
    caption: () => {
      const tw = lastPulse() && lastPulse()[S.layerTeam];
      if (!tw || !tw.shape_in) return "Average positions appear after a few minutes of play.";
      const out = tw.shape_out;
      return `${teamName(S.layerTeam)}, last 5 minutes. With the ball (solid) they line up ${tw.shape_in.formation}; without it (hollow) ${out ? out.formation : "—"}, with the back line ${out ? Math.round(out.line_height) : "—"} m from their goal and ${out ? Math.round(out.gap_def_mid) : "—"} m between defence and midfield.`;
    },
    legend: () => `<span>● with the ball</span><span>○ without the ball</span><span>lines join players read as one line</span>`,
    draw(ctx, sx, sy, dpr) {
      const tw = lastPulse() && lastPulse()[S.layerTeam];
      if (!tw) return;
      const side = S.layerTeam, col = teamCol(side);
      const drawShape = (shape, solid) => {
        if (!shape) return;
        const pts = shape.avg.map(([x, y]) => abs(side, x, y));
        const out = pts.slice(1).map((p, i) => ({ p, i: i + 1, own: shape.avg[i + 1][0] }));
        out.sort((a, b) => a.own - b.own);
        let k = 0;
        ctx.strokeStyle = col; ctx.lineWidth = (solid ? 2 : 1.5) * dpr; ctx.globalAlpha = solid ? 0.9 : 0.6;
        ctx.setLineDash(solid ? [] : [4 * dpr, 4 * dpr]);
        for (const n of shape.formation.split("-").map(Number)) {
          const line = out.slice(k, k + n).sort((a, b) => a.p[1] - b.p[1]); k += n;
          ctx.beginPath(); line.forEach(({ p }, j) => (j ? ctx.lineTo(p[0] * sx, p[1] * sy) : ctx.moveTo(p[0] * sx, p[1] * sy))); ctx.stroke();
        }
        ctx.setLineDash([]); ctx.globalAlpha = 1;
        pts.forEach(([x, y], i) => dot(ctx, x * sx, y * sy, Math.max(6 * dpr, sx * (i ? 1 : 0.85)), solid ? col : css("--pitch"), col, 2 * dpr));
      };
      drawShape(tw.shape_out, false);
      drawShape(tw.shape_in, true);
    },
  },
  threat: {
    team: true,
    caption: () => {
      const m = lastPulse() && lastPulse().match[S.layerTeam];
      if (!m) return "The threat map fills in as the game goes on.";
      const lanes = [["down the left", m.xt_share_left], ["through the middle", m.xt_share_centre], ["down the right", m.xt_share_right]];
      const [lane, share] = lanes.sort((a, b) => (b[1] || 0) - (a[1] || 0))[0];
      return `Where ${teamName(S.layerTeam)}'s passes and carries took the ball closer to scoring this match (expected threat, xT). Brighter = more danger. ${share ? `${Math.round(share * 100)}% of it came ${lane}.` : ""}`;
    },
    legend: () => `<span>each block = one sixth of the length × one third of the width</span><span>number = xT added there</span>`,
    draw(ctx, sx, sy, dpr) {
      const m = lastPulse() && lastPulse().match[S.layerTeam];
      if (!m) return;
      const zones = m.xt_zone, max = Math.max(...zones, 0.001), side = S.layerTeam;
      ctx.font = `700 ${12 * dpr}px "Saira Condensed", sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      zones.forEach((v, idx) => {
        const i = Math.floor(idx / 3), j = idx % 3;
        let [x0, y0] = abs(side, i * 17.5, j * (68 / 3));
        if (side === "away") { x0 -= 17.5; y0 -= 68 / 3; }
        ctx.globalAlpha = 0.08 + 0.72 * (v / max);
        ctx.fillStyle = teamCol(side);
        ctx.fillRect(x0 * sx + dpr, y0 * sy + dpr, 17.5 * sx - 2 * dpr, (68 / 3) * sy - 2 * dpr);
        ctx.globalAlpha = 1;
        if (v >= 0.05 * max && v > 0.005) {
          ctx.fillStyle = v / max > 0.55 ? (side === "home" ? css("--on-home") : "#fff") : "#fff";
          ctx.fillText(v.toFixed(2), (x0 + 8.75) * sx, (y0 + 34 / 3) * sy);
        }
      });
    },
  },
  passes: {
    caption: () => S.hurt.length
      ? `The ${S.hurt.length} completed passes that added the most expected threat so far. Thicker = more dangerous. A ring at the start means the pass beat a line of opponents; the label says which.`
      : "The most dangerous passes appear here as the game goes on.",
    legend: () => `<span><span class="swatch home"></span>${esc(teamShort("home"))}</span><span><span class="swatch away"></span>${esc(teamShort("away"))}</span><span>labels: passer and xT added</span>`,
    draw(ctx, sx, sy, dpr) {
      const top = S.hurt;
      const max = top.length ? top[0].xt : 1;
      ctx.font = `600 ${11 * dpr}px "IBM Plex Sans", sans-serif`; ctx.textBaseline = "bottom";
      [...top].reverse().forEach((ev) => {
        const [x1, y1] = abs(ev.side, ev.x, ev.y), [x2, y2] = abs(ev.side, ev.end_x, ev.end_y);
        const col = teamCol(ev.side);
        ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = (1.5 + 3.5 * (ev.xt / max)) * dpr;
        ctx.globalAlpha = 0.5 + 0.5 * (ev.xt / max);
        arrow(ctx, x1 * sx, y1 * sy, x2 * sx, y2 * sy, 9 * dpr);
        if (ev.lb) dot(ctx, x1 * sx, y1 * sy, 5 * dpr, null, col, 2 * dpr);
      });
      ctx.globalAlpha = 1;
      top.slice(0, 4).forEach((ev) => {
        const [x2, y2] = abs(ev.side, ev.end_x, ev.end_y);
        ctx.fillStyle = "#fff"; ctx.textAlign = x2 > 80 ? "right" : "left";
        const lx = x2 * sx + (x2 > 80 ? -8 : 8) * dpr;
        ctx.fillText(`${surname(ev.player_id)} +${ev.xt.toFixed(2)}`, lx, y2 * sy - 6 * dpr);
        if (ev.lbl && ev.lbl.length) { // which lines the pass beat
          ctx.font = `500 ${10 * dpr}px "IBM Plex Sans", sans-serif`; ctx.globalAlpha = 0.85;
          ctx.fillText(`beat ${ev.lbl.map((l) => LINE_NAMES[l] || l).join(" + ")}`, lx, y2 * sy + 8 * dpr);
          ctx.globalAlpha = 1; ctx.font = `600 ${11 * dpr}px "IBM Plex Sans", sans-serif`;
        }
      });
    },
  },
  shots: {
    caption: () => {
      const g = S.shots.filter((s) => s.outcome === "goal").length;
      return S.shots.length
        ? `All ${S.shots.length} shots so far. The bigger the circle, the better the chance (xG). Filled circles were on target; rings mark the ${g} goal${g === 1 ? "" : "s"}.`
        : "No shots yet.";
    },
    legend: () => `<span><span class="swatch home"></span>${esc(teamShort("home"))} shoots →</span><span><span class="swatch away"></span>← ${esc(teamShort("away"))} shoots</span>`,
    draw(ctx, sx, sy, dpr) {
      for (const ev of S.shots) {
        const [x, y] = abs(ev.side, ev.x, ev.y);
        const r = (4 + 22 * Math.sqrt(ev.xg || 0.01)) * dpr, col = teamCol(ev.side);
        const onTarget = ev.outcome === "goal" || ev.outcome === "saved";
        ctx.globalAlpha = onTarget ? 0.85 : 0.5;
        dot(ctx, x * sx, y * sy, r, onTarget ? col : null, col, 2 * dpr);
        ctx.globalAlpha = 1;
        if (ev.outcome === "goal") dot(ctx, x * sx, y * sy, r + 4 * dpr, null, "#fff", 2.5 * dpr);
      }
    },
  },
};
function drawPitch() {
  const [ctx, W, H, dpr] = fit($("pitch"));
  const [sx, sy] = pitchBase(ctx, W, H, dpr);
  const layer = LAYERS[S.layer];
  layer.draw(ctx, sx, sy, dpr);
  $("layer-team").hidden = !layer.team;
  $("layer-team").querySelectorAll("button").forEach((b) => {
    b.textContent = teamShort(b.dataset.team);
    b.setAttribute("aria-pressed", String(b.dataset.team === S.layerTeam));
  });
  $("pitch-caption").textContent = layer.caption();
  $("pitch-legend").innerHTML = layer.legend();
}
document.querySelectorAll("#layers button").forEach((b) => b.addEventListener("click", () => {
  S.layer = b.dataset.layer;
  document.querySelectorAll("#layers button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  schedule();
}));
document.querySelectorAll("#layer-team button").forEach((b) => b.addEventListener("click", () => {
  S.layerTeam = b.dataset.team;
  schedule();
}));

// Momentum: xT created per minute (home up, away down), who controls the game, goals and shifts.
function drawPulse() {
  const [ctx, W, H, dpr] = fit($("pulse"));
  ctx.clearRect(0, 0, W, H);
  const top = 8 * dpr, bottom = H - 18 * dpr, mid = (top + bottom) / 2, half = (bottom - top) / 2;
  const maxMin = Math.max(90, ...S.pulses.map((p) => p.minute + 1));
  const X = (m) => (m / maxMin) * W;
  // backdrop: who controls the game, a faint band per minute
  for (const p of S.pulses) {
    const col = p.state === "home_control" ? css("--home") : p.state === "away_control" ? css("--away") : p.state === "chaos" ? css("--chaos") : null;
    if (!col) continue;
    ctx.globalAlpha = 0.09; ctx.fillStyle = col; ctx.fillRect(X(p.minute), top, X(1) + 0.5, bottom - top);
  }
  ctx.globalAlpha = 1;
  ctx.strokeStyle = css("--line-strong"); ctx.lineWidth = dpr;
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(W, mid); ctx.stroke();
  ctx.strokeStyle = css("--line");
  for (let m = 15; m < maxMin; m += 15) { ctx.beginPath(); ctx.moveTo(X(m), top); ctx.lineTo(X(m), bottom); ctx.stroke(); }
  ctx.fillStyle = css("--muted"); ctx.font = `${11 * dpr}px "IBM Plex Sans", sans-serif`; ctx.textBaseline = "alphabetic"; ctx.textAlign = "left";
  for (let m = 0; m <= maxMin; m += 15) ctx.fillText(m === 45 ? "HT" : `${m}'`, Math.min(X(m) + 3 * dpr, W - 22 * dpr), H - 4 * dpr);
  // bars
  const maxXt = Math.max(0.08, ...S.pulses.map((p) => Math.max(p.xt_minute.home, p.xt_minute.away)));
  const bw = Math.max(1, X(1) - 2 * dpr);
  for (const p of S.pulses) {
    const hh = (Math.max(0, p.xt_minute.home) / maxXt) * half * 0.95;
    const ah = (Math.max(0, p.xt_minute.away) / maxXt) * half * 0.95;
    ctx.fillStyle = css("--home"); ctx.fillRect(X(p.minute) + dpr, mid - hh, bw, hh);
    ctx.fillStyle = css("--away"); ctx.fillRect(X(p.minute) + dpr, mid, bw, ah);
  }
  // 5-minute balance line
  const pts = S.pulses.map((p) => [X(p.minute + 1), mid - ((p.xt_minute ? p.home.xt - p.away.xt : 0) / (maxXt * 3)) * half]);
  if (pts.length > 1) {
    ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, Math.max(top, Math.min(bottom, y))) : ctx.moveTo(x, y)));
    ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1.6 * dpr; ctx.stroke();
  }
  ctx.setLineDash([3 * dpr, 4 * dpr]); ctx.strokeStyle = css("--muted"); ctx.lineWidth = dpr;
  for (const t of S.transitions) { const x = X(t.estimated_minute); ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); }
  ctx.setLineDash([]);
  for (const c of S.cues.filter((q) => q.kind === "goal")) {
    const y = c.side === "home" ? top + 7 * dpr : bottom - 7 * dpr;
    dot(ctx, X(c.minute + 0.5), y, 6 * dpr, teamCol(c.side), css("--panel"), 2 * dpr);
  }
  if (!S.ended && S.matchT) {
    const nowX = X(S.matchT / 60);
    ctx.strokeStyle = css("--ink"); ctx.lineWidth = dpr; ctx.beginPath(); ctx.moveTo(nowX, top); ctx.lineTo(nowX, bottom); ctx.stroke();
  }
  $("pulse-legend").innerHTML = `<span><span class="swatch home"></span>${esc(teamShort("home"))} threat ↑</span>
    <span><span class="swatch away"></span>${esc(teamShort("away"))} threat ↓</span>
    <span>line = 5-minute balance</span><span>tinted background = who controls the game (cyan = broken)</span><span>dot = goal · dashed = shift confirmed</span>`;
}

// ----------------------------------------------------------------------------- players
function tallyPlayer(d) {
  const id = d.player_id;
  if (!id) return;
  const p = (S.pl[id] ||= { passes: 0, done: 0, xt: 0, lb: 0, pk: 0, shots: 0, xg: 0, goals: 0, wins: 0, speed: 0 });
  if (d.type === "pass") { p.passes++; if (d.outcome === "complete") p.done++; }
  if (d.xt) p.xt += d.xt;
  if (d.lb) p.lb++;
  if (d.pk) p.pk += d.pk;
  if (d.type === "shot") { p.shots++; p.xg += d.xg || 0; if (d.outcome === "goal") p.goals++; }
  if (d.type === "interception" || (d.type === "tackle" && d.outcome === "won")) p.wins++;
  if (d.type === "carry" && d.ball_speed_kmh) p.speed = Math.max(p.speed, d.ball_speed_kmh);
}
const PL_COLS = [
  ["Passes", (p) => p.done, (p) => `${p.done}/${p.passes}`],
  ["xT added", (p) => p.xt, (p) => p.xt.toFixed(2)],
  ["Line breaks", (p) => p.lb, (p) => p.lb],
  ["Bypassed", (p) => p.pk, (p) => p.pk],
  ["Shots", (p) => p.shots, (p) => p.shots],
  ["xG", (p) => p.xg, (p) => p.xg.toFixed(2)],
  ["Goals", (p) => p.goals, (p) => p.goals],
  ["Ball wins", (p) => p.wins, (p) => p.wins],
  ["Top speed", (p) => p.speed, (p) => (p.speed ? `${Math.round(p.speed)} km/h` : "—")],
];
function playerRows() {
  if (!S.info) return [];
  const rows = [];
  for (const side of ["home", "away"]) {
    if (S.plTeam !== "both" && S.plTeam !== side) continue;
    for (const pl of S.info[side].players) {
      rows.push({ pl, side, s: S.pl[pl.id] || { passes: 0, done: 0, xt: 0, lb: 0, pk: 0, shots: 0, xg: 0, goals: 0, wins: 0, speed: 0 } });
    }
  }
  return rows;
}
function renderPlayers() {
  const rows = playerRows();
  const col = PL_COLS[S.plSort];
  rows.sort((a, b) => col[1](b.s) - col[1](a.s));
  const best = rows.length ? col[1](rows[0].s) : 0;
  $("players-table").innerHTML = `<thead><tr><th>Player</th><th>Pos</th>${PL_COLS.map((c, i) =>
    `<th data-col="${i}" ${i === S.plSort ? 'aria-sort="descending"' : ""} tabindex="0">${c[0]}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(({ pl, side, s }) => `<tr class="${side}"><td class="name"><i></i>${pl.number} ${esc(pl.name)}</td>
      <td>${esc(pl.position)}</td>${PL_COLS.map((c, i) =>
        `<td class="${i === S.plSort && best > 0 && c[1](s) === best ? "top" : ""}">${c[2](s)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  // stand-outs over both teams, whatever the filter
  const all = [];
  if (S.info) for (const side of ["home", "away"]) for (const pl of S.info[side].players) all.push({ pl, side, s: S.pl[pl.id] });
  const pick = (f) => all.filter((r) => r.s).sort((a, b) => f(b.s) - f(a.s))[0];
  const cards = [
    ["Most threat created", (s) => s.xt, (s) => `${s.xt.toFixed(2)} xT`, "Moved the ball closest to scoring with passes and carries."],
    ["Most line-breaking passes", (s) => s.lb, (s) => s.lb, "Passes that went past at least one line of opponents."],
    ["Most ball wins", (s) => s.wins, (s) => s.wins, "Tackles won and interceptions."],
    ["Best chances", (s) => s.xg, (s) => `${s.xg.toFixed(2)} xG`, "Expected goals from the player's shots."],
  ];
  $("standouts").innerHTML = cards.map(([what, f, show, why]) => {
    const r = pick(f);
    if (!r || f(r.s) <= 0) return `<div class="standout"><div class="what">${esc(what)}</div><div class="who">—</div></div>`;
    return `<div class="standout ${r.side}"><div class="what">${esc(what)}</div>
      <div class="who">${esc(r.pl.name)} <span class="hint">${esc(teamShort(r.side))}</span></div>
      <div class="val">${show(r.s)}</div><div class="why">${esc(why)}</div></div>`;
  }).join("");
}
$("players-table").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-col]");
  if (th) { S.plSort = +th.dataset.col; renderPlayers(); }
});
$("players-table").addEventListener("keydown", (e) => {
  const th = e.target.closest("th[data-col]");
  if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); S.plSort = +th.dataset.col; renderPlayers(); }
});
document.querySelectorAll("#pl-team button").forEach((b) => b.addEventListener("click", () => {
  S.plTeam = b.dataset.team;
  document.querySelectorAll("#pl-team button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderPlayers();
}));

// ----------------------------------------------------------------------------- broadcast
function renderBroadcast() {
  const [ctx, W, H, dpr] = fit($("bc-pitch"));
  // the 16:9 stage is wider than the pitch: centre the pitch and let the stage colour frame it
  ctx.clearRect(0, 0, W, H);
  const ph = H * 0.86, pw = ph * (105 / 68);
  ctx.save();
  ctx.translate((W - pw) / 2, (H - ph) / 2);
  const [sx, sy] = pitchBase(ctx, pw, ph, dpr);
  LAYERS.live.draw(ctx, sx, sy, dpr);
  ctx.restore();
  const mins = Math.floor(S.matchT / 60);
  const bar = (side) => `<i style="background:var(--${side})"></i>${esc(teamShort(side))}`;
  $("bc-bug").innerHTML = `<span class="t">${bar("home")}</span><span class="s">${S.score[0]}–${S.score[1]}</span>
    <span class="t">${esc(teamShort("away"))}<i style="background:var(--away)"></i></span>
    <span class="c">${S.ended ? "FT" : `${mins}'`}</span>`;
  const tr = S.trust;
  $("bc-trust").innerHTML = `Verified on air <b>${tr ? Math.round(tr.truth_score * 100) : 100}%</b>`;
  const cue = [...S.cues].reverse().find((c) => c.t_in <= S.matchT + 1);
  const el = $("bc-third");
  if (!cue) { el.className = "bc-third off"; return; }
  if (el.dataset.id !== cue.cue_id) {
    el.dataset.id = cue.cue_id;
    el.className = `bc-third ${cueSideClass(cue) || "none"}`;
    el.innerHTML = `<span class="k">${esc(KINDS[cue.kind] || cue.kind)}</span>
      <span class="m">${cue.minute}'</span>
      <div class="b"><h3>${esc(cue.headline)}</h3><p>${esc(cue.body)} <span class="v">✓ checked</span></p></div>`;
  }
}
document.querySelectorAll("#bc-bg button").forEach((b) => b.addEventListener("click", () => {
  $("stage").classList.toggle("key", b.dataset.bg === "key");
  document.querySelectorAll("#bc-bg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
}));
$("bc-full").addEventListener("click", () => {
  const st = $("stage");
  if (document.fullscreenElement) document.exitFullscreen();
  else if (st.requestFullscreen) st.requestFullscreen().catch(() => {});
});
document.addEventListener("fullscreenchange", schedule);

function schedule() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => {
    drawQueued = false;
    renderScoreboards();
    if ($("view-studio").classList.contains("active")) { drawPitch(); drawPulse(); }
    if ($("view-broadcast").classList.contains("active")) renderBroadcast();
    if ($("view-players").classList.contains("active")) renderPlayers();
  });
}

// ----------------------------------------------------------------------------- tabs, boot
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${tab.dataset.view}`));
    if (["studio", "broadcast"].includes(tab.dataset.view)) schedule();
    if (tab.dataset.view === "players") renderPlayers();
    if (tab.dataset.view === "trust") { renderTrust(); renderVerdicts(); }
    if (tab.dataset.view === "fan") renderFan();
  }));
$("start").addEventListener("click", start);
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
  const light = theme ? theme === "light" : matchMedia("(prefers-color-scheme: light)").matches;
  $("theme").textContent = light ? "Dark" : "Light";
  schedule();
}
$("theme").addEventListener("click", () => {
  const light = $("theme").textContent === "Light";
  const next = light ? "light" : "dark";
  try { localStorage.setItem("wim-theme", next); } catch { /* private mode */ }
  applyTheme(next);
});
try { applyTheme(localStorage.getItem("wim-theme")); } catch { applyTheme(null); }
$("seed").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
window.addEventListener("resize", schedule);

// Static mode when served without the API: `?static=1`, or /health is unreachable / not ours.
async function detectStatic() {
  if (new URLSearchParams(location.search).get("static") === "1") return true;
  try {
    const r = await fetch("health");
    return !(r.ok && (await r.json()).status === "ok");
  } catch { return true; }
}
function enableStaticUi() {
  const sel = document.createElement("select");
  sel.id = "seed";
  sel.title = "Pre-recorded matches";
  sel.innerHTML = Object.entries(MANIFEST.seeds)
    .map(([s, m]) => `<option value="${esc(s)}">${esc(s)} · ${esc(m.home)} v ${esc(m.away)}</option>`).join("");
  $("seed").replaceWith(sel);
  sel.addEventListener("change", start);
  sel.addEventListener("change", () => $("recap").close());
  const label = sel.closest("label");
  if (label && label.firstChild) label.firstChild.textContent = "Recorded matches ";
  document.querySelector("footer").insertAdjacentHTML("afterbegin",
    "<b>Static demo:</b> pre-recorded matches replayed in your browser, no server involved. ");
}
async function boot() {
  STATIC = await detectStatic();
  if (STATIC) {
    try { MANIFEST = await (await fetch("data/index.json")).json(); } catch { MANIFEST = null; }
    if (!MANIFEST) { $("rail").innerHTML = `<div class="empty">No backend and no pre-recorded data found.</div>`; return; }
    enableStaticUi();
  }
  const wanted = new URLSearchParams(location.search).get("seed");
  if (wanted !== null) pendingSeed = wanted;
  start();
}
boot();
