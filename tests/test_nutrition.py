"""Verpflegung vor, während und nach einer Einheit."""

from app import nutrition
from app.workouts import repeat, step

from helpers import SETTINGS


FUEL_SETTINGS = {**SETTINGS, "weight": 80, "goal_date": "2027-06-27"}


def _ride(name, minutes, pct, date_="2026-11-22", **extra):
    return {"date": date_, "sport": "ride", "name": name, "target": "power",
            "steps": [step("steady", minutes, pct)], **extra}


def test_nutrition_scales_with_weight_and_session():
    long_ride = _ride("Rad lang Z2", 210, 70)
    n = nutrition.plan(long_ride, FUEL_SETTINGS)
    assert n["kind"] == "long"
    assert n["phases"]["before"]["carbs"] == {"low": 160, "high": 240, "unit": "g", "per_kg": (2, 3)}
    assert (n["phases"]["during"]["carbs"]["low"], n["phases"]["during"]["carbs"]["high"]) == (90, 90)  # Grundlage
    # 12 Wochen vor dem Rennen: Darmtraining in Renndosis
    late = nutrition.plan({**long_ride, "date": "2027-04-20"}, FUEL_SETTINGS)
    assert (late["phases"]["during"]["carbs"]["low"], late["phases"]["during"]["carbs"]["high"]) == (100, 120)

    easy_run = {"date": "2026-11-24", "sport": "run", "name": "Lauf locker", "steps": [step("steady", 45, 75)]}
    assert nutrition.plan(easy_run, FUEL_SETTINGS)["phases"]["during"]["carbs"]["high"] == 0
    short_vo2 = _ride("VO2", 60, 70) | {"steps": [step("warmup", 15, 55, 70), repeat(5, step("interval", 4, 112),
                                                                                     step("recovery", 3, 50)),
                                                  step("cooldown", 10, 50)]}
    n = nutrition.plan(short_vo2, FUEL_SETTINGS)
    assert n["kind"] == "quality" and n["phases"]["during"]["carbs"]["high"] == 30
    assert n["phases"]["before"]["carbs"]["per_kg"] == (1, 2)


def test_nutrition_context_brick_early_start_and_fast_refuel():
    ride = _ride("Rad lang Z2", 180, 70, id=1)
    brick = {"id": 2, "date": "2026-11-22", "sport": "run", "name": "Koppellauf 5 km", "steps": [step("steady", 30, 80)]}
    n_ride = nutrition.plan(ride, FUEL_SETTINGS, [ride, brick])
    assert "Koppellauf" in n_ride["phases"]["after"]["hint"]
    n_brick = nutrition.plan(brick, FUEL_SETTINGS, [ride, brick])
    assert n_brick["kind"] == "brick" and n_brick["phases"]["before"]["carbs"] is None
    assert n_brick["phases"]["during"]["carbs"]["high"] == 90

    morning = _ride("07:00 · Rad Z2", 90, 68, id=3)
    evening = _ride("13:00 · Rad Sweet Spot", 90, 90, id=4)
    n = nutrition.plan(morning, FUEL_SETTINGS, [morning, evening])
    assert n["start"] == "07:00" and n["end"] == "08:30"
    assert n["phases"]["before"]["carbs"]["per_kg"] == (0.5, 1)          # früher Start
    assert n["phases"]["after"]["carbs"]["unit"] == "g/h"                # Qualität in < 8 h → schnell auffüllen
    assert n["phases"]["during"]["carbs"]["high"] == 90                  # locker vor harter Folgeeinheit


def test_nutrition_prefers_numbers_from_plan_text():
    desc = ("Z2.\n\nKH (80 kg):\n- Vorher: 0,5–1 g/kg (45–85 g) 60–90 min vorher.\n"
            "- Während: bis 90 min 60 g/h, danach 90 g/h.\n"
            "- Danach: Mahlzeit mit 85–130 g KH + 30–40 g Protein; Tagesziel 6–10 g/kg (510–850 g).")
    n = nutrition.plan(_ride("Rad", 150, 70, description=desc), FUEL_SETTINGS)
    ph = n["phases"]
    assert (ph["before"]["carbs"]["low"], ph["before"]["carbs"]["high"], ph["before"]["source"]) == (45, 85, "plan")
    assert (ph["during"]["carbs"]["low"], ph["during"]["carbs"]["high"]) == (60, 90)
    assert (ph["after"]["carbs"]["low"], ph["after"]["carbs"]["high"]) == (85, 130)
    assert (ph["after"]["protein"]["low"], ph["after"]["protein"]["high"]) == (30, 40)
    assert ph["during"]["plan_text"].startswith("bis 90 min") and ph["during"]["hint"] == ""
    assert n["day"]["per_kg"] == (6, 10) and n["day"]["source"] == "plan"


def test_nutrition_fluid_from_sweat_rate():
    ride = _ride("Rad", 120, 70)
    unknown = nutrition.plan(ride, FUEL_SETTINGS)
    assert unknown["phases"]["during"]["fluid"]["unit"] == "ml/h" and unknown["phases"]["after"]["fluid"] is None
    n = nutrition.plan(ride, {**FUEL_SETTINGS, "sweat_rate": 1.5})
    fluid = n["phases"]["during"]["fluid"]
    # 80 kg, 2 h: 2 % = 1,6 l → 1,5 − 0,8 = 0,7 l/h; 1 % → 1,1 l/h; nie mehr als die Schweißrate
    assert (fluid["low"], fluid["high"]) == (700, 1100)
    assert n["phases"]["after"]["fluid"]["low"] > 0
