// Workout-Editor: Vorlage, Schritte, Vorschau, Speichern und an Geräte senden.
import { $, api, dataChanged, reportSync, state, toast, withBusy } from "./core.js";
import { escapeHtml, fmtMin, todayIso } from "./format.js";
import { DEFAULT_TARGET, KIND_LABEL, TARGET_SHORT, TARGETS_FOR, TIMER_SPORTS } from "./labels.js";
import { absoluteRange, drawProfile, stepTarget, workoutStats } from "./workout.js";

const editor = $("#editor");
const form = $("#editor-form");
let current = null;  // das Workout im Editor (Schritte werden direkt darin geändert)

export function openEditor(workout) {
  current = {
    sport: "ride", target: "power", name: "Neues Workout", description: "", steps: [], status: "planned",
    ...structuredClone(workout),
  };
  const w = current;
  $("#editor-title").textContent = w.id ? "Workout bearbeiten" : "Neues Workout";
  form.date.value = w.date;
  form.sport.value = w.sport;
  form.target.value = w.target;
  form.name.value = w.name;
  form.description.value = w.description || "";
  form.done.checked = w.status === "done";
  form.actual_tss.value = w.actual_tss ?? "";
  form.rpe.value = w.rpe ?? "";
  form.feel.value = w.feel ?? "";
  form.note.value = w.note || "";
  for (const cb of $("#sync-box").querySelectorAll("input")) {
    cb.checked = Boolean(w.sync?.[cb.value])
      || (!w.id && state.settings.auto_sync.includes(cb.value) && state.connected?.[cb.value] !== false);
  }
  const synced = Object.keys(w.sync || {});
  $("#sync-state").textContent = synced.length ? `Übertragen: ${synced.join(", ")}` : "";
  $("#btn-delete").hidden = !w.id;
  $("#btn-circuit").hidden = !TIMER_SPORTS.includes(w.sport);
  renderTemplateOptions(w.sport);
  if (w.template) $("#tpl-kind").value = w.template;
  renderSteps();
  if (!editor.open) editor.showModal();
}

function renderTemplateOptions(sport) {
  const fitting = state.templates.filter((t) => t.sports.includes(sport));
  $("#tpl-kind").innerHTML = (fitting.length ? fitting : state.templates)
    .map((t) => `<option value="${t.key}">${escapeHtml(t.name)}</option>`).join("");
}

// Formular → Workout (für Speichern und den Zirkel-Timer)
export function readForm() {
  Object.assign(current, {
    date: form.date.value, sport: form.sport.value, target: form.target.value,
    name: form.name.value, description: form.description.value,
    status: form.done.checked ? "done" : "planned",
    actual_tss: form.actual_tss.value === "" ? null : Number(form.actual_tss.value),
    rpe: form.rpe.value === "" ? null : Number(form.rpe.value),
    feel: form.feel.value === "" ? null : Number(form.feel.value),
    note: form.note.value.trim(),
  });
  return current;
}

function stepRow(s, list, index) {
  const row = document.createElement("div");
  row.className = "step";
  row.innerHTML = `
    <select>${Object.entries(KIND_LABEL).map(([k, l]) => `<option value="${k}" ${k === s.kind ? "selected" : ""}>${l}</option>`).join("")}</select>
    <label class="inline"><input type="number" min="0.25" step="0.25" value="${s.duration / 60}"><span class="unit">min</span></label>
    <label class="inline"><input type="number" min="0" max="200" value="${s.low}"><span class="unit">%</span></label>
    <label class="inline"><input type="number" min="0" max="200" value="${s.high}"><span class="unit">%</span></label>
    <select class="step-target" title="Woran sich dieser Schritt orientiert – unabhängig von den anderen Schritten"></select>
    <span class="abs" title="Zielbereich aus deinen Schwellenwerten"></span>
    <button type="button" class="ghost" title="Entfernen">✕</button>`;
  const [kind, dur, low, high, target] = row.querySelectorAll("select, input");
  const abs = row.querySelector(".abs");
  const showAbs = () => (abs.textContent = absoluteRange(s, form.sport.value, form.target.value));
  // Ziel je Schritt: z. B. Einlaufen nach Puls, Intervalle nach Pace – leer heißt „wie das Workout“
  const sportChoices = TARGETS_FOR[form.sport.value] || [];
  const choices = sportChoices.length ? [...new Set([form.target.value, ...sportChoices])] : [];
  if (s.target && !choices.includes(s.target)) delete s.target;  // z. B. nach Wechsel Laufen → Rad
  target.style.visibility = choices.length ? "" : "hidden";  // Platz in der Zeile behalten
  target.innerHTML = choices.map((k) => `<option value="${k}">${TARGET_SHORT[k]}</option>`).join("");
  target.value = stepTarget(s, form.target.value);
  const update = () => {
    Object.assign(s, { kind: kind.value, duration: Math.round(Number(dur.value) * 60), low: Number(low.value), high: Number(high.value) });
    if (choices.length && target.value !== form.target.value) s.target = target.value;
    else delete s.target;
    showAbs();
    updatePreview();
  };
  showAbs();
  [kind, dur, low, high, target].forEach((el) => el.addEventListener("input", update));
  row.querySelector("button").onclick = () => { list.splice(index, 1); renderSteps(); };
  return row;
}

