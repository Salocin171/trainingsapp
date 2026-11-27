// Renntag-Planung (Reiter in der Analyse): Zielwerte, Zeiten und Verpflegung je Disziplin.
import { $, api, state } from "./core.js";
import { escapeHtml, fmtDate, fmtTime, secToPace } from "./format.js";

// Alle Annahmen hier als Standardwerte – im Tab änderbar und in settings.race_plan gespeichert.
const RACE_DEFAULTS = {
  swim_km: 3.8, bike_km: 180, run_km: 42.2, bike_hm: 0,
  swim_offset: 5,        // s/100 m langsamer als CSS (lange Strecke, Massenstart)
  wetsuit: true,         // Neopren: ca. 3 s/100 m schneller
  bike_if: 0.70,         // Ironman-Rad: IF 0,65–0,75 je nach Leistungsniveau
  cda: 0.25, crr: 0.004, bike_kg: 9,
  run_pct: 82,           // % der Schwellengeschwindigkeit (Ironman-Marathon ≈ 80–85 %)
  t1: 6, t2: 4,          // Wechsel in Minuten
  temp: 25,              // erwartete Temperatur °C
  carbs_bike: 90, carbs_run: 60,   // g Kohlenhydrate pro Stunde
  sodium: 800,           // mg Natrium pro Liter
};
let saveTimer;

// Geschwindigkeit (m/s) auf flacher Strecke für eine Leistung – Luftwiderstand + Rollwiderstand, 97,6 % Antrieb
function bikeSpeed(watts, cda, crr, mass) {
  let lo = 1, hi = 25;
  for (let i = 0; i < 50; i++) {
    const v = (lo + hi) / 2;
    const need = (0.5 * 1.2 * cda * v ** 3 + crr * mass * 9.81 * v) / 0.976;
    if (need > watts) hi = v; else lo = v;
  }
  return lo;
}

function racePlan(p, st) {
  const weight = st.weight || 75;
  const fluid = p.temp >= 25 ? 900 : p.temp >= 20 ? 700 : 500;  // ml pro Stunde
  // Schwimmen: CSS + Zuschlag, Neopren schneller
  const swimPace = st.css + p.swim_offset - (p.wetsuit ? 3 : 0);
  const swimSec = (p.swim_km * 1000 / 100) * swimPace;
  // Rad: Ziel-NP = IF × FTP; Zeit aus Flachgeschwindigkeit + Kletterarbeit (30 % kommt bergab zurück)
  const watts = Math.round(p.bike_if * st.ftp);
  const mass = weight + Number(p.bike_kg);
  const v = bikeSpeed(watts, p.cda, p.crr, mass);
  const bikeSec = (p.bike_km * 1000) / v + (mass * 9.81 * p.bike_hm * 0.7) / watts;
  // Laufen: % der Schwellengeschwindigkeit
  const runPace = st.threshold_pace / (p.run_pct / 100);
  const runSec = p.run_km * runPace;
  const legs = [
    { name: "Schwimmen", target: `${secToPace(swimPace)} /100 m`, detail: `CSS ${secToPace(st.css)} + ${p.swim_offset} s${p.wetsuit ? " − 3 s Neo" : ""}`,
      sec: swimSec, carbs: 0, fluid: 0 },
    { name: "Wechsel 1", target: "", detail: "", sec: p.t1 * 60, carbs: 0, fluid: 0 },
    { name: "Rad", target: `${watts} W NP`, detail: `IF ${p.bike_if} · ${(v * 3.6).toFixed(1)} km/h flach · ${Math.round(watts / weight * 10) / 10} W/kg`,
      sec: bikeSec, carbs: p.carbs_bike, fluid },
    { name: "Wechsel 2", target: "", detail: "", sec: p.t2 * 60, carbs: 0, fluid: 0 },
    { name: "Laufen", target: `${secToPace(runPace)} /km`, detail: `${p.run_pct} % der Schwelle (${secToPace(st.threshold_pace)})`,
      sec: runSec, carbs: p.carbs_run, fluid: Math.round(fluid * 0.8) },
  ];
  for (const l of legs) {
    const h = l.sec / 3600;
    Object.assign(l, { carbsTotal: Math.round(l.carbs * h), fluidTotal: Math.round(l.fluid * h),
      sodiumTotal: Math.round((l.fluid * h / 1000) * p.sodium) });
  }
  return { legs, total: legs.reduce((a, l) => a + l.sec, 0), weight, fluid };
}

