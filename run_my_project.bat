@echo off
TITLE Saurabh Tools Launcher
color 0B

echo ==========================================
echo    SAURABH TOOLS PROJECT LAUNCHER
echo ==========================================

:: 1. Backend Setup Check
echo [1/3] Checking Backend (API)...
cd /d "%~dp0api"
if not exist "venv" (
    echo Creating Python Virtual Environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing/Updating Backend Dependencies...
pip install fastapi uvicorn pymongo google-genai pillow requests python-multipart

:: 2. Frontend Setup Check
echo [2/3] Checking Frontend (Web)...
cd /d "%~dp0web"
if not exist "node_modules" (
    echo Installing Node.js Dependencies (This may take a minute)...
    call npm install
)

:: 3. Launching both servers
echo [3/3] Launching Servers...

:: Start Backend in a new window
start "BACKEND - FastAPI" cmd /k "cd /d %~dp0api && venv\Scripts\activate && uvicorn app:app --reload --port 8000"

:: Start Frontend in a new window
start "FRONTEND - Next.js" cmd /k "cd /d %~dp0web && npm run dev"

echo.
echo SUCCESS! Both windows are opening now.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
pause