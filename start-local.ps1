# Restart the native PostgreSQL development database and backend configured locally.
# Run the frontend separately with: cd frontend; npm run dev
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$postgresDirectory = 'C:\Program Files\PostgreSQL\17\bin'
$databaseDirectory = Join-Path $projectDirectory '.local\postgres-dev\data'
$pythonExecutable = Join-Path $projectDirectory 'backend\.venv\Scripts\python.exe'
$backendPort = 8001

if (!(Test-Path (Join-Path $databaseDirectory 'PG_VERSION'))) {
    throw 'Local development database is missing. Follow the README setup instructions.'
}

& (Join-Path $postgresDirectory 'pg_isready.exe') -h 127.0.0.1 -p 55432 -q
if ($LASTEXITCODE -ne 0) {
    Start-Process -FilePath (Join-Path $postgresDirectory 'postgres.exe') `
        -ArgumentList '-D .local/postgres-dev/data -h 127.0.0.1 -p 55432' `
        -WorkingDirectory $projectDirectory -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $projectDirectory '.local\postgres-dev\stdout.log') `
        -RedirectStandardError (Join-Path $projectDirectory '.local\postgres-dev\server.log')
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & (Join-Path $postgresDirectory 'pg_isready.exe') -h 127.0.0.1 -p 55432 -q
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start. Check .local/postgres-dev/server.log.' }
}

Push-Location (Join-Path $projectDirectory 'backend')
try {
    & $pythonExecutable -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }

    $backendReady = $false
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$backendPort/health" -TimeoutSec 5
        $backendReady = $health.status -eq 'ok' -and $health.database -eq 'ok'
    } catch {
        $backendReady = $false
    }
    if ($backendReady) {
        Write-Host 'Backend and database are already healthy.'
    } else {
        & $pythonExecutable -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort
    }
} finally {
    Pop-Location
}