export function raceTab() {
  const st = state.settings;
  const p = { ...RACE_DEFAULTS, ...(st.race_plan || {}) };
  const field = (key, label, attrs = 'step="any"') =>
    `<label>${label} <input type="number" name="${key}" value="${p[key]}" ${attrs}></label>`;
  return `
    <p class="muted small">Planung für ${escapeHtml(st.goal_name || "den Wettkampf")}${st.goal_date ? ` am ${fmtDate(st.goal_date, { day: "2-digit", month: "2-digit", year: "numeric" })}` : ""}.
      Basis: deine Schwellen (FTP ${st.ftp} W, Schwelle ${secToPace(st.threshold_pace)}/km, CSS ${secToPace(st.css)}/100 m)${st.weight ? `, Gewicht ${st.weight} kg` : ""}.
      Alle Werte sind Schätzungen – im Training testen und anpassen.</p>
    <div id="race-form" class="grid race-grid">
      ${field("swim_km", "Schwimmen (km)")}${field("bike_km", "Rad (km)")}${field("run_km", "Laufen (km)")}
      ${field("bike_hm", "Höhenmeter Rad (laut Veranstalter)", 'step="10"')}${field("swim_offset", "Schwimmen: s/100 m über CSS")}
      <label class="inline"><input type="checkbox" name="wetsuit" ${p.wetsuit ? "checked" : ""}> Neoprenanzug</label>
      ${field("bike_if", "Rad-Intensität (IF)", 'step="0.01" min="0.5" max="0.85"')}${field("cda", "CdA (m²)", 'step="0.005"')}
      ${field("crr", "Rollwiderstand Crr", 'step="0.0005"')}${field("bike_kg", "Rad + Ausrüstung (kg)")}
      ${field("run_pct", "Laufen: % der Schwelle", 'step="1" min="70" max="95"')}
      ${field("t1", "Wechsel 1 (min)")}${field("t2", "Wechsel 2 (min)")}${field("temp", "Temperatur (°C)")}
      ${field("carbs_bike", "KH Rad (g/h)", 'step="5"')}${field("carbs_run", "KH Laufen (g/h)", 'step="5"')}
      ${field("sodium", "Natrium (mg/l)", 'step="50"')}
    </div>
    <div id="race-result"></div>`;
}

function renderRaceResult() {
  const p = { ...RACE_DEFAULTS };  // Eingaben liegen in einem div (Formulare dürfen nicht verschachtelt werden)
  for (const el of $("#race-form").querySelectorAll("input")) p[el.name] = el.type === "checkbox" ? el.checked : Number(el.value);
  const r = racePlan(p, state.settings);
  const sum = (k) => r.legs.reduce((a, l) => a + l[k], 0);
  $("#race-result").innerHTML = `
    <table class="race-table">
      <tr><th>Abschnitt</th><th>Ziel</th><th>Zeit</th><th>Kohlenhydrate</th><th>Flüssigkeit</th><th>Natrium</th></tr>
      ${r.legs.map((l) => `<tr><td><b>${l.name}</b><div class="muted small">${l.detail}</div></td><td>${l.target}</td>
        <td>${fmtTime(l.sec)}</td><td>${l.carbs ? `${l.carbs} g/h · ${l.carbsTotal} g` : ""}</td>
        <td>${l.fluid ? `${l.fluid} ml/h · ${(l.fluidTotal / 1000).toFixed(1)} l` : ""}</td>
        <td>${l.sodiumTotal ? `${l.sodiumTotal} mg` : ""}</td></tr>`).join("")}
      <tr class="total"><td>Gesamt</td><td></td><td>${fmtTime(r.total)}</td><td>${sum("carbsTotal")} g</td>
        <td>${(sum("fluidTotal") / 1000).toFixed(1)} l</td><td>${sum("sodiumTotal")} mg</td></tr>
    </table>
    <h3>Vorbereitung</h3>
    <ul class="notes">
      <li><b>Carbo-Loading</b> die 2 Tage vor dem Rennen: ${Math.round(r.weight * 8)}–${Math.round(r.weight * 10)} g Kohlenhydrate pro Tag (8–10 g/kg), ballaststoffarm.</li>
      <li><b>Frühstück</b> 3 h vor dem Start: ca. ${Math.round(r.weight * 1.5)} g Kohlenhydrate (1–2 g/kg), gewohnte Lebensmittel.</li>
      <li><b>Verpflegung testen</b>: ${p.carbs_bike} g/h auf dem Rad in den langen Einheiten üben – der Magen muss das lernen.</li>
      ${p.temp >= 25 ? `<li><b>Hitze</b>: ${r.fluid} ml/h eingeplant, Natrium eher an der oberen Grenze. Hitzeakklimatisierung läuft in den 6 Wochen vorher.</li>` : ""}
      <li>Die Radzeit ist eine Flachstrecken-Schätzung plus Kletterarbeit. Für deinen Wettkampf die Höhenmeter laut Veranstalter eintragen.</li>
    </ul>`;
  return p;
}

export function bindRaceTab() {
  renderRaceResult();
  $("#race-form").oninput = () => {
    const p = renderRaceResult();
    clearTimeout(saveTimer);  // Eingaben gesammelt speichern
    saveTimer = setTimeout(async () => {
      state.settings = await api("/api/settings", { method: "PUT", body: { race_plan: p } });
    }, 800);
  };
}
