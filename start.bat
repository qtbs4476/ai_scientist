@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   AI Scientist Mock Fullstack
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建 Python 虚拟环境...
    py -3.11 -m venv .venv 2>nul
    if errorlevel 1 (
        python -m venv .venv
    )
)

echo [2/3] 安装/检查依赖...
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements.txt

echo [3/3] 启动服务...
echo.
echo 浏览器地址: http://127.0.0.1:8899
echo 关闭此窗口即可停止服务。
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8899"
python -m uvicorn src.app:app --host 127.0.0.1 --port 8899

pause
