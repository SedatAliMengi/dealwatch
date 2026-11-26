<#
  Dealwatch desktop launcher (Windows). Started hidden by "Start Dealwatch.vbs".

  - No console windows: everything runs hidden, and a tray icon (next to the
    clock) lets you Open the page, Check prices now, Show the log, or Quit.
  - Works from any folder: every path is relative to this script, so the
    project folder can be moved or renamed freely.
  - First run sets everything up (Python packages, React build, database).
    Later runs only redo a step when its files changed (after an update).
  - Data and logs (launcher.log, server.log) live in <project>\data and move with the folder.

  Optional settings: backend\.env (see .env.example). Port: DEALWATCH_PORT.
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$Root     = Split-Path -Parent $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Dist     = Join-Path $Frontend 'dist'
$Data     = Join-Path $Root 'data'
$LogFile  = Join-Path $Data 'launcher.log'   # setup steps + launcher messages
$ServerLog = Join-Path $Data 'server.log'    # the running API (separate file: no locking clash)
$VenvDir  = Join-Path $Backend '.venv'
$VenvPy   = Join-Path $VenvDir 'Scripts\python.exe'
$IconFile = Join-Path $PSScriptRoot 'dealwatch.ico'
$Port     = if ($env:DEALWATCH_PORT) { [int]$env:DEALWATCH_PORT } else { 8765 }
$Url      = "http://localhost:$Port"

New-Item -ItemType Directory -Force -Path $Data | Out-Null
foreach ($f in @($LogFile, $ServerLog)) {
    try {
        if ((Test-Path $f) -and (Get-Item $f).Length -gt 2MB) {
            Move-Item -Force $f ($f -replace '\.log$', '.old.log')
        }
    } catch { }
}

# ---- helpers ---------------------------------------------------------------

function Write-Log($msg) {
    # Logging must never crash the launcher.
    try { Add-Content -Path $LogFile -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) } catch { }
}

function Show-Error($msg) {
    Write-Log "ERROR: $msg"
    [System.Windows.Forms.MessageBox]::Show(
        "$msg`n`nDetails are in:`n$Data", 'Dealwatch',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}

function Start-Hidden([string]$CommandLine, [string]$WorkDir = $Root, [string]$OutFile = $LogFile) {
    # Runs a command with NO window (not even in Windows Terminal) and appends
    # its output to the log. Returns the Process object.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "$env:ComSpec"
    $psi.Arguments = "/d /s /c `"chcp 65001 >nul & $CommandLine >> `"$OutFile`" 2>&1`""
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    return [System.Diagnostics.Process]::Start($psi)
}

function Invoke-Hidden([string]$CommandLine, [string]$WorkDir = $Root) {
    Write-Log "> $CommandLine"
    $p = Start-Hidden $CommandLine $WorkDir
    $p.WaitForExit()
    return $p.ExitCode
}

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
    try { return (Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2).status -eq 'ok' }
    catch { return $false }
}

function Find-Python {
    foreach ($c in @(@{ Exe = 'py'; Args = @('-3') }, @{ Exe = 'python'; Args = @() })) {
        if (Get-Command $c.Exe -ErrorAction SilentlyContinue) {
            $extra = $c.Args
            $ok = & $c.Exe @extra -c 'import sys; print(sys.version_info >= (3, 11))' 2>$null
            if ($ok -eq 'True') { return ("$($c.Exe) " + ($extra -join ' ')).Trim() }
        }
    }
    throw 'Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and start Dealwatch again.'
}

function Stop-Server {
    # Stop whatever serves our port (covers a server left over from before).
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty OwningProcess -Unique)
    if ($script:Server -and -not $script:Server.HasExited) { $pids += $script:Server.Id }
    foreach ($id in $pids) { Invoke-Hidden "taskkill /PID $id /T /F" | Out-Null }
}

# ---- only one launcher at a time -------------------------------------------

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\DealwatchLauncher', [ref]$createdNew)
if (-not $createdNew) {
    # Already running: just bring up the page.
    if (Test-Healthy) { Start-Process $Url }
    exit 0
}

# ---- tray icon -------------------------------------------------------------

$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Icon = New-Object System.Drawing.Icon($IconFile)
$tray.Text = 'Dealwatch - starting...'
$tray.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$miOpen  = $menu.Items.Add('Open Dealwatch')
$miCheck = $menu.Items.Add('Check prices now')
$miLog   = $menu.Items.Add('Show log')
[void]$menu.Items.Add('-')
$miQuit  = $menu.Items.Add('Quit Dealwatch')
$miOpen.Font = New-Object System.Drawing.Font($miOpen.Font, [System.Drawing.FontStyle]::Bold)
$tray.ContextMenuStrip = $menu

$script:Ready = $false
$script:Server = $null

function Exit-Launcher {
    Write-Log 'Quitting.'
    if ($script:Timer) { $script:Timer.Stop() }
    Stop-Server
    $tray.Visible = $false
    $tray.Dispose()
    [System.Windows.Forms.Application]::Exit()
}

