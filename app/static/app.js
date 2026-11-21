// Trainingsapp – Oberfläche. Kein Build-Schritt nötig: Datei ändern, Browser neu laden.

const $ = (sel, root = document) => root.querySelector(sel);
const SPORT_LABEL = {
  swim: "Schwimmen", ride: "Rad", run: "Laufen", strength: "Stabi / Kraft", mobility: "Dehnen / Yoga", other: "Sonstiges",
};
const KIND_LABEL = {
  warmup: "Einwärmen", interval: "Intervall", recovery: "Erholung", steady: "Konstant", cooldown: "Ausfahren",
};
const SUGGESTION_LABEL = { rest: "Ruhetag", race: "Wettkampf" };
const WEEKDAYS = [["mon", "Mo"], ["tue", "Di"], ["wed", "Mi"], ["thu", "Do"], ["fri", "Fr"], ["sat", "Sa"], ["sun", "So"]];
const SLOT_TYPES = { recovery: "Regeneration", easy: "Locker", hard: "Hart", long: "Lang" };
const RACE_TYPES = { ironman: "Ironman (Langdistanz)", half: "Ironman 70.3 (Mitteldistanz)", other: "Anderer Wettkampf" };
const DEFAULT_TARGET = { ride: "power", run: "pace", swim: "pace" };
const fmtDate = (iso, opts = { day: "2-digit", month: "2-digit" }) => new Date(iso).toLocaleDateString("de-DE", opts);
const fmtHours = (h) => `${String(Math.round(h * 10) / 10).replace(".", ",")} h`;
const isoWeek = (iso) => {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  return Math.ceil(((d - new Date(Date.UTC(d.getUTCFullYear(), 0, 1))) / 86400000 + 1) / 7);
};

// Anstrengung (modifizierte Borg-Skala 0–10, wie TrainingPeaks) und Befinden 1–5
const RPE_LABEL = ["Ruhe", "sehr, sehr leicht", "leicht", "moderat", "etwas schwer", "schwer", "schwer+",
  "sehr schwer", "sehr schwer+", "extrem schwer", "maximal"];
const FEEL_LABEL = { 1: "😫 sehr schlecht", 2: "🙁 schlecht", 3: "😐 normal", 4: "🙂 gut", 5: "💪 sehr gut" };
const COMPLIANCE_LABEL = { green: "im Plan", yellow: "etwas daneben", orange: "deutlich daneben", red: "verpasst" };

const state = { settings: null, templates: [], suggestions: [], goals: [], current: null, goal: null };

// ---------------------------------------------------------------- Hilfen
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function toast(msg, ms = 3500) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), ms);
}

