// Plan-Import: JSON prüfen und importieren, KI-Auftrag für einen Block kopieren.
import { $, api, dataChanged, state, toast, withBusy } from "./core.js";
import { gotoDate } from "./calendar.js";
import { escapeHtml, fmtDate, fmtHours, fmtMin, isoWeek, sportColor } from "./format.js";

const planDialog = $("#plan-dialog");
const pform = $("#plan-form");

// Nächster Montag (heute, falls heute Montag ist) – wie plan_import.default_start
function nextMonday() {
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7));
  return d.toLocaleDateString("sv-SE");
}

async function copyPlanPrompt() {
  const weeks = Number($("#plan-ai-weeks").value) || 4;
  const notes = $("#plan-ai-notes").value;
  const res = await api("/api/plan/prompt", { method: "POST", body: { weeks, start: pform.start.value || "", notes } });
  state.settings.availability = notes.trim();
  const box = $("#plan-ai-text");
  box.value = res.text;
  box.hidden = false;
  const calendars = (state.settings.calendar_ics || []).length;
  const info = [calendars ? `${res.busy_days} Tage mit Terminen aus ${calendars} Kalender${calendars > 1 ? "n" : ""}` : "",
    ...res.errors].filter(Boolean).join(" · ");
  try {
    await navigator.clipboard.writeText(res.text);
    $("#plan-ai-state").textContent = `✓ Kopiert (ca. ${Math.round(res.text.length / 3.5)} Tokens)${info ? ` · ${info}` : ""} – in die KI einfügen`;
  } catch {
    box.select();
    $("#plan-ai-state").textContent = `Text markiert – mit ⌘C kopieren${info ? ` · ${info}` : ""}`;
  }
}

function openPlanImport() {
  $("#plan-ai-notes").value = state.settings.availability || "";
  $("#plan-ai-text").hidden = true;
  $("#plan-ai-state").textContent = "";
  pform.start.value = nextMonday();
  delete pform.start.dataset.touched;
  $("#plan-preview").innerHTML = "";
  $("#btn-plan-import").disabled = true;
  planDialog.showModal();
}

// KI-Antworten enthalten oft ```json …``` oder Text drumherum: nur das äußerste { … } verwenden
function extractJson(text) {
  const start = text.indexOf("{"), end = text.lastIndexOf("}");
  return start >= 0 && end > start ? text.slice(start, end + 1) : text;
}

function planBody() {
  let plan;
  try {
    plan = JSON.parse(extractJson($("#plan-json").value));
  } catch (e) {
    throw new Error(`Kein gültiges JSON: ${e.message}`);
  }
  return { plan, start: pform.start.value || null, replace: pform.replace.checked };
}

function planChanged() {
  $("#btn-plan-import").disabled = true;
  $("#plan-preview").innerHTML = "";
}

async function checkPlan() {
  try {
    const body = planBody();
    // Startdatum aus dem Plan übernehmen, solange keins von Hand gewählt wurde
    if (body.plan.start && !pform.start.dataset.touched) body.start = pform.start.value = body.plan.start;
    const res = await api("/api/plan/preview", { method: "POST", body });
    renderPlanPreview(res);
    $("#btn-plan-import").disabled = false;
    $("#btn-plan-import").textContent = `${res.workouts.length} Workouts importieren`;
  } catch (e) {
    $("#plan-preview").innerHTML = `<p class="warn">⚠︎ ${escapeHtml(e.message)}</p>`;
    $("#btn-plan-import").disabled = true;
  }
}

function renderPlanPreview(res) {
  const hours = res.workouts.reduce((sum, w) => sum + w.duration, 0) / 3600;
  const byWeek = {};
  for (const w of res.workouts) (byWeek[`KW ${isoWeek(w.date)}`] ||= []).push(w);
  const weekday = (iso) => new Date(iso).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  const warnings = res.warnings?.length
    ? `<ul class="warn">${res.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>` : "";
  $("#plan-preview").innerHTML = `
    <p><b>${res.workouts.length} Workouts</b> · ${fmtDate(res.start)} – ${fmtDate(res.end)} · ${fmtHours(hours)} gesamt</p>
    ${warnings}
    ${res.existing ? `<p class="warn small">Im Zeitraum sind schon ${res.existing} geplante Workouts.
      ${pform.replace.checked ? "Sie werden ersetzt (auch auf den Geräten)." : "Sie bleiben zusätzlich bestehen."}</p>` : ""}
    <div class="plan-weeks">${Object.entries(byWeek).map(([week, list]) => `
      <div class="plan-week">
        <div class="row-between"><b>${week}</b><span class="muted small">${fmtHours(list.reduce((s, w) => s + w.duration, 0) / 3600)}</span></div>
        ${list.map((w) => `<div class="plan-item"><span class="muted">${weekday(w.date)}</span>
          <span><span class="dot" style="background:${sportColor(w.sport)}"></span>${escapeHtml(w.name)}</span>
          <span class="muted">${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS</span></div>`).join("")}
      </div>`).join("")}</div>`;
}

async function importPlan() {
  const res = await api("/api/plan/import", { method: "POST", body: planBody() });
  planDialog.close();
  toast(`${res.created} Workouts importiert${res.removed ? `, ${res.removed} ersetzt` : ""}` +
    (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""), res.errors.length ? 10000 : 4000);
  gotoDate(res.start);
  dataChanged();
}

export function bindPlanImport() {
  $("#btn-plan").onclick = openPlanImport;
  $("#plan-json").oninput = planChanged;
  pform.start.onchange = () => { pform.start.dataset.touched = "1"; planChanged(); };
  pform.replace.onchange = () => $("#plan-preview").innerHTML && checkPlan();
  $("#plan-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    $("#plan-json").value = await file.text();
    e.target.value = "";
    checkPlan();
  };
  $("#btn-plan-example").onclick = async () => {
    $("#plan-json").value = await (await fetch("/static/plan-example.json")).text();
    checkPlan();
  };
  $("#btn-plan-check").onclick = withBusy($("#btn-plan-check"), checkPlan);
  $("#btn-plan-ai").onclick = withBusy($("#btn-plan-ai"), copyPlanPrompt);
  $("#btn-plan-import").onclick = withBusy($("#btn-plan-import"), importPlan);
}
