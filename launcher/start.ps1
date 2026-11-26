<#
  Dealwatch desktop launcher (Windows). Started by "Start Dealwatch.bat".

  - Works from any folder: every path is relative to this script, so the
    project folder can be moved or renamed freely.
  - First run sets everything up (Python packages, React build, database).
  - Later runs only redo a step when its files changed (e.g. after you
    update the code), so upgrades are picked up automatically.
  - Data is stored in <project>\data\dealwatch.db and moves with the folder.
  - Close the window to stop Dealwatch.

  Optional settings: create backend\.env (see .env.example), e.g.
  PRICE_SOURCE=fake or CHECK_INTERVAL_HOURS=12. Port: set DEALWATCH_PORT.
#>

$ErrorActionPreference = 'Stop'
$Root     = Split-Path -Parent $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Dist     = Join-Path $Frontend 'dist'
$Data     = Join-Path $Root 'data'
$VenvDir  = Join-Path $Backend '.venv'
$VenvPy   = Join-Path $VenvDir 'Scripts\python.exe'
$Port     = if ($env:DEALWATCH_PORT) { [int]$env:DEALWATCH_PORT } else { 8765 }
$Url      = "http://localhost:$Port"

$Host.UI.RawUI.WindowTitle = 'Dealwatch'

function Write-Step($msg) { Write-Host "-> $msg" -ForegroundColor Cyan }

function Get-FilesHash([string[]]$Paths) {
    # One fingerprint for a set of files: changes when any of them changes.
    $parts = foreach ($p in $Paths) {
        if (Test-Path $p) {
            Get-ChildItem -Path $p -Recurse -File | Sort-Object FullName | ForEach-Object {
                (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
            }
        }
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($parts -join '|'))
    $sha = [Security.Cryptography.SHA256]::Create()
    return [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '')
}

function Read-Stamp($file) { if (Test-Path $file) { (Get-Content -Raw $file).Trim() } else { '' } }

function Test-Healthy {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        return $r.status -eq 'ok'
    } catch { return $false }
}

function Find-Python {
    # Prefer the Windows "py" launcher, fall back to python on PATH.
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3') },
        @{ Exe = 'python'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (Get-Command $c.Exe -ErrorAction SilentlyContinue) {
            $extra = $c.Args
            $ok = & $c.Exe @extra -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($ok -eq 'True') { return $c }
        }
    }
    throw 'Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and try again.'
}

try {
    Write-Host ''
    Write-Host '  Dealwatch - game price alerts' -ForegroundColor White
    Write-Host "  Folder: $Root" -ForegroundColor DarkGray
    Write-Host ''

    # Already running? Just open the page.
    if (Test-Healthy) {
        Write-Step "Dealwatch is already running, opening $Url"
        Start-Process $Url
        Start-Sleep -Seconds 2
        exit 0
    }

    # 1. Python virtual environment (recreated if missing or broken).
    $venvOk = (Test-Path $VenvPy) -and ((& $VenvPy -c "print('ok')" 2>$null) -eq 'ok')
    if (-not $venvOk) {
        Write-Step 'Creating Python environment (first run only)...'
        if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
        $py = Find-Python
        $pyArgs = $py.Args
        & $py.Exe @pyArgs -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }

    # 2. Python packages (reinstalled when requirements.txt changes).
    $reqFile  = Join-Path $Backend 'requirements.txt'
    $reqStamp = Join-Path $VenvDir '.dealwatch-deps'
    $reqHash  = Get-FilesHash @($reqFile)
    if ($reqHash -ne (Read-Stamp $reqStamp)) {
        Write-Step 'Installing Python packages...'
        & $VenvPy -m pip install --disable-pip-version-check -q -r $reqFile
        if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed (are you online?).' }
        Set-Content -Path $reqStamp -Value $reqHash
    }

    # 3. Web page (rebuilt when frontend source files change).
    $buildStamp = Join-Path $Dist '.dealwatch-build'
    $srcHash = Get-FilesHash @(
        (Join-Path $Frontend 'src'), (Join-Path $Frontend 'public'),
        (Join-Path $Frontend 'index.html'), (Join-Path $Frontend 'vite.config.js'),
        (Join-Path $Frontend 'package-lock.json'))
    if ($srcHash -ne (Read-Stamp $buildStamp)) {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            if (Test-Path (Join-Path $Dist 'index.html')) {
                Write-Host '   Node.js not found: using the existing web page build.' -ForegroundColor Yellow
            } else {
                throw 'Node.js is needed once to build the web page. Install it from https://nodejs.org and try again.'
            }
        } else {
            Push-Location $Frontend
            try {
                $lockStamp = Join-Path $Frontend 'node_modules\.dealwatch-lock'
                $lockHash  = Get-FilesHash @((Join-Path $Frontend 'package-lock.json'))
                if ($lockHash -ne (Read-Stamp $lockStamp)) {
                    Write-Step 'Installing web page packages...'
                    & npm ci --no-audit --no-fund --loglevel=error
                    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
                    Set-Content -Path $lockStamp -Value $lockHash
                }
                Write-Step 'Building the web page...'
                & npm run build --silent
                if ($LASTEXITCODE -ne 0) { throw 'Building the web page failed.' }
                Set-Content -Path $buildStamp -Value $srcHash
            } finally { Pop-Location }
        }
    }

    # 4. Database: create/upgrade the schema (safe to run every time).
    New-Item -ItemType Directory -Force -Path $Data | Out-Null
    $env:DATABASE_URL        = 'sqlite:///../data/dealwatch.db'   # relative to backend\
    $env:FRONTEND_DIST       = $Dist
    $env:RUN_CHECK_ON_STARTUP = 'true'
    Push-Location $Backend
    Write-Step 'Updating the database...'
    # Alembic logs to stderr; in Windows PowerShell that must not count as an error.
    $ErrorActionPreference = 'Continue'
    $migrateLog = & $VenvPy -m alembic -c alembic.ini upgrade head 2>&1 | ForEach-Object { "$_" }
    $migrateExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($migrateExit -ne 0) { throw "Database update failed:`n$($migrateLog -join "`n")" }
    $migrateLog | Where-Object { $_ -match 'Running upgrade' } | ForEach-Object { Write-Host "   $_" }

    # 5. Keep the desktop shortcut pointing at this folder (after a move).
    & (Join-Path $PSScriptRoot 'create-shortcut.ps1') -OnlyIfExists | Out-Null

    # 6. Open the browser as soon as the server answers.
    Start-Job -ArgumentList $Port, $Url -ScriptBlock {
        param($Port, $Url)
        for ($i = 0; $i -lt 60; $i++) {
            try { Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1 | Out-Null; Start-Process $Url; return } catch { Start-Sleep -Milliseconds 500 }
        }
    } | Out-Null

    Write-Host ''
    Write-Host "  Dealwatch is running at $Url" -ForegroundColor Green
    Write-Host '  Close this window to stop it.' -ForegroundColor Green
    Write-Host ''

    # 7. Run the server (blocks until the window is closed).
    & $VenvPy -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port --log-level warning
    if ($LASTEXITCODE -ne 0) { throw "The server stopped with an error. Is port $Port already used by another program? Set DEALWATCH_PORT to change it." }
}
catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}