const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sportColor = (sport) => getComputedStyle(document.documentElement).getPropertyValue(`--${sport || "other"}`).trim();
const fmtMin = (sec) => {
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h}:${String(m).padStart(2, "0")} h` : `${m} min`;
};
const paceToSec = (txt) => {
  const [m, s = "0"] = String(txt).split(":");
  return Number(m) * 60 + Number(s);
};
const secToPace = (sec) => {
  const t = Math.round(sec);  // erst runden, sonst entsteht z. B. "3:60"
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

// Gleiche Formel wie app/workouts.py (für die Live-Vorschau im Editor)
const FLAT_TSS_PER_HOUR = { strength: 40, mobility: 10 };
function* flatten(steps) {
  for (const s of steps) {
    if (s.kind === "repeat") for (let i = 0; i < s.count; i++) yield* flatten(s.steps);
    else yield s;
  }
}
function workoutStats(w) {
  let duration = 0, tss = 0;
  for (const s of flatten(w.steps || [])) {
    duration += s.duration;
    const intensity = (Number(s.low) + Number(s.high)) / 200;
    tss += (s.duration / 3600) * intensity ** 2 * 100;
  }
  if (w.sport in FLAT_TSS_PER_HOUR) tss = (duration / 3600) * FLAT_TSS_PER_HOUR[w.sport];
  const IF = duration ? Math.sqrt(tss / ((duration / 3600) * 100)) : 0;
  return { duration, tss: Math.round(tss), IF: IF.toFixed(2) };
}

function zoneColor(pct) {
  if (pct < 56) return "#94a3b8";
  if (pct < 76) return "#3b82f6";
  if (pct < 88) return "#22c55e";
  if (pct < 95) return "#eab308";
  if (pct < 106) return "#f97316";
  return "#ef4444";
}

function drawProfile(svg, steps) {
  const all = [...flatten(steps)];
  const total = all.reduce((a, s) => a + s.duration, 0) || 1;
  const W = 600, H = 90, max = 140;
  let x = 0, out = "";
  for (const s of all) {
    const w = (s.duration / total) * W;
    const h1 = (Math.min(s.low, max) / max) * H, h2 = (Math.min(s.high, max) / max) * H;
    const color = zoneColor((Number(s.low) + Number(s.high)) / 2);
    if (s.kind === "warmup" || s.kind === "cooldown") {
      // Einwärmen/Ausfahren: Rampe von → bis
      const [a, b] = s.kind === "warmup" ? [h1, h2] : [h2, h1];
      out += `<polygon points="${x},${H} ${x},${H - a} ${x + w},${H - b} ${x + w},${H}"
               fill="${color}" stroke="var(--panel)" stroke-width="0.5"/>`;
    } else {
      // Intervall/Konstant: Zielbereich – voll bis zur Untergrenze, heller Streifen bis zur Obergrenze
      const lo = Math.min(h1, h2), hi = Math.max(h1, h2);
      out += `<rect x="${x}" y="${H - lo}" width="${w}" height="${lo}" fill="${color}" stroke="var(--panel)" stroke-width="0.5"/>`;
      if (hi > lo) out += `<rect x="${x}" y="${H - hi}" width="${w}" height="${hi - lo}" fill="${color}" opacity="0.4"/>`;
    }
    x += w;
  }
  const ftpLine = H - (100 / max) * H;
  out += `<line x1="0" x2="${W}" y1="${ftpLine}" y2="${ftpLine}" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="0.7"/>`;
  svg.innerHTML = out;
}

// ---------------------------------------------------------------- Kalender
let calendar;
let scrollListToToday = false;
const STACKED = matchMedia("(max-width: 900px)");  // Seitenleiste unter dem Kalender, die Seite scrollt als Ganzes
const NARROW = matchMedia("(max-width: 700px)");   // zu schmal für sieben Spalten: Woche als Liste
const weekView = () => (NARROW.matches ? "listWeek" : "dayGridWeek");
const calendarToolbar = () => ({ left: "prev,next today", center: "title", right: `dayGridMonth,${weekView()},listMonth` });

function adaptCalendar() {
  calendar.setOption("height", STACKED.matches ? "auto" : "100%");
  calendar.setOption("headerToolbar", calendarToolbar());
  const view = calendar.view.type;
  if (view === "dayGridWeek" || view === "listWeek") calendar.changeView(weekView());
}

// Liste: zum heutigen (oder nächsten) Tag springen statt am Monatsanfang zu stehen
function scrollList() {
  if (!scrollListToToday) return;
  const scroller = $("#calendar .fc-list")?.closest(".fc-scroller") || $("#calendar .fc-scroller");
  const today = new Date().toLocaleDateString("sv-SE");
  const day = [...document.querySelectorAll("#calendar .fc-list-day")].find((el) => el.dataset.date >= today);
  if (!scroller || !day) return;
  scrollListToToday = false;
  scroller.scrollTop += day.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
}

function eventCard(arg) {
  const p = arg.event.extendedProps;
  const card = document.createElement("div");
  card.className = "ev";
  const name = document.createElement("div");
  name.className = "ev-name";
  name.textContent = p.name || arg.event.title;
  card.append(name);
  if (p.meta) {
    const meta = document.createElement("div");
    meta.className = "ev-meta";
    meta.textContent = p.meta;
    card.append(meta);
  }
  if (p.note) {
    const note = document.createElement("div");
    note.className = "ev-note";
    note.textContent = p.note;
    card.append(note);
  }
  const plan = p.workout || p.plan || p.suggestion?.workout;
  if (arg.view.type === "dayGridWeek" && plan?.steps?.length && !(plan.sport in FLAT_TSS_PER_HOUR)) {
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

function initCalendar() {
  calendar = new FullCalendar.Calendar($("#calendar"), {
    initialView: NARROW.matches ? "listWeek" : "dayGridMonth",
    locale: "de",
    firstDay: 1,
    height: STACKED.matches ? "auto" : "100%",
    editable: true,
    eventStartEditable: true,
    headerToolbar: calendarToolbar(),
    buttonText: { today: "Heute", dayGridMonth: "Monat", dayGridWeek: "Woche", listWeek: "Woche", listMonth: "Liste" },
    views: { dayGrid: { dayHeaderContent: dayHeader } },
    listDayFormat: { weekday: "long", day: "numeric", month: "long" },
    listDaySideFormat: false,
    stickyHeaderDates: false,
    eventContent: eventCard,
    datesSet: (info) => {
      scrollListToToday = info.view.type === "listMonth" && !STACKED.matches;
      setTimeout(scrollList);
    },
    eventsSet: () => setTimeout(scrollList),
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
        const res = await api("/api/workouts", { method: "POST", body: { ...p.workout, date: info.event.startStr } });
        reportSync(res);
        refreshSidebar();
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

async function loadEvents(info, success, failure) {
  try {
    const data = await api(`/api/calendar?start=${info.startStr.slice(0, 10)}&end=${info.endStr.slice(0, 10)}`);
    const events = [];
    const workoutById = Object.fromEntries(data.workouts.map((w) => [w.id, w]));
    for (const w of data.workouts) {
      const c = w.compliance, clash = w.conflict;
      if (c?.match === "same") continue;  // erkannt: erscheint als eine Karte zusammen mit der Aktivität
      const synced = Object.keys(w.sync || {}).length ? " ⇄" : "";
      const tips = [
        c?.reason ? `Anders als geplant: ${c.reason}` : c ? `Compliance: ${COMPLIANCE_LABEL[c.color]}${c.basis ? ` – ${c.pct} % (${c.basis})` : ""}` : "",
        clash ? `⚠ ${clash.race.name}: ${clash.problem} (Vorschlag in der Seitenleiste)` : "",
      ].filter(Boolean);
      events.push({
        title: `${clash ? "⚠ " : ""}${w.status === "done" ? "✓ " : ""}${w.name} · ${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS${synced}`,
        start: w.date, allDay: true,
        classNames: ["planned", `sport-${w.sport || "other"}`, ...(w.status === "done" ? ["done"] : []),
          ...(c ? [`c-${c.color}`] : []), ...(clash ? ["conflict"] : [])],
        extendedProps: { workout: w, tip: tips.join("\n"), name: `${clash ? "⚠ " : ""}${w.name}`,
          meta: `${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS${synced}`, note: c?.reason ? `≠ anders als geplant (${c.reason})` : "" },
      });
    }
    for (const a of data.activities) {
      const km = a.distance ? ` · ${(a.distance / 1000).toFixed(a.sport === "swim" ? 1 : 0)} km` : "";
      const rpe = a.feedback?.rpe != null ? ` · RPE ${a.feedback.rpe}` : "";
      const planned = a.plan && workoutById[a.plan.workout_id];
      const same = a.plan?.match === "same" ? planned : null;
      const c = same?.compliance;
      const tip = same ? `Geplant: ${same.name} (${fmtMin(same.duration)}) – ${COMPLIANCE_LABEL[c.color]}, ${c.pct} %`
        : planned ? `Nicht wie geplant: ${planned.name} (${c?.reason || planned.compliance?.reason})`
        : a.unplanned ? "Ungeplante Einheit" : "";
      events.push({
        title: `${same?.name || a.name}${km} · ${Math.round(a.tss)} TSS${rpe}`, start: a.date, allDay: true, editable: false,
        classNames: ["activity", `sport-${a.sport || "other"}`, ...(a.unplanned ? ["unplanned"] : []), ...(c ? [`c-${c.color}`] : [])],
        extendedProps: { activity: a, plan: same, dayWorkouts: data.workouts.filter((w) => w.date === a.date),
          tip: [tip, "Klick für Details und Feedback"].filter(Boolean).join("\n"),
          name: same?.name || a.name, meta: `${fmtMin(a.duration)}${km} · ${Math.round(a.tss)} TSS${rpe}` },
      });
    }
    for (const r of data.races || []) {
      events.push({ title: `🏁 ${r.name} (${r.priority})`, start: r.date, allDay: true, editable: false,
        classNames: ["race", `race-${r.priority}`], extendedProps: { tip: `${r.priority}-Wettkampf` }, order: -1 });
    }
    for (const s of state.suggestions) {
      if (!s.workout) continue;
      events.push({
        title: `Vorschlag: ${s.workout.name} · ${Math.round(s.tss)} TSS`, start: s.date, allDay: true,
        editable: false, classNames: ["suggestion", `sport-${s.workout.sport || "other"}`],
        extendedProps: { suggestion: s, name: `Vorschlag: ${s.workout.name}`, meta: `${Math.round(s.tss)} TSS` },
      });
    }
    success(events);
  } catch (e) {
    failure(e);
  }
}

// ---------------------------------------------------------------- Seitenleiste
function initSidebarToggle() {
  const apply = (hidden) => {
    document.body.classList.toggle("no-aside", hidden);
    $("#btn-sidebar").setAttribute("aria-pressed", String(!hidden));
    calendar.updateSize();
  };
  try { apply(localStorage.getItem("sidebarHidden") === "1"); } catch { /* egal */ }
  $("#btn-sidebar").onclick = () => {
    const hidden = !document.body.classList.contains("no-aside");
    apply(hidden);
    try { localStorage.setItem("sidebarHidden", hidden ? "1" : "0"); } catch { /* egal */ }
  };
}

async function refreshSidebar() {
  const [rec, series, weeks, goals, clashes] = await Promise.all([
    api("/api/recommendations"), api("/api/load?days=90"), api("/api/weeks"), api("/api/goals"), api("/api/conflicts"),
  ]);
  renderConflicts(clashes);
  const st = rec.status;
  $("#m-ctl").textContent = Math.round(st.ctl);
  $("#m-atl").textContent = Math.round(st.atl);
  $("#m-tsb").textContent = Math.round(st.tsb);
  $("#m-form").textContent = `${st.form} · Rampe ${st.ramp > 0 ? "+" : ""}${st.ramp} CTL/Woche`;
  $("#warnings").innerHTML =
    st.warnings.map((w) => `<li class="warn">⚠︎ ${w}</li>`).join("") + st.hints.map((h) => `<li>${h}</li>`).join("");
  drawLoadChart(series);
  renderBlock(st);
  renderWeeks(weeks);
  state.goals = goals;
  renderGoals(goals);
  renderSuggestions(rec.days);
  calendar.refetchEvents();
}

// Aktueller Block, Zeitleiste bis zum Wettkampf, Position im Belastungszyklus
function renderBlock(st) {
  const w = st.week;
  $("#block-title").textContent = w.block_week ? `${w.block_name} · Woche ${w.block_week}/${w.block_weeks}` : w.block_name;
  $("#race-countdown").textContent = st.days_to_goal != null
    ? `${st.goal_name || "Wettkampf"} in ${w.weeks_to_race} Wo (${st.days_to_goal} Tage)` : "";

  const today = new Date().toISOString().slice(0, 10);
  const days = (a, b) => (new Date(b) - new Date(a)) / 86400000 + 1;
  const total = st.timeline.reduce((sum, b) => sum + days(b.start, b.end), 0);
  $("#block-timeline").innerHTML = st.timeline.map((b) => {
    const share = (days(b.start, b.end) / total) * 100;
    const active = b.start <= today && today <= b.end;
    const marker = active ? `<i style="left:${(days(b.start, today) / days(b.start, b.end)) * 100}%"></i>` : "";
    return `<div class="seg ${b.key} ${active ? "active" : ""}" style="flex-basis:${share}%"
      title="${b.name}: ${fmtDate(b.start)} – ${fmtDate(b.end)}"><span>${b.name}</span>${marker}</div>`;
  }).join("");

  let cycle = "";
  if (w.cycle_len && w.cycle_week) {
    cycle = Array.from({ length: w.cycle_len }, (_, i) => {
      const n = i + 1, recovery = n === w.cycle_len && (w.recovery || w.cycle_week !== w.cycle_len);
      return `<span class="${recovery ? "rec" : "load"} ${n === w.cycle_week ? "now" : ""}"
        title="${recovery ? "Entlastungswoche" : `Belastungswoche ${n}`}">${recovery ? "E" : `B${n}`}</span>`;
    }).join("");
  }
  $("#cycle").innerHTML = cycle;

  let info = w.recovery ? "Entlastungswoche – Umfang runter, Intensität raus"
    : w.cycle_week === w.cycle_len ? `Belastungswoche ${w.cycle_week} – letzte vor dem Tapering`
    : w.cycle_week ? `Belastungswoche ${w.cycle_week} von ${w.cycle_len - 1}` : "";
  if (w.block === "taper") info = w.race_week ? "Rennwoche" : `Tapering – noch ${w.weeks_to_race} Wochen`;
  if (w.cycle_starts) info = `Vorlauf – Belastungsrhythmus startet am ${fmtDate(w.cycle_starts)}`;
  if (st.next_recovery && !w.recovery) info += ` · nächste Entlastung ab ${fmtDate(st.next_recovery)}`;
  info += ` · Soll ${fmtHours(w.target_hours)}`;
  if (w.heat) info += ` · 🔥 Hitzetraining (${w.heat_sessions}×)`;
  $("#block-week").textContent = info;
  $("#block-focus").textContent = `Fokus: ${w.focus}`;
  const p = st.ctl_plan;
  const riskLabel = { low: "niedriges Risiko", medium: "mittleres Risiko", high: "hohes Risiko" };
  $("#ctl-plan").innerHTML = !p ? "" : p.weeks
    ? `<b>Ziel-CTL ${p.target}</b> bis ${fmtDate(p.taper_start)}: CTL ${Math.round(p.ctl)} → ${p.ramp > 0 ? "+" : ""}${p.ramp}/Woche
       <span class="risk-${p.risk}">(${riskLabel[p.risk]})</span> · nötig ≈ ${p.weekly_tss} TSS bzw. ${fmtHours(p.weekly_hours)} pro Woche
       (eingestellt: ${fmtHours(state.settings.week_hours)})`
    : `Ziel-CTL ${p.target}: Tapering hat begonnen.`;
}

function renderWeeks(weeks) {
  const max = Math.max(1, ...weeks.map((w) => Math.max(w.target_hours, w.done_hours + w.planned_hours)));
  $("#weeks").innerHTML = weeks.map((w) => {
    const pct = (h) => (h / max) * 100;
    return `<div class="week ${w.current ? "current" : ""}" title="${w.block_name}${w.recovery ? " · Entlastung" : ""}">
      <span class="wk">KW ${isoWeek(w.week_start)}${w.recovery ? " E" : ""}</span>
      <div class="bar">
        <span class="done" style="width:${pct(w.done_hours)}%"></span>
        <span class="planned" style="width:${pct(w.planned_hours)}%"></span>
        <i style="left:${pct(w.target_hours)}%" title="Soll ${fmtHours(w.target_hours)}"></i>
      </div>
      <span class="hrs">${fmtHours(w.done_hours + w.planned_hours)} / ${fmtHours(w.target_hours)}</span>
    </div>`;
  }).join("");
  const current = weeks.find((w) => w.current);
  $("#week-sports").innerHTML = current ? Object.entries(current.by_sport)
    .sort(([a], [b]) => Object.keys(SPORT_LABEL).indexOf(a) - Object.keys(SPORT_LABEL).indexOf(b))
    .map(([sport, v]) => `<span><span class="dot" style="background:${sportColor(sport)}"></span>${SPORT_LABEL[sport] || sport}
      ${fmtHours(v.done)}${v.planned ? ` <span class="muted">+ ${fmtHours(v.planned)} geplant</span>` : ""}</span>`)
    .join("") : "";
}

function renderGoals(goals) {
  const periodLabel = { week: "diese Woche", month: "diesen Monat", year: "dieses Jahr" };
  $("#goals").innerHTML = goals.length ? goals.map((g, i) => {
    const unit = g.metric === "km" ? "km" : "h";
    const title = g.name || `${g.sport === "all" ? "Gesamt" : SPORT_LABEL[g.sport]} ${unit === "km" ? "Kilometer" : "Stunden"}`;
    const when = periodLabel[g.period] || `${fmtDate(g.start)} – ${fmtDate(g.end)}`;
    const planned = g.planned ? ` (+ ${g.planned} geplant)` : "";
    const behind = g.pct + 5 < g.expected;
    return `<li data-goal="${i}" title="Bearbeiten">
      <div class="row-between"><b>${title}</b><span class="muted small">${when}</span></div>
      <div class="bar"><span class="done" style="width:${Math.min(100, g.pct)}%"></span><i style="left:${g.expected}%"></i></div>
      <div class="small ${behind ? "behind" : "muted"}">${String(g.value).replace(".", ",")} / ${g.target} ${unit}${planned} · ${g.pct}%${behind ? " – hinter Plan" : ""}</div>
    </li>`;
  }).join("") : `<li class="muted small">Noch keine Ziele. Mit „+ Ziel“ z.B. 300 km Rad pro Monat anlegen.</li>`;
}

// Geplante Workouts, die nicht zu Taper/Erholung eines Wettkampfs passen
function renderConflicts(list) {
  state.conflicts = list;
  $("#conflicts-card").hidden = !list.length;
  $("#btn-fix-all").hidden = list.length < 2;
  const day = (iso) => new Date(iso).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  $("#conflicts").innerHTML = list.map((c) => {
    const p = c.proposal;
    const change = c.action === "delete" ? "entfernen"
      : `→ ${p.sport !== c.sport ? `${SPORT_LABEL[p.sport]}: ` : ""}${p.name.replace(/ \(statt .*\)$/, "")} ${fmtMin(p.duration)}`;
    return `<li>
      <div><div class="sname"><span class="dot" style="background:${sportColor(c.sport)}"></span>${day(c.date)} · ${c.name} (${c.minutes} min)</div>
        <div class="sreason">${c.race.priority}-Wettkampf ${c.race.name} · ${c.phase}: ${c.problem}<br><b>Vorschlag: ${change}</b></div></div>
      <button class="small" data-fix="${c.workout_id}">Anpassen</button>
    </li>`;
  }).join("");
}

async function fixConflicts(ids) {
  const res = await api("/api/conflicts/apply", { method: "POST", body: { workout_ids: ids } });
  toast(`${res.applied.length} Workout(s) angepasst` + (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""),
    res.errors.length ? 10000 : 4000);
  refreshSidebar();
}

function renderSuggestions(days) {
  state.suggestions = days;
  let lastDate = null;
  $("#suggestions").innerHTML = days.length
    ? days.map((s, i) => {
        const w = s.workout;
        const title = w ? w.name : SUGGESTION_LABEL[s.kind] || s.kind;
        const meta = w ? `${SPORT_LABEL[w.sport]} · ${fmtMin(workoutStats(w).duration)} · ${Math.round(s.tss)} TSS` : "";
        const dot = w ? `<span class="dot" style="background:${sportColor(w.sport)}"></span>` : "";
        const day = s.date !== lastDate ? s.weekday : "";
        const first = s.date !== lastDate;
        lastDate = s.date;
        return `<li class="${first ? "first" : ""}">
          <span class="sday">${day}</span>
          <div><div class="sname">${dot}${title}</div>
            <div class="sreason">${meta}${meta ? "<br>" : ""}${s.reasons.join(" · ")}</div></div>
          ${w ? `<button class="small" data-accept="${i}">+</button>` : ""}
        </li>`;
      }).join("")
    : `<li class="muted">Die nächsten 7 Tage sind bereits verplant.</li>`;
}

function drawLoadChart(series) {
  const svg = $("#load-chart");
  if (!series.length) return (svg.innerHTML = "");
  const W = 320, H = 110;
  const values = series.flatMap((d) => [d.ctl, d.atl, d.tsb]);
  const max = Math.max(10, ...values), min = Math.min(-10, ...values);
  const y = (v) => H - ((v - min) / (max - min)) * H;
  const x = (i) => (i / Math.max(1, series.length - 1)) * W;
  const line = (key, color) =>
    `<polyline fill="none" stroke="${color}" stroke-width="1.6" points="${series.map((d, i) => `${x(i)},${y(d[key])}`).join(" ")}"/>`;
  svg.innerHTML =
    `<line x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}" stroke="var(--border)"/>` +
    line("tsb", "var(--tsb)") + line("atl", "var(--atl)") + line("ctl", "var(--ctl)");
}

async function acceptSuggestion(s) {
  const res = await api("/api/workouts", { method: "POST", body: { ...s.workout, date: s.date } });
  reportSync(res);
}

