// Workout-Details mit Ablauf und Ernährung vor · während · nach der Einheit.
import { $, api, reportSync, withBusy } from "./core.js";
import { openEditor } from "./editor.js";
import { escapeHtml, fmtDate, fmtMin, fmtNum, sportColor } from "./format.js";
import { KIND_LABEL, SPORT_LABEL, TIMER_SPORTS } from "./labels.js";
import { acceptSuggestion } from "./sidebar.js";
import { openCircuit } from "./timer.js";
import { absoluteRange, drawProfile, isFlat, workoutStats } from "./workout.js";

const detailDialog = $("#detail-dialog");
const FUEL_PHASES = { before: "Vor dem Training", during: "Während des Trainings", after: "Nach dem Training" };
const FUEL_SHORT = { before: "Vorher", during: "Während", after: "Danach" };
const fmtQty = (q) => q && `${q.low === q.high ? q.low : `${q.low}–${q.high}`} ${q.unit}`;
const fmtPerKg = (q) => q?.per_kg && `${q.per_kg.map(fmtNum).join("–")} ${q.unit === "ml" ? "ml" : "g"}/kg${q.unit.endsWith("/h") ? "/h" : ""}`;
let openToken = 0;  // nur die Antwort zum zuletzt geöffneten Workout anzeigen

