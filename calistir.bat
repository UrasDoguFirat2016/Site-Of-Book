@echo off
title Sesli Kitap
cd /d "%~dp0"

echo ========================================
echo       SESLI KITAP BASLATILIYOR
echo ========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

%PY% -m pip install -r requirements.txt

echo.
echo Sunucu baslatiliyor...
start "" http://127.0.0.1:5000
%PY% app.py

pause
