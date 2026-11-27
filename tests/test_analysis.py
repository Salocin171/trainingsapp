"""Efficiency Factor (Watt/Tempo bei Referenzpuls)."""
from datetime import date

import pytest


def test_ef_series_skips_mixed_and_off_intensity_rides():
    from app import analysis

    def ride(day, np_, avg_power, hr, zones=(0, 3600, 0, 0, 0), **extra):
        return {"date": f"2026-11-{day:02d}", "sport": "ride", "name": f"R{day}", "duration": 7200,
                "metrics": {"np": np_, "avg_power": avg_power, "avg_hr": hr, "hr_zones": list(zones), **extra}}

    acts = [
        ride(1, 250, 248, 145),                                # gleichmäßige Grundlage → zählt
        ride(2, 300, 250, 148, zones=(0, 2500, 400, 700, 0)),  # 1 h Intervalle + 1 h locker → hohe NP, niedriger Puls
        ride(3, 280, 240, 135),                                # Kurzintervalle ohne Puls in Z4 → VI zu hoch
        ride(4, 160, 159, 125),                                # Ausrollen < 45 % FTP
        ride(5, 320, 318, 160),                                # Schwelle ≥ 80 % FTP
        ride(6, 250, 247, 140, anaerobic_te=2.1),              # Antritte laut Garmin
        ride(7, 250, 236, 140, indoor=True),                   # Rolle: VI 1,06 > 1,05
        ride(8, 240, 238, 142, event_type="race"),
    ]
    e = analysis.ef_series(acts, date(2026, 11, 25), ftp=385)["ride"]
    assert [p["name"] for p in e["points"]] == ["R1"]
    reasons = {x["name"]: x["reason"] for x in e["excluded"]}
    assert set(reasons) == {"R2", "R3", "R4", "R5", "R6", "R7", "R8"}
    assert "ungleichmäßig" in reasons["R3"] and "ungleichmäßig" in reasons["R7"]
    assert "zu locker" in reasons["R4"] and "zu intensiv" in reasons["R5"]
    assert "anaerob" in reasons["R6"] and reasons["R8"] == "Wettkampf"
    assert e["np_range"] == [173, 308] and e["ref_hr"] == 145


def test_ef_series_normalizes_to_reference_hr_and_detects_bricks():
    from app import analysis

    # gleiche Form: Puls = 80 + 0,25 × Watt → bei jedem Puls dieselbe Leistung beim Referenzpuls
    rides = [{"date": f"2026-11-{d:02d}", "sport": "ride", "name": "R", "duration": 5400,
              "metrics": {"np": w, "avg_power": w, "avg_hr": 80 + 0.25 * w, "hr_zones": [0, 3600, 0, 0, 0],
                          "start_time": f"2026-11-{d:02d} 08:00:00"}}
             for d, w in zip(range(1, 13), (200, 220, 240, 260, 280, 210, 230, 250, 270, 205, 245, 265))]
    run = {"date": "2026-11-05", "sport": "run", "name": "Koppel", "duration": 1800,
           "metrics": {"avg_hr": 150, "gap": 3.0, "hr_zones": [0, 1800, 0, 0, 0], "start_time": "2026-11-05 09:40:00"}}
    r = analysis.ef_series(rides + [run], date(2026, 11, 25), ftp=385)
    assert abs(r["ride"]["slope"] - 0.25) < 0.01
    at_ref = {p["at_ref"] for p in r["ride"]["points"]}
    assert max(at_ref) - min(at_ref) < 1                   # Intensität herausgerechnet
    assert r["run"]["excluded"][0]["reason"].startswith("Koppellauf")


def test_ef_series_scales_with_performance_level():
    """Halbe Watt bei halber FTP und gleichem Puls → gleiche Einheiten zählen, Steigung doppelt so steil."""
    from app import analysis

    def rides(factor):
        return [{"date": f"2026-11-{d:02d}", "sport": "ride", "name": f"R{d}", "duration": 5400,
                 "metrics": {"np": w * factor, "avg_power": w * factor, "avg_hr": hr, "hr_zones": [0, 3600, 0, 0, 0]}}
                for d, (w, hr) in enumerate(((200, 130), (230, 140), (260, 146), (215, 137), (245, 141)), start=1)]

    strong = analysis.ef_series(rides(1), date(2026, 11, 25), ftp=385)["ride"]
    weak = analysis.ef_series(rides(0.5), date(2026, 11, 25), ftp=192.5)["ride"]
    assert len(strong["points"]) == len(weak["points"]) == 5
    assert weak["slope"] == pytest.approx(2 * strong["slope"], abs=0.002)  # zu wenig Paare → Standard, skaliert mit FTP
    assert weak["slope"] == pytest.approx(110 / 192.5, abs=0.001)
    assert [p["at_ref"] for p in weak["points"]] == pytest.approx([p["at_ref"] / 2 for p in strong["points"]], abs=0.1)
