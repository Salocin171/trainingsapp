// Feedback zu importierten Aktivitäten: Kennzahlen, Pulszonen, RPE, Befinden, Zuordnung zum Plan.
import { $, api, dataChanged, toast, withBusy } from "./core.js";
import { showActivityLaps } from "./activity-laps.js";
import { openDetail } from "./detail.js";
import { escapeHtml, fmtMin } from "./format.js";
import { FEEL_LABEL, RPE_LABEL, SPORT_LABEL } from "./labels.js";
import { efficiency, zoneBar } from "./workout.js";

const feedbackDialog = $("#feedback-dialog");
const fform = $("#feedback-form");
let activity = null;  // Aktivität im Dialog

// RPE- und Befinden-Auswahl in allen Formularen (Feedback und Workout-Editor)
function fillFeedbackOptions(root) {
  root.querySelectorAll('select[name="rpe"]').forEach((el) => (el.innerHTML = `<option value="">–</option>` +
    RPE_LABEL.map((l, i) => `<option value="${i}">${i} – ${l}</option>`).join("")));
  root.querySelectorAll('select[name="feel"]').forEach((el) => (el.innerHTML = `<option value="">–</option>` +
    Object.entries(FEEL_LABEL).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")));
}

export function openFeedback(a, plan, dayWorkouts = []) {
  activity = a;
  const link = a.feedback?.plan_link;
  $("#feedback-plan-select").innerHTML = [
    `<option value="">Automatisch${link === undefined ? ` (${plan ? escapeHtml(plan.name) : "keins erkannt"})` : ""}</option>`,
    ...dayWorkouts.map((w) => `<option value="${w.id}">${escapeHtml(w.name)} (${fmtMin(w.duration)})</option>`),
    `<option value="0">Gehört zu keinem Plan</option>`,
  ].join("");
  $("#feedback-plan-select").value = link ?? "";
  $("#btn-open-plan").hidden = !plan;
  $("#btn-open-plan").onclick = () => { feedbackDialog.close(); openDetail(plan); };
  const m = a.metrics || {};
  const ef = efficiency(a);
  const facts = [
    [SPORT_LABEL[a.sport] || a.sport, a.date.split("-").reverse().join(".")],
    ["Dauer", fmtMin(a.duration)],
    a.distance ? ["Distanz", `${(a.distance / 1000).toFixed(a.sport === "swim" ? 2 : 1)} km`] : null,
    ["TSS", Math.round(a.tss)],
    m.avg_hr ? ["Ø Puls", `${Math.round(m.avg_hr)} bpm`] : null,
    m.np ? ["NP", `${Math.round(m.np)} W`] : null,
    ef ? ["EF", ef.toFixed(2)] : null,
  ].filter(Boolean);
  $("#feedback-title").textContent = a.name;
  $("#feedback-facts").innerHTML = facts.map(([k, v]) => `<div><span class="label">${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`).join("");
  $("#feedback-zones").innerHTML = m.hr_zones ? zoneBar(m.hr_zones) : "";
  const fb = a.feedback || {};
  fform.rpe.value = fb.rpe ?? "";
  fform.feel.value = fb.feel ?? "";
  fform.note.value = fb.note || "";
  feedbackDialog.showModal();
  if (["swim", "ride", "run"].includes(a.sport)) showActivityLaps($("#feedback-laps"), a.id);
  else $("#feedback-laps").innerHTML = "";
}

async function saveFeedback() {
  const id = encodeURIComponent(activity.id);
  const body = {
    rpe: fform.rpe.value === "" ? null : Number(fform.rpe.value),
    feel: fform.feel.value === "" ? null : Number(fform.feel.value),
    note: fform.note.value.trim(),
  };
  await api(`/api/activities/${id}/feedback`, { method: "PUT", body });
  const link = $("#feedback-plan-select").value;
  await api(`/api/activities/${id}/plan`, { method: "PUT", body: { workout_id: link === "" ? null : Number(link) } });
  feedbackDialog.close();
  toast("Feedback gespeichert");
  dataChanged();
}

async function deleteActivity() {
  if (!confirm(`„${activity.name}" aus der App löschen?\n\nGedacht für doppelt hochgeladene Einheiten. `
    + "Bei Garmin bleibt sie bestehen, wird aber nicht erneut importiert.")) return;
  await api(`/api/activities/${encodeURIComponent(activity.id)}`, { method: "DELETE" });
  feedbackDialog.close();
  toast("Aktivität gelöscht");
  dataChanged();
}

export function bindFeedback() {
  fillFeedbackOptions(document);
  $("#btn-save-feedback").onclick = withBusy($("#btn-save-feedback"), saveFeedback);
  $("#btn-delete-activity").onclick = withBusy($("#btn-delete-activity"), deleteActivity);
}
