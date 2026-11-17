try { $r = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -ErrorAction Stop; Write-Host "Frontend: OK ($($r.StatusCode))" } catch { Write-Host "Frontend: FAIL" }
try { $r = Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -ErrorAction Stop; Write-Host "Backend: OK ($($r.StatusCode))" } catch { Write-Host "Backend: FAIL" }
