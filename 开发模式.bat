@echo off
chcp 65001 >nul
cd /d %~dp0
echo [开发模式] 后端 :8000 + 前端热更新 :5173
start "chatkb-backend" /min cmd /c "python backend\main.py"
cd frontend
start "chatkb-vite" cmd /k "npm run dev"
timeout /t 4 >nul
start http://127.0.0.1:5173
