// Kalender (FullCalendar): Workouts, Aktivitäten, Wettkämpfe, Vorschläge und Belastungsblöcke als Hintergrund.
import { $, api, reportSync, state, toast } from "./core.js";
import { openDetail } from "./detail.js";
import { openEditor } from "./editor.js";
import { openFeedback } from "./feedback.js";
import { fmtMin, todayIso } from "./format.js";
import { COMPLIANCE_LABEL } from "./labels.js";
import { hideWeekSummary, showWeekSummary } from "./week-summary.js";
import { drawProfile, isFlat } from "./workout.js";

let calendar;
let scrollListToToday = false;
const STACKED = matchMedia("(max-width: 900px)");  // Seitenleiste unter dem Kalender, die Seite scrollt als Ganzes
const NARROW = matchMedia("(max-width: 700px)");   // zu schmal für sieben Spalten: Woche als Liste
const isWeekView = (view) => view === "dayGridWeek" || view === "listWeek";
// Monat/Block füllen die Fläche; die Woche ist nur so hoch wie ihre Einträge, darunter steht die Wochenübersicht
const calendarHeight = (view) => (STACKED.matches || isWeekView(view) ? "auto" : "100%");
const weekView = () => (NARROW.matches ? "listWeek" : "dayGridWeek");
const blockView = () => (NARROW.matches ? "listBlock" : "dayGridBlock");
const isBlockView = (view) => view === "dayGridBlock" || view === "listBlock";
const calendarToolbar = () => ({ left: "prev,next today", center: "title",
  right: `dayGridMonth,${blockView()},${weekView()},listMonth` });

export const refetchEvents = () => calendar.refetchEvents();
export const updateCalendarSize = () => calendar.updateSize();
export const gotoDate = (iso) => calendar.gotoDate(iso);

// Block-Ansicht: immer ein ganzer Belastungszyklus (z. B. 4 Wochen), ‹ › springt blockweise.
// Ausgerichtet am laufenden Zyklus (aus dem Status); ohne Zyklus (Tapering, kein Rhythmus) ab dieser Woche.
const cycleLen = () => Number(state.settings?.recovery_every) || 4;
function blockRange(date) {
  const monday = (d) => new Date(`${mondayOf(d.toLocaleDateString("sv-SE"))}T00:00`);
  const anchor = state.cycleStart ? new Date(`${state.cycleStart}T00:00`) : monday(new Date());
  const n = cycleLen();
  const weeks = Math.floor(Math.round((monday(date) - anchor) / 864e5) / 7 / n) * n;
  const start = new Date(anchor);
  start.setDate(start.getDate() + weeks * 7);
  const end = new Date(start);
  end.setDate(end.getDate() + n * 7);
  return { start, end };
}

// Montag des laufenden Zyklus merken (aus der Seitenleiste) und die Block-Ansicht neu ausrichten
export function setCycleStart(cycleStart) {
  if (cycleStart === state.cycleStart) return;
  state.cycleStart = cycleStart;
  const view = calendar.view.type;
  if (isBlockView(view)) calendar.changeView(view, calendar.getDate());
}

function adaptCalendar() {
  calendar.setOption("height", calendarHeight(calendar.view.type));
  calendar.setOption("headerToolbar", calendarToolbar());
  const view = calendar.view.type;
  if (view === "dayGridWeek" || view === "listWeek") calendar.changeView(weekView());
  if (isBlockView(view)) calendar.changeView(blockView());
}

// Liste: zum heutigen (oder nächsten) Tag springen statt am Monatsanfang zu stehen
function scrollList() {
  if (!scrollListToToday) return;
  const scroller = $("#calendar .fc-list")?.closest(".fc-scroller") || $("#calendar .fc-scroller");
  const today = todayIso();
  const day = [...document.querySelectorAll("#calendar .fc-list-day")].find((el) => el.dataset.date >= today);
  if (!scroller || !day) return;
  scrollListToToday = false;
  scroller.scrollTop += day.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
}

