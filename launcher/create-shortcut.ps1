<#
  Sets up the "Dealwatch" desktop icon.

  The icon does NOT point into this project folder (that broke when the
  folder was moved). It points to a small helper in %LOCALAPPDATA%\Dealwatch,
  which never moves. The helper remembers where the project is, and if the
  project was moved it searches Desktop / Documents / Downloads for it.

  start.ps1 runs this on every start (with -OnlyIfExists), so the remembered
  folder is always up to date. Run "Create Desktop Shortcut.bat" to (re)create
  the icon itself.
#>
param([switch]$OnlyIfExists)

$Root     = Split-Path -Parent $PSScriptRoot
$HelperDir = Join-Path $env:LOCALAPPDATA 'Dealwatch'
$Helper   = Join-Path $HelperDir 'launch.vbs'
$Icon     = Join-Path $HelperDir 'dealwatch.ico'
$Desktop  = [Environment]::GetFolderPath('Desktop')
$LinkPath = Join-Path $Desktop 'Dealwatch.lnk'
$Wscript  = Join-Path $env:SystemRoot 'System32\wscript.exe'
$LinkArgs = "`"$Helper`""

# 1. Install / refresh the helper and remember where this project lives.
New-Item -ItemType Directory -Force -Path $HelperDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'desktop-launch.vbs') $Helper
Copy-Item -Force (Join-Path $PSScriptRoot 'dealwatch.ico') $Icon
Set-Content -Path (Join-Path $HelperDir 'project-path.txt') -Value $Root -Encoding Unicode -NoNewline

# 2. The desktop icon itself.
if ($OnlyIfExists -and -not (Test-Path $LinkPath)) { return }

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut($LinkPath)
if ($OnlyIfExists -and $link.TargetPath -eq $Wscript -and $link.Arguments -eq $LinkArgs -and
    $link.IconLocation -eq "$Icon,0") { return }

$link.TargetPath       = $Wscript   # no console window, ever
$link.Arguments        = $LinkArgs
$link.WorkingDirectory = $HelperDir
$link.IconLocation     = "$Icon,0"
$link.Description      = 'Dealwatch - game price alerts'
$link.Save()
Write-Host "Desktop icon ready: $LinkPath (project: $Root)"
