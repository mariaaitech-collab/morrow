try { $f = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -ErrorAction Stop; Write-Output "Frontend: $($f.StatusCode)" } catch { Write-Output "Frontend: FAIL" }
try { $b = Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -ErrorAction Stop; Write-Output "Backend: $($b.StatusCode)" } catch { Write-Output "Backend: FAIL" }