// ---------------------------------------------------------------- Editor
const editor = $("#editor");
const form = $("#editor-form");

function openEditor(workout) {
  state.current = {
    sport: "ride", target: "power", name: "Neues Workout", description: "", steps: [], status: "planned",
    ...structuredClone(workout),
  };
  const w = state.current;
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
  editor.showModal();
}

function renderTemplateOptions(sport) {
  const fitting = state.templates.filter((t) => t.sports.includes(sport));
  $("#tpl-kind").innerHTML = (fitting.length ? fitting : state.templates)
    .map((t) => `<option value="${t.key}">${t.name}</option>`).join("");
}

function readForm() {
  const w = state.current;
  Object.assign(w, {
    date: form.date.value, sport: form.sport.value, target: form.target.value,
    name: form.name.value, description: form.description.value,
    status: form.done.checked ? "done" : "planned",
    actual_tss: form.actual_tss.value === "" ? null : Number(form.actual_tss.value),
    rpe: form.rpe.value === "" ? null : Number(form.rpe.value),
    feel: form.feel.value === "" ? null : Number(form.feel.value),
    note: form.note.value.trim(),
  });
  return w;
}

// Prozent → absoluter Zielwert, mit denselben Bezugsgrößen wie app/sync/garmin.py
function absoluteTarget(pct, sport = form.sport.value, target = form.target.value) {
  const st = state.settings;
  if (target === "power") return Math.round((st.ftp * pct) / 100);
  if (target === "hr") return Math.round(((sport === "ride" ? st.lthr_ride : st.lthr_run) * pct) / 100);
  return secToPace((sport === "swim" ? st.css : st.threshold_pace) / (pct / 100));  // mehr % = schneller
}

function absoluteRange(s, sport = form.sport.value, target = form.target.value) {
  if (["strength", "mobility"].includes(sport) || !(Number(s.low) || Number(s.high))) return "";
  const unit = target === "power" ? "W" : target === "hr" ? "bpm" : sport === "swim" ? "/100 m" : "/km";
  const lo = absoluteTarget(Number(s.low), sport, target), hi = absoluteTarget(Number(s.high), sport, target);
  return `${lo === hi ? lo : `${lo}–${hi}`} ${unit}`;
}

function stepRow(s, list, index) {
  const row = document.createElement("div");
  row.className = "step";
  row.innerHTML = `
    <select>${Object.entries(KIND_LABEL).map(([k, l]) => `<option value="${k}" ${k === s.kind ? "selected" : ""}>${l}</option>`).join("")}</select>
    <label class="inline"><input type="number" min="0.25" step="0.25" value="${s.duration / 60}"><span class="unit">min</span></label>
    <label class="inline"><input type="number" min="0" max="200" value="${s.low}"><span class="unit">%</span></label>
    <label class="inline"><input type="number" min="0" max="200" value="${s.high}"><span class="unit">%</span></label>
    <span class="abs" title="Zielbereich aus deinen Schwellenwerten"></span>
    <button type="button" class="ghost" title="Entfernen">✕</button>`;
  const [kind, dur, low, high] = row.querySelectorAll("select, input");
  const abs = row.querySelector(".abs");
  const update = () => {
    Object.assign(s, { kind: kind.value, duration: Math.round(Number(dur.value) * 60), low: Number(low.value), high: Number(high.value) });
    abs.textContent = absoluteRange(s);
    updatePreview();
  };
  abs.textContent = absoluteRange(s);
  [kind, dur, low, high].forEach((el) => el.addEventListener("input", update));
  row.querySelector("button").onclick = () => { list.splice(index, 1); renderSteps(); };
  return row;
}

function renderSteps() {
  const box = $("#steps");
  box.innerHTML = "";
  const steps = state.current.steps;
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
  const w = state.current;
  drawProfile($("#profile"), w.steps);
  const st = workoutStats(w);
  $("#stats").textContent = `Dauer ${fmtMin(st.duration)} · geschätzter TSS ${st.tss} · IF ${st.IF}`;
}

async function saveCurrent(syncTargets = null) {
  const w = readForm();
  let res = await api("/api/workouts", { method: "POST", body: w });
  // Beim Speichern wurden bereits übertragene Ziele aktualisiert – nur neue noch senden.
  const missing = (syncTargets || []).filter((t) => !res.workout.sync?.[t]);
  if (missing.length) {
    const sent = await api(`/api/workouts/${res.workout.id}/sync`, { method: "POST", body: { targets: missing } });
    res = { workout: sent.workout, errors: { ...res.errors, ...sent.errors } };
  }
  editor.close();
  reportSync(res);
}

function reportSync(res) {
  const errors = Object.entries(res.errors || {});
  const synced = Object.keys(res.workout?.sync || {});
  if (errors.length) toast(errors.map(([k, v]) => `${k}: ${v}`).join(" | "), 8000);
  else toast(synced.length ? `Gespeichert und übertragen an ${synced.join(", ")}` : "Gespeichert");
  refreshSidebar();
}

function withBusy(button, fn) {
  return async () => {
    button.disabled = true;
    try { await fn(); } catch (e) { toast(e.message, 8000); } finally { button.disabled = false; }
  };
}

// ---------------------------------------------------------------- Einrichtung (erster Start)
const setupDialog = $("#setup-dialog");
const suform = $("#setup-form");
const SETUP_NUMBERS = ["weight", "max_hr", "ftp", "lthr_ride", "lthr_run", "week_hours"];

function fillSetup(values) {
  for (const key of [...SETUP_NUMBERS, "goal_name", "goal_date"]) if (values[key] != null) suform[key].value = values[key] || "";
  if (values.threshold_pace) suform.threshold_pace.value = secToPace(values.threshold_pace);
  if (values.css) suform.css.value = secToPace(values.css);
  if (values.race_type) suform.race_type.value = values.race_type;
  if (values.plant_based != null) suform.plant_based.checked = values.plant_based;
}

function openSetup() {
  const s = state.settings;
  suform.race_type.innerHTML = Object.entries(RACE_TYPES).map(([k, l]) => `<option value="${k}">${l}</option>`).join("");
  fillSetup({ ...s, weight: s.weight || "" });
  state.setupProfile = {};
  const connected = state.connected?.garmin;
  $("#setup-garmin-state").textContent = connected ? "✓ Garmin ist bereits verbunden" : "";
  $("#btn-setup-garmin").textContent = connected ? "Neu verbinden" : "Mit Garmin verbinden";
  $("#setup-mfa").hidden = true;
  suform.garmin_code.value = suform.garmin_password.value = "";
  setupDialog.showModal();
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
  state.setupProfile = res.profile || {};
  fillSetup(state.setupProfile);
  const found = Object.keys(state.setupProfile).filter((k) => !k.endsWith("_seen")).length;
  $("#setup-garmin-state").textContent = `✓ Verbunden${res.name ? ` als ${res.name}` : ""}` +
    (found ? ` – ${found} Werte übernommen, bitte prüfen.` : " – keine Leistungswerte gefunden, bitte selbst eintragen.");
  refreshStatus();
  // Verlauf im Hintergrund laden (dauert etwas) – Fitness/Form brauchen ca. 6 Wochen, besser ein Jahr
  api("/api/import/garmin?days=365", { method: "POST" })
    .then((r) => { toast(`${r.imported} Garmin-Aktivitäten importiert`); refreshSidebar(); })
    .catch((e) => toast(`Import: ${e.message}`, 8000));
}

async function saveSetup(done = true) {
  const num = (key) => (suform[key].value === "" ? undefined : Number(suform[key].value));
  const pace = (key) => (suform[key].value.trim() ? paceToSec(suform[key].value) : undefined);
  if (done && !(num("weight") > 0)) return toast("Bitte dein Gewicht eintragen (für die Ernährungswerte).");
  const values = {
    ...Object.fromEntries(Object.entries(state.setupProfile || {}).filter(([k]) => k === "css_garmin_seen")),
    ...Object.fromEntries(SETUP_NUMBERS.map((k) => [k, num(k)])),
    threshold_pace: pace("threshold_pace"), css: pace("css"),
    goal_name: suform.goal_name.value.trim(), goal_date: suform.goal_date.value, race_type: suform.race_type.value,
    plant_based: suform.plant_based.checked, setup_done: true,
  };
  const body = done ? values : { setup_done: true };
  state.settings = await api("/api/settings", {
    method: "PUT", body: Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined && !Number.isNaN(v))),
  });
  setupDialog.close();
  toast(done ? "Eingerichtet – viel Spaß beim Training!" : "Einrichtung findest du jederzeit unter Einstellungen.");
  refreshSidebar();
}

// ---------------------------------------------------------------- Workout-Details mit Ernährung
const detailDialog = $("#detail-dialog");
const FUEL_PHASES = { before: "Vor dem Training", during: "Während des Trainings", after: "Nach dem Training" };
const FUEL_SHORT = { before: "Vorher", during: "Während", after: "Danach" };
const fmtNum = (n) => String(n).replace(".", ",");
const fmtQty = (q) => q && `${q.low === q.high ? q.low : `${q.low}–${q.high}`} ${q.unit}`;
const fmtPerKg = (q) => q?.per_kg && `${q.per_kg.map(fmtNum).join("–")} ${q.unit === "ml" ? "ml" : "g"}/kg${q.unit.endsWith("/h") ? "/h" : ""}`;

