@echo off
cd /d "D:\Websites\fyp-brandaura\Brandora (2)\Brandora\backend"
.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
