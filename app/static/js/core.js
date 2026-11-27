// Grundlagen für alle Module: DOM-Kurzform, API-Aufrufe, Meldungen, gemeinsamer Zustand.

export const $ = (sel, root = document) => root.querySelector(sel);

// Daten, die mehrere Teile der Oberfläche brauchen (beim Start bzw. von der Seitenleiste geladen)
export const state = {
  settings: null, templates: [], raceTypes: [], connected: null,
  suggestions: [], goals: [], conflicts: [], cycleStart: null,
};

// Konstanten vom Server (GET /api/meta), damit sie nicht doppelt gepflegt werden – beim Start gefüllt
export const meta = { flat_tss_per_hour: {}, circuit_limits: {}, exercise_limits: {}, race_types: {} };

export async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data.detail) || res.statusText);
  return data;
}

// FastAPI liefert Prüffehler (422) als Liste: [{loc: ["body", "ftp"], msg: "..."}]
function errorText(detail) {
  if (!Array.isArray(detail)) return detail;
  return detail.map((d) => `${d.loc?.slice(1).join(".") || ""}: ${d.msg}`).join(" · ");
}

export function toast(msg, ms = 3500) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), ms);
}

// Knopf während der Aktion sperren, Fehler als Meldung zeigen
export function withBusy(button, fn) {
  return async () => {
    button.disabled = true;
    try { await fn(); } catch (e) { toast(e.message, 8000); } finally { button.disabled = false; }
  };
}

// Nach jeder Änderung Seitenleiste und Kalender neu laden. main.js meldet dafür refreshSidebar an –
// so müssen Dialoge die Seitenleiste nicht kennen.
const changeListeners = [];
export const onDataChanged = (fn) => changeListeners.push(fn);
export const dataChanged = () => changeListeners.forEach((fn) => fn());

// Antwort von POST /api/workouts bzw. …/sync melden
export function reportSync(res) {
  const errors = Object.entries(res.errors || {});
  const synced = Object.keys(res.workout?.sync || {});
  if (errors.length) toast(errors.map(([k, v]) => `${k}: ${v}`).join(" | "), 8000);
  else toast(synced.length ? `Gespeichert und übertragen an ${synced.join(", ")}` : "Gespeichert");
  dataChanged();
}
