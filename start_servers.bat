@echo off
cd /d "%~dp0backend"
start "Brandora Backend" ".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
cd /d "%~dp0frontend"
start "Brandora Frontend" cmd /k "npm run dev"
echo Servers started!
echo Frontend: http://localhost:5173
echo Backend: http://localhost:8000
