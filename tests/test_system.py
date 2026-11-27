"""Updates von GitHub und Autostart."""


def test_updater_detects_and_applies_new_commits(tmp_path, monkeypatch):
    import subprocess
    from app import config, updater

    def git(cwd, *args):
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                       capture_output=True)

    origin, upstream, local = tmp_path / "origin.git", tmp_path / "upstream", tmp_path / "local"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(upstream))
    (upstream / "app").mkdir()
    (upstream / "app" / "x.py").write_text("A = 1\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-q", "-m", "Erste Version")
    git(upstream, "push", "-q", "origin", "HEAD:main")
    git(tmp_path, "clone", "-q", str(origin), str(local))
    monkeypatch.setattr(config, "ROOT", local)

    assert updater.status(force=True)["available"] is False
    (upstream / "app" / "x.py").write_text("A = 2\n")
    git(upstream, "commit", "-qam", "Neue Funktion")
    git(upstream, "push", "-q", "origin", "HEAD:main")
    s = updater.status(force=True)
    assert s["available"] and s["behind"] == 1 and s["commits"] == ["Neue Funktion"]

    res = updater.apply()
    assert res["updated"] and res["restart_claude"] and (local / "app" / "x.py").read_text() == "A = 2\n"
    assert updater.status(force=True)["available"] is False

    monkeypatch.setattr(config, "ROOT", tmp_path / "zip-download")  # ohne .git: kein Button, Hinweis auf Update.command
    (tmp_path / "zip-download").mkdir()
    assert updater.status(force=True)["supported"] is False


def test_autostart_status_knows_the_folder(tmp_path, monkeypatch):
    import plistlib
    from app import autostart, config
    plist = tmp_path / "de.trainingsapp.plist"
    monkeypatch.setattr(autostart, "PLIST", plist)
    monkeypatch.setattr(autostart, "_service_pid", lambda: None)
    assert autostart.status()["installed"] is False
    plist.write_bytes(plistlib.dumps({"Label": "de.trainingsapp", "WorkingDirectory": str(tmp_path / "anderswo")}))
    s = autostart.status()
    assert s["installed"] and not s["this_folder"] and not s["active"]
    plist.write_bytes(plistlib.dumps({"Label": "de.trainingsapp", "WorkingDirectory": str(config.ROOT)}))
    assert autostart.status()["this_folder"]
