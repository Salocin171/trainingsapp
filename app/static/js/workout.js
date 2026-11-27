// Workout-Berechnungen und -Grafiken (gleiche Formeln wie app/workouts.py, für die Live-Vorschau).
import { meta, state } from "./core.js";
import { fmtMin, secToPace } from "./format.js";
import { TARGET_SHORT, ZONE_COLORS } from "./labels.js";

// Stabi, Dehnen: TSS pauschal pro Stunde, keine Intensität und kein Profil
export const isFlat = (sport) => sport in meta.flat_tss_per_hour;

export const stepTarget = (s, workoutTarget) => (s.target in TARGET_SHORT ? s.target : workoutTarget);

export function* flatten(steps) {
  for (const s of steps) {
    if (s.kind === "repeat") for (let i = 0; i < s.count; i++) yield* flatten(s.steps);
    else yield s;
  }
}

export function workoutStats(w) {
  let duration = 0, tss = 0;
  for (const s of flatten(w.steps || [])) {
    duration += s.duration;
    const intensity = (Number(s.low) + Number(s.high)) / 200;
    tss += (s.duration / 3600) * intensity ** 2 * 100;
  }
  if (isFlat(w.sport)) tss = (duration / 3600) * meta.flat_tss_per_hour[w.sport];
  const IF = duration ? Math.sqrt(tss / ((duration / 3600) * 100)) : 0;
  return { duration, tss: Math.round(tss), IF: IF.toFixed(2) };
}

// Prozent → absoluter Zielwert, mit denselben Bezugsgrößen wie app/sync/garmin.py
function absoluteTarget(pct, sport, target) {
  const st = state.settings;
  if (target === "power") return Math.round((st.ftp * pct) / 100);
  if (target === "hr") return Math.round(((sport === "ride" ? st.lthr_ride : st.lthr_run) * pct) / 100);
  return secToPace((sport === "swim" ? st.css : st.threshold_pace) / (pct / 100));  // mehr % = schneller
}

// Zielbereich eines Schritts in Watt / bpm / Pace, z. B. „210–230 W“
export function absoluteRange(s, sport, workoutTarget) {
  const target = stepTarget(s, workoutTarget);
  if (["strength", "mobility"].includes(sport) || !(Number(s.low) || Number(s.high))) return "";
  const unit = target === "power" ? "W" : target === "hr" ? "bpm" : sport === "swim" ? "/100 m" : "/km";
  const lo = absoluteTarget(Number(s.low), sport, target), hi = absoluteTarget(Number(s.high), sport, target);
  return `${lo === hi ? lo : `${lo}–${hi}`} ${unit}`;
}

function zoneColor(pct) {
  if (pct < 56) return "#94a3b8";
  if (pct < 76) return "#3b82f6";
  if (pct < 88) return "#22c55e";
  if (pct < 95) return "#eab308";
  if (pct < 106) return "#f97316";
  return "#ef4444";
}

// Intensitätsprofil als SVG (Kalenderkarte, Editor, Details)
export function drawProfile(svg, steps) {
  const all = [...flatten(steps)];
  const total = all.reduce((a, s) => a + s.duration, 0) || 1;
  const W = 600, H = 90, max = 140;
  let x = 0, out = "";
  for (const s of all) {
    const w = (s.duration / total) * W;
    const h1 = (Math.min(s.low, max) / max) * H, h2 = (Math.min(s.high, max) / max) * H;
    const color = zoneColor((Number(s.low) + Number(s.high)) / 2);
    if (s.kind === "warmup" || s.kind === "cooldown") {
      // Einwärmen/Ausfahren: Rampe von → bis
      const [a, b] = s.kind === "warmup" ? [h1, h2] : [h2, h1];
      out += `<polygon points="${x},${H} ${x},${H - a} ${x + w},${H - b} ${x + w},${H}"
               fill="${color}" stroke="var(--panel)" stroke-width="0.5"/>`;
    } else {
      // Intervall/Konstant: Zielbereich – voll bis zur Untergrenze, heller Streifen bis zur Obergrenze
      const lo = Math.min(h1, h2), hi = Math.max(h1, h2);
      out += `<rect x="${x}" y="${H - lo}" width="${w}" height="${lo}" fill="${color}" stroke="var(--panel)" stroke-width="0.5"/>`;
      if (hi > lo) out += `<rect x="${x}" y="${H - hi}" width="${w}" height="${hi - lo}" fill="${color}" opacity="0.4"/>`;
    }
    x += w;
  }
  const ftpLine = H - (100 / max) * H;
  out += `<line x1="0" x2="${W}" y1="${ftpLine}" y2="${ftpLine}" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="0.7"/>`;
  svg.innerHTML = out;
}

// Gestapelter Balken: Zeit in Pulszone 1–5
export function zoneBar(zones) {
  const total = zones.reduce((a, b) => a + b, 0) || 1;
  return `<div class="zonebar">${zones.map((z, i) => z ? `<span style="flex:${z};background:${ZONE_COLORS[i]}"
    title="Zone ${i + 1}: ${fmtMin(z)} (${Math.round((z / total) * 100)} %)">${z / total > 0.08 ? `Z${i + 1}` : ""}</span>` : "").join("")}</div>`;
}

// Efficiency Factor: NP bzw. steigungsbereinigtes Tempo (m/min) pro Herzschlag – wie app/analysis.py
export function efficiency(a) {
  const m = a.metrics || {};
  if (!m.avg_hr) return null;
  if (a.sport === "ride" && m.np) return m.np / m.avg_hr;
  if (a.sport === "run" && (m.gap || m.speed)) return ((m.gap || m.speed) * 60) / m.avg_hr;
  return null;
}
