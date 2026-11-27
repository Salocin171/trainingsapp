// Analyse-Dialog: Garmin-Kennzahlen, Leistungskurve, Effizienz, Pulszonen und Renntag.
import { $, api, state } from "./core.js";
import { chart, tile } from "./charts.js";
import { escapeHtml, fmtDate, fmtDuration, fmtMin, fmtTime, isoWeek, secToPace } from "./format.js";
import { ZONE_COLORS } from "./labels.js";
import { bindRaceTab, raceTab } from "./raceday.js";

const analysisDialog = $("#analysis-dialog");
let data = null;          // letzte Antwort von /api/analysis
let tab = "metrics";      // zuletzt gewählter Reiter

async function openAnalysis(refresh = false) {
  analysisDialog.showModal();
  $("#analysis-body").innerHTML = `<p class="muted">Lade Daten …</p>`;
  try {
    data = await api(`/api/analysis${refresh ? "?refresh=1" : ""}`);
    showTab(tab);
  } catch (e) {
    $("#analysis-body").innerHTML = `<p class="warn">⚠︎ ${escapeHtml(e.message)}</p>`;
  }
}

function showTab(name) {
  tab = name;
  analysisDialog.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("#analysis-body").innerHTML = { metrics: metricsTab, power: powerTab, ef: efTab, zones: zonesTab, race: raceTab }[name](data);
  if (name === "race") bindRaceTab();
}

function metricsTab(d) {
  const g = d.garmin;
  if (!g) return `<p class="muted">Garmin-Kennzahlen nicht verfügbar${d.garmin_error ? `: ${escapeHtml(d.garmin_error)}` : " (Garmin nicht verbunden)"}.</p>`;
  const st = g.training_status, s = state.settings, pred = g.race_predictions || {};
  const cssNote = g.css ? `Garmin ${secToPace(g.css.css)} (${fmtDate(g.css.at.slice(0, 10), { day: "2-digit", month: "2-digit", year: "2-digit" })}) · eingestellt ${secToPace(s.css)}` : "";
  return `
    <div class="tiles">
      ${tile("Trainingsstatus", st ? escapeHtml(st.label) : null, st ? `Akut ${st.acute_load} / chronisch ${st.chronic_load} · Verhältnis ${st.ratio}` : "")}
      ${tile("VO2max Laufen", g.vo2max?.run?.toFixed(1))}
      ${tile("VO2max Rad", g.vo2max?.ride?.toFixed(1))}
      ${tile("Endurance Score", g.endurance?.current)}
      ${tile("Hitzeanpassung", g.heat_acclimation != null ? `${g.heat_acclimation} %` : null, "steigt mit Hitzetraining")}
      ${tile("CSS Schwimmen", g.css ? `${secToPace(g.css.css)} /100 m` : null, cssNote)}
    </div>
    <h3>Renn-Prognosen Laufen (Garmin)</h3>
    <div class="tiles">${["5K", "10K", "HalfMarathon", "Marathon"].map((k) =>
      tile({ HalfMarathon: "Halbmarathon" }[k] || k, pred[k] ? fmtTime(pred[k]) : null)).join("")}</div>
    <h3>Endurance Score</h3>
    ${chart({ series: [{ name: "Endurance Score", color: "var(--accent)", dots: true,
      points: (g.endurance?.series || []).map((p) => ({ x: p.date, y: p.value, tip: `Woche ab ${fmtDate(p.date)}: ${p.value}` })) }] })}
    <h3>FTP-Verlauf Rad (Garmin) <span class="label">Garmin-Einträge aus Tests, automatischer Erkennung und Änderungen</span></h3>
    ${chart({ series: [{ name: "FTP", color: "var(--ride)", dots: true, line: false,
      points: g.ftp_series.map((p) => ({ x: p.date, y: p.value, tip: `${fmtDate(p.date)}: ${p.value} W` })) }],
      refs: [{ y: s.ftp, label: `eingestellt ${s.ftp} W` }] })}
    <h3>VO2max (90 Tage)</h3>
    ${chart({ series: [
      { name: "Laufen", color: "var(--run)", points: g.vo2max_series.filter((p) => p.run).map((p) => ({ x: p.date, y: p.run, tip: `Laufen ${fmtDate(p.date)}: ${p.run}` })) },
      { name: "Rad", color: "var(--ride)", points: g.vo2max_series.filter((p) => p.ride).map((p) => ({ x: p.date, y: p.ride, tip: `Rad ${fmtDate(p.date)}: ${p.ride}` })) },
    ], yFormat: (v) => v.toFixed(0) })}
    <p class="muted small">Stand: ${d.garmin_at ? new Date(d.garmin_at).toLocaleString("de-DE") : "–"} · Garmin-Werte werden 6 h zwischengespeichert.</p>`;
}

