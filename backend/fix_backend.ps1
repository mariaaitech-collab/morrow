# Kill any existing python processes on port 8000
# Then start fresh
$backendProc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID }
if ($backendProc) {
    $backendProc | Stop-Process -Force
    Write-Output "Killed existing python processes"
}
Start-Sleep -Seconds 2

# Start backend fresh
Start-Process cmd -ArgumentList '/k cd /d "D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend" & .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000'
Start-Sleep -Seconds 5

# Check
try { $b = Invoke-WebRequest -Uri 'http://localhost:8000' -UseBasicParsing -ErrorAction SilentlyContinue; Write-Output "Backend: $($b.StatusCode)" } catch { Write-Output "Backend: FAIL" }
try { $f = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -ErrorAction SilentlyContinue; Write-Output "Frontend: $($f.StatusCode)" } catch { Write-Output "Frontend: FAIL" }
