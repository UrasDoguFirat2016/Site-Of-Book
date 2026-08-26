@echo off
title Vercel Proje Guncelleme

echo ==============================
echo   Vercel Projesi GitHub'a
echo   Gonderiliyor...
echo ==============================
echo.

git add .
git commit -m "PyMuPDF eklendi ve proje guncellendi"
git push

echo.
echo ==============================
echo   TAMAMLANDI!
echo ==============================
echo.
pause
