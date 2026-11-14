Start-Job -Name "backend" -ScriptBlock { cd "D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend"; & ".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 }
Start-Sleep -Seconds 2
Start-Job -Name "frontend" -ScriptBlock { cd "D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\frontend"; npm run dev }
Start-Sleep -Seconds 10
try { $f = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -ErrorAction Stop; Write-Output "Frontend: $($f.StatusCode)" } catch { Write-Output "Frontend: FAIL" }
try { $b = Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -ErrorAction Stop; Write-Output "Backend: $($b.StatusCode)" } catch { Write-Output "Backend: FAIL" }
Get-Job | Format-Table Name, State, HasMoreData
