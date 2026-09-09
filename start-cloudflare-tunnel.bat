@echo off
title Vignesh GrowthLab ERP - Cloudflare Public Demo Tunnel
color 0B

echo.
echo ============================================================
echo   Vignesh GrowthLab ERP - Cloudflare Public Demo Tunnel
echo ============================================================
echo.
echo Starting Cloudflare Tunnel on http://127.0.0.1:5173...
echo.
echo When the URL appears below, copy the https://....trycloudflare.com link
echo and send it to your client along with their credentials!
echo.
echo Press Ctrl+C anytime to stop the public demo.
echo ============================================================
echo.

"D:\BOOMERM\cloudflared.exe" tunnel --url http://127.0.0.1:5173
pause