$miOpen.add_Click({ try { Start-Process $Url } catch { Write-Log "Open failed: $_" } })
$tray.add_DoubleClick({ if ($script:Ready) { Start-Process $Url } })
$miLog.add_Click({ try { Start-Process notepad.exe -ArgumentList "`"$ServerLog`"" } catch { Write-Log "Show log failed: $_" } })
$miQuit.add_Click({ try { Exit-Launcher } catch { [System.Windows.Forms.Application]::Exit() } })
$miCheck.add_Click({
    try {
        $r = Invoke-RestMethod -Method Post "http://127.0.0.1:$Port/api/checker/run" -TimeoutSec 180
        $tray.ShowBalloonTip(4000, 'Dealwatch', "Checked $($r.checked) game(s), $($r.alerts_created) new alert(s).", 'Info')
    } catch {
        $tray.ShowBalloonTip(4000, 'Dealwatch', "Price check failed: $($_.Exception.Message)", 'Warning')
    }
})

# ---- setup + start ---------------------------------------------------------

try {
    Write-Log "Starting from $Root"

    if (Test-Healthy) {
        Write-Log "A Dealwatch server is already answering on port $Port; using it."
    } else {
        # 1. Python virtual environment (recreated if missing or broken).
        $venvOk = (Test-Path $VenvPy) -and ((& $VenvPy -c "print('ok')" 2>$null) -eq 'ok')
        if (-not $venvOk) {
            $tray.ShowBalloonTip(5000, 'Dealwatch', 'First start: setting things up. This can take a minute or two.', 'Info')
            if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
            $py = Find-Python
            if ((Invoke-Hidden "$py -m venv `"$VenvDir`"") -ne 0) { throw 'Could not create the Python environment.' }
        }

        # 2. Python packages (reinstalled when requirements.txt changes).
        $reqFile  = Join-Path $Backend 'requirements.txt'
        $reqStamp = Join-Path $VenvDir '.dealwatch-deps'
        $reqHash  = Get-FilesHash @($reqFile)
        if ($reqHash -ne (Read-Stamp $reqStamp)) {
            $tray.Text = 'Dealwatch - installing packages...'
            $code = Invoke-Hidden "`"$VenvPy`" -m pip install --disable-pip-version-check -q -r `"$reqFile`""
            if ($code -ne 0) { throw 'Installing Python packages failed. Are you online?' }
            Set-Content -Path $reqStamp -Value $reqHash
        }

        # 3. Web page (rebuilt when frontend files change).
        $buildStamp = Join-Path $Dist '.dealwatch-build'
        $srcHash = Get-FilesHash @(
            (Join-Path $Frontend 'src'), (Join-Path $Frontend 'public'),
            (Join-Path $Frontend 'index.html'), (Join-Path $Frontend 'vite.config.js'),
            (Join-Path $Frontend 'package-lock.json'))
        if ($srcHash -ne (Read-Stamp $buildStamp)) {
            if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
                if (-not (Test-Path (Join-Path $Dist 'index.html'))) {
                    throw 'Node.js is needed once to build the web page. Install it from https://nodejs.org and start Dealwatch again.'
                }
                Write-Log 'Node.js not found: using the existing web page build.'
            } else {
                $tray.Text = 'Dealwatch - building the page...'
                $lockStamp = Join-Path $Frontend 'node_modules\.dealwatch-lock'
                $lockHash  = Get-FilesHash @((Join-Path $Frontend 'package-lock.json'))
                if ($lockHash -ne (Read-Stamp $lockStamp)) {
                    if ((Invoke-Hidden 'npm ci --no-audit --no-fund --loglevel=error' $Frontend) -ne 0) { throw 'npm ci failed.' }
                    Set-Content -Path $lockStamp -Value $lockHash
                }
                if ((Invoke-Hidden 'npm run build --silent' $Frontend) -ne 0) { throw 'Building the web page failed.' }
                Set-Content -Path $buildStamp -Value $srcHash
            }
        }

        # 4. Database schema (safe to run every time).
        $env:DATABASE_URL         = 'sqlite:///../data/dealwatch.db'   # relative to backend\
        $env:FRONTEND_DIST        = $Dist
        $env:RUN_CHECK_ON_STARTUP = 'true'
        $env:PYTHONUNBUFFERED     = '1'
        if ((Invoke-Hidden "`"$VenvPy`" -m alembic -c alembic.ini upgrade head" $Backend) -ne 0) {
            throw 'Updating the database failed.'
        }

        # 5. The server itself, hidden, output to the log.
        $tray.Text = 'Dealwatch - starting server...'
        Write-Log "Starting server on $Url"
        $script:Server = Start-Hidden "`"$VenvPy`" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port" $Backend $ServerLog
    }

    # Keep the desktop shortcut pointing at this folder (after a move).
    try { & (Join-Path $PSScriptRoot 'create-shortcut.ps1') -OnlyIfExists | Out-Null } catch { Write-Log "Shortcut update skipped: $_" }
}
catch {
    Show-Error $_.Exception.Message
    $tray.Visible = $false; $tray.Dispose()
    exit 1
}

# Poll until the server answers, then open the browser ONCE.
$script:Waited = 0
$script:Timer = New-Object System.Windows.Forms.Timer
$script:Timer.Interval = 500
$script:Timer.add_Tick({ try {
    if ($script:Server -and $script:Server.HasExited) {
        $script:Timer.Stop()
        Show-Error "The Dealwatch server stopped unexpectedly. Is port $Port used by another program? (You can set DEALWATCH_PORT to change it.)"
        Exit-Launcher
        return
    }
    if (-not $script:Ready) {
        if (Test-Healthy) {
            $script:Ready = $true
            $tray.Text = "Dealwatch - running at $Url"
            Write-Log 'Server is ready.'
            Start-Process $Url
            $tray.ShowBalloonTip(4000, 'Dealwatch is running', 'Right-click the tray icon to open it or quit.', 'Info')
            $script:Timer.Interval = 5000   # afterwards just watch the server
        } elseif (($script:Waited += 500) -gt 60000) {
            $script:Timer.Stop()
            Show-Error 'The Dealwatch server did not start within 60 seconds.'
            Exit-Launcher
        }
    }
} catch { Write-Log "Timer error: $_" } })
$script:Timer.Start()

[System.Windows.Forms.Application]::Run()
$mutex.ReleaseMutex()
