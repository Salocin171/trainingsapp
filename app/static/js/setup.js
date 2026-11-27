// Einrichtung (erster Start): Garmin verbinden, Schwellen und Saisonziel, Kalender, Autostart.
import { $, api, dataChanged, state, toast, withBusy } from "./core.js";
import { paceToSec, secToPace } from "./format.js";
import { fillCalendarSelect, icsLinks, raceTypeOptions, refreshStatus } from "./settings.js";

const setupDialog = $("#setup-dialog");
const suform = $("#setup-form");
const SETUP_NUMBERS = ["weight", "max_hr", "ftp", "lthr_ride", "lthr_run", "week_hours"];
let garminProfile = {};  // von Garmin geholte Werte (noch nicht gespeichert)

function fillSetup(values) {
  for (const key of [...SETUP_NUMBERS, "goal_name", "goal_date"]) if (values[key] != null) suform[key].value = values[key] || "";
  if (values.threshold_pace) suform.threshold_pace.value = secToPace(values.threshold_pace);
  if (values.css) suform.css.value = secToPace(values.css);
  if (values.race_type) suform.race_type.value = values.race_type;
  if (values.plant_based != null) suform.plant_based.checked = values.plant_based;
  if (values.availability != null) suform.availability.value = values.availability;
  if (values.calendar_ics) suform.calendar_ics.value = values.calendar_ics.join("\n");
}

export function openSetup() {
  const s = state.settings;
  fillCalendarSelect(suform.mac_calendar, s.mac_calendar);
  suform.race_type.innerHTML = raceTypeOptions();
  fillSetup({ ...s, weight: s.weight || "" });
  garminProfile = {};
  const connected = state.connected?.garmin;
  $("#setup-garmin-state").textContent = connected ? "✓ Garmin ist bereits verbunden" : "";
  $("#btn-setup-garmin").textContent = connected ? "Neu verbinden" : "Mit Garmin verbinden";
  $("#setup-mfa").hidden = true;
  suform.garmin_code.value = suform.garmin_password.value = "";
  $("#setup-autostart").hidden = true;
  refreshAutostart().catch(() => {});
  setupDialog.showModal();
}

// Autostart: autostart.command für genau diesen Ordner ausführen (startet den Server als Hintergrunddienst neu)
function renderAutostart(a, text = "") {
  $("#setup-autostart").hidden = !a.supported;
  $("#autostart-folder").textContent = a.folder;
  const ok = a.installed && a.this_folder && a.active;
  $("#btn-autostart").textContent = ok ? "Neu einrichten" : "Autostart einrichten";
  $("#autostart-state").textContent = text || (ok ? "✓ Läuft als Hintergrunddienst für diesen Ordner"
    : a.installed && !a.this_folder ? "Eingerichtet, aber für einen anderen Ordner – hier neu einrichten"
      : a.installed ? "Eingerichtet, läuft gerade aber nicht – neu einrichten" : "");
}

async function refreshAutostart() {
  renderAutostart(await api("/api/setup/autostart"));
}

async function installAutostart() {
  const before = await api("/api/setup/autostart");
  const res = await api("/api/setup/autostart", { method: "POST" });
  if (res.restart === false) return renderAutostart(await api("/api/setup/autostart"), "✓ Eingerichtet.");
  renderAutostart(before, "Wird eingerichtet … die App startet dabei kurz neu.");
  // Warten, bis der Server als Dienst neu gestartet ist (andere Startzeit); beim ersten Mal kann das dauern (Pakete)
  for (let i = 0; i < 180; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const now = await api("/api/setup/autostart").catch(() => null);
    if (now && now.started !== before.started && now.active) {
      renderAutostart(now, "✓ Eingerichtet – die App startet ab jetzt automatisch im Hintergrund.");
      refreshStatus();
      return;
    }
  }
  renderAutostart(before, `Hat nicht geklappt – Details im Log: ${res.log}`);
}