function renderSteps() {
  const box = $("#steps");
  box.innerHTML = "";
  const steps = current.steps;
  steps.forEach((s, i) => {
    if (s.kind !== "repeat") return box.append(stepRow(s, steps, i));
    const block = document.createElement("div");
    block.className = "repeat";
    block.innerHTML = `<div class="head">Wiederholung <input type="number" min="1" value="${s.count}"> ×
      <button type="button" class="small">+ Schritt</button><button type="button" class="ghost" title="Entfernen">✕</button></div>`;
    const [count] = block.querySelectorAll("input");
    count.oninput = () => { s.count = Number(count.value) || 1; updatePreview(); };
    const [add, remove] = block.querySelectorAll("button");
    add.onclick = () => { s.steps.push({ kind: "interval", duration: 300, low: 95, high: 100 }); renderSteps(); };
    remove.onclick = () => { steps.splice(i, 1); renderSteps(); };
    s.steps.forEach((c, j) => block.append(stepRow(c, s.steps, j)));
    box.append(block);
  });
  updatePreview();
}

function updatePreview() {
  drawProfile($("#profile"), current.steps);
  const st = workoutStats(current);
  $("#stats").textContent = `Dauer ${fmtMin(st.duration)} · geschätzter TSS ${st.tss} · IF ${st.IF}`;
}

async function saveCurrent(syncTargets = null) {
  let res = await api("/api/workouts", { method: "POST", body: readForm() });
  // Beim Speichern wurden bereits übertragene Ziele aktualisiert – nur neue noch senden.
  const missing = (syncTargets || []).filter((t) => !res.workout.sync?.[t]);
  if (missing.length) {
    const sent = await api(`/api/workouts/${res.workout.id}/sync`, { method: "POST", body: { targets: missing } });
    res = { workout: sent.workout, errors: { ...res.errors, ...sent.errors } };
  }
  editor.close();
  reportSync(res);
}

export function bindEditor() {
  $("#btn-new").onclick = () => openEditor({ date: todayIso() });
  $("#btn-template").onclick = async () => {
    const t = await api(`/api/templates/${$("#tpl-kind").value}?sport=${form.sport.value}&minutes=${$("#tpl-min").value}`);
    Object.assign(current, { steps: t.steps, template: t.template, target: t.target, circuit: t.circuit });
    if (!form.name.value || form.name.value === "Neues Workout") form.name.value = t.name;
    if (!form.description.value) form.description.value = t.description;
    form.target.value = t.target;
    renderSteps();
  };
  $("#btn-add-step").onclick = () => { current.steps.push({ kind: "steady", duration: 600, low: 65, high: 75 }); renderSteps(); };
  $("#btn-add-repeat").onclick = () => {
    current.steps.push({ kind: "repeat", count: 4, steps: [
      { kind: "interval", duration: 240, low: 105, high: 110 }, { kind: "recovery", duration: 240, low: 50, high: 55 },
    ] });
    renderSteps();
  };
  form.sport.onchange = () => {
    form.target.value = DEFAULT_TARGET[form.sport.value] || "hr";
    $("#btn-circuit").hidden = !TIMER_SPORTS.includes(form.sport.value);
    renderTemplateOptions(form.sport.value);
    renderSteps();
  };
  form.target.onchange = renderSteps;  // Absolutwerte (W / Pace / bpm) neu berechnen
  $("#btn-save").onclick = withBusy($("#btn-save"), () => saveCurrent());
  $("#btn-send").onclick = withBusy($("#btn-send"), () =>
    saveCurrent([...$("#sync-box").querySelectorAll("input:checked")].map((cb) => cb.value)));
  $("#btn-delete").onclick = withBusy($("#btn-delete"), async () => {
    if (!confirm("Workout löschen? Es wird auch auf den Geräten entfernt.")) return;
    await api(`/api/workouts/${current.id}`, { method: "DELETE" });
    editor.close();
    toast("Gelöscht");
    dataChanged();
  });
}
