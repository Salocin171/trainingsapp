// Updates von GitHub: Button „⬆ Update“ zeigen und auf Klick die neue Version holen.
import { $, api, toast, withBusy } from "./core.js";

const UPDATE_CHECK_MS = 30 * 60 * 1000;  // der Server fragt GitHub höchstens so oft

async function checkForUpdate() {
  const u = await api("/api/update");
  const btn = $("#btn-update");
  btn.hidden = !u.available;
  if (!u.available) return;
  btn.textContent = `⬆ Update${u.behind > 1 ? ` (${u.behind})` : ""}`;
  btn.title = `Neu:\n${u.commits.map((c) => `• ${c}`).join("\n")}`;
}

async function runUpdate() {
  const u = await api("/api/update");
  if (!u.available) { $("#btn-update").hidden = true; return toast("Die App ist schon aktuell."); }
  const list = u.commits.map((c) => `• ${c}`).join("\n");
  if (!confirm(`Neue Version der Trainingsapp holen?\n\n${list}\n\nDeine Trainingsdaten bleiben unverändert.`)) return;
  toast("Update wird geholt …", 60000);
  const res = await api("/api/update", { method: "POST" });
  const note = res.restart_claude
    ? "Aktualisiert. Nutzt du die Trainingsapp in Claude: Claude einmal neu starten, damit es die neue Version kennt."
    : "Aktualisiert.";
  sessionStorage.setItem("updateNote", note);
  // Server lädt neuen Code selbst neu – warten, bis der neue läuft (andere Startzeit), dann Seite neu laden
  for (let i = 0; res.reload && i < 40; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const now = await api("/api/update").catch(() => null);
    if (now && now.started !== u.started) break;
  }
  location.reload();
}

export function initUpdates() {
  const note = sessionStorage.getItem("updateNote");
  if (note) { sessionStorage.removeItem("updateNote"); toast(note, 10000); }
  checkForUpdate().catch(() => {});
  setInterval(() => checkForUpdate().catch(() => {}), UPDATE_CHECK_MS);
  $("#btn-update").onclick = withBusy($("#btn-update"), runUpdate);
}
