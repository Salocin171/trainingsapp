// Seitenleiste: Form (CTL/ATL/TSB), aktueller Block, Wochenstunden, Ziele, Konflikte und Vorschläge.
import { $, api, dataChanged, reportSync, state, toast, withBusy } from "./core.js";
import { refetchEvents, setBlockColor, setCycleStart, updateCalendarSize } from "./calendar.js";
import { escapeHtml, fmtDate, fmtHours, fmtMin, isoWeek, sportColor, todayIso } from "./format.js";
import { renderGoals } from "./goals.js";
import { SPORT_LABEL, SUGGESTION_LABEL } from "./labels.js";
import { workoutStats } from "./workout.js";

export function initSidebarToggle() {
  const apply = (hidden) => {
    document.body.classList.toggle("no-aside", hidden);
    $("#btn-sidebar").setAttribute("aria-pressed", String(!hidden));
    updateCalendarSize();
  };
  try { apply(localStorage.getItem("sidebarHidden") === "1"); } catch { /* egal */ }
  $("#btn-sidebar").onclick = () => {
    const hidden = !document.body.classList.contains("no-aside");
    apply(hidden);
    try { localStorage.setItem("sidebarHidden", hidden ? "1" : "0"); } catch { /* egal */ }
  };
}

export async function refreshSidebar() {
  const [rec, series, weeks, goals, clashes] = await Promise.all([
    api("/api/recommendations"), api("/api/load?days=90"), api("/api/weeks"), api("/api/goals"), api("/api/conflicts"),
  ]);
  renderConflicts(clashes);
  const st = rec.status;
  $("#m-ctl").textContent = Math.round(st.ctl);
  $("#m-atl").textContent = Math.round(st.atl);
  $("#m-tsb").textContent = Math.round(st.tsb);
  $("#m-form").textContent = `${st.form} · Rampe ${st.ramp > 0 ? "+" : ""}${st.ramp} CTL/Woche`;
  $("#warnings").innerHTML = st.warnings.map((w) => `<li class="warn">⚠︎ ${escapeHtml(w)}</li>`).join("")
    + st.hints.map((h) => `<li>${escapeHtml(h)}</li>`).join("");
  drawLoadChart(series);
  renderBlock(st);
  renderWeeks(weeks);
  renderGoals(goals);
  renderSuggestions(rec.days);
  refetchEvents();
}

