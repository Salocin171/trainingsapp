// Wochenübersicht unter der Wochenansicht: Tage, Umfang je Sport, Soll, Intensität, Form am Ende der Woche.
// Erledigtes zählt mit echten Werten, Geplantes geschätzt (Strecke aus Name bzw. Tempo-Ziel → „≈“).
import { $, api } from "./core.js";
import { escapeHtml, fmtHours, fmtMin, fmtNum, isoWeek } from "./format.js";
import { SPORT_LABEL } from "./labels.js";

const box = $("#week-summary");
let token = 0;  // nur die Antwort zur zuletzt angezeigten Woche zeigen
const DISTANCE_SPORTS = ["swim", "run"];  // Hauptwert in km; sonst Stunden
const WEEKDAY = (iso) => new Date(`${iso}T12:00`).toLocaleDateString("de-DE", { weekday: "short" }).replace(".", "");

// → true, wenn die Übersicht vorher zu sehen war (Breite des Kalenders ändert sich)
export function hideWeekSummary() {
  token++;
  const was = !box.hidden;
  box.hidden = true;
  return was;
}

export async function showWeekSummary(startIso) {
  const mine = ++token;
  try {
    const s = await api(`/api/week-summary?start=${startIso}`);
    if (mine !== token) return;
    box.innerHTML = head(s) + days(s) + sports(s) + stats(s);
    box.hidden = false;
  } catch {
    if (mine === token) box.hidden = true;  // Übersicht ist ein Zusatz – Kalender funktioniert auch ohne
  }
}

const km = (m, estimated) => `${estimated ? "≈ " : ""}${fmtNum(Math.round(m / 100) / 10)} km`;
const pct = (part, total) => (total ? Math.round((part / total) * 100) : 0);

function weekLabel(w) {
  if (w.race_week) return "Rennwoche";
  const parts = [];
  if (w.cycle_no) parts.push(`Block ${w.cycle_no}`);
  if (w.recovery) parts.push("Entlastungswoche");
  else if (w.cycle_week) parts.push(`Belastungswoche ${w.cycle_week}`);
  return parts.join(" · ");
}

function head(s) {
  const w = s.week, t = s.totals;
  const target = w.target_hours * 3600, total = t.endurance_seconds;
  const scale = Math.max(target, total) || 1;
  const sessions = `${t.done_sessions} von ${t.sessions} Einheiten erledigt` + (t.missed ? ` · ${t.missed} verpasst` : "");
  return `<div class="ws-head">
    <div><h2>KW ${isoWeek(s.week_start)}${weekLabel(w) ? ` · ${weekLabel(w)}` : ""}</h2>
      <p class="muted small">${escapeHtml(w.block_name)} · ${sessions}${w.heat ? ` · 🔥 ${w.heat_sessions}× Hitze` : ""}</p></div>
    <div class="ws-target" title="Schwimmen + Rad + Laufen: erledigt, noch geplant und Soll der Woche">
      <div class="row-between"><span>Ausdauer <b>${fmtHours(total / 3600)}</b>${t.endurance_done_seconds ? ` <span class="muted">(${fmtHours(t.endurance_done_seconds / 3600)} erledigt)</span>` : ""}</span>
        <span class="muted">Soll ${fmtHours(w.target_hours)} · ${pct(total, target)} %</span></div>
      <div class="ws-bar"><span class="done" style="width:${pct(t.endurance_done_seconds, scale)}%"></span>
        <span class="planned" style="width:${pct(total - t.endurance_done_seconds, scale)}%"></span>
        ${target ? `<i style="left:calc(${pct(target, scale)}% - 1px)"></i>` : ""}</div>
    </div>
  </div>`;
}

// Eine Spalte je Tag, genau unter den Kalenderspalten
function days(s) {
  const max = Math.max(1, ...s.days.map((d) => d.seconds));
  const order = Object.keys(SPORT_LABEL);
  return `<div class="ws-days">${s.days.map((d) => {
    const segments = Object.entries(d.by_sport).sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
      .map(([sport, sec]) => `<span class="sport-${sport}" style="height:${(sec / max) * 100}%" title="${SPORT_LABEL[sport] || sport}: ${fmtMin(sec)}"></span>`).join("");
    const miss = d.missed ? `<span class="miss">${d.missed} verpasst</span>` : "";
    if (!d.sessions) return `<div class="ws-day rest"><div class="ws-col"></div><span>${miss ? "" : "Ruhetag"}</span>${miss}</div>`;
    return `<div class="ws-day ${d.done ? "" : "planned"}" title="${WEEKDAY(d.date)}: ${d.sessions} Einheit${d.sessions > 1 ? "en" : ""}${d.done ? " (erledigt)" : ""}">
      <div class="ws-col">${segments}</div><b>${fmtMin(d.seconds)}</b><span class="muted tss">${d.tss} TSS</span>${miss}</div>`;
  }).join("")}</div>`;
}

