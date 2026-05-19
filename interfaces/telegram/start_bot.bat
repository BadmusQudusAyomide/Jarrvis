@echo off
echo Starting Jarvis Telegram Bot...
cd /d "%~dp0\..\.."
python interfaces\telegram\bot.py
pause