async function connectGarmin() {
  const mfa = !$("#setup-mfa").hidden;
  const body = mfa ? { code: suform.garmin_code.value }
    : { email: suform.garmin_email.value, password: suform.garmin_password.value };
  if (mfa ? !body.code : !body.email || !body.password) return toast(mfa ? "Code eingeben" : "E-Mail und Passwort eingeben");
  $("#setup-garmin-state").textContent = "Verbinde …";
  let res;
  try {
    res = await api("/api/setup/garmin", { method: "POST", body });
  } catch (e) {
    $("#setup-garmin-state").textContent = "";
    throw e;
  }
  if (res.mfa) {
    $("#setup-mfa").hidden = false;
    suform.garmin_code.focus();
    $("#setup-garmin-state").textContent = "Garmin hat dir einen Code geschickt – eintragen und nochmal klicken.";
    return;
  }
  suform.garmin_password.value = suform.garmin_code.value = "";
  $("#setup-mfa").hidden = true;
  garminProfile = res.profile || {};
  fillSetup(garminProfile);
  const found = Object.keys(garminProfile).filter((k) => !k.endsWith("_seen")).length;
  $("#setup-garmin-state").textContent = `✓ Verbunden${res.name ? ` als ${res.name}` : ""}` +
    (found ? ` – ${found} Werte übernommen, bitte prüfen.` : " – keine Leistungswerte gefunden, bitte selbst eintragen.");
  refreshStatus();
  // Verlauf im Hintergrund laden (dauert etwas) – Fitness/Form brauchen ca. 6 Wochen, besser ein Jahr
  api("/api/import/garmin?days=365", { method: "POST" })
    .then((r) => { toast(`${r.imported} Garmin-Aktivitäten importiert`); dataChanged(); })
    .catch((e) => toast(`Import: ${e.message}`, 8000));
}

async function saveSetup(done = true) {
  const num = (key) => (suform[key].value === "" ? undefined : Number(suform[key].value));
  const pace = (key) => (suform[key].value.trim() ? paceToSec(suform[key].value) : undefined);
  if (done && !(num("weight") > 0)) return toast("Bitte dein Gewicht eintragen (für die Ernährungswerte).");
  const values = {
    ...Object.fromEntries(Object.entries(garminProfile).filter(([k]) => k === "css_garmin_seen")),
    ...Object.fromEntries(SETUP_NUMBERS.map((k) => [k, num(k)])),
    threshold_pace: pace("threshold_pace"), css: pace("css"),
    goal_name: suform.goal_name.value.trim(), goal_date: suform.goal_date.value, race_type: suform.race_type.value,
    plant_based: suform.plant_based.checked, setup_done: true,
    availability: suform.availability.value.trim(), calendar_ics: icsLinks(suform.calendar_ics.value),
    mac_calendar: suform.mac_calendar.value,
    ...(suform.mac_calendar.value && !state.settings.auto_sync.includes("calendar")
      ? { auto_sync: [...state.settings.auto_sync, "calendar"] } : {}),  // gewählter Kalender = Trainings automatisch eintragen
  };
  const body = done ? values : { setup_done: true };
  state.settings = await api("/api/settings", {
    method: "PUT", body: Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined && !Number.isNaN(v))),
  });
  setupDialog.close();
  toast(done ? "Eingerichtet – viel Spaß beim Training!" : "Einrichtung findest du jederzeit unter Einstellungen.");
  dataChanged();
}

export function bindSetup() {
  $("#btn-setup-garmin").onclick = withBusy($("#btn-setup-garmin"), connectGarmin);
  $("#btn-autostart").onclick = withBusy($("#btn-autostart"), installAutostart);
  $("#btn-setup-save").onclick = withBusy($("#btn-setup-save"), () => saveSetup(true));
  $("#btn-setup-skip").onclick = withBusy($("#btn-setup-skip"), () => saveSetup(false));
  $("#setup-garmin-login").onkeydown = (e) => {  // Enter in den Garmin-Feldern = verbinden (nicht Dialog schließen)
    if (e.key === "Enter") { e.preventDefault(); $("#btn-setup-garmin").click(); }
  };
}
