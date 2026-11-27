@echo off
rem Windows: Doppelklick startet die Trainingsapp und oeffnet sie im Browser. Beenden: Fenster schliessen oder Strg+C.
rem (Mac: Trainingsapp.command)
cd /d "%~dp0"
call scripts\find_python.bat || exit /b 1
%PY% scripts\launcher.py start %* & exit /b