// Der KH-Block der Beschreibung steht schon im Ernährungsteil – oben nur den Rest zeigen
function withoutFuelBlock(text) {
  return (text || "").split("\n")
    .filter((line) => !/^\s*KH\s*\(.*kg\)\s*:?\s*$/i.test(line) && !/^\s*[-•·*]?\s*(Vorher|Während|Danach)\s*:/i.test(line))
    .join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function stepDuration(sec) {
  return sec % 60 ? `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")} min` : fmtMin(sec);
}

function stepLine(s, w) {
  const pct = Number(s.low) === Number(s.high) ? `${s.low} %` : `${s.low}–${s.high} %`;
  const abs = absoluteRange(s, w.sport, w.target);
  const zone = Number(s.low) || Number(s.high) ? ` · ${pct}` : "";
  return `${KIND_LABEL[s.kind] || escapeHtml(s.kind)} ${stepDuration(s.duration)}${zone}${abs ? ` · <span class="abs">${abs}</span>` : ""}`;
}

function renderDetailSteps(w) {
  const items = (w.steps || []).map((s) => s.kind === "repeat"
    ? `<li>${s.count} × ( ${s.steps.map((c) => stepLine(c, w)).join(" / ")} )</li>`
    : `<li>${stepLine(s, w)}</li>`);
  $("#d-steps").innerHTML = items.join("");
  $("#d-steps-box").hidden = !items.length || isFlat(w.sport);
}

function fuelCell(label, q, sub = "", src = "") {
  return `<div class="fuel-cell"><span class="label">${label}</span>
    <b class="${q ? "" : "none"}">${q ? fmtQty(q) : "–"}</b>
    ${sub ? `<span class="sub">${escapeHtml(sub)}</span>` : ""}${src ? `<span class="src">${src}</span>` : ""}</div>`;
}

function renderNutrition(n) {
  $("#d-fuel-kind").textContent = n.kind_label;
  // Nur Zeilen zeigen, die in mindestens einer Phase einen Wert haben (Kraft: nur Eiweiß, Yoga: keine)
  const show = (field) => Object.values(n.phases).some((p) => p[field]);
  $("#d-fuel").innerHTML = Object.entries(FUEL_PHASES).map(([key, title]) => {
    const p = n.phases[key];
    const carbSub = [fmtPerKg(p.carbs), p.total ? `≈ ${fmtQty(p.total)} gesamt` : ""].filter(Boolean).join(" · ");
    const when = p.timing || p.hint;
    return `<div class="fuel-col ${key}"><h4>${title}</h4>
      ${show("carbs") ? fuelCell("Kohlenhydrate", p.carbs, carbSub, p.source === "plan" ? "aus deinem Plan" : "") : ""}
      ${show("fluid") ? fuelCell("Flüssigkeit", p.fluid, p.fluid_hint || fmtPerKg(p.fluid) || "") : ""}
      ${show("protein") ? fuelCell("Eiweiß", p.protein, fmtPerKg(p.protein) || "") : ""}
      ${when ? `<div class="fuel-when">${escapeHtml(when)}</div>` : ""}</div>`;
  }).join("");
  $("#d-fuel-plan").innerHTML = Object.keys(FUEL_PHASES).filter((k) => n.phases[k].plan_text)
    .map((k) => `<div class="${k}"><b>${FUEL_SHORT[k]}:</b> ${escapeHtml(n.phases[k].plan_text)}</div>`).join("");
  const d = n.day;
  $("#d-fuel-day").innerHTML = `Kohlenhydrate heute gesamt: <b>${fmtQty(d)}</b> <span class="muted">(${fmtPerKg(d)} · ${escapeHtml(d.label)})</span>`;
  $("#d-fuel-notes").innerHTML = n.notes.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const sweat = n.sweat_rate ? `, Schweißrate ${fmtNum(n.sweat_rate)} l/h` : "";
  $("#d-fuel-basis").textContent = `Richtwerte für ${fmtNum(n.weight)} kg${sweat}${n.weeks_to_race != null
    ? `, ${Math.floor(n.weeks_to_race)} Wochen bis zum Wettkampf` : ""}. Ersetzt keine medizinische Beratung.`;
}

// workout: gespeichertes Workout oder Vorschlag (dann suggestion gesetzt)
export async function openDetail(workout, suggestion = null) {
  const token = ++openToken;
  let w = { steps: [], ...workout };
  const stats = workoutStats(w);
  const fill = () => {
    $("#d-title").textContent = w.name;
    $("#d-sport").style.setProperty("--sport", sportColor(w.sport));
    $("#d-sport").title = SPORT_LABEL[w.sport] || "";
    const desc = $("#d-desc");
    desc.textContent = withoutFuelBlock(w.description);
    desc.classList.remove("open");
    const n = w.nutrition;
    const facts = [
      [SPORT_LABEL[w.sport] || w.sport, fmtDate(w.date, { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })],
      n?.start ? ["Uhrzeit", n.end ? `${n.start}–${n.end}` : n.start] : null,
      ["Dauer", fmtMin(w.duration ?? stats.duration)],
      ["TSS", Math.round(w.tss ?? stats.tss)],
      isFlat(w.sport) ? null : ["IF", Number(w.if ?? stats.IF).toFixed(2).replace(".", ",")],
      suggestion ? ["Status", "Vorschlag"] : ["Status", w.status === "done" ? "✓ erledigt" : "geplant"],
    ].filter(Boolean);
    $("#d-facts").innerHTML = facts.map(([k, v]) => `<div><span class="label">${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`).join("");
    const profile = $("#d-profile");
    const showProfile = w.steps.length && !isFlat(w.sport);
    profile.style.display = showProfile ? "" : "none";  // SVG kennt kein .hidden
    if (showProfile) drawProfile(profile, w.steps);
    renderDetailSteps(w);
    $("#d-done").hidden = Boolean(suggestion) || !w.id;
    $("#d-done").textContent = w.status === "done" ? "Wieder als offen markieren" : "Als erledigt markieren";
    $("#d-accept").hidden = !suggestion;
    $("#d-start").hidden = Boolean(suggestion) || !TIMER_SPORTS.includes(w.sport);
    $("#d-edit").textContent = suggestion ? "Anpassen" : "Bearbeiten";
  };
  fill();
  $("#d-fuel").innerHTML = `<p class="muted">Ernährung wird berechnet …</p>`;
  ["#d-fuel-plan", "#d-fuel-day", "#d-fuel-notes", "#d-fuel-basis"].forEach((sel) => ($(sel).innerHTML = ""));
  $("#d-fuel-kind").textContent = "";
  if (!detailDialog.open) detailDialog.showModal();
  requestAnimationFrame(() => {
    const desc = $("#d-desc");
    $("#d-more").hidden = desc.scrollHeight <= desc.clientHeight + 2;
  });

  $("#d-more").onclick = () => { $("#d-desc").classList.add("open"); $("#d-more").hidden = true; };
  $("#d-edit").onclick = () => { detailDialog.close(); openEditor(w); };
  $("#d-start").onclick = () => { detailDialog.close(); openCircuit(w); };
  $("#d-accept").onclick = withBusy($("#d-accept"), async () => { await acceptSuggestion(suggestion); detailDialog.close(); });
  $("#d-done").onclick = withBusy($("#d-done"), async () => {
    const res = await api("/api/workouts", { method: "POST", body: { ...w, status: w.status === "done" ? "planned" : "done" } });
    reportSync(res);
    openDetail(res.workout);
  });

  try {
    if (w.id && !suggestion) w = await api(`/api/workouts/${w.id}`);
    else w.nutrition = await api("/api/nutrition", { method: "POST", body: w });
    if (token !== openToken) return;
    fill();
    renderNutrition(w.nutrition);
  } catch (e) {
    if (token === openToken) $("#d-fuel").innerHTML = `<p class="muted">Ernährung nicht verfügbar: ${escapeHtml(e.message)}</p>`;
  }
}