// Der KH-Block der Beschreibung steht schon im Ernährungsteil – oben nur den Rest zeigen
function withoutFuelBlock(text) {
  return (text || "").split("\n")
    .filter((line) => !/^\s*KH\s*\(.*kg\)\s*:?\s*$/i.test(line) && !/^\s*[-•·*]?\s*(Vorher|Während|Danach)\s*:/i.test(line))
    .join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function stepDuration(sec) {
  return sec % 60 ? `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")} min` : fmtMin(sec);
}

function stepLine(s, w) {
  const pct = Number(s.low) === Number(s.high) ? `${s.low} %` : `${s.low}–${s.high} %`;
  const abs = absoluteRange(s, w.sport, w.target);
  const zone = Number(s.low) || Number(s.high) ? ` · ${pct}` : "";
  return `${KIND_LABEL[s.kind] || s.kind} ${stepDuration(s.duration)}${zone}${abs ? ` · <span class="abs">${abs}</span>` : ""}`;
}

function renderDetailSteps(w) {
  const items = (w.steps || []).map((s) => s.kind === "repeat"
    ? `<li>${s.count} × ( ${s.steps.map((c) => stepLine(c, w)).join(" / ")} )</li>`
    : `<li>${stepLine(s, w)}</li>`);
  $("#d-steps").innerHTML = items.join("");
  $("#d-steps-box").hidden = !items.length || w.sport in FLAT_TSS_PER_HOUR;
}

function fuelCell(label, q, sub = "", src = "") {
  return `<div class="fuel-cell"><span class="label">${label}</span>
    <b class="${q ? "" : "none"}">${q ? fmtQty(q) : "–"}</b>
    ${sub ? `<span class="sub">${escapeHtml(sub)}</span>` : ""}${src ? `<span class="src">${src}</span>` : ""}</div>`;
}

function renderNutrition(n) {
  $("#d-fuel-kind").textContent = n.kind_label;
  // Nur Zeilen zeigen, die in mindestens einer Phase einen Wert haben (Kraft: nur Eiweiß, Yoga: keine)
  const show = (field) => Object.values(n.phases).some((p) => p[field]);
  $("#d-fuel").innerHTML = Object.entries(FUEL_PHASES).map(([key, title]) => {
    const p = n.phases[key];
    const carbSub = [fmtPerKg(p.carbs), p.total ? `≈ ${fmtQty(p.total)} gesamt` : ""].filter(Boolean).join(" · ");
    const when = p.timing || p.hint;
    return `<div class="fuel-col ${key}"><h4>${title}</h4>
      ${show("carbs") ? fuelCell("Kohlenhydrate", p.carbs, carbSub, p.source === "plan" ? "aus deinem Plan" : "") : ""}
      ${show("fluid") ? fuelCell("Flüssigkeit", p.fluid, p.fluid_hint || fmtPerKg(p.fluid) || "") : ""}
      ${show("protein") ? fuelCell("Eiweiß", p.protein, fmtPerKg(p.protein) || "") : ""}
      ${when ? `<div class="fuel-when">${escapeHtml(when)}</div>` : ""}</div>`;
  }).join("");
  $("#d-fuel-plan").innerHTML = Object.keys(FUEL_PHASES).filter((k) => n.phases[k].plan_text)
    .map((k) => `<div class="${k}"><b>${FUEL_SHORT[k]}:</b> ${escapeHtml(n.phases[k].plan_text)}</div>`).join("");
  const d = n.day;
  $("#d-fuel-day").innerHTML = `Kohlenhydrate heute gesamt: <b>${fmtQty(d)}</b> <span class="muted">(${fmtPerKg(d)} · ${d.label})</span>`;
  $("#d-fuel-notes").innerHTML = n.notes.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const sweat = n.sweat_rate ? `, Schweißrate ${fmtNum(n.sweat_rate)} l/h` : "";
  $("#d-fuel-basis").textContent = `Richtwerte für ${fmtNum(n.weight)} kg${sweat}${n.weeks_to_race != null
    ? `, ${Math.floor(n.weeks_to_race)} Wochen bis zum Wettkampf` : ""}. Ersetzt keine medizinische Beratung.`;
}

async function openDetail(workout, suggestion = null) {
  const token = (openDetail.token = (openDetail.token || 0) + 1);
  let w = { steps: [], ...workout };
  const stats = workoutStats(w);
  const fill = () => {
    $("#d-title").textContent = w.name;
    $("#d-sport").style.setProperty("--sport", sportColor(w.sport));
    $("#d-sport").title = SPORT_LABEL[w.sport] || "";
    const desc = $("#d-desc");
    desc.textContent = withoutFuelBlock(w.description);
    desc.classList.remove("open");
    const n = w.nutrition;
    const facts = [
      [SPORT_LABEL[w.sport] || w.sport, fmtDate(w.date, { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })],
      n?.start ? ["Uhrzeit", n.end ? `${n.start}–${n.end}` : n.start] : null,
      ["Dauer", fmtMin(w.duration ?? stats.duration)],
      ["TSS", Math.round(w.tss ?? stats.tss)],
      w.sport in FLAT_TSS_PER_HOUR ? null : ["IF", Number(w.if ?? stats.IF).toFixed(2).replace(".", ",")],
      suggestion ? ["Status", "Vorschlag"] : ["Status", w.status === "done" ? "✓ erledigt" : "geplant"],
    ].filter(Boolean);
    $("#d-facts").innerHTML = facts.map(([k, v]) => `<div><span class="label">${k}</span><b>${escapeHtml(v)}</b></div>`).join("");
    const profile = $("#d-profile");
    const showProfile = w.steps.length && !(w.sport in FLAT_TSS_PER_HOUR);
    profile.style.display = showProfile ? "" : "none";  // SVG kennt kein .hidden
    if (showProfile) drawProfile(profile, w.steps);
    renderDetailSteps(w);
    $("#d-done").hidden = Boolean(suggestion) || !w.id;
    $("#d-done").textContent = w.status === "done" ? "Wieder als offen markieren" : "Als erledigt markieren";
    $("#d-accept").hidden = !suggestion;
    $("#d-start").hidden = Boolean(suggestion) || !TIMER_SPORTS.includes(w.sport);
    $("#d-edit").textContent = suggestion ? "Anpassen" : "Bearbeiten";
  };
  fill();
  $("#d-fuel").innerHTML = `<p class="muted">Ernährung wird berechnet …</p>`;
  ["#d-fuel-plan", "#d-fuel-day", "#d-fuel-notes", "#d-fuel-basis"].forEach((sel) => ($(sel).innerHTML = ""));
  $("#d-fuel-kind").textContent = "";
  if (!detailDialog.open) detailDialog.showModal();
  requestAnimationFrame(() => {
    const desc = $("#d-desc");
    $("#d-more").hidden = desc.scrollHeight <= desc.clientHeight + 2;
  });

  $("#d-more").onclick = () => { $("#d-desc").classList.add("open"); $("#d-more").hidden = true; };
  $("#d-edit").onclick = () => { detailDialog.close(); openEditor(w); };
  $("#d-start").onclick = () => { detailDialog.close(); openCircuit(w); };
  $("#d-accept").onclick = withBusy($("#d-accept"), async () => { await acceptSuggestion(suggestion); detailDialog.close(); });
  $("#d-done").onclick = withBusy($("#d-done"), async () => {
    const res = await api("/api/workouts", { method: "POST", body: { ...w, status: w.status === "done" ? "planned" : "done" } });
    reportSync(res);
    openDetail(res.workout);
  });

  try {
    if (w.id && !suggestion) w = await api(`/api/workouts/${w.id}`);
    else w.nutrition = await api("/api/nutrition", { method: "POST", body: w });
    if (token !== openDetail.token) return;
    fill();
    renderNutrition(w.nutrition);
  } catch (e) {
    if (token === openDetail.token) $("#d-fuel").innerHTML = `<p class="muted">Ernährung nicht verfügbar: ${escapeHtml(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------- Zirkel-Timer (Kraft/Stabi)
const timerDialog = $("#timer-dialog");
const tform = $("#timer-form");
const TIMER_SPORTS = ["strength", "mobility", "other"];
const CIRCUIT_DEFAULT = { work: 40, rest: 20, rounds: 3, round_rest: 60, exercises: [] };
const CIRCUIT_LIMITS = { work: [5, 600], rest: [0, 600], rounds: [1, 60], round_rest: [0, 900] };  // wie plan_import.py
const PHASE_LABEL = { prep: "Gleich geht's los", work: "Los!", rest: "Pause", round: "Rundenpause" };
const PREP_SECONDS = 10;
const timer = { workout: null, circuit: null, phases: [], index: 0, start: 0, end: 0, left: 0, paused: false, tick: null,
                lastSec: null, lock: null, audio: null, startedAt: 0, pausedAt: 0, pausedMs: 0 };

// Kleine Merkhilfe pro Browser (Ton/Ansage, letzter freier Timer) – darf fehlen
const timerPrefs = {
  get() { try { return JSON.parse(localStorage.getItem("timer") || "{}"); } catch { return {}; } },
  set(p) { try { localStorage.setItem("timer", JSON.stringify({ ...this.get(), ...p })); } catch { /* egal */ } },
};

// Übung: {name, reps?, seconds?}; ältere Zirkel speichern nur den Namen. Wiederholungen ohne Zahl: reps 0.
// Eingabe eine pro Zeile, Kurzform hinter dem letzten „|“: „12 Wdh“, „Wdh“ oder „45 s“ (wie plan_import.py)
const exerciseOf = (e) => (typeof e === "string" ? { name: e } : e);
const repsLabel = (reps) => (reps ? `${reps} Wdh` : "Wdh");
const exerciseLine = (e) => e.name + ("reps" in e ? ` | ${repsLabel(e.reps)}` : e.seconds ? ` | ${e.seconds} s` : "");
function parseExerciseLine(line) {
  const bar = line.lastIndexOf("|"), tail = line.slice(bar + 1).trim(), name = line.slice(0, bar).trim();
  const reps = tail.match(/^(\d*)\s*(wdh\.?|wiederholungen|reps?|x)$/i), secs = tail.match(/^(\d+)\s*(s|sek\.?|sekunden)$/i);
  if (bar < 0 || !name || !(reps || secs)) return { name: line };
  return reps ? { name, reps: Math.min(200, Number(reps[1]) || 0) } : { name, seconds: Math.min(600, Math.max(5, Number(secs[1]))) };
}

// Ohne gespeicherten Zirkel: Übungen und „40 s … / 20 s“ aus der Beschreibung, Runden aus der Wiederholung
function circuitFor(w) {
  if (w.circuit) return { ...CIRCUIT_DEFAULT, ...w.circuit, exercises: (w.circuit.exercises || []).map(exerciseOf) };
  const text = w.description || "";
  const times = text.match(/(\d+)\s*s\b[^/\d]*\/\s*(\d+)\s*s\b/);
  const repeat = (w.steps || []).find((s) => s.kind === "repeat");
  const roundRest = repeat?.steps.find((s) => s.kind === "recovery");
  return {
    ...CIRCUIT_DEFAULT,
    ...(times && { work: Number(times[1]), rest: Number(times[2]) }),
    ...(repeat && { rounds: repeat.count }),
    ...(roundRest && { round_rest: roundRest.duration }),
    exercises: (text.split(":")[1] || "").split(/[,;\n]/).map((e) => e.trim().replace(/\.$/, "")).filter(Boolean).map(exerciseOf),
  };
}

function readCircuit() {
  const lines = tform.exercises.value.split("\n").map((e) => e.trim()).filter(Boolean);
  const c = { exercises: lines.slice(0, 30).map(parseExerciseLine) };
  for (const [key, [lo, hi]] of Object.entries(CIRCUIT_LIMITS)) {
    c[key] = Math.min(hi, Math.max(lo, Math.round(Number(tform[key].value) || 0)));
  }
  return c;
}

// Ablauf: Vorlauf, dann je Runde jede Übung (Belastung + Pause), nach der Runde die Rundenpause.
// Übungen mit Wiederholungen laufen bis „Fertig“ (manual) – ihre Dauer ist nur die Schätzung „work“.
function circuitPhases(c) {
  const list = c.exercises.length ? c.exercises : [{ name: "" }];
  const phases = [{ type: "prep", duration: PREP_SECONDS, exercise: list[0].name, round: 1, station: 1 }];
  for (let round = 1; round <= c.rounds; round++) {
    list.forEach((ex, i) => {
      phases.push({ type: "work", duration: ex.seconds || c.work, exercise: ex.name, reps: ex.reps, manual: "reps" in ex,
                    round, station: i + 1 });
      const last = i === list.length - 1;
      if (last && round === c.rounds) return;
      const roundBreak = last && c.round_rest > 0;
      const next = { exercise: list[last ? 0 : i + 1].name, round: last ? round + 1 : round, station: last ? 1 : i + 2 };
      if (roundBreak || c.rest) phases.push({ type: roundBreak ? "round" : "rest", duration: roundBreak ? c.round_rest : c.rest, ...next });
    });
  }
  return phases;
}

const phasesTotal = (phases) => phases.reduce((sum, p) => sum + (p.type === "prep" ? 0 : p.duration), 0);

function renderCircuitSummary() {
  const c = readCircuit(), n = c.exercises.length;
  const intervals = c.rounds * Math.max(1, n);
  const manual = c.exercises.some((e) => "reps" in e);
  $("#timer-summary").textContent = (n ? `${c.rounds} Runden × ${n} Übungen = ${intervals} Intervalle` : `${intervals} Intervalle`)
    + ` · Dauer ${manual ? "ca. " : ""}${fmtTime(phasesTotal(circuitPhases(c)))} min`
    + (manual ? " (Wiederholungen mit Belastungszeit geschätzt, weiter per „Fertig“)" : "");
}

function showTimerView(view) {
  for (const v of ["setup", "run", "done"]) {
    $(`#timer-${v}`).hidden = $(`#timer-${v}-actions`).hidden = v !== view;
  }
  if (view !== "run") delete timerDialog.dataset.phase;
}

function openCircuit(workout = null) {
  const prefs = timerPrefs.get();
  timer.workout = workout;
  const c = workout ? circuitFor(workout) : { ...CIRCUIT_DEFAULT, ...prefs.circuit };
  for (const key of Object.keys(CIRCUIT_LIMITS)) tform[key].value = c[key];
  tform.exercises.value = c.exercises.map((e) => exerciseLine(exerciseOf(e))).join("\n");
  tform.sound.checked = prefs.sound ?? true;
  tform.voice.checked = prefs.voice ?? true;
  $("#timer-title").textContent = workout ? `Zirkel-Timer · ${workout.name}` : "Zirkel-Timer";
  $("#btn-t-finish").hidden = !workout;
  showTimerView("setup");
  renderCircuitSummary();
  timerDialog.showModal();
}

function startCircuit() {
  const c = readCircuit();
  timer.circuit = c;
  if (timer.workout) timer.workout.circuit = c;  // wird mit dem Workout gespeichert
  else timerPrefs.set({ circuit: c });
  timer.phases = circuitPhases(c);
  Object.assign(timer, { paused: false, startedAt: Date.now(), pausedMs: 0 });
  timer.audio ||= new (window.AudioContext || window.webkitAudioContext)();
  timer.audio.resume();
  showTimerView("run");
  enterPhase(0);
  clearInterval(timer.tick);
  timer.tick = setInterval(tickCircuit, 100);
  keepAwake(true);
}

function enterPhase(i, start = Date.now()) {
  timer.index = Math.max(0, Math.min(i, timer.phases.length));
  if (timer.index === timer.phases.length) return finishCircuit();
  const p = timer.phases[timer.index];
  timer.start = start;
  timer.end = start + p.duration * 1000;
  timer.left = timer.end - Date.now();
  timer.lastSec = null;
  if (p.type === "work") {
    beep(880, 0.5);
    say(p.manual ? `${p.exercise}, ${p.reps ? `${p.reps} Wiederholungen` : "Wiederholungen"}` : p.exercise || "Los");
  } else if (p.type === "prep") say(p.exercise ? `Gleich geht's los mit ${p.exercise}` : "Gleich geht's los");
  else { beep(440, 0.5); say(p.exercise ? `${PHASE_LABEL[p.type]}. Als Nächstes ${p.exercise}` : PHASE_LABEL[p.type]); }
  $("#t-bar").style.transition = "none";  // Balken springt zurück statt rückwärts zu laufen
  renderCircuit();
  requestAnimationFrame(() => { $("#t-bar").style.transition = ""; });
}

function tickCircuit() {
  if (timer.paused) return;
  timer.left = timer.end - Date.now();
  if (timer.phases[timer.index].manual) return renderCircuit();  // wartet auf „Fertig“
  const sec = Math.ceil(timer.left / 1000);
  if (sec !== timer.lastSec && sec >= 1 && sec <= 3) beep(660, 0.12);
  timer.lastSec = sec;
  // Ab der alten Endzeit weiterzählen, damit nichts driftet (auch wenn der Tab gedrosselt war)
  if (timer.left <= 0) enterPhase(timer.index + 1, timer.end);
  else renderCircuit();
}

function renderCircuit() {
  const p = timer.phases[timer.index], c = timer.circuit;
  const after = timer.phases.slice(timer.index + 1);
  const remaining = Math.max(0, timer.left) / 1000 + phasesTotal(after);
  const estimated = p.manual || after.some((q) => q.manual);
  timerDialog.dataset.phase = p.type;
  timerDialog.classList.toggle("manual", Boolean(p.manual));
  $("#t-phase").textContent = timer.paused ? "Angehalten" : p.manual ? fmtTime(Math.floor((Date.now() - timer.start) / 1000)) : PHASE_LABEL[p.type];
  $("#t-clock").textContent = p.manual ? repsLabel(p.reps) : fmtTime(Math.ceil(Math.max(0, timer.left) / 1000));
  $("#t-exercise").textContent = p.type === "work" ? p.exercise : p.exercise && `Als Nächstes: ${p.exercise}`;
  const next = p.type === "work" && after.find((q) => q.type === "work");
  $("#t-next").textContent = next?.exercise ? `danach: ${next.exercise}` : "";
  $("#t-bar").style.width = p.manual ? "100%" : `${100 * (1 - Math.max(0, timer.left) / (p.duration * 1000))}%`;
  const n = c.exercises.length;
  $("#t-progress").textContent = `Runde ${p.round}/${c.rounds}` + (n > 1 ? ` · Übung ${p.station}/${n}` : "")
    + ` · noch ${estimated ? "ca. " : ""}${fmtTime(Math.ceil(remaining))}`;
  $("#btn-t-pause").textContent = timer.paused ? "▶ Weiter" : "⏸ Pause";
  $("#btn-t-pause").hidden = Boolean(p.manual);
  $("#btn-t-done").hidden = !p.manual;
}

function pauseCircuit() {
  if (timer.phases[timer.index].manual) return;
  timer.paused = !timer.paused;
  if (timer.paused) timer.pausedAt = Date.now();
  else { timer.pausedMs += Date.now() - timer.pausedAt; timer.end = Date.now() + timer.left; }
  renderCircuit();
}

function stepCircuit(delta) {
  // Zurück: erst die laufende Phase neu starten, innerhalb der ersten 2 s eine Phase zurück
  const target = delta > 0 ? timer.index + 1 : Date.now() - timer.start > 2000 ? timer.index : timer.index - 1;
  if (timer.paused) pauseCircuit();
  enterPhase(target);
}

function stopCircuit() {
  clearInterval(timer.tick);
  timer.tick = null;
  keepAwake(false);
  timer.utterance = null;
  window.speechSynthesis?.cancel();
  if (document.fullscreenElement) document.exitFullscreen();
}

function finishCircuit() {
  const { phases, index } = timer;
  const complete = index === phases.length;
  const works = phases.filter((p) => p.type === "work").length;
  const done = phases.slice(0, index).filter((p) => p.type === "work").length;
  const pausedMs = timer.pausedMs + (timer.paused ? Date.now() - timer.pausedAt : 0);
  const seconds = Math.max(0, (Date.now() - timer.startedAt - pausedMs) / 1000 - PREP_SECONDS);  // echte Zeit
  stopCircuit();
  if (complete) { beep(880, 0.2); setTimeout(() => beep(1175, 0.6), 250); say("Geschafft"); }
  $("#t-done-title").textContent = complete ? "Geschafft 💪" : "Beendet";
  $("#t-done-summary").textContent = `${done} von ${works} Intervallen · ${fmtTime(Math.round(seconds))} min`;
  showTimerView("done");
}

async function saveCircuitDone() {
  form.done.checked = true;
  const res = await api("/api/workouts", { method: "POST", body: readForm() });
  timerDialog.close();
  editor.close();
  openEditor(res.workout);  // offen lassen für RPE / Befinden
  toast("Als erledigt gespeichert – RPE und Befinden kannst du noch eintragen");
  refreshSidebar();
}

function beep(freq, seconds) {
  if (!tform.sound.checked || !timer.audio) return;
  const ctx = timer.audio, osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.3, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + seconds);
  osc.connect(gain).connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + seconds);
}

