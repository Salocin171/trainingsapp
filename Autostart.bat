@echo off
rem Windows: Trainingsapp als Hintergrunddienst einrichten - startet beim Anmelden ohne Fenster und nach einem
rem Absturz neu. Entfernen: "Autostart.bat off" in der Eingabeaufforderung. (Mac: autostart.command)
cd /d "%~dp0"
call scripts\find_python.bat || exit /b 1
%PY% scripts\launcher.py autostart %* & exit /b