function sportTile(sport, v) {
  const byDistance = DISTANCE_SPORTS.includes(sport) && v.meters;
  const main = byDistance ? km(v.meters, v.estimated) : fmtHours(v.seconds / 3600);
  const done = byDistance ? (v.done_meters ? `erledigt ${km(v.done_meters)}` : "")
    : v.done_seconds ? `erledigt ${fmtHours(v.done_seconds / 3600)}` : "";
  const l = v.longest;
  const longest = l && v.sessions > 1
    ? `längste: ${byDistance && l.meters ? km(l.meters) : fmtMin(l.seconds)} (${WEEKDAY(l.date)})` : "";
  const ridden = sport === "ride" && v.done_meters ? ` · ${km(v.done_meters)} gefahren` : "";
  return `<div class="ws-tile sport-${sport}">
    <span class="label"><i class="dot"></i>${SPORT_LABEL[sport] || escapeHtml(sport)}</span>
    <b>${main}</b>
    <span class="sub">${v.sessions} Einheit${v.sessions > 1 ? "en" : ""} · ${byDistance ? fmtMin(v.seconds) : `${v.tss} TSS`}${ridden}</span>
    ${done || longest ? `<span class="sub">${[done, longest].filter(Boolean).join(" · ")}</span>` : ""}
  </div>`;
}

function sports(s) {
  const order = Object.keys(SPORT_LABEL);
  const list = Object.entries(s.sports).sort(([a], [b]) => order.indexOf(a) - order.indexOf(b));
  return list.length ? `<div class="ws-sports">${list.map(([k, v]) => sportTile(k, v)).join("")}</div>` : "";
}

function stats(s) {
  const t = s.totals, i = s.intensity;
  const sum = i.easy + i.moderate + i.hard;
  const mix = sum ? `<div class="ws-mix">${["easy", "moderate", "hard"].map((k) => `<span class="${k}" style="width:${pct(i[k], sum)}%"></span>`).join("")}</div>
      <span class="ws-legend"><span><i style="background:#3b82f6"></i>locker ${pct(i.easy, sum)} %</span>
        <span><i style="background:#22c55e"></i>mittel ${pct(i.moderate, sum)} %</span>
        <span><i style="background:#f97316"></i>hart ${pct(i.hard, sum)} %</span></span>` : `<span class="sub">keine Ausdauereinheiten</span>`;
  const hard = s.hard_sessions;
  const load = s.load;
  return `<div class="ws-stats">
    <div class="ws-tile"><span class="label">Gesamt</span><b>${fmtMin(t.seconds)}</b>
      <span class="sub">${t.tss} TSS${t.done_tss ? ` · ${t.done_tss} erledigt` : ""} · ${t.rest_days} Ruhetag${t.rest_days === 1 ? "" : "e"}</span></div>
    <div class="ws-tile" title="Zeit in Zone 1–2 / 3 / 4–5 (Schwimmen, Rad, Laufen): erledigt aus den Pulszonen, geplant aus den Schritten">
      <span class="label">Intensität</span>${mix}</div>
    <div class="ws-tile"><span class="label">Harte Einheiten</span><b>${hard.length}</b>
      <span class="sub list">${hard.map((h) => `${WEEKDAY(h.date)} ${escapeHtml(h.name.replace(/^\d{1,2}:\d{2}\s*·\s*/, ""))}`).join(" · ") || "keine"}</span></div>
    ${load ? `<div class="ws-tile" title="Fitness (CTL), Ermüdung (ATL) und Form (TSB) nach Sonntag – mit den geplanten Workouts">
      <span class="label">Ende der Woche</span><b>Form ${load.tsb > 0 ? "+" : ""}${load.tsb}</b>
      <span class="sub">${escapeHtml(load.form)} · Fitness ${load.ctl} · Ermüdung ${load.atl}</span></div>` : ""}
  </div>`;
}
