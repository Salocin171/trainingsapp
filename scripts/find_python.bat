@echo off
rem Sucht ein installiertes Python und legt es in PY ab (fuer Trainingsapp.bat, Update.bat, Autostart.bat).
rem Die Version prueft scripts\launcher.py (ab 3.12; sonst sucht er ueber "py" eine neuere oder hilft beim Installieren).
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if defined PY exit /b 0
echo.
echo Fuer die Trainingsapp wird Python 3.12 oder neuer gebraucht.
echo 1. Auf der Seite, die sich gleich oeffnet, "Download Python" klicken und den Installer starten.
echo 2. Im Installer unten "Add python.exe to PATH" anhaken, dann "Install Now".
echo 3. Danach diese Datei noch einmal doppelklicken.
start "" "https://www.python.org/downloads/windows/"
echo.
pause
exit /b 1
