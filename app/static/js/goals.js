// Eigene Ziele (Stunden oder Kilometer pro Woche/Monat/Jahr bzw. Zeitraum): Liste in der Seitenleiste und Dialog.
import { $, api, dataChanged, state, toast, withBusy } from "./core.js";
import { escapeHtml, fmtDate, todayIso } from "./format.js";
import { SPORT_LABEL } from "./labels.js";

const goalDialog = $("#goal-dialog");
const gform = $("#goal-form");
let editing = null;  // Ziel im Dialog

export function renderGoals(goals) {
  state.goals = goals;
  const periodLabel = { week: "diese Woche", month: "diesen Monat", year: "dieses Jahr" };
  $("#goals").innerHTML = goals.length ? goals.map((g, i) => {
    const unit = g.metric === "km" ? "km" : "h";
    const title = g.name || `${g.sport === "all" ? "Gesamt" : SPORT_LABEL[g.sport]} ${unit === "km" ? "Kilometer" : "Stunden"}`;
    const when = periodLabel[g.period] || `${fmtDate(g.start)} – ${fmtDate(g.end)}`;
    const planned = g.planned ? ` (+ ${g.planned} geplant)` : "";
    const behind = g.pct + 5 < g.expected;
    return `<li data-goal="${i}" title="Bearbeiten">
      <div class="row-between"><b>${escapeHtml(title)}</b><span class="muted small">${when}</span></div>
      <div class="bar"><span class="done" style="width:${Math.min(100, g.pct)}%"></span><i style="left:${g.expected}%"></i></div>
      <div class="small ${behind ? "behind" : "muted"}">${String(g.value).replace(".", ",")} / ${g.target} ${unit}${planned} · ${g.pct}%${behind ? " – hinter Plan" : ""}</div>
    </li>`;
  }).join("") : `<li class="muted small">Noch keine Ziele. Mit „+ Ziel“ z.B. 300 km Rad pro Monat anlegen.</li>`;
}

function openGoal(goal) {
  editing = goal;
  $("#goal-title").textContent = goal.id ? "Ziel bearbeiten" : "Neues Ziel";
  gform.name.value = goal.name || "";
  gform.sport.value = goal.sport || "all";
  gform.metric.value = goal.metric || "hours";
  gform.period.value = goal.period || "week";
  gform.target.value = goal.target ?? "";
  gform.start.value = goal.period === "custom" ? goal.start : todayIso();
  gform.end.value = goal.period === "custom" ? goal.end : state.settings.goal_date || "";
  $("#btn-delete-goal").hidden = !goal.id;
  toggleGoalRange();
  goalDialog.showModal();
}

function toggleGoalRange() {
  gform.querySelectorAll(".custom-range").forEach((el) => (el.hidden = gform.period.value !== "custom"));
}

async function saveGoal() {
  if (!gform.target.value) return toast("Bitte einen Zielwert eintragen");
  const custom = gform.period.value === "custom";
  await api("/api/goals", {
    method: "POST",
    body: {
      id: editing.id, name: gform.name.value.trim(), sport: gform.sport.value, metric: gform.metric.value,
      period: gform.period.value, target: Number(gform.target.value),
      start: custom ? gform.start.value : "", end: custom ? gform.end.value : "",
    },
  });
  goalDialog.close();
  toast("Ziel gespeichert");
  dataChanged();
}

export function bindGoals() {
  $("#btn-add-goal").onclick = () => openGoal({});
  $("#goals").onclick = (e) => {
    const li = e.target.closest("[data-goal]");
    if (li) openGoal(state.goals[li.dataset.goal]);
  };
  gform.period.onchange = toggleGoalRange;
  $("#btn-save-goal").onclick = withBusy($("#btn-save-goal"), saveGoal);
  $("#btn-delete-goal").onclick = withBusy($("#btn-delete-goal"), async () => {
    await api(`/api/goals/${editing.id}`, { method: "DELETE" });
    goalDialog.close();
    toast("Ziel gelöscht");
    dataChanged();
  });
}