function powerTab(d) {
  const pc = d.power_curve;
  const pts = (list, label) => list.map((p) => ({ x: p.duration, y: p.watts,
    tip: `${label} ${fmtDuration(p.duration)}: ${p.watts} W (${fmtDate(p.date)}, ${escapeHtml(p.name)})` }));
  return `
    <div class="tiles">
      ${tile("FTP eingestellt", `${pc.ftp} W`)}
      ${pc.estimates.map((e) => tile(e.method, `${e.watts} W`, `${e.watts >= pc.ftp ? "+" : ""}${e.watts - pc.ftp} W zur Einstellung`)).join("")}
    </div>
    ${chart({ x: "log", height: 260, series: [
      { name: "Letzte 365 Tage", color: "var(--muted)", dots: true, points: pts(pc.year, "365 Tage") },
      { name: "Letzte 90 Tage", color: "var(--accent)", dots: true, points: pts(pc.recent, "90 Tage") },
    ], refs: [{ y: pc.ftp, label: `FTP ${pc.ftp} W` }] })}
    <p class="muted small">Beste Durchschnittsleistung je Dauer aus allen Radeinheiten (Garmin-Zusammenfassung).
      Die Schätzungen nutzen nur die letzten 90 Tage – ohne echte Maximaltests fallen sie eher zu niedrig aus.</p>`;
}

