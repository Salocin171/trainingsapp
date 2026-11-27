// Bezeichnungen und feste Zuordnungen der Oberfläche.

export const SPORT_LABEL = {
  swim: "Schwimmen", ride: "Rad", run: "Laufen", strength: "Stabi / Kraft", mobility: "Dehnen / Yoga", other: "Sonstiges",
};
export const KIND_LABEL = {
  warmup: "Einwärmen", interval: "Intervall", recovery: "Erholung", steady: "Konstant", cooldown: "Ausfahren",
};
export const SUGGESTION_LABEL = { rest: "Ruhetag", race: "Wettkampf" };
export const WEEKDAYS = [["mon", "Mo"], ["tue", "Di"], ["wed", "Mi"], ["thu", "Do"], ["fri", "Fr"], ["sat", "Sa"], ["sun", "So"]];
export const SLOT_TYPES = { recovery: "Regeneration", easy: "Locker", hard: "Hart", long: "Lang" };

export const DEFAULT_TARGET = { ride: "power", run: "pace", swim: "pace" };
// Ziel je Schritt (überschreibt das Ziel des Workouts): kurze Namen für die Auswahl im Schritt
export const TARGET_SHORT = { power: "Watt", pace: "Pace", hr: "Puls" };
export const TARGETS_FOR = { ride: ["power", "hr"], run: ["pace", "hr", "power"], swim: ["pace", "hr"] };

// Anstrengung (modifizierte Borg-Skala 0–10, wie TrainingPeaks) und Befinden 1–5
export const RPE_LABEL = ["Ruhe", "sehr, sehr leicht", "leicht", "moderat", "etwas schwer", "schwer", "schwer+",
  "sehr schwer", "sehr schwer+", "extrem schwer", "maximal"];
export const FEEL_LABEL = { 1: "😫 sehr schlecht", 2: "🙁 schlecht", 3: "😐 normal", 4: "🙂 gut", 5: "💪 sehr gut" };
export const COMPLIANCE_LABEL = { green: "im Plan", yellow: "etwas daneben", orange: "deutlich daneben", red: "verpasst" };

export const ZONE_COLORS = ["#94a3b8", "#3b82f6", "#22c55e", "#f97316", "#ef4444"];  // Pulszone 1–5
export const TIMER_SPORTS = ["strength", "mobility", "other"];  // Sportarten mit Zirkel-Timer
