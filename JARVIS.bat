@echo off
chcp 65001 >nul 2>&1
title JARVIS ULTIMATE
cd /d "%~dp0"
echo ========================================
echo   JARVIS ULTIMATE - Запуск...
echo ========================================
echo.
python jarvis_eel.py
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Программа завершилась с ошибкой.
    echo Нажмите любую клавишу для выхода...
    pause >nul
)
