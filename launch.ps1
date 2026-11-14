Start-Process cmd.exe -ArgumentList "/k cd /d D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend && D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"
Start-Sleep -Seconds 3
Start-Process cmd.exe -ArgumentList "/k cd /d D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\frontend && npm run dev"
Write-Host "Both servers starting..."
