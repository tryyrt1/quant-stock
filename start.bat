@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================
echo   AI 量化选股系统 - 启动
echo ======================================
echo 正在检查依赖...
pip install flask requests jieba -q
echo.
python server.py
pause
