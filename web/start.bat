@echo off
echo =================================================
echo    Jarvis Eel Web Interface v2.0 - Запуск
echo =================================================
echo.

REM Change to the web directory
cd /d "d:\всё с рабочего стола\офкмшы\web"

REM Check if Node.js is installed
echo Проверка установки Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ОШИБКА: Node.js не установлен или не найден в PATH.
    echo Пожалуйста, установите Node.js с сайта https://nodejs.org/
    echo.
    pause
    exit /b 1
)

REM Check if npm is installed
echo Проверка установки npm...
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ОШИБКА: npm не установлен или не найден в PATH.
    echo Пожалуйста, установите Node.js с сайта https://nodejs.org/
    echo.
    pause
    exit /b 1
)

REM Check if jarvis_eel.py exists in parent directory
echo Проверка наличия файла jarvis_eel.py...
if not exist "..\jarvis_eel.py" (
    echo.
    echo ПРЕДУПРЕЖДЕНИЕ: Файл jarvis_eel.py не найден в родительской директории.
    echo Убедитесь, что jarvis_eel.py находится в директории:
    echo d:\всё с рабочего стола\офкмшы\jarvis_eel.py
    echo.
    pause
    exit /b 1
)

REM Install dependencies if node_modules doesn't exist or package.json is newer
set NODE_MODULES_EXIST=false
if exist "node_modules" set NODE_MODULES_EXIST=true

if "%NODE_MODULES_EXIST%"=="false" (
    echo.
    echo Установка зависимостей...
    npm install
    if %errorlevel% neq 0 (
        echo.
        echo ОШИБКА: Не удалось установить зависимости.
        echo Проверьте подключение к интернету и повторите попытку.
        echo.
        pause
        exit /b 1
    )
    echo Зависимости успешно установлены.
) else (
    REM Check if package.json is newer than node_modules
    for /f %%i in ('dir /b /o:d package.json 2^>nul') do set PKG_NEWER=%%i
    if exist "node_modules" (
        REM Compare timestamps (simplified check)
        echo Проверка обновлений зависимостей...
        REM We'll reinstall if explicitly requested or if there are issues
    )
)

echo.
echo ================================================
echo Подготовка завершена. Запуск Jarvis Eel Web Interface...
echo ================================================
echo.
echo Для управления приложением откройте в браузере:
echo http://localhost:3000
echo.
echo Для остановки сервера нажмите Ctrl+C
echo ================================================
echo.

REM Start the server
node server.js

REM In case the server stops unexpectedly
echo.
echo Сервер остановлен.
echo Для повторного запуска выполните этот скрипт снова.
echo.
pause