// Formatierung von Datum, Dauer, Tempo und HTML-sicherer Text.

export const escapeHtml = (text) =>
  String(text ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export const sportColor = (sport) => getComputedStyle(document.documentElement).getPropertyValue(`--${sport || "other"}`).trim();

export const fmtDate = (iso, opts = { day: "2-digit", month: "2-digit" }) => new Date(iso).toLocaleDateString("de-DE", opts);
export const fmtNum = (n) => String(n).replace(".", ",");
export const fmtHours = (h) => `${fmtNum(Math.round(h * 10) / 10)} h`;

export const isoWeek = (iso) => {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  return Math.ceil(((d - new Date(Date.UTC(d.getUTCFullYear(), 0, 1))) / 86400000 + 1) / 7);
};

// Dauer als „1:05 h“ bzw. „45 min“
export const fmtMin = (sec) => {
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h}:${String(m).padStart(2, "0")} h` : `${m} min`;
};

// Uhr: „1:02:03“ bzw. „4:05“
export const fmtTime = (seconds) => {
  const sec = Math.round(seconds);  // erst runden, sonst entsteht z. B. "3:60"
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
};

// Dauer der Leistungskurve: „5 s“, „20 min“, „1 h“
export const fmtDuration = (d) => (d < 60 ? `${d} s` : d < 3600 ? `${d / 60} min` : `${d / 3600} h`);

export const paceToSec = (txt) => {
  const [m, s = "0"] = String(txt).split(":");
  return Number(m) * 60 + Number(s);
};

export const secToPace = (sec) => {
  const t = Math.round(sec);  // erst runden, sonst entsteht z. B. "3:60"
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

export const todayIso = () => new Date().toLocaleDateString("sv-SE");  // JJJJ-MM-TT in lokaler Zeit