function say(text) {
  if (!tform.voice.checked || !text || !window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = timer.utterance = new SpeechSynthesisUtterance(text);
  u.lang = "de-DE";
  speechSynthesis.speak(u);
}

// Bildschirm während des Timers anlassen (geht nicht in jedem Browser)
async function keepAwake(on) {
  try {
    if (on && !timer.lock) timer.lock = await navigator.wakeLock?.request("screen");
    if (!on && timer.lock) { await timer.lock.release(); timer.lock = null; }
  } catch { timer.lock = null; }
}

function bindCircuitTimer() {
  $("#btn-timer").onclick = () => openCircuit();
  $("#btn-circuit").onclick = () => openCircuit(readForm());
  tform.oninput = (e) => {
    if (["sound", "voice"].includes(e.target.name)) timerPrefs.set({ [e.target.name]: e.target.checked });
    else if (!$("#timer-setup").hidden) renderCircuitSummary();
  };
  $("#btn-t-start").onclick = startCircuit;
  $("#btn-t-again").onclick = () => showTimerView("setup");
  $("#btn-t-pause").onclick = pauseCircuit;
  $("#btn-t-done").onclick = () => stepCircuit(1);
  $("#btn-t-prev").onclick = () => stepCircuit(-1);
  $("#btn-t-next").onclick = () => stepCircuit(1);
  $("#btn-t-stop").onclick = finishCircuit;
  $("#btn-t-full").onclick = () => (document.fullscreenElement ? document.exitFullscreen() : timerDialog.requestFullscreen?.());
  $("#btn-t-finish").onclick = withBusy($("#btn-t-finish"), saveCircuitDone);
  timerDialog.addEventListener("keydown", (e) => {
    if (!timer.tick || e.target.matches("input, textarea")) return;
    // Leertaste/Enter: bei Wiederholungen „Fertig“, sonst Pause
    const manual = timer.phases[timer.index]?.manual, done = () => stepCircuit(1);
    const keys = { " ": manual ? done : pauseCircuit, Enter: manual ? done : null, ArrowRight: done, ArrowLeft: () => stepCircuit(-1) };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  });
  timerDialog.addEventListener("cancel", (e) => { if (timer.tick && !confirm("Timer abbrechen?")) e.preventDefault(); });
  timerDialog.addEventListener("close", stopCircuit);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && timer.tick) { timer.lock = null; keepAwake(true); }
  });
}

// ---------------------------------------------------------------- Einstellungen
const settingsDialog = $("#settings");
const sform = $("#settings-form");

function openSettings() {
  const s = state.settings;
  sform.race_type.innerHTML = Object.entries(RACE_TYPES).map(([k, l]) => `<option value="${k}">${l}</option>`).join("");
  $("#race-type").innerHTML = state.raceTypes.map((t) => `<option value="${t.key}">${t.label}</option>`).join("");
  $("#race-type").value = "run_half";
  renderRaceTypeHint();
  renderRaces();
  for (const key of ["ftp", "lthr_run", "lthr_ride", "max_hr", "weight", "sweat_rate", "goal_name", "goal_date", "race_type", "week_hours",
    "recovery_every", "cycle_start", "taper_weeks", "target_ctl", "zwift_dir", "google_calendar"]) {
    sform[key].value = s[key] ?? "";
  }
  sform.threshold_pace.value = secToPace(s.threshold_pace);
  sform.css.value = secToPace(s.css);
  sform.garmin_profile.checked = s.garmin_profile;
  sform.plant_based.checked = s.plant_based;
  $("#garmin-profile-at").textContent = s.garmin_profile_at
    ? `zuletzt übernommen: ${new Date(s.garmin_profile_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}`
    : "";
  sform.querySelectorAll('[name="auto_sync"]').forEach((cb) => (cb.checked = s.auto_sync.includes(cb.value)));
  state.pattern = structuredClone(s.week_pattern);
  renderPattern();
  settingsDialog.showModal();
}

// Weitere Wettkämpfe (B/C) – werden sofort gespeichert
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
      <span>${r.name}</span><span class="muted small" title="${recoveryText(r.race_type, r.priority)}">${label(r.race_type)}</span>
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
  refreshSidebar();
}

// Wochenmuster: pro Tag beliebig viele Einheiten (Sport + Typ)
function renderPattern() {
  const options = (labels, value) =>
    Object.entries(labels).map(([k, l]) => `<option value="${k}" ${k === value ? "selected" : ""}>${l}</option>`).join("");
  $("#pattern").innerHTML = WEEKDAYS.map(([day, label]) => `
    <div class="pattern-day">
      <b>${label}</b>
      <div class="slots">
        ${(state.pattern[day] || []).map((slot, i) => `
          <span class="slot" style="border-color:${sportColor(slot.sport)}">
            <select data-day="${day}" data-i="${i}" data-field="sport">${options(
              Object.fromEntries(Object.entries(SPORT_LABEL).filter(([k]) => k !== "other")), slot.sport)}</select>
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
      zwift_dir: sform.zwift_dir.value.trim(), google_calendar: sform.google_calendar.value.trim() || "Sport",
      garmin_profile: sform.garmin_profile.checked, plant_based: sform.plant_based.checked,
      auto_sync: [...sform.querySelectorAll('[name="auto_sync"]:checked')].map((cb) => cb.value),
      week_pattern: state.pattern,
    },
  });
  settingsDialog.close();
  toast("Einstellungen gespeichert");
  refreshSidebar();
  refreshStatus();
}

// ---------------------------------------------------------------- Ziele
const goalDialog = $("#goal-dialog");
const gform = $("#goal-form");

function openGoal(goal) {
  state.goal = goal;
  const today = new Date().toISOString().slice(0, 10);
  $("#goal-title").textContent = goal.id ? "Ziel bearbeiten" : "Neues Ziel";
  gform.name.value = goal.name || "";
  gform.sport.value = goal.sport || "all";
  gform.metric.value = goal.metric || "hours";
  gform.period.value = goal.period || "week";
  gform.target.value = goal.target ?? "";
  gform.start.value = goal.period === "custom" ? goal.start : today;
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
  await api("/api/goals", {
    method: "POST",
    body: {
      id: state.goal.id, name: gform.name.value.trim(), sport: gform.sport.value, metric: gform.metric.value,
      period: gform.period.value, target: Number(gform.target.value),
      start: gform.period.value === "custom" ? gform.start.value : "",
      end: gform.period.value === "custom" ? gform.end.value : "",
    },
  });
  goalDialog.close();
  toast("Ziel gespeichert");
  refreshSidebar();
}

async function refreshStatus() {
  const s = state.connected = await api("/api/status");
  const names = { garmin: "Garmin", intervals: "intervals.icu → Wahoo", zwift: "Zwift", google: "Google Kalender" };
  $("#status").innerHTML = Object.entries(names)
    .map(([k, l]) => `<span class="pill ${s[k] ? "on" : ""}" title="${l}: ${s[k] ? "verbunden" : "nicht eingerichtet – siehe README"}">${s[k] ? "●" : "○"}<span class="pill-label"> ${l}</span></span>`)
    .join("");
}

