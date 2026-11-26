<#
  Creates (or fixes) the "Dealwatch" shortcut on your desktop so it points
  at THIS copy of the project. Run it again after moving the folder:
  double-click "Create Desktop Shortcut.bat" in the project folder.
#>
param([switch]$OnlyIfExists)

$Root     = Split-Path -Parent $PSScriptRoot
$Target   = Join-Path $Root 'Start Dealwatch.bat'
$Icon     = Join-Path $PSScriptRoot 'dealwatch.ico'
$Desktop  = [Environment]::GetFolderPath('Desktop')
$LinkPath = Join-Path $Desktop 'Dealwatch.lnk'

if ($OnlyIfExists -and -not (Test-Path $LinkPath)) { return }

$shell = New-Object -ComObject WScript.Shell
$link  = $shell.CreateShortcut($LinkPath)
if ($OnlyIfExists -and $link.TargetPath -eq $Target) { return }  # already correct

$link.TargetPath       = $Target
$link.WorkingDirectory = $Root
$link.IconLocation     = "$Icon,0"
$link.Description      = 'Dealwatch - game price alerts'
$link.Save()
Write-Host "Desktop shortcut ready: $LinkPath -> $Target"
