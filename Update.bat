@echo off
rem Windows: Doppelklick holt die neueste Version von GitHub. Deine Daten (Ordner data\ und %USERPROFILE%\.trainingsapp)
rem bleiben unveraendert. Funktioniert auch, wenn die App als ZIP heruntergeladen wurde. (Mac: Update.command)
cd /d "%~dp0"
call scripts\find_python.bat || exit /b 1
rem Alles in einer Zeile: das Update darf diese Datei ersetzen, waehrend sie laeuft
%PY% scripts\launcher.py update %* & exit /b