// Aktueller Block, Zeitleiste bis zum Wettkampf, Position im Belastungszyklus
function renderBlock(st) {
  const w = st.week;
  const start = w.cycle_week ? new Date(`${w.week_start}T00:00`) : null;
  start?.setDate(start.getDate() - (w.cycle_week - 1) * 7);
  setCycleStart(start?.toLocaleDateString("sv-SE") || null);
  $("#block-title").textContent = w.block_week ? `${w.block_name} · Woche ${w.block_week}/${w.block_weeks}` : w.block_name;
  $("#race-countdown").textContent = st.days_to_goal != null
    ? `${st.goal_name || "Wettkampf"} in ${w.weeks_to_race} Wo (${st.days_to_goal} Tage)` : "";

  const today = todayIso();
  const days = (a, b) => (new Date(b) - new Date(a)) / 86400000 + 1;
  const total = st.timeline.reduce((sum, b) => sum + days(b.start, b.end), 0);
  $("#block-timeline").innerHTML = st.timeline.map((b) => {
    const share = (days(b.start, b.end) / total) * 100;
    const active = b.start <= today && today <= b.end;
    const marker = active ? `<i style="left:${(days(b.start, today) / days(b.start, b.end)) * 100}%"></i>` : "";
    return `<div class="seg ${b.key} ${active ? "active" : ""}" style="flex-basis:${share}%"
      title="${escapeHtml(b.name)}: ${fmtDate(b.start)} – ${fmtDate(b.end)}"><span>${escapeHtml(b.name)}</span>${marker}</div>`;
  }).join("");

  let cycle = "";
  if (w.cycle_len && w.cycle_week) {
    cycle = Array.from({ length: w.cycle_len }, (_, i) => {
      const n = i + 1, recovery = n === w.cycle_len && (w.recovery || w.cycle_week !== w.cycle_len);
      return `<span class="${recovery ? "rec" : "load"} ${n === w.cycle_week ? "now" : ""}"
        title="${recovery ? "Entlastungswoche" : `Belastungswoche ${n}`}">${recovery ? "E" : `B${n}`}</span>`;
    }).join("");
    if (w.cycle_no) cycle = `<b class="cyc-name">Block ${w.cycle_no}</b>${cycle}`;
  }
  $("#cycle").innerHTML = cycle;
  setBlockColor($("#cycle"), { ...w, prelude: Boolean(w.cycle_starts) });

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
  $("#weeks").innerHTML = weeks.map((w, i) => {
    const pct = (h) => (h / max) * 100;
    const starts = i > 0 && w.cycle_week === 1;  // neuer Belastungszyklus: Trennlinie
    return `<div class="week ${w.current ? "current" : ""} ${starts ? "cycle-start" : ""}" data-blk="${w.block}"
      data-wk="${w.recovery ? "rec" : "load"}" ${w.cycle_color != null ? `data-cyc="${w.cycle_color}"` : ""}
      title="${w.cycle_no ? `Block ${w.cycle_no} · ` : ""}${escapeHtml(w.block_name)}${w.recovery ? " · Entlastung" : ""}">
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
  const order = Object.keys(SPORT_LABEL);
  $("#week-sports").innerHTML = current ? Object.entries(current.by_sport)
    .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
    .map(([sport, v]) => `<span><span class="dot" style="background:${sportColor(sport)}"></span>${SPORT_LABEL[sport] || escapeHtml(sport)}
      ${fmtHours(v.done)}${v.planned ? ` <span class="muted">+ ${fmtHours(v.planned)} geplant</span>` : ""}</span>`)
    .join("") : "";
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
      : `→ ${p.sport !== c.sport ? `${SPORT_LABEL[p.sport]}: ` : ""}${escapeHtml(p.name.replace(/ \(statt .*\)$/, ""))} ${fmtMin(p.duration)}`;
    return `<li>
      <div><div class="sname"><span class="dot" style="background:${sportColor(c.sport)}"></span>${day(c.date)} · ${escapeHtml(c.name)} (${c.minutes} min)</div>
        <div class="sreason">${c.race.priority}-Wettkampf ${escapeHtml(c.race.name)} · ${escapeHtml(c.phase)}: ${escapeHtml(c.problem)}<br><b>Vorschlag: ${change}</b></div></div>
      <button class="small" data-fix="${c.workout_id}">Anpassen</button>
    </li>`;
  }).join("");
}

async function fixConflicts(ids) {
  const res = await api("/api/conflicts/apply", { method: "POST", body: { workout_ids: ids } });
  toast(`${res.applied.length} Workout(s) angepasst` + (res.errors.length ? ` – Probleme: ${res.errors.join(" | ")}` : ""),
    res.errors.length ? 10000 : 4000);
  dataChanged();
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
        const first = s.date !== lastDate;
        lastDate = s.date;
        return `<li class="${first ? "first" : ""}">
          <span class="sday">${first ? s.weekday : ""}</span>
          <div><div class="sname">${dot}${escapeHtml(title)}</div>
            <div class="sreason">${meta}${meta ? "<br>" : ""}${s.reasons.map(escapeHtml).join(" · ")}</div></div>
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

export async function acceptSuggestion(s) {
  reportSync(await api("/api/workouts", { method: "POST", body: { ...s.workout, date: s.date } }));
}

export function bindSidebar() {
  $("#suggestions").onclick = (e) => {
    const i = e.target.dataset.accept;
    if (i !== undefined) withBusy(e.target, () => acceptSuggestion(state.suggestions[i]))();
  };
  $("#btn-accept-all").onclick = withBusy($("#btn-accept-all"), async () => {
    for (const s of state.suggestions.filter((s) => s.workout)) {
      await api("/api/workouts", { method: "POST", body: { ...s.workout, date: s.date } });
    }
    toast("Vorschläge in den Kalender übernommen");
    dataChanged();
  });
  $("#conflicts").onclick = (e) => {
    const id = e.target.dataset.fix;
    if (id) withBusy(e.target, () => fixConflicts([Number(id)]))();
  };
  $("#btn-fix-all").onclick = withBusy($("#btn-fix-all"), async () => {
    if (!confirm(`${state.conflicts.length} Workouts wie vorgeschlagen anpassen? Bereits übertragene Workouts werden auch auf den Geräten geändert.`)) return;
    await fixConflicts(state.conflicts.map((c) => c.workout_id));
  });
}
