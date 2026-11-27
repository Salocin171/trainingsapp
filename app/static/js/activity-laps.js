// Abschnitte einer Aktivität im Aktivitätsdialog: Intervalle mit Zwischenzeit, Pace/Leistung, Puls und Ziel aus dem Plan.
// Spalten je Sport: Laufen Pace, Rad Watt, Schwimmen Pace/100 m mit SWOLF. Daten: GET /api/activities/{id}/laps.
import { api } from "./core.js";
import { escapeHtml, fmtNum, fmtTime } from "./format.js";

const KIND = {
  warmup: { run: "Einlaufen", ride: "Einfahren", swim: "Einschwimmen" },
  cooldown: { run: "Auslaufen", ride: "Ausfahren", swim: "Ausschwimmen" },
  recovery: { run: "Trabpause", ride: "Erholung", swim: "Pause" },
  interval: "Intervall", steady: "Konstant", rest: "Pause",
};
const SOURCE_NOTE = {
  steps: "Abschnitte aus dem Workout auf der Uhr",
  plan: "Nach den Schritten des Plans geschnitten (ab Start der Aufzeichnung)",
  laps: "Runden wie aufgezeichnet",
};
let token = 0;

// --- Formate

const per = (sport) => (sport === "swim" ? 100 : 1000);
function pace(speed, sport) {
  if (!speed) return "–";
  if (sport === "ride") return `${fmtNum((speed * 3.6).toFixed(1))} km/h`;
  const sec = Math.round(per(sport) / speed);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}
const paceUnit = (sport) => (sport === "swim" ? "/100 m" : "/km");
const num = (v, unit = "") => (v ? `${Math.round(v)}${unit}` : "–");
const dist = (m) => (!m ? "–" : m >= 1000 ? `${fmtNum((m / 1000).toFixed(2))} km` : `${Math.round(m)} m`);

function targetText(t, sport) {
  if (!t) return "";
  if (t.type === "power") return `${Math.round(t.low)}–${Math.round(t.high)} W`;
  if (t.type === "hr") return `${Math.round(t.low)}–${Math.round(t.high)} bpm`;
  return `${pace(t.high, sport)}–${pace(t.low, sport)}${paceUnit(sport)}`;  // schneller (hohe Geschwindigkeit) zuerst
}

function label(s, sport, i) {
  const k = KIND[s.kind];
  let text = typeof k === "object" ? k[sport] || k.run : k;
  if (!text) {  // Runden ohne Workout: Schwimmserie nach Strecke, sonst durchnummeriert
    text = sport === "swim" ? `${Math.round(s.distance)} m${s.stroke ? ` ${s.stroke}` : ""}` : `Runde ${i + 1}`;
  } else if (sport === "swim" && s.kind !== "rest" && s.distance) {
    text += ` ${Math.round(s.distance)} m`;
  }
  return `${escapeHtml(text)}${s.rep ? ` <span class="muted">${s.rep}</span>` : ""}`;
}

// --- Tabelle: Spalten je Sport; die Spalte des Ziels (Pace, Watt oder Puls) wird grün/orange markiert

function columns(sport) {
  const hr = [["Ø HF", (s) => num(s.hr), "hr"], ["max", (s) => num(s.max_hr)]];
  if (sport === "ride") {
    return [["Zeit", (s) => fmtTime(s.duration)], ["Ø Watt", (s) => num(s.power, " W"), "power"],
      ["NP", (s) => num(s.np)], ...hr, ["Kadenz", (s) => num(s.cadence)], ["Tempo", (s) => (s.speed ? pace(s.speed, "ride") : "–")]];
  }
  if (sport === "swim") {
    return [["Zeit", (s) => fmtTime(s.duration)], ["Strecke", (s) => dist(s.distance)],
      [`Pace${paceUnit(sport)}`, (s) => pace(s.speed, sport), "pace"], ...hr.slice(0, 1),
      ["SWOLF", (s) => num(s.swolf)], ["Züge", (s) => num(s.strokes)]];
  }
  return [["Zeit", (s) => fmtTime(s.duration)], ["Strecke", (s) => dist(s.distance)],
    [`Pace${paceUnit(sport)}`, (s) => pace(s.speed, sport), "pace"], ...hr, ["Kadenz", (s) => num(s.cadence)]];
}

