// Kleine SVG-Diagramme für die Analyse (ohne Bibliothek).

// Liniendiagramm mit einer y-Achse. series: [{name, color, points: [{x, y, tip}], dots, line, dashed}]
// x: "time" (ISO-Datum) oder "log" (Sekunden, Leistungskurve). refs: waagrechte Bezugslinien [{y, label}].
export function chart({ series, x = "time", yFormat = (v) => Math.round(v), refs = [], height = 220 }) {
  const W = 640, H = height, L = 44, R = 12, T = 12, B = 26;
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) return `<p class="muted small">Noch keine Daten.</p>`;
  const xv = (p) => (x === "time" ? new Date(p.x).getTime() : Math.log(p.x));
  const ys = [...pts.map((p) => p.y), ...refs.map((r) => r.y)];
  // runde Achsenwerte: Schrittweite 1/2/5 × 10^n, Bereich auf ganze Schritte erweitert
  const raw = (Math.max(...ys) - Math.min(...ys)) / 4 || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * mag).find((v) => v >= raw);
  const y0 = Math.floor(Math.min(...ys) / step) * step, y1 = Math.ceil(Math.max(...ys) / step) * step;
  const [x0, x1] = [Math.min(...pts.map(xv)), Math.max(...pts.map(xv))];
  const sx = (v) => L + ((v - x0) / (x1 - x0 || 1)) * (W - L - R);
  const sy = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let out = "";
  for (let v = y0; v <= y1 + step / 2; v += step) {  // dezente Gitterlinien + y-Beschriftung
    out += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/>
      <text x="${L - 6}" y="${sy(v) + 4}" class="tick" text-anchor="end">${yFormat(v)}</text>`;
  }
  const xticks = x === "log"
    ? [[5, "5 s"], [30, "30 s"], [60, "1 min"], [300, "5 min"], [1200, "20 min"], [3600, "1 h"], [7200, "2 h"]]
      .filter(([d]) => Math.log(d) >= x0 && Math.log(d) <= x1).map(([d, l]) => [Math.log(d), l])
    : Array.from({ length: 5 }, (_, i) => x0 + ((x1 - x0) * i) / 4)
      .map((t) => [t, new Date(t).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })]);
  for (const [v, label] of xticks) out += `<text x="${sx(v)}" y="${H - 8}" class="tick" text-anchor="middle">${label}</text>`;
  for (const r of refs) {
    out += `<line x1="${L}" x2="${W - R}" y1="${sy(r.y)}" y2="${sy(r.y)}" class="ref"/>
      <text x="${W - R}" y="${sy(r.y) - 4}" class="tick" text-anchor="end">${r.label}</text>`;
  }
  for (const s of series) {
    const p = [...s.points].sort((a, b) => xv(a) - xv(b));
    // Linie in Abschnitte teilen: Punkte mit gap: true beginnen einen neuen Abschnitt (Datenlücke)
    const segments = s.line === false ? [] : p.reduce((acc, q) => {
      if (q.gap || !acc.length) acc.push([]);
      acc[acc.length - 1].push(q);
      return acc;
    }, []);
    for (const seg of segments.filter((g) => g.length > 1)) {
      out += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round"
        ${s.dashed ? 'stroke-dasharray="5 4"' : ""} points="${seg.map((q) => `${sx(xv(q))},${sy(q.y)}`).join(" ")}"/>`;
    }
    for (const q of p) {  // sichtbarer Punkt + größere unsichtbare Trefferfläche mit Tooltip
      if (s.dots) out += `<circle cx="${sx(xv(q))}" cy="${sy(q.y)}" r="3.5" fill="${s.color}" stroke="var(--panel)" stroke-width="1.5"/>`;
      out += `<circle cx="${sx(xv(q))}" cy="${sy(q.y)}" r="9" fill="transparent"><title>${q.tip || `${s.name}: ${yFormat(q.y)}`}</title></circle>`;
    }
  }
  const legend = series.length > 1
    ? `<div class="chart-legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("")}</div>` : "";
  return `${legend}<svg class="chart" viewBox="0 0 ${W} ${H}">${out}</svg>`;
}

// Kachel mit Kennzahl
export const tile = (label, value, sub = "") =>
  `<div class="tile"><span class="label">${label}</span><b>${value ?? "–"}</b>${sub ? `<span class="muted small">${sub}</span>` : ""}</div>`;
