// Trainingsapp – Oberfläche. Kein Build-Schritt: Datei ändern, Browser neu laden.
//
// Ein Modul je Bereich; jedes bindet seine Knöpfe selbst (bind…). Gemeinsames steht in core.js (API, Zustand,
// Meldungen), format.js (Datum, Dauer, Tempo), labels.js (Bezeichnungen) und workout.js (TSS, Profil, Zielwerte).
import { $, api, dataChanged, meta, onDataChanged, state, toast, withBusy } from "./core.js";
import { bindAnalysis } from "./analysis.js";
import { initCalendar } from "./calendar.js";
import { bindEditor } from "./editor.js";
import { bindFeedback } from "./feedback.js";
import { bindGoals } from "./goals.js";
import { bindPlanImport } from "./plan-import.js";
import { bindSettings, refreshFromGarmin, refreshStatus } from "./settings.js";
import { bindSetup, openSetup } from "./setup.js";
import { bindSidebar, initSidebarToggle, refreshSidebar } from "./sidebar.js";
import { bindTimer } from "./timer.js";
import { initUpdates } from "./update.js";

// Aktivitäten von allen verbundenen Quellen holen → Anzahl
async function importActivities(days) {
  const st = await api("/api/status");
  const sources = ["garmin", "intervals"].filter((s) => st[s]);
  let total = 0;
  for (const s of sources) total += (await api(`/api/import/${s}?days=${days}`, { method: "POST" })).imported;
  return { sources, total };
}

async function main() {
  let serverMeta;
  [state.settings, state.templates, state.raceTypes, serverMeta] = await Promise.all([
    api("/api/settings"), api("/api/templates"), api("/api/race-types"), api("/api/meta"),
  ]);
  Object.assign(meta, serverMeta);
  onDataChanged(() => refreshSidebar().catch((e) => toast(e.message)));

  initCalendar();
  initSidebarToggle();
  await refreshStatus().catch(() => {});
  if (!state.settings.setup_done) openSetup();
  dataChanged();
  refreshFromGarmin().catch((e) => toast(e.message, 6000));
  // Beim Öffnen die letzten 14 Tage nachladen, damit Wochenstunden und Ziele aktuell sind
  importActivities(14).then(({ sources }) => sources.length && dataChanged()).catch((e) => toast(`Import: ${e.message}`, 6000));
  initUpdates();

  bindSidebar();
  bindEditor();
  bindTimer();
  bindFeedback();
  bindGoals();
  bindSettings();
  bindSetup();
  bindAnalysis();
  bindPlanImport();
  $("#btn-import").onclick = withBusy($("#btn-import"), async () => {
    const { sources, total } = await importActivities(365);
    if (!sources.length) return toast("Weder Garmin noch intervals.icu verbunden – siehe README.", 6000);
    toast(`${total} Aktivitäten (365 Tage) importiert`);
    dataChanged();
  });
}

main();
