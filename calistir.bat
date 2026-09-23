@echo off
title Site Of Book - GitHub Guncelleme
cd /d "%~dp0"

echo ==============================
echo   GitHub'a gonderiliyor...
echo ==============================
echo.

git add .
git commit -m "Vercel Flask duzeltmeleri"
git push

echo.
echo ==============================
echo   TAMAMLANDI!
echo ==============================
pause
