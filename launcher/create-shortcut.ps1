<#
  Creates (or fixes) the "Dealwatch" shortcut on your desktop so it points
  at THIS copy of the project. Run it again after moving the folder:
  double-click "Create Desktop Shortcut.bat" in the project folder.
  (Starting Dealwatch from the new folder also fixes it automatically.)
#>
param([switch]$OnlyIfExists)

$Root     = Split-Path -Parent $PSScriptRoot
$Vbs      = Join-Path $Root 'Start Dealwatch.vbs'
$Icon     = Join-Path $PSScriptRoot 'dealwatch.ico'
$Desktop  = [Environment]::GetFolderPath('Desktop')
$LinkPath = Join-Path $Desktop 'Dealwatch.lnk'
$Wscript  = Join-Path $env:SystemRoot 'System32\wscript.exe'
$LinkArgs = "`"$Vbs`""

if ($OnlyIfExists -and -not (Test-Path $LinkPath)) { return }

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut($LinkPath)
if ($OnlyIfExists -and $link.TargetPath -eq $Wscript -and $link.Arguments -eq $LinkArgs) { return }

# wscript.exe has no console, so starting Dealwatch never flashes a window.
$link.TargetPath       = $Wscript
$link.Arguments        = $LinkArgs
$link.WorkingDirectory = $Root
$link.IconLocation     = "$Icon,0"
$link.Description      = 'Dealwatch - game price alerts'
$link.Save()
Write-Host "Desktop shortcut ready: $LinkPath -> $Vbs"