function eventCard(arg) {
  const p = arg.event.extendedProps;
  const card = document.createElement("div");
  card.className = "ev";
  for (const [cls, text] of [["ev-name", p.name || arg.event.title], ["ev-meta", p.meta], ["ev-note", p.note]]) {
    if (!text) continue;
    const el = document.createElement("div");
    el.className = cls;
    el.textContent = text;
    card.append(el);
  }
  const plan = p.workout || p.plan || p.suggestion?.workout;
  if (arg.view.type === "dayGridWeek" && plan?.steps?.length && !isFlat(plan.sport)) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ev-profile");
    svg.setAttribute("viewBox", "0 0 600 90");
    svg.setAttribute("preserveAspectRatio", "none");
    drawProfile(svg, plan.steps);
    card.append(svg);
  }
  return { domNodes: [card] };
}

function dayHeader(arg) {
  const [weekday, day] = [arg.date.toLocaleDateString("de-DE", { weekday: "short" }).replace(".", ""), arg.date.getDate()];
  if (arg.view.type !== "dayGridWeek") return weekday;
  return { html: `<span class="dh-weekday">${weekday}</span><span class="dh-day">${day}</span>` };
}

// --- Belastungszyklen (z. B. 3 Belastungs- + 1 Entlastungswoche) als Hintergrund der Tage

const blockWeeks = {};  // Montag → Wocheninfo aus /api/calendar