function efTab(d) {
  const median = (v) => { const a = [...v].sort((x, y) => x - y), m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; };
  const DAY = 864e5;
  // Laufen: m/min → Tempo min:ss/km
  const pace = (mpm) => { const sec = 60000 / mpm; return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`; };
  const block = (sport, label, color) => {
    const e = d.efficiency[sport];
    const isRun = sport === "run";
    const fmt = isRun ? (v) => `${pace(v)}/km` : (v) => `${Math.round(v)} W`;
    const what = isRun ? `Tempo bei ${e.ref_hr} bpm` : `Watt bei ${e.ref_hr} bpm`;
    const points = e.points.map((p) => ({ x: p.date, y: p.at_ref,
      tip: `${fmtDate(p.date)} ${escapeHtml(p.name)}: ${fmt(p.at_ref)} bei ${e.ref_hr} bpm (EF roh ${p.ef.toFixed(2)})` }));
    // gleitender 28-Tage-Median, nur wo mindestens 3 Einheiten im Fenster liegen – sonst Lücke statt Linie
    let gap = false;
    const trend = [];
    for (const p of points) {
      const t = new Date(p.x).getTime();
      const win = points.filter((q) => { const u = new Date(q.x).getTime(); return u <= t && u > t - 28 * DAY; });
      if (win.length < 3) { gap = true; continue; }
      const y = median(win.map((q) => q.y));
      trend.push({ x: p.x, y, gap, tip: `28-Tage-Median (${win.length} Einheiten): ${fmt(y)}` });
      gap = false;
    }
    const trendText = e.trend == null
      ? `zu wenig Daten (${e.n_recent} bzw. ${e.n_before} Einheiten, nötig je 3)`
      : `${e.trend > 0 ? "+" : ""}${e.trend} %`;
    const excluded = (e.excluded || []).slice().reverse();
    return `<h3>${label} <span class="label">${what}</span></h3>
      <div class="tiles">${tile("Trend", trendText, e.trend == null ? "" : `Median 28 Tage (${e.n_recent}) vs. davor (${e.n_before})`)}
        ${tile("Einheiten", e.points.length, "vergleichbar")}${tile("Nicht gezählt", excluded.length, "siehe Liste unten")}
        ${tile("Referenzpuls", `${e.ref_hr} bpm`, isRun ? `+1 bpm ≈ ${(1 / e.slope).toFixed(1)} m/min` : `+1 bpm ≈ ${(1 / e.slope).toFixed(1)} W`)}</div>
      ${chart({ yFormat: isRun ? pace : (v) => Math.round(v), series: [
        { name: "Einzelne Einheiten", color, dots: true, line: false, points },
        { name: "28-Tage-Median", color: "var(--text)", points: trend },
      ] })}
      ${excluded.length ? `<details class="small"><summary class="muted">Nicht gezählte Einheiten (${excluded.length})</summary>
        <table class="small">${excluded.map((x) => `<tr><td>${fmtDate(x.date)}</td><td>${escapeHtml(x.name)}</td>
          <td>EF ${x.ef.toFixed(2)}</td><td class="muted">${escapeHtml(x.reason)}</td></tr>`).join("")}</table></details>` : ""}`;
  };
  const { ride, run } = d.efficiency;
  const np = ride.np_range ? `NP ${ride.np_range[0]}–${ride.np_range[1]} W (45–80 % FTP)` : "NP 45–80 % FTP";
  return `<p class="muted small"><b>Watt bzw. Tempo bei gleichem Puls.</b> Steigt der Wert, wächst die Grundlage.
      Punkte = einzelne Einheiten, Linie = Median über 28 Tage.</p>
    <details class="small ef-rules"><summary>Wie wird gerechnet, welche Einheiten zählen?</summary>
      <ul>
        <li><b>Umrechnung:</b> Jede Einheit wird auf deinen Referenzpuls umgerechnet (Rad ${ride.ref_hr ?? "–"} bpm,
          Laufen ${run.ref_hr ?? "–"} bpm = Median deiner Einheiten). So misst der Wert die Form, nicht die Intensität.</li>
        <li><b>Rad:</b> 45 min–3 h · ${np} · gleichmäßig (NP höchstens 5 % auf der Rolle bzw. 12 % draußen über Ø-Leistung)</li>
        <li><b>Laufen:</b> 30–90 min · draußen · kein Koppellauf</li>
        <li><b>Beides:</b> höchstens 10 % in Zone 4–5 · Puls gleichmäßig · keine Intervalle (anaerober Trainingseffekt unter 1,5)
          · kein Wettkampf · nicht über 28 °C</li>
      </ul>
    </details>
    ${block("ride", "Rad", "var(--ride)")}${block("run", "Laufen", "var(--run)")}`;
}

function zonesTab(d) {
  const max = Math.max(1, ...d.zones.map((w) => w.zones.reduce((a, b) => a + b, 0)));
  const bars = d.zones.map((w) => {
    const total = w.zones.reduce((a, b) => a + b, 0);
    return `<div class="zweek">
      <div class="zstack" style="height:${(total / max) * 100}%">${w.zones.map((z, i) => z ? `<span style="flex:${z};background:${ZONE_COLORS[i]}"
        title="KW ${isoWeek(w.week_start)} · Zone ${i + 1}: ${fmtMin(z)}"></span>` : "").reverse().join("")}</div>
      <b class="small">${w.low_pct != null ? `${w.low_pct} %` : "–"}</b>
      <span class="muted small">KW ${isoWeek(w.week_start)}</span></div>`;
  }).join("");
  return `<p class="muted small">Zeit in Pulszonen (Schwimmen, Rad, Laufen) pro Woche. Die Zahl unter jedem Balken ist der
      Anteil locker (Zone 1–2). Für Ironman-Vorbereitung sind ~80 % locker ein guter Richtwert.</p>
    <div class="chart-legend">${ZONE_COLORS.map((c, i) => `<span><i style="background:${c}"></i>Zone ${i + 1}</span>`).join("")}</div>
    <div class="zchart">${bars}</div>`;
}

export function bindAnalysis() {
  $("#btn-analysis").onclick = () => openAnalysis();
  $("#btn-analysis-refresh").onclick = () => openAnalysis(true);
  analysisDialog.querySelector(".tabs").onclick = (e) => e.target.dataset.tab && showTab(e.target.dataset.tab);
}
