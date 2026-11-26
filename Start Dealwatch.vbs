' Double-click to start Dealwatch. No console window opens: look for the
' Dealwatch icon next to the clock (right-click it to open or quit).
Dim fso, here, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File """ & here & "\launcher\start.ps1"""
CreateObject("WScript.Shell").Run cmd, 0, False