async function refreshFromGarmin() {
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
    refreshSidebar();
  }
}

// ---------------------------------------------------------------- Diagramme
// Liniendiagramm mit einer y-Achse. series: [{name, color, points: [{x, y, tip}], dots, line, dashed}]
// x: "time" (ISO-Datum) oder "log" (Sekunden, Leistungskurve). refs: waagrechte Bezugslinien [{y, label}].
function chart({ series, x = "time", yFormat = (v) => Math.round(v), refs = [], height = 220 }) {
  const W = 640, H = height, L = 44, R = 12, T = 12, B = 26;
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) return `<p class="muted small">Noch keine Daten.</p>`;
  const xv = (p) => (x === "time" ? new Date(p.x).getTime() : Math.log(p.x));
  const ys = [...pts.map((p) => p.y), ...refs.map((r) => r.y)];
  // runde Achsenwerte: Schrittweite 1/2/5 × 10^n, Bereich auf ganze Schritte erweitert
  const raw = (Math.max(...ys) - Math.min(...ys)) / 4 || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * mag).find((v) => v >= raw);
  const y0 = Math.floor(Math.min(...ys) / step) * step, y1 = Math.ceil(Math.max(...ys) / step) * step;
  const [x0, x1] = [Math.min(...pts.map(xv)), Math.max(...pts.map(xv))];
  const sx = (v) => L + ((v - x0) / (x1 - x0 || 1)) * (W - L - R);
  const sy = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let out = "";
  for (let v = y0; v <= y1 + step / 2; v += step) {  // dezente Gitterlinien + y-Beschriftung
    out += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/>
      <text x="${L - 6}" y="${sy(v) + 4}" class="tick" text-anchor="end">${yFormat(v)}</text>`;
  }
  const xticks = x === "log"
    ? [[5, "5 s"], [30, "30 s"], [60, "1 min"], [300, "5 min"], [1200, "20 min"], [3600, "1 h"], [7200, "2 h"]]
      .filter(([d]) => Math.log(d) >= x0 && Math.log(d) <= x1).map(([d, l]) => [Math.log(d), l])
    : Array.from({ length: 5 }, (_, i) => x0 + ((x1 - x0) * i) / 4)
      .map((t) => [t, new Date(t).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })]);
  for (const [v, label] of xticks) out += `<text x="${sx(v)}" y="${H - 8}" class="tick" text-anchor="middle">${label}</text>`;
  for (const r of refs) {
    out += `<line x1="${L}" x2="${W - R}" y1="${sy(r.y)}" y2="${sy(r.y)}" class="ref"/>
      <text x="${W - R}" y="${sy(r.y) - 4}" class="tick" text-anchor="end">${r.label}</text>`;
  }
  for (const s of series) {
    const p = [...s.points].sort((a, b) => xv(a) - xv(b));
    if (s.line !== false && p.length > 1) {
      out += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round"
        ${s.dashed ? 'stroke-dasharray="5 4"' : ""} points="${p.map((q) => `${sx(xv(q))},${sy(q.y)}`).join(" ")}"/>`;
    }
    for (const q of p) {  // sichtbarer Punkt + größere unsichtbare Trefferfläche mit Tooltip
      if (s.dots) out += `<circle cx="${sx(xv(q))}" cy="${sy(q.y)}" r="3.5" fill="${s.color}" stroke="var(--panel)" stroke-width="1.5"/>`;
      out += `<circle cx="${sx(xv(q))}" cy="${sy(q.y)}" r="9" fill="transparent"><title>${q.tip || `${s.name}: ${yFormat(q.y)}`}</title></circle>`;
    }
  }
  const legend = series.length > 1
    ? `<div class="chart-legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("")}</div>` : "";
  return `${legend}<svg class="chart" viewBox="0 0 ${W} ${H}">${out}</svg>`;
}

