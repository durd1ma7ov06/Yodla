@echo off
title Sozla AI Telegram Bot
color 0b
echo ==================================================
echo           SOZLA AI TELEGRAM BOT
echo ==================================================
echo.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [XATO] Virtual muhit topilmadi!
    pause
    exit /b
)

echo [OK] Bot ishga tushirilmoqda...
.\venv\Scripts\python main.py
pause

