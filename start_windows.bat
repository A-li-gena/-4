@echo off
echo ========================================
echo    Workers System - Windows Launcher
echo ========================================

echo.
echo 1. Проверяем MongoDB...

REM Проверяем, запущен ли MongoDB
tasklist /fi "imagename eq mongod.exe" | find /i "mongod.exe" >nul
if errorlevel 1 (
    echo ❌ MongoDB не запущен. Запускаем...
    
    REM Пытаемся запустить как службу Windows
    net start MongoDB 2>nul
    if errorlevel 1 (
        echo ⚠️  Служба MongoDB не найдена. Попробуйте запустить вручную:
        echo    mongod.exe --dbpath C:\data\db
        echo.
    ) else (
        echo ✅ MongoDB запущен как служба
    )
) else (
    echo ✅ MongoDB уже запущен
)

echo.
echo 2. Устанавливаем зависимости Python...
pip install -r requirements.txt

echo.
echo 3. Запускаем Workers System...
echo 🚀 Сервер будет доступен по адресу: http://localhost:8001
echo 📱 Telegram бот будет активен (если настроен токен)
echo.

python server_fixed.py

pause