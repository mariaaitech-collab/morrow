Start-Process cmd -ArgumentList '/k cd /d "D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend" & .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000'
Start-Sleep -Seconds 2
Start-Process cmd -ArgumentList '/k cd /d "D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\frontend" & npm run dev'
Write-Output "Both servers launching..."
Write-Output "Waiting for startup..."
Start-Sleep -Seconds 8
try { $f = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -ErrorAction SilentlyContinue; Write-Output "Frontend: $($f.StatusCode)" } catch { Write-Output "Frontend: FAIL" }
try { $b = Invoke-WebRequest -Uri 'http://localhost:8000' -UseBasicParsing -ErrorAction SilentlyContinue; Write-Output "Backend: $($b.StatusCode)" } catch { Write-Output "Backend: FAIL" }
