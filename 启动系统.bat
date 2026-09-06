@echo off
chcp 65001 >nul
cd /d %~dp0
echo [聊天知识库系统] 启动后端（含前端界面）...
start "chatkb-backend" /min cmd /c "python backend\main.py"
timeout /t 4 >nul
start http://127.0.0.1:8000
echo 已在浏览器打开 http://127.0.0.1:8000
