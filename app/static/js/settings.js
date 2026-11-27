// Einstellungen: Schwellen, Wettkämpfe (A/B/C), Wochenmuster, Geräte; Verbindungsstatus und Garmin-Werte.
import { $, api, dataChanged, meta, state, toast, withBusy } from "./core.js";
import { escapeHtml, fmtDate, paceToSec, secToPace, sportColor } from "./format.js";
import { SLOT_TYPES, SPORT_LABEL, WEEKDAYS } from "./labels.js";
import { openSetup } from "./setup.js";

const settingsDialog = $("#settings");
const sform = $("#settings-form");
let pattern = {};  // Wochenmuster in Bearbeitung (erst beim Speichern übernommen)

// iCal-Links aus einem Textfeld (einer pro Zeile); webcal:// wird serverseitig zu https://
export const icsLinks = (text) => text.split(/\s+/).map((l) => l.trim()).filter((l) => /^(https?|webcal):\/\//i.test(l));

export const raceTypeOptions = () =>
  Object.entries(meta.race_types).map(([k, l]) => `<option value="${k}">${escapeHtml(l)}</option>`).join("");

// Kalender der Kalender-App zur Auswahl; beim ersten Mal fragt macOS nach der Berechtigung
export async function fillCalendarSelect(select, current) {
  select.innerHTML = `<option value="${escapeHtml(current || "")}">${escapeHtml((current || "– keiner –").trim())}</option>`;
  try {
    const list = await api("/api/calendars");
    select.innerHTML = `<option value="">– keiner –</option>` + list.filter((c) => c.writable)
      .map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name.trim())}</option>`).join("");
    select.value = current || "";
  } catch (e) {
    toast(e.message, 10000);
  }
}

function openSettings() {
  const s = state.settings;
  fillCalendarSelect(sform.mac_calendar, s.mac_calendar);
  sform.race_type.innerHTML = raceTypeOptions();
  $("#race-type").innerHTML = state.raceTypes.map((t) => `<option value="${t.key}">${escapeHtml(t.label)}</option>`).join("");
  $("#race-type").value = "run_half";
  renderRaceTypeHint();
  renderRaces();
  for (const key of ["ftp", "lthr_run", "lthr_ride", "max_hr", "weight", "sweat_rate", "goal_name", "goal_date", "race_type", "week_hours",
    "recovery_every", "cycle_start", "taper_weeks", "target_ctl", "zwift_dir"]) {
    sform[key].value = s[key] ?? "";
  }
  sform.threshold_pace.value = secToPace(s.threshold_pace);
  sform.css.value = secToPace(s.css);
  sform.garmin_profile.checked = s.garmin_profile;
  sform.plant_based.checked = s.plant_based;
  sform.availability.value = s.availability || "";
  sform.calendar_ics.value = (s.calendar_ics || []).join("\n");
  $("#garmin-profile-at").textContent = s.garmin_profile_at
    ? `zuletzt übernommen: ${new Date(s.garmin_profile_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}`
    : "";
  sform.querySelectorAll('[name="auto_sync"]').forEach((cb) => (cb.checked = s.auto_sync.includes(cb.value)));
  pattern = structuredClone(s.week_pattern);
  renderPattern();
  settingsDialog.showModal();
}

// --- Weitere Wettkämpfe (B/C) – werden sofort gespeichert

// Kurzbeschreibung von Taper/Erholung, z. B. "7 Tage Mini-Taper · 14 Tage Erholung (3 nur locker) · 5 Tage Laufpause"
function recoveryText(key, priority) {
  const t = state.raceTypes.find((x) => x.key === key);
  if (!t) return "";
  const p = t[priority];
  return [`${p.taper} Tag${p.taper === 1 ? "" : "e"} ${priority === "B" ? "Mini-Taper" : "locker davor"}`,
    `${p.recovery} Tage Erholung${p.rest ? ` (${p.rest} nur Regeneration)` : ""}`,
    p.no_run ? `${p.no_run} Tage Laufpause` : ""].filter(Boolean).join(" · ");
}

function renderRaceTypeHint() {
  $("#race-type-hint").textContent = `${$("#race-priority").value}-Wettkampf: ${recoveryText($("#race-type").value, $("#race-priority").value)}`;
}

async function renderRaces() {
  const races = await api("/api/races");
  const label = (key) => state.raceTypes.find((t) => t.key === key)?.label || key;
  $("#races").innerHTML = races.length ? races.map((r) => `<div class="race-row">
      <b>${r.priority}</b><span>${fmtDate(r.date, { day: "2-digit", month: "2-digit", year: "numeric" })}</span>
      <span>${escapeHtml(r.name)}</span><span class="muted small" title="${recoveryText(r.race_type, r.priority)}">${escapeHtml(label(r.race_type))}</span>
      <button type="button" class="ghost" data-race="${r.id}" title="Entfernen">✕</button></div>`).join("")
    : `<p class="muted small">Keine. Das A-Rennen ist der Wettkampf oben.</p>`;
}

async function addRace() {
  const name = $("#race-name").value.trim(), date = $("#race-date").value;
  if (!name || !date) return toast("Name und Datum angeben");
  await api("/api/races", { method: "POST", body: { name, date, priority: $("#race-priority").value, race_type: $("#race-type").value } });
  $("#race-name").value = "";
  $("#race-date").value = "";
  renderRaces();
  dataChanged();
}

// --- Wochenmuster: pro Tag beliebig viele Einheiten (Sport + Typ)

function renderPattern() {
  const options = (labels, value) =>
    Object.entries(labels).map(([k, l]) => `<option value="${k}" ${k === value ? "selected" : ""}>${l}</option>`).join("");
  const sports = Object.fromEntries(Object.entries(SPORT_LABEL).filter(([k]) => k !== "other"));
  $("#pattern").innerHTML = WEEKDAYS.map(([day, label]) => `
    <div class="pattern-day">
      <b>${label}</b>
      <div class="slots">
        ${(pattern[day] || []).map((slot, i) => `
          <span class="slot" style="border-color:${sportColor(slot.sport)}">
            <select data-day="${day}" data-i="${i}" data-field="sport">${options(sports, slot.sport)}</select>
            <select data-day="${day}" data-i="${i}" data-field="type"
              ${["strength", "mobility"].includes(slot.sport) ? "hidden" : ""}>${options(SLOT_TYPES, slot.type)}</select>
            <button type="button" class="ghost" data-day="${day}" data-remove="${i}" title="Entfernen">✕</button>
          </span>`).join("") || `<span class="muted small">Ruhetag</span>`}
        <button type="button" class="small" data-add="${day}">+</button>
      </div>
    </div>`).join("");
}

async function saveSettings() {
  state.settings = await api("/api/settings", {
    method: "PUT",
    body: {
      ftp: Number(sform.ftp.value), lthr_run: Number(sform.lthr_run.value), lthr_ride: Number(sform.lthr_ride.value),
      max_hr: Number(sform.max_hr.value),
      weight: Number(sform.weight.value) || 0, sweat_rate: Number(sform.sweat_rate.value) || 0,
      threshold_pace: paceToSec(sform.threshold_pace.value), css: paceToSec(sform.css.value),
      goal_name: sform.goal_name.value, goal_date: sform.goal_date.value, race_type: sform.race_type.value,
      week_hours: Number(sform.week_hours.value), recovery_every: Number(sform.recovery_every.value),
      target_ctl: Number(sform.target_ctl.value) || 0,
      cycle_start: sform.cycle_start.value, taper_weeks: Number(sform.taper_weeks.value) || 0,
      zwift_dir: sform.zwift_dir.value.trim(), mac_calendar: sform.mac_calendar.value,
      garmin_profile: sform.garmin_profile.checked, plant_based: sform.plant_based.checked,
      availability: sform.availability.value.trim(), calendar_ics: icsLinks(sform.calendar_ics.value),
      auto_sync: [...sform.querySelectorAll('[name="auto_sync"]:checked')].map((cb) => cb.value),
      week_pattern: pattern,
    },
  });
  settingsDialog.close();
  toast("Einstellungen gespeichert");
  dataChanged();
  refreshStatus();
}

// --- Verbindungen (Punkte oben rechts) und Leistungswerte von Garmin

export async function refreshStatus() {
  const s = state.connected = await api("/api/status");
  const names = { garmin: "Garmin", intervals: "intervals.icu → Wahoo", zwift: "Zwift", calendar: "Kalender" };
  $("#status").innerHTML = Object.entries(names)
    .map(([k, l]) => `<span class="pill ${s[k] ? "on" : ""}" title="${l}: ${s[k] ? "verbunden" : "nicht eingerichtet – siehe README"}">${s[k] ? "●" : "○"}<span class="pill-label"> ${l}</span></span>`)
    .join("");
}

export async function refreshFromGarmin() {
  const { changed, settings } = await api("/api/settings/garmin", { method: "POST" });
  state.settings = settings;
  const labels = {
    ftp: (v) => `FTP ${v} W`, lthr_run: (v) => `LTHR Laufen ${v}`, lthr_ride: (v) => `LTHR Rad ${v}`,
    max_hr: (v) => `Max-Puls ${v}`,
    threshold_pace: (v) => `Schwelle ${secToPace(v)}/km`,
  };
  const parts = Object.entries(changed).filter(([k]) => labels[k]).map(([k, v]) => labels[k](v));
  if (parts.length) {
    toast(`Von Garmin übernommen: ${parts.join(", ")}`, 6000);
    dataChanged();
  }
}

export function bindSettings() {
  $("#btn-settings").onclick = openSettings;
  $("#btn-open-setup").onclick = () => { settingsDialog.close(); openSetup(); };
  $("#btn-save-settings").onclick = withBusy($("#btn-save-settings"), saveSettings);
  $("#btn-add-race").onclick = withBusy($("#btn-add-race"), addRace);
  $("#btn-bulk-calendar").onclick = withBusy($("#btn-bulk-calendar"), async () => {
    if (sform.mac_calendar.value !== state.settings.mac_calendar) await saveSettings();  // gewählten Kalender erst speichern
    const res = await api("/api/sync/bulk", { method: "POST", body: { target: "calendar", resend: true } });
    toast(`${res.sent} Workouts im Kalender eingetragen bzw. aktualisiert` + (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""),
      res.errors.length ? 10000 : 4000);
    dataChanged();
  });
  $("#race-type").onchange = $("#race-priority").onchange = renderRaceTypeHint;
  $("#races").onclick = async (e) => {
    if (!e.target.dataset.race) return;
    await api(`/api/races/${e.target.dataset.race}`, { method: "DELETE" });
    renderRaces();
    dataChanged();
  };
  $("#pattern").onchange = (e) => {
    const { day, i, field } = e.target.dataset;
    if (!field) return;
    pattern[day][i][field] = e.target.value;
    if (field === "sport") renderPattern();
  };
  $("#pattern").onclick = (e) => {
    const { add, day, remove } = e.target.dataset;
    if (add) (pattern[add] ||= []).push({ type: "easy", sport: "ride" });
    else if (remove !== undefined) pattern[day].splice(Number(remove), 1);
    else return;
    renderPattern();
  };
}