function mondayOf(iso) {
  const d = new Date(`${iso}T12:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.toLocaleDateString("sv-SE");
}

function weekTag(w) {
  if (w.race_week) return { short: "Rennen", long: "Rennwoche" };
  if (w.prelude) return { short: "Vorlauf", long: "Vorlauf vor dem ersten Zyklus" };
  if (!w.cycle_week) return { short: w.block_name, long: w.block_name };
  const week = w.recovery ? "E" : `B${w.cycle_week}`;
  const long = `${w.block_name} · ${w.recovery ? "Entlastungswoche" : `Belastungswoche ${w.cycle_week}`}`;
  return w.cycle_no
    ? { short: `Block ${w.cycle_no} · ${week}`, long: `Block ${w.cycle_no} · ${long}` }
    : { short: `${week} · ${w.block_name}`, long };
}

// Farbe des Belastungszyklus (reihum) bzw. der Phase, wenn kein Zyklus läuft (Tapering, Regeneration)
export function setBlockColor(el, w) {
  el.dataset.blk = w.block;
  el.dataset.wk = w.prelude ? "pre" : w.recovery ? "rec" : "load";
  if (w.cycle_color != null) el.dataset.cyc = w.cycle_color;
  else delete el.dataset.cyc;
}

// showTag: Wochenlabel zeigen – im Raster am Montag, in der Liste am ersten aufgeführten Tag der Woche
function paintDay(el, showTag) {
  const iso = el.dataset.date;
  const w = iso && blockWeeks[mondayOf(iso)];
  if (!w) return;
  setBlockColor(el, w);
  el.toggleAttribute("data-starts", iso === w.week_start && w.starts);
  const host = el.querySelector(".fc-list-day-cushion, .fc-daygrid-day-top");
  let tag = host?.querySelector(".blk-tag");
  if (host && showTag) {
    if (!tag) {
      tag = document.createElement("span");
      tag.className = "blk-tag";
      host.append(tag);  // Kopfzeile ist row-reverse: letztes Kind steht links
    }
    const t = weekTag(w);
    const list = el.classList.contains("fc-list-day");  // in der Liste ist Platz für den vollen Text
    tag.textContent = list ? t.long : t.short;
    tag.title = t.long;
  } else tag?.remove();
}

function paintBlocks() {
  document.querySelectorAll("#calendar .fc-daygrid-day[data-date]").forEach((el) => paintDay(el, el.dataset.date === mondayOf(el.dataset.date)));
  const seen = new Set();
  document.querySelectorAll("#calendar .fc-list-day[data-date]").forEach((el) => {
    const week = mondayOf(el.dataset.date);
    paintDay(el, !seen.has(week));
    seen.add(week);
  });
}

// --- Termine

function workoutEvent(w) {
  const c = w.compliance, clash = w.conflict;
  const synced = Object.keys(w.sync || {}).length ? " ⇄" : "";
  const tips = [
    c?.reason ? `Anders als geplant: ${c.reason}` : c ? `Compliance: ${COMPLIANCE_LABEL[c.color]}${c.basis ? ` – ${c.pct} % (${c.basis})` : ""}` : "",
    clash ? `⚠ ${clash.race.name}: ${clash.problem} (Vorschlag in der Seitenleiste)` : "",
  ].filter(Boolean);
  return {
    title: `${clash ? "⚠ " : ""}${w.status === "done" ? "✓ " : ""}${w.name} · ${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS${synced}`,
    start: w.date, allDay: true,
    classNames: ["planned", `sport-${w.sport || "other"}`, ...(w.status === "done" ? ["done"] : []),
      ...(c ? [`c-${c.color}`] : []), ...(clash ? ["conflict"] : [])],
    extendedProps: { workout: w, tip: tips.join("\n"), name: `${clash ? "⚠ " : ""}${w.name}`,
      meta: `${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS${synced}`, note: c?.reason ? `≠ anders als geplant (${c.reason})` : "" },
  };
}

function activityEvent(a, workouts, workoutById) {
  const km = a.distance ? ` · ${(a.distance / 1000).toFixed(a.sport === "swim" ? 1 : 0)} km` : "";
  const rpe = a.feedback?.rpe != null ? ` · RPE ${a.feedback.rpe}` : "";
  const planned = a.plan && workoutById[a.plan.workout_id];
  const same = a.plan?.match === "same" ? planned : null;
  const c = same?.compliance;
  const tip = same ? `Geplant: ${same.name} (${fmtMin(same.duration)}) – ${COMPLIANCE_LABEL[c.color]}, ${c.pct} %`
    : planned ? `Nicht wie geplant: ${planned.name} (${c?.reason || planned.compliance?.reason})`
    : a.unplanned ? "Ungeplante Einheit" : "";
  return {
    title: `${same?.name || a.name}${km} · ${Math.round(a.tss)} TSS${rpe}`, start: a.date, allDay: true, editable: false,
    classNames: ["activity", `sport-${a.sport || "other"}`, ...(a.unplanned ? ["unplanned"] : []), ...(c ? [`c-${c.color}`] : [])],
    extendedProps: { activity: a, plan: same, dayWorkouts: workouts.filter((w) => w.date === a.date),
      tip: [tip, "Klick für Details und Feedback"].filter(Boolean).join("\n"),
      name: same?.name || a.name, meta: `${fmtMin(a.duration)}${km} · ${Math.round(a.tss)} TSS${rpe}` },
  };
}

async function loadEvents(info, success, failure) {
  try {
    const data = await api(`/api/calendar?start=${info.startStr.slice(0, 10)}&end=${info.endStr.slice(0, 10)}`);
    for (const w of data.weeks || []) blockWeeks[w.week_start] = w;
    const workoutById = Object.fromEntries(data.workouts.map((w) => [w.id, w]));
    const events = [
      // erkannte Workouts erscheinen als eine Karte zusammen mit der Aktivität
      ...data.workouts.filter((w) => w.compliance?.match !== "same").map(workoutEvent),
      ...data.activities.map((a) => activityEvent(a, data.workouts, workoutById)),
      ...(data.races || []).map((r) => ({ title: `🏁 ${r.name} (${r.priority})`, start: r.date, allDay: true, editable: false,
        classNames: ["race", `race-${r.priority}`], extendedProps: { tip: `${r.priority}-Wettkampf` }, order: -1 })),
      ...state.suggestions.filter((s) => s.workout).map((s) => ({
        title: `Vorschlag: ${s.workout.name} · ${Math.round(s.tss)} TSS`, start: s.date, allDay: true,
        editable: false, classNames: ["suggestion", `sport-${s.workout.sport || "other"}`],
        extendedProps: { suggestion: s, name: `Vorschlag: ${s.workout.name}`, meta: `${Math.round(s.tss)} TSS` },
      })),
    ];
    success(events);
  } catch (e) {
    failure(e);
  }
}

export function initCalendar() {
  const initialView = NARROW.matches ? "listWeek" : "dayGridMonth";
  calendar = new FullCalendar.Calendar($("#calendar"), {
    initialView,
    locale: "de",
    firstDay: 1,
    height: calendarHeight(initialView),
    editable: true,
    eventStartEditable: true,
    headerToolbar: calendarToolbar(),
    buttonText: { today: "Heute", dayGridMonth: "Monat", dayGridWeek: "Woche", listWeek: "Woche", listMonth: "Liste" },
    views: {
      dayGrid: { dayHeaderContent: dayHeader },
      dayGridBlock: { type: "dayGrid", visibleRange: blockRange, dateIncrement: { weeks: cycleLen() }, buttonText: "Block",
        // nur die Tageszahl, am Monatsersten kurz mit Monat (sonst „30. November“ in jeder Ecke)
        dayCellContent: (arg) => (arg.date.getDate() === 1
          ? arg.date.toLocaleDateString("de-DE", { day: "numeric", month: "short" }) : String(arg.date.getDate())) },
      listBlock: { type: "list", visibleRange: blockRange, dateIncrement: { weeks: cycleLen() }, buttonText: "Block" },
    },
    listDayFormat: { weekday: "long", day: "numeric", month: "long" },
    listDaySideFormat: false,
    stickyHeaderDates: false,
    eventContent: eventCard,
    datesSet: (info) => {
      scrollListToToday = info.view.type === "listMonth" && !STACKED.matches;
      setTimeout(scrollList);
      const height = calendarHeight(info.view.type);
      if (calendar.getOption("height") !== height) setTimeout(() => calendar.setOption("height", height));
      if (!isWeekView(info.view.type) && hideWeekSummary()) setTimeout(() => calendar.updateSize());
    },
    eventsSet: () => setTimeout(() => {
      paintBlocks();
      scrollList();
      if (calendar.view.type === "dayGridBlock") calendar.updateSize();  // Scrollbalken erst nach dem Laden der Termine
      // nach jedem Laden der Termine (Wochenwechsel, Änderungen) die Übersicht der Woche neu holen
      if (isWeekView(calendar.view.type)) {
        // Übersicht ein-/umblenden ändert die Breite (Scrollleiste) – FullCalendar misst nur bei Fenstergröße neu
        showWeekSummary(calendar.view.currentStart.toLocaleDateString("sv-SE")).then(() => calendar.updateSize());
      }
    }),
    dayCellDidMount: (info) => paintDay(info.el, info.el.dataset.date === mondayOf(info.el.dataset.date || "")),
    events: loadEvents,
    dateClick: (info) => openEditor({ date: info.dateStr }),
    eventClick: (info) => {
      const p = info.event.extendedProps;
      if (p.workout) openDetail(p.workout);
      else if (p.suggestion) openDetail({ ...p.suggestion.workout, date: p.suggestion.date }, p.suggestion);
      else if (p.activity) openFeedback(p.activity, p.plan, p.dayWorkouts);
    },
    eventDidMount: (info) => {
      const p = info.event.extendedProps;
      info.el.title = [p.name && p.meta ? `${p.name} · ${p.meta}` : "", p.tip].filter(Boolean).join("\n");
    },
    eventDrop: async (info) => {
      const p = info.event.extendedProps;
      if (!p.workout) return info.revert();
      try {
        reportSync(await api("/api/workouts", { method: "POST", body: { ...p.workout, date: info.event.startStr } }));
      } catch (e) {
        info.revert();
        toast(e.message);
      }
    },
    eventAllow: (_, event) => Boolean(event.extendedProps.workout),
  });
  calendar.render();
  STACKED.addEventListener("change", adaptCalendar);
  NARROW.addEventListener("change", adaptCalendar);
}