const fmtTime = (sec) => {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.round(sec % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
};
const fmtDuration = (d) => (d < 60 ? `${d} s` : d < 3600 ? `${d / 60} min` : `${d / 3600} h`);
const tile = (label, value, sub = "") => `<div class="tile"><span class="label">${label}</span><b>${value ?? "–"}</b>${sub ? `<span class="muted small">${sub}</span>` : ""}</div>`;

// ---------------------------------------------------------------- Analyse
const analysisDialog = $("#analysis-dialog");

async function openAnalysis(refresh = false) {
  analysisDialog.showModal();
  $("#analysis-body").innerHTML = `<p class="muted">Lade Daten …</p>`;
  try {
    state.analysis = await api(`/api/analysis${refresh ? "?refresh=1" : ""}`);
    showAnalysisTab(state.analysisTab || "metrics");
  } catch (e) {
    $("#analysis-body").innerHTML = `<p class="warn">⚠︎ ${e.message}</p>`;
  }
}

function showAnalysisTab(tab) {
  state.analysisTab = tab;
  analysisDialog.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const d = state.analysis;
  $("#analysis-body").innerHTML = { metrics: metricsTab, power: powerTab, ef: efTab, zones: zonesTab, race: raceTab }[tab](d);
  if (tab === "race") bindRaceTab();
}

function metricsTab(d) {
  const g = d.garmin;
  if (!g) return `<p class="muted">Garmin-Kennzahlen nicht verfügbar${d.garmin_error ? `: ${d.garmin_error}` : " (Garmin nicht verbunden)"}.</p>`;
  const st = g.training_status, s = state.settings, pred = g.race_predictions || {};
  const cssNote = g.css ? `Garmin ${secToPace(g.css.css)} (${fmtDate(g.css.at.slice(0, 10), { day: "2-digit", month: "2-digit", year: "2-digit" })}) · eingestellt ${secToPace(s.css)}` : "";
  return `
    <div class="tiles">
      ${tile("Trainingsstatus", st?.label, st ? `Akut ${st.acute_load} / chronisch ${st.chronic_load} · Verhältnis ${st.ratio}` : "")}
      ${tile("VO2max Laufen", g.vo2max?.run?.toFixed(1))}
      ${tile("VO2max Rad", g.vo2max?.ride?.toFixed(1))}
      ${tile("Endurance Score", g.endurance?.current)}
      ${tile("Hitzeanpassung", g.heat_acclimation != null ? `${g.heat_acclimation} %` : null, "steigt mit Hitzetraining")}
      ${tile("CSS Schwimmen", g.css ? `${secToPace(g.css.css)} /100 m` : null, cssNote)}
    </div>
    <h3>Renn-Prognosen Laufen (Garmin)</h3>
    <div class="tiles">${["5K", "10K", "HalfMarathon", "Marathon"].map((k) =>
      tile({ HalfMarathon: "Halbmarathon" }[k] || k, pred[k] ? fmtTime(pred[k]) : null)).join("")}</div>
    <h3>Endurance Score</h3>
    ${chart({ series: [{ name: "Endurance Score", color: "var(--accent)", dots: true,
      points: (g.endurance?.series || []).map((p) => ({ x: p.date, y: p.value, tip: `Woche ab ${fmtDate(p.date)}: ${p.value}` })) }] })}
    <h3>FTP-Verlauf Rad (Garmin) <span class="label">Garmin-Einträge aus Tests, automatischer Erkennung und Änderungen</span></h3>
    ${chart({ series: [{ name: "FTP", color: "var(--ride)", dots: true, line: false,
      points: g.ftp_series.map((p) => ({ x: p.date, y: p.value, tip: `${fmtDate(p.date)}: ${p.value} W` })) }],
      refs: [{ y: s.ftp, label: `eingestellt ${s.ftp} W` }] })}
    <h3>VO2max (90 Tage)</h3>
    ${chart({ series: [
      { name: "Laufen", color: "var(--run)", points: g.vo2max_series.filter((p) => p.run).map((p) => ({ x: p.date, y: p.run, tip: `Laufen ${fmtDate(p.date)}: ${p.run}` })) },
      { name: "Rad", color: "var(--ride)", points: g.vo2max_series.filter((p) => p.ride).map((p) => ({ x: p.date, y: p.ride, tip: `Rad ${fmtDate(p.date)}: ${p.ride}` })) },
    ], yFormat: (v) => v.toFixed(0) })}
    <p class="muted small">Stand: ${d.garmin_at ? new Date(d.garmin_at).toLocaleString("de-DE") : "–"} · Garmin-Werte werden 6 h zwischengespeichert.</p>`;
}

function powerTab(d) {
  const pc = d.power_curve;
  const pts = (list, label) => list.map((p) => ({ x: p.duration, y: p.watts,
    tip: `${label} ${fmtDuration(p.duration)}: ${p.watts} W (${fmtDate(p.date)}, ${p.name})` }));
  return `
    <div class="tiles">
      ${tile("FTP eingestellt", `${pc.ftp} W`)}
      ${pc.estimates.map((e) => tile(e.method, `${e.watts} W`, `${e.watts >= pc.ftp ? "+" : ""}${e.watts - pc.ftp} W zur Einstellung`)).join("")}
    </div>
    ${chart({ x: "log", height: 260, series: [
      { name: "Letzte 365 Tage", color: "var(--muted)", dots: true, points: pts(pc.year, "365 Tage") },
      { name: "Letzte 90 Tage", color: "var(--accent)", dots: true, points: pts(pc.recent, "90 Tage") },
    ], refs: [{ y: pc.ftp, label: `FTP ${pc.ftp} W` }] })}
    <p class="muted small">Beste Durchschnittsleistung je Dauer aus allen Radeinheiten (Garmin-Zusammenfassung).
      Die Schätzungen nutzen nur die letzten 90 Tage – ohne echte Maximaltests fallen sie eher zu niedrig aus.</p>`;
}

function efTab(d) {
  const block = (sport, label, color, digits) => {
    const e = d.efficiency[sport];
    const points = e.points.map((p) => ({ x: p.date, y: p.ef, tip: `${fmtDate(p.date)} ${p.name}: ${p.ef.toFixed(digits)}` }));
    // gleitender 28-Tage-Mittelwert als Trendlinie
    const trend = points.map((p) => {
      const t = new Date(p.x).getTime();
      const win = points.filter((q) => { const u = new Date(q.x).getTime(); return u <= t && u > t - 28 * 864e5; });
      return { x: p.x, y: win.reduce((a, q) => a + q.y, 0) / win.length, tip: `28-Tage-Mittel: ${(win.reduce((a, q) => a + q.y, 0) / win.length).toFixed(digits)}` };
    });
    const trendText = e.trend == null ? "zu wenig Daten" : `${e.trend > 0 ? "+" : ""}${e.trend} % (28 Tage vs. davor)`;
    return `<h3>${label} <span class="label">${e.unit}</span></h3>
      <div class="tiles">${tile("Trend", trendText)}${tile("Einheiten", e.points.length, "locker & gleichmäßig")}</div>
      ${chart({ yFormat: (v) => v.toFixed(digits), series: [
        { name: "Einzelne Einheiten", color, dots: true, line: false, points },
        { name: "28-Tage-Mittel", color: "var(--text)", points: trend },
      ] })}`;
  };
  return `<p class="muted small">Efficiency Factor = Leistung (Rad: NP) bzw. steigungsbereinigtes Tempo (Laufen) pro Herzschlag.
      Steigt er bei lockeren Einheiten, wächst die aerobe Grundlage. Nur lockere, mindestens 45 (Rad) bzw. 30 min (Laufen)
      lange Einheiten zählen. Hitze, Schlaf und Koffein verfälschen einzelne Werte – auf den Trend achten.</p>
    ${block("ride", "Rad", "var(--ride)", 2)}${block("run", "Laufen", "var(--run)", 2)}`;
}

// ---------------------------------------------------------------- Renntag
// Alle Annahmen hier als Standardwerte – im Tab änderbar und in settings.race_plan gespeichert.
const RACE_DEFAULTS = {
  swim_km: 3.8, bike_km: 180, run_km: 42.2, bike_hm: 0,
  swim_offset: 5,        // s/100 m langsamer als CSS (lange Strecke, Massenstart)
  wetsuit: true,         // Neopren: ca. 3 s/100 m schneller
  bike_if: 0.70,         // Ironman-Rad: IF 0,65–0,75 je nach Leistungsniveau
  cda: 0.25, crr: 0.004, bike_kg: 9,
  run_pct: 82,           // % der Schwellengeschwindigkeit (Ironman-Marathon ≈ 80–85 %)
  t1: 6, t2: 4,          // Wechsel in Minuten
  temp: 25,              // erwartete Temperatur °C
  carbs_bike: 90, carbs_run: 60,   // g Kohlenhydrate pro Stunde
  sodium: 800,           // mg Natrium pro Liter
};

// Geschwindigkeit (m/s) auf flacher Strecke für eine Leistung – Luftwiderstand + Rollwiderstand, 97,6 % Antrieb
function bikeSpeed(watts, cda, crr, mass) {
  let lo = 1, hi = 25;
  for (let i = 0; i < 50; i++) {
    const v = (lo + hi) / 2;
    const need = (0.5 * 1.2 * cda * v ** 3 + crr * mass * 9.81 * v) / 0.976;
    if (need > watts) hi = v; else lo = v;
  }
  return lo;
}

function racePlan(p, st) {
  const weight = st.weight || 75;
  const fluid = p.temp >= 25 ? 900 : p.temp >= 20 ? 700 : 500;  // ml pro Stunde
  // Schwimmen: CSS + Zuschlag, Neopren schneller
  const swimPace = st.css + p.swim_offset - (p.wetsuit ? 3 : 0);
  const swimSec = (p.swim_km * 1000 / 100) * swimPace;
  // Rad: Ziel-NP = IF × FTP; Zeit aus Flachgeschwindigkeit + Kletterarbeit (30 % kommt bergab zurück)
  const watts = Math.round(p.bike_if * st.ftp);
  const mass = weight + Number(p.bike_kg);
  const v = bikeSpeed(watts, p.cda, p.crr, mass);
  const bikeSec = (p.bike_km * 1000) / v + (mass * 9.81 * p.bike_hm * 0.7) / watts;
  // Laufen: % der Schwellengeschwindigkeit
  const runPace = st.threshold_pace / (p.run_pct / 100);
  const runSec = p.run_km * runPace;
  const legs = [
    { name: "Schwimmen", target: `${secToPace(swimPace)} /100 m`, detail: `CSS ${secToPace(st.css)} + ${p.swim_offset} s${p.wetsuit ? " − 3 s Neo" : ""}`,
      sec: swimSec, carbs: 0, fluid: 0 },
    { name: "Wechsel 1", target: "", detail: "", sec: p.t1 * 60, carbs: 0, fluid: 0 },
    { name: "Rad", target: `${watts} W NP`, detail: `IF ${p.bike_if} · ${(v * 3.6).toFixed(1)} km/h flach · ${Math.round(watts / weight * 10) / 10} W/kg`,
      sec: bikeSec, carbs: p.carbs_bike, fluid },
    { name: "Wechsel 2", target: "", detail: "", sec: p.t2 * 60, carbs: 0, fluid: 0 },
    { name: "Laufen", target: `${secToPace(runPace)} /km`, detail: `${p.run_pct} % der Schwelle (${secToPace(st.threshold_pace)})`,
      sec: runSec, carbs: p.carbs_run, fluid: Math.round(fluid * 0.8) },
  ];
  for (const l of legs) {
    const h = l.sec / 3600;
    Object.assign(l, { carbsTotal: Math.round(l.carbs * h), fluidTotal: Math.round(l.fluid * h),
      sodiumTotal: Math.round((l.fluid * h / 1000) * p.sodium) });
  }
  return { legs, total: legs.reduce((a, l) => a + l.sec, 0), weight, fluid };
}

function raceTab() {
  const st = state.settings;
  const p = { ...RACE_DEFAULTS, ...(st.race_plan || {}) };
  const field = (key, label, attrs = 'step="any"') =>
    `<label>${label} <input type="number" name="${key}" value="${p[key]}" ${attrs}></label>`;
  return `
    <p class="muted small">Planung für ${st.goal_name || "den Wettkampf"}${st.goal_date ? ` am ${fmtDate(st.goal_date, { day: "2-digit", month: "2-digit", year: "numeric" })}` : ""}.
      Basis: deine Schwellen (FTP ${st.ftp} W, Schwelle ${secToPace(st.threshold_pace)}/km, CSS ${secToPace(st.css)}/100 m)${st.weight ? `, Gewicht ${st.weight} kg` : ""}.
      Alle Werte sind Schätzungen – im Training testen und anpassen.</p>
    <div id="race-form" class="grid race-grid">
      ${field("swim_km", "Schwimmen (km)")}${field("bike_km", "Rad (km)")}${field("run_km", "Laufen (km)")}
      ${field("bike_hm", "Höhenmeter Rad (laut Veranstalter)", 'step="10"')}${field("swim_offset", "Schwimmen: s/100 m über CSS")}
      <label class="inline"><input type="checkbox" name="wetsuit" ${p.wetsuit ? "checked" : ""}> Neoprenanzug</label>
      ${field("bike_if", "Rad-Intensität (IF)", 'step="0.01" min="0.5" max="0.85"')}${field("cda", "CdA (m²)", 'step="0.005"')}
      ${field("crr", "Rollwiderstand Crr", 'step="0.0005"')}${field("bike_kg", "Rad + Ausrüstung (kg)")}
      ${field("run_pct", "Laufen: % der Schwelle", 'step="1" min="70" max="95"')}
      ${field("t1", "Wechsel 1 (min)")}${field("t2", "Wechsel 2 (min)")}${field("temp", "Temperatur (°C)")}
      ${field("carbs_bike", "KH Rad (g/h)", 'step="5"')}${field("carbs_run", "KH Laufen (g/h)", 'step="5"')}
      ${field("sodium", "Natrium (mg/l)", 'step="50"')}
    </div>
    <div id="race-result"></div>`;
}

function renderRaceResult() {
  const p = { ...RACE_DEFAULTS };  // Eingaben liegen in einem div (Formulare dürfen nicht verschachtelt werden)
  for (const el of $("#race-form").querySelectorAll("input")) p[el.name] = el.type === "checkbox" ? el.checked : Number(el.value);
  const r = racePlan(p, state.settings);
  const sum = (k) => r.legs.reduce((a, l) => a + l[k], 0);
  $("#race-result").innerHTML = `
    <table class="race-table">
      <tr><th>Abschnitt</th><th>Ziel</th><th>Zeit</th><th>Kohlenhydrate</th><th>Flüssigkeit</th><th>Natrium</th></tr>
      ${r.legs.map((l) => `<tr><td><b>${l.name}</b><div class="muted small">${l.detail}</div></td><td>${l.target}</td>
        <td>${fmtTime(l.sec)}</td><td>${l.carbs ? `${l.carbs} g/h · ${l.carbsTotal} g` : ""}</td>
        <td>${l.fluid ? `${l.fluid} ml/h · ${(l.fluidTotal / 1000).toFixed(1)} l` : ""}</td>
        <td>${l.sodiumTotal ? `${l.sodiumTotal} mg` : ""}</td></tr>`).join("")}
      <tr class="total"><td>Gesamt</td><td></td><td>${fmtTime(r.total)}</td><td>${sum("carbsTotal")} g</td>
        <td>${(sum("fluidTotal") / 1000).toFixed(1)} l</td><td>${sum("sodiumTotal")} mg</td></tr>
    </table>
    <h3>Vorbereitung</h3>
    <ul class="notes">
      <li><b>Carbo-Loading</b> die 2 Tage vor dem Rennen: ${Math.round(r.weight * 8)}–${Math.round(r.weight * 10)} g Kohlenhydrate pro Tag (8–10 g/kg), ballaststoffarm.</li>
      <li><b>Frühstück</b> 3 h vor dem Start: ca. ${Math.round(r.weight * 1.5)} g Kohlenhydrate (1–2 g/kg), gewohnte Lebensmittel.</li>
      <li><b>Verpflegung testen</b>: ${p.carbs_bike} g/h auf dem Rad in den langen Einheiten üben – der Magen muss das lernen.</li>
      ${p.temp >= 25 ? `<li><b>Hitze</b>: ${r.fluid} ml/h eingeplant, Natrium eher an der oberen Grenze. Hitzeakklimatisierung läuft in den 6 Wochen vorher.</li>` : ""}
      <li>Die Radzeit ist eine Flachstrecken-Schätzung plus Kletterarbeit. Für deinen Wettkampf die Höhenmeter laut Veranstalter eintragen.</li>
    </ul>`;
  return p;
}

let raceSaveTimer;
function bindRaceTab() {
  renderRaceResult();
  $("#race-form").oninput = () => {
    const p = renderRaceResult();
    clearTimeout(raceSaveTimer);  // Eingaben gesammelt speichern
    raceSaveTimer = setTimeout(async () => {
      state.settings = await api("/api/settings", { method: "PUT", body: { race_plan: p } });
    }, 800);
  };
}

function zonesTab(d) {
  const max = Math.max(1, ...d.zones.map((w) => w.zones.reduce((a, b) => a + b, 0)));
  const bars = d.zones.map((w) => {
    const total = w.zones.reduce((a, b) => a + b, 0);
    return `<div class="zweek">
      <div class="zstack" style="height:${(total / max) * 100}%">${w.zones.map((z, i) => z ? `<span style="flex:${z};background:${ZONE_COLORS[i]}"
        title="KW ${isoWeek(w.week_start)} · Zone ${i + 1}: ${fmtMin(z)}"></span>` : "").reverse().join("")}</div>
      <b class="small">${w.low_pct != null ? `${w.low_pct} %` : "–"}</b>
      <span class="muted small">KW ${isoWeek(w.week_start)}</span></div>`;
  }).join("");
  return `<p class="muted small">Zeit in Pulszonen (Schwimmen, Rad, Laufen) pro Woche. Die Zahl unter jedem Balken ist der
      Anteil locker (Zone 1–2). Für Ironman-Vorbereitung sind ~80 % locker ein guter Richtwert.</p>
    <div class="chart-legend">${ZONE_COLORS.map((c, i) => `<span><i style="background:${c}"></i>Zone ${i + 1}</span>`).join("")}</div>
    <div class="zchart">${bars}</div>`;
}

// ---------------------------------------------------------------- Feedback zu Aktivitäten
const feedbackDialog = $("#feedback-dialog");
const fform = $("#feedback-form");

function fillFeedbackOptions(root) {
  root.querySelectorAll('select[name="rpe"]').forEach((el) => (el.innerHTML = `<option value="">–</option>` +
    RPE_LABEL.map((l, i) => `<option value="${i}">${i} – ${l}</option>`).join("")));
  root.querySelectorAll('select[name="feel"]').forEach((el) => (el.innerHTML = `<option value="">–</option>` +
    Object.entries(FEEL_LABEL).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")));
}

function openFeedback(a, plan, dayWorkouts = []) {
  state.activity = a;
  const link = a.feedback?.plan_link;
  $("#feedback-plan-select").innerHTML = [
    `<option value="">Automatisch${link === undefined ? ` (${plan ? plan.name : "keins erkannt"})` : ""}</option>`,
    ...dayWorkouts.map((w) => `<option value="${w.id}">${escapeHtml(w.name)} (${fmtMin(w.duration)})</option>`),
    `<option value="0">Gehört zu keinem Plan</option>`,
  ].join("");
  $("#feedback-plan-select").value = link ?? "";
  $("#btn-open-plan").hidden = !plan;
  $("#btn-open-plan").onclick = () => { feedbackDialog.close(); openDetail(plan); };
  const m = a.metrics || {};
  const facts = [
    [SPORT_LABEL[a.sport] || a.sport, a.date.split("-").reverse().join(".")],
    ["Dauer", fmtMin(a.duration)],
    a.distance ? ["Distanz", `${(a.distance / 1000).toFixed(a.sport === "swim" ? 2 : 1)} km`] : null,
    ["TSS", Math.round(a.tss)],
    m.avg_hr ? ["Ø Puls", `${Math.round(m.avg_hr)} bpm`] : null,
    m.np ? ["NP", `${Math.round(m.np)} W`] : null,
    efficiency(a) ? ["EF", efficiency(a).toFixed(2)] : null,
  ].filter(Boolean);
  $("#feedback-title").textContent = a.name;
  $("#feedback-facts").innerHTML = facts.map(([k, v]) => `<div><span class="label">${k}</span><b>${v}</b></div>`).join("");
  $("#feedback-zones").innerHTML = m.hr_zones ? zoneBar(m.hr_zones) : "";
  const fb = a.feedback || {};
  fform.rpe.value = fb.rpe ?? "";
  fform.feel.value = fb.feel ?? "";
  fform.note.value = fb.note || "";
  feedbackDialog.showModal();
}

async function saveFeedbackPlanLink() {
  const value = $("#feedback-plan-select").value;
  await api(`/api/activities/${encodeURIComponent(state.activity.id)}/plan`, {
    method: "PUT", body: { workout_id: value === "" ? null : Number(value) },
  });
}

async function saveFeedback() {
  const body = {
    rpe: fform.rpe.value === "" ? null : Number(fform.rpe.value),
    feel: fform.feel.value === "" ? null : Number(fform.feel.value),
    note: fform.note.value.trim(),
  };
  await api(`/api/activities/${encodeURIComponent(state.activity.id)}/feedback`, { method: "PUT", body });
  await saveFeedbackPlanLink();
  feedbackDialog.close();
  toast("Feedback gespeichert");
  refreshSidebar();
}

// Efficiency Factor: NP bzw. steigungsbereinigtes Tempo (m/min) pro Herzschlag – wie app/analysis.py
function efficiency(a) {
  const m = a.metrics || {};
  if (!m.avg_hr) return null;
  if (a.sport === "ride" && m.np) return m.np / m.avg_hr;
  if (a.sport === "run" && (m.gap || m.speed)) return ((m.gap || m.speed) * 60) / m.avg_hr;
  return null;
}

// Gestapelter Balken: Zeit in Pulszone 1–5
const ZONE_COLORS = ["#94a3b8", "#3b82f6", "#22c55e", "#f97316", "#ef4444"];
function zoneBar(zones) {
  const total = zones.reduce((a, b) => a + b, 0) || 1;
  return `<div class="zonebar">${zones.map((z, i) => z ? `<span style="flex:${z};background:${ZONE_COLORS[i]}"
    title="Zone ${i + 1}: ${fmtMin(z)} (${Math.round((z / total) * 100)} %)">${z / total > 0.08 ? `Z${i + 1}` : ""}</span>` : "").join("")}</div>`;
}

// ---------------------------------------------------------------- Plan-Import
const planDialog = $("#plan-dialog");
const pform = $("#plan-form");

// Nächster Montag (heute, falls heute Montag ist) – wie plan_import.default_start
function nextMonday() {
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function openPlanImport() {
  pform.start.value = nextMonday();
  delete pform.start.dataset.touched;
  $("#plan-preview").innerHTML = "";
  $("#btn-plan-import").disabled = true;
  planDialog.showModal();
}

function planBody() {
  let plan;
  try {
    plan = JSON.parse($("#plan-json").value);
  } catch (e) {
    throw new Error(`Kein gültiges JSON: ${e.message}`);
  }
  return { plan, start: pform.start.value || null, replace: pform.replace.checked };
}

function planChanged() {
  $("#btn-plan-import").disabled = true;
  $("#plan-preview").innerHTML = "";
}

async function checkPlan() {
  try {
    const body = planBody();
    // Startdatum aus dem Plan übernehmen, solange keins von Hand gewählt wurde
    if (body.plan.start && !pform.start.dataset.touched) body.start = pform.start.value = body.plan.start;
    const res = await api("/api/plan/preview", { method: "POST", body });
    renderPlanPreview(res);
    $("#btn-plan-import").disabled = false;
    $("#btn-plan-import").textContent = `${res.workouts.length} Workouts importieren`;
  } catch (e) {
    $("#plan-preview").innerHTML = `<p class="warn">⚠︎ ${e.message}</p>`;
    $("#btn-plan-import").disabled = true;
  }
}

function renderPlanPreview(res) {
  const hours = res.workouts.reduce((sum, w) => sum + w.duration, 0) / 3600;
  const byWeek = {};
  for (const w of res.workouts) (byWeek[`KW ${isoWeek(w.date)}`] ||= []).push(w);
  const weekday = (iso) => new Date(iso).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  $("#plan-preview").innerHTML = `
    <p><b>${res.workouts.length} Workouts</b> · ${fmtDate(res.start)} – ${fmtDate(res.end)} · ${fmtHours(hours)} gesamt</p>
    ${res.existing ? `<p class="warn small">Im Zeitraum sind schon ${res.existing} geplante Workouts.
      ${pform.replace.checked ? "Sie werden ersetzt (auch auf den Geräten)." : "Sie bleiben zusätzlich bestehen."}</p>` : ""}
    <div class="plan-weeks">${Object.entries(byWeek).map(([week, list]) => `
      <div class="plan-week">
        <div class="row-between"><b>${week}</b><span class="muted small">${fmtHours(list.reduce((s, w) => s + w.duration, 0) / 3600)}</span></div>
        ${list.map((w) => `<div class="plan-item"><span class="muted">${weekday(w.date)}</span>
          <span><span class="dot" style="background:${sportColor(w.sport)}"></span>${w.name}</span>
          <span class="muted">${fmtMin(w.duration)} · ${Math.round(w.tss)} TSS</span></div>`).join("")}
      </div>`).join("")}</div>`;
}

async function importPlan() {
  const res = await api("/api/plan/import", { method: "POST", body: planBody() });
  planDialog.close();
  toast(`${res.created} Workouts importiert${res.removed ? `, ${res.removed} ersetzt` : ""}` +
    (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""), res.errors.length ? 10000 : 4000);
  calendar.gotoDate(res.start);
  refreshSidebar();
}

// Beim Öffnen die letzten 14 Tage nachladen, damit Wochenstunden und Ziele aktuell sind
async function autoImport() {
  const st = await api("/api/status");
  const sources = ["garmin", "intervals"].filter((s) => st[s]);
  for (const s of sources) await api(`/api/import/${s}?days=14`, { method: "POST" });
  if (sources.length) refreshSidebar();
}

// ---------------------------------------------------------------- Start
async function main() {
  [state.settings, state.templates, state.raceTypes] = await Promise.all([
    api("/api/settings"), api("/api/templates"), api("/api/race-types"),
  ]);
  initCalendar();
  initSidebarToggle();
  await refreshStatus().catch(() => {});
  if (!state.settings.setup_done) openSetup();
  refreshSidebar().catch((e) => toast(e.message));
  refreshFromGarmin().catch((e) => toast(e.message, 6000));
  autoImport().catch((e) => toast(`Import: ${e.message}`, 6000));

  $("#btn-new").onclick = () => openEditor({ date: new Date().toISOString().slice(0, 10) });
  $("#btn-settings").onclick = openSettings;
  $("#btn-open-setup").onclick = () => { settingsDialog.close(); openSetup(); };
  $("#btn-setup-garmin").onclick = withBusy($("#btn-setup-garmin"), connectGarmin);
  $("#btn-setup-save").onclick = withBusy($("#btn-setup-save"), () => saveSetup(true));
  $("#btn-setup-skip").onclick = withBusy($("#btn-setup-skip"), () => saveSetup(false));
  $("#setup-garmin-login").onkeydown = (e) => {  // Enter in den Garmin-Feldern = verbinden (nicht Dialog schließen)
    if (e.key === "Enter") { e.preventDefault(); $("#btn-setup-garmin").click(); }
  };
  $("#btn-save-settings").onclick = withBusy($("#btn-save-settings"), saveSettings);
  $("#btn-import").onclick = withBusy($("#btn-import"), async () => {
    const st = await api("/api/status");
    const sources = ["garmin", "intervals"].filter((s) => st[s]);
    if (!sources.length) return toast("Weder Garmin noch intervals.icu verbunden – siehe README.", 6000);
    let total = 0;
    for (const s of sources) total += (await api(`/api/import/${s}?days=365`, { method: "POST" })).imported;
    toast(`${total} Aktivitäten (365 Tage) importiert`);
    refreshSidebar();
  });
  $("#suggestions").onclick = (e) => {
    const i = e.target.dataset.accept;
    if (i !== undefined) withBusy(e.target, () => acceptSuggestion(state.suggestions[i]))();
  };
  $("#btn-accept-all").onclick = withBusy($("#btn-accept-all"), async () => {
    for (const s of state.suggestions.filter((s) => s.workout)) {
      await api("/api/workouts", { method: "POST", body: { ...s.workout, date: s.date } });
    }
    toast("Vorschläge in den Kalender übernommen");
    refreshSidebar();
  });

  fillFeedbackOptions(document);
  bindCircuitTimer();
  $("#btn-add-race").onclick = withBusy($("#btn-add-race"), addRace);
  $("#btn-bulk-google").onclick = withBusy($("#btn-bulk-google"), async () => {
    const res = await api("/api/sync/bulk", { method: "POST", body: { target: "google" } });
    toast(`${res.sent} Workouts an Google Kalender gesendet` + (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""),
      res.errors.length ? 10000 : 4000);
    refreshSidebar();
  });
  $("#race-type").onchange = $("#race-priority").onchange = renderRaceTypeHint;
  $("#races").onclick = async (e) => {
    if (!e.target.dataset.race) return;
    await api(`/api/races/${e.target.dataset.race}`, { method: "DELETE" });
    renderRaces();
    refreshSidebar();
  };
  $("#btn-analysis").onclick = () => openAnalysis();
  $("#btn-analysis-refresh").onclick = () => openAnalysis(true);
  analysisDialog.querySelector(".tabs").onclick = (e) => e.target.dataset.tab && showAnalysisTab(e.target.dataset.tab);
  $("#btn-save-feedback").onclick = withBusy($("#btn-save-feedback"), saveFeedback);

  $("#conflicts").onclick = (e) => {
    const id = e.target.dataset.fix;
    if (id) withBusy(e.target, () => fixConflicts([Number(id)]))();
  };
  $("#btn-fix-all").onclick = withBusy($("#btn-fix-all"), async () => {
    if (!confirm(`${state.conflicts.length} Workouts wie vorgeschlagen anpassen? Bereits übertragene Workouts werden auch auf den Geräten geändert.`)) return;
    await fixConflicts(state.conflicts.map((c) => c.workout_id));
  });

  $("#btn-plan").onclick = openPlanImport;
  $("#plan-json").oninput = planChanged;
  pform.start.onchange = () => { pform.start.dataset.touched = "1"; planChanged(); };
  pform.replace.onchange = () => $("#plan-preview").innerHTML && checkPlan();
  $("#plan-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    $("#plan-json").value = await file.text();
    e.target.value = "";
    checkPlan();
  };
  $("#btn-plan-example").onclick = async () => {
    $("#plan-json").value = await (await fetch("/static/plan-example.json")).text();
    checkPlan();
  };
  $("#btn-plan-check").onclick = withBusy($("#btn-plan-check"), checkPlan);
  $("#btn-plan-import").onclick = withBusy($("#btn-plan-import"), importPlan);

  $("#btn-add-goal").onclick = () => openGoal({});
  $("#goals").onclick = (e) => {
    const li = e.target.closest("[data-goal]");
    if (li) openGoal(state.goals[li.dataset.goal]);
  };
  gform.period.onchange = toggleGoalRange;
  $("#btn-save-goal").onclick = withBusy($("#btn-save-goal"), saveGoal);
  $("#btn-delete-goal").onclick = withBusy($("#btn-delete-goal"), async () => {
    await api(`/api/goals/${state.goal.id}`, { method: "DELETE" });
    goalDialog.close();
    toast("Ziel gelöscht");
    refreshSidebar();
  });

  $("#pattern").onchange = (e) => {
    const { day, i, field } = e.target.dataset;
    if (!field) return;
    state.pattern[day][i][field] = e.target.value;
    if (field === "sport") renderPattern();
  };
  $("#pattern").onclick = (e) => {
    const { add, day, remove } = e.target.dataset;
    if (add) (state.pattern[add] ||= []).push({ type: "easy", sport: "ride" });
    else if (remove !== undefined) state.pattern[day].splice(Number(remove), 1);
    else return;
    renderPattern();
  };

  $("#btn-template").onclick = async () => {
    const t = await api(`/api/templates/${$("#tpl-kind").value}?sport=${form.sport.value}&minutes=${$("#tpl-min").value}`);
    Object.assign(state.current, { steps: t.steps, template: t.template, target: t.target, circuit: t.circuit });
    if (!form.name.value || form.name.value === "Neues Workout") form.name.value = t.name;
    if (!form.description.value) form.description.value = t.description;
    form.target.value = t.target;
    renderSteps();
  };
  $("#btn-add-step").onclick = () => { state.current.steps.push({ kind: "steady", duration: 600, low: 65, high: 75 }); renderSteps(); };
  $("#btn-add-repeat").onclick = () => {
    state.current.steps.push({ kind: "repeat", count: 4, steps: [
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
    await api(`/api/workouts/${state.current.id}`, { method: "DELETE" });
    editor.close();
    toast("Gelöscht");
    refreshSidebar();
  });
}

main();
