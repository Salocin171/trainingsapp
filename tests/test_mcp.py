"""MCP-Server: Tools gegen die echte API."""
import pytest

from app import db, templates


def test_mcp_server_tools(tmp_path, monkeypatch):
    """MCP-Tools gegen die echte API (TestClient + temporäre DB) statt gegen die laufende App."""
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from app import mcp_server
    from app.main import app

    db.set_db_path(tmp_path / "mcp.db")
    client = TestClient(app)

    def fake_api(method, path, text=False, **kwargs):
        r = client.request(method, path, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(r.json().get("detail"))
        return r.text if text else r.json()

    monkeypatch.setattr(mcp_server, "_api", fake_api)
    call = lambda name, args: json.loads(asyncio.run(mcp_server.server.call_tool(name, args)).content[0].text)  # noqa: E731

    tools = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"get_status", "get_calendar", "create_workout", "import_plan", "set_activity_feedback"} <= tools

    created = call("create_workout", {"date": "2027-03-02", "sport": "ride", "name": "Schwelle 4x8", "steps": [
        {"kind": "warmup", "minutes": 15, "low": 50, "high": 75},
        {"repeat": 4, "steps": [{"kind": "interval", "minutes": 8, "low": 97, "high": 102},
                                {"kind": "recovery", "minutes": 4, "low": 50, "high": 55}]}]})
    wid = created["workout"]["id"]
    assert created["workout"]["minutes"] == 15 + 4 * 12
    assert call("update_workout", {"workout_id": wid, "rpe": 7, "note": "zäh"})["workout"]["rpe"] == 7
    assert [w["id"] for w in call("get_calendar", {"start": "2027-03-01", "end": "2027-03-07"})["workouts"]] == [wid]
    assert call("create_workout", {"date": "2027-03-03", "sport": "swim", "template": "threshold", "minutes": 50})["workout"]["sport"] == "swim"
    call("update_workout", {"workout_id": wid, "circuit": {"rounds": 3, "exercises": ["Plank"]}})
    assert db.get_workout(wid)["circuit"]["rounds"] == 3
    call("delete_workout", {"workout_id": wid})
    assert wid not in [w["id"] for w in call("get_calendar", {"start": "2027-03-01", "end": "2027-03-07"})["workouts"]]
    preview = call("import_plan", {"plan": {"weeks": [{"days": {
        "mon": [{"sport": "run", "template": "endurance", "pace": "5:00"}],
        "tue": [{"sport": "ride", "name": "VO2", "time": "6:30", "steps": "w15@55-75, 5x(i4@110-118, r4@50), c10@50"}]}}]},
        "start": "2027-03-08"})
    assert preview["start"] == "2027-03-08" and preview["warnings"] == ["Woche 1 Mo, Workout 1: Feld 'pace' unbekannt – ignoriert"]
    assert preview["weeks"]["KW 10"]["workouts"][1].startswith("03-09 ride 06:30 · VO2 65′")
    res = call("import_plan", {"preview_id": preview["preview_id"]})  # Plan nicht erneut senden
    assert res["created"] == 2 and db.list_workouts("2027-03-09", "2027-03-09")[0]["name"] == "06:30 · VO2"
    with pytest.raises(Exception):  # dieselbe Vorschau ist nur einmal importierbar
        call("import_plan", {"preview_id": preview["preview_id"]})
    brief = asyncio.run(mcp_server.server.call_tool("get_plan_brief", {"start": "2027-03-15", "weeks": 2})).content[0].text
    assert "Woche 2 (ab 22.03.)" in brief and "w=Einwärmen" in brief
    short = call("create_workout", {"date": "2027-03-04", "sport": "run", "steps": "w10@70-80, 3x(i6@97-101, r2@65), c10@65",
                                    "time": "18:00", "fueling": {"during": "0–30 g/h"}})
    assert short["workout"]["minutes"] == 44 and short["workout"]["name"].startswith("18:00 · ")
    assert call("update_settings", {"values": {"week_hours": 10}}) == {"week_hours": 10}


def test_mcp_conflict_tools(tmp_path, monkeypatch):
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from app import mcp_server
    from app.main import app

    db.set_db_path(tmp_path / "mcpconf.db")
    db.save_race({"name": "10 km Silvesterlauf", "date": "2027-12-31", "priority": "C", "race_type": "run_10k"})
    w = db.save_workout({"date": "2027-12-30", "status": "planned", **templates.build("vo2max", "run", 50)})
    client = TestClient(app)
    monkeypatch.setattr(mcp_server, "_api", lambda m, p, **kw: client.request(m, p, **kw).json())
    call = lambda name, args: json.loads(asyncio.run(mcp_server.server.call_tool(name, args)).content[0].text)  # noqa: E731
    found = call("check_race_conflicts", {})  # eine Liste mit einem Eintrag kommt als einzelnes Objekt an
    assert (found if isinstance(found, dict) else found[0])["workout_id"] == w["id"]
    call("resolve_race_conflicts", {"workout_ids": [w["id"]]})
    assert db.get_workout(w["id"])["template"] == "endurance"