function table(rows, sport, { total = null, targets = false } = {}) {
  const cols = columns(sport).filter(([, fn]) => rows.some((r) => fn(r) !== "–"));  // leere Spalten weglassen
  const hasTarget = targets && rows.some((r) => r.target);
  const cell = (s, [, fn, key]) => {
    const mark = key && s.target?.type === key && s.in_target != null ? (s.in_target ? "ok" : "off") : "";
    return `<td class="${mark}">${fn(s)}</td>`;
  };
  return `<div class="laps-scroll"><table class="laps-table">
    <tr><th></th>${cols.map(([h]) => `<th>${h}</th>`).join("")}${hasTarget ? "<th>Ziel</th>" : ""}</tr>
    ${rows.map((s, i) => `<tr class="k-${s.kind || "lap"}"><td>${label(s, sport, i)}</td>${cols.map((c) => cell(s, c)).join("")}
      ${hasTarget ? `<td class="muted">${targetText(s.target, sport)}</td>` : ""}</tr>`).join("")}
    ${total ? `<tr class="total"><td>Gesamt</td>${cols.map(([, fn]) => `<td>${fn(total)}</td>`).join("")}${hasTarget ? "<td></td>" : ""}</tr>` : ""}
  </table></div>`;
}

// Kurzfassung je Intervall-Gruppe, z. B. „5 × 4:00 · Ø 1,02 km · Ø 3:55/km · Ø HF 183 · 5/5 im Ziel“
function summary(g, sport) {
  // Schwimmen: Serien nach Strecke; Laufen: Dauer plus Ø Strecke; Rad: Dauer
  const size = sport === "swim" && g.avg_distance ? dist(g.avg_distance) : fmtTime(g.avg_duration);
  const parts = [
    sport === "run" && g.avg_distance ? `Ø ${dist(g.avg_distance)}` : "",
    `Ø ${sport === "ride" ? num(g.power, " W") : `${pace(g.speed, sport)}${paceUnit(sport)}`}`,
    g.hr ? `Ø HF ${Math.round(g.hr)}${g.max_hr ? ` (max ${Math.round(g.max_hr)})` : ""}` : "",
  ].filter(Boolean).map((t) => `<span>${t}</span>`).join("");
  const target = g.rated ? `<span class="${g.in_target === g.rated ? "ok" : "off"}">${g.in_target}/${g.rated} im Ziel</span>
    <span class="muted">(${targetText(g.target, sport)})</span>` : "";
  return `<div class="lap-sum"><b>${g.count} × ${size}</b>${parts}${target}</div>`;
}

export async function showActivityLaps(box, activityId) {
  const mine = ++token;
  box.innerHTML = `<p class="muted small">Abschnitte werden geladen …</p>`;
  let res;
  try {
    res = await api(`/api/activities/${encodeURIComponent(activityId)}/laps`);
  } catch (e) {
    if (mine === token) box.innerHTML = `<p class="muted small">Abschnitte nicht verfügbar: ${escapeHtml(e.message)}</p>`;
    return;
  }
  if (mine !== token) return;
  if (res.source === "none" || !res.segments?.length) {
    box.innerHTML = res.message ? `<p class="muted small">${escapeHtml(res.message)}</p>` : "";
    return;
  }
  const sport = res.sport;
  const plan = res.workout ? ` · Plan: ${escapeHtml(res.workout.name)}` : "";
  box.innerHTML = `<h3>Abschnitte</h3>
    ${res.intervals.map((g) => summary(g, sport)).join("")}
    ${table(res.segments, sport, { total: res.total, targets: true })}
    <p class="muted small">${SOURCE_NOTE[res.source]}${plan}</p>
    ${res.laps.length ? `<details class="small"><summary class="muted">Alle Runden (${res.laps.length})</summary>
      ${table(res.laps, sport)}</details>` : ""}`;
}
