// Zirkel-Timer für Kraft/Stabi: Belastung/Pause, Runden, Wiederholungen bis „Fertig“, Ton und Ansage.
import { $, api, dataChanged, meta, toast, withBusy } from "./core.js";
import { openEditor, readForm } from "./editor.js";
import { fmtTime } from "./format.js";

const timerDialog = $("#timer-dialog");
const tform = $("#timer-form");
const CIRCUIT_DEFAULT = { work: 40, rest: 20, rounds: 3, round_rest: 60, exercises: [] };
const PHASE_LABEL = { prep: "Gleich geht's los", work: "Los!", rest: "Pause", round: "Rundenpause" };
const PREP_SECONDS = 10;
const timer = { workout: null, circuit: null, phases: [], index: 0, start: 0, end: 0, left: 0, paused: false, tick: null,
                lastSec: null, lock: null, audio: null, startedAt: 0, pausedAt: 0, pausedMs: 0 };

// Kleine Merkhilfe pro Browser (Ton/Ansage, letzter freier Timer) – darf fehlen
const timerPrefs = {
  get() { try { return JSON.parse(localStorage.getItem("timer") || "{}"); } catch { return {}; } },
  set(p) { try { localStorage.setItem("timer", JSON.stringify({ ...this.get(), ...p })); } catch { /* egal */ } },
};

const clamp = (value, [lo, hi]) => Math.min(hi, Math.max(lo, value));

// Übung: {name, reps?, seconds?}; ältere Zirkel speichern nur den Namen. Wiederholungen ohne Zahl: reps 0.
// Eingabe eine pro Zeile, Kurzform hinter dem letzten „|“: „12 Wdh“, „Wdh“ oder „45 s“ (wie plan_import.py)
const exerciseOf = (e) => (typeof e === "string" ? { name: e } : e);
const repsLabel = (reps) => (reps ? `${reps} Wdh` : "Wdh");
const exerciseLine = (e) => e.name + ("reps" in e ? ` | ${repsLabel(e.reps)}` : e.seconds ? ` | ${e.seconds} s` : "");
function parseExerciseLine(line) {
  const bar = line.lastIndexOf("|"), tail = line.slice(bar + 1).trim(), name = line.slice(0, bar).trim();
  const reps = tail.match(/^(\d*)\s*(wdh\.?|wiederholungen|reps?|x)$/i), secs = tail.match(/^(\d+)\s*(s|sek\.?|sekunden)$/i);
  if (bar < 0 || !name || !(reps || secs)) return { name: line };
  const limits = meta.exercise_limits;
  return reps ? { name, reps: clamp(Number(reps[1]) || 0, limits.reps) } : { name, seconds: clamp(Number(secs[1]), limits.seconds) };
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
  for (const [key, limits] of Object.entries(meta.circuit_limits)) {
    c[key] = clamp(Math.round(Number(tform[key].value) || 0), limits);
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

// Ohne Workout: freier Timer mit den zuletzt benutzten Einstellungen
export function openCircuit(workout = null) {
  const prefs = timerPrefs.get();
  timer.workout = workout;
  const c = workout ? circuitFor(workout) : { ...CIRCUIT_DEFAULT, ...prefs.circuit };
  for (const key of Object.keys(meta.circuit_limits)) tform[key].value = c[key];
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

// Das Workout des Timers speichern (aus dem Editor oder der Detailansicht gestartet), danach im Editor öffnen
async function saveCircuitDone() {
  const res = await api("/api/workouts", { method: "POST", body: { ...timer.workout, status: "done" } });
  timerDialog.close();
  openEditor(res.workout);  // offen lassen für RPE / Befinden
  toast("Als erledigt gespeichert – RPE und Befinden kannst du noch eintragen");
  dataChanged();
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

export function bindTimer() {
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
