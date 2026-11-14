# Start the BrandAura backend (uvicorn, port 8000) and frontend (Vite, port 5173),
# each in its own window. Everything runs on localhost (see APP_BASE_URL in backend/.env).
# Usage, from the repo root:  .\start_servers.ps1
# To stop a server, close its window (or press Ctrl+C in it).
$root = $PSScriptRoot

function Test-Listening($port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# Skip a server that is already up, so running this twice never starts a duplicate.
# cmd /k keeps the window open if the server crashes, so the error stays readable.
if (Test-Listening 8000) {
    Write-Host "Backend is already running on port 8000; not starting another."
} else {
    Start-Process cmd.exe -WorkingDirectory "$root\backend" -ArgumentList '/k title BrandAura backend 8000 && .venv\Scripts\python.exe -m uvicorn main:app --port 8000'
}
if (Test-Listening 5173) {
    Write-Host "Frontend is already running on port 5173; not starting another."
} else {
    Start-Process cmd.exe -WorkingDirectory "$root\frontend" -ArgumentList '/k title BrandAura frontend 5173 && npm run dev'
}

Write-Host "Waiting for both servers..."
for ($i = 0; $i -lt 60 -and -not ((Test-Listening 8000) -and (Test-Listening 5173)); $i++) {
    Start-Sleep -Seconds 1
}

$be = if (Test-Listening 8000) { "up" } else { "NOT up - check the backend window" }
$fe = if (Test-Listening 5173) { "up" } else { "NOT up - check the frontend window" }
Write-Host ""
Write-Host "Frontend: http://localhost:5173  ($fe)"
Write-Host "Backend:  http://localhost:8000  ($be)   health: http://localhost:8000/api/health"
