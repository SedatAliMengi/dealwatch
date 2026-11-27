' Dealwatch desktop helper.
' create-shortcut.ps1 copies this file to %LOCALAPPDATA%\Dealwatch, a place
' that never moves, and the desktop icon runs it from there. So the icon keeps
' working even after you move or rename the project folder:
'   1. read the remembered project folder (project-path.txt next to this file)
'   2. if it is gone, search Desktop / Documents / Downloads for the project
'   3. remember the folder it found, then start Dealwatch from it (no window)
Option Explicit

Const MAX_DEPTH = 5
Dim fso, shell, here, pathFile, project
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
pathFile = here & "\project-path.txt"

project = ReadRemembered()
If Not IsProject(project) Then
    project = FindProject()
    If project = "" Then
        MsgBox "Dealwatch could not find its project folder." & vbCrLf & vbCrLf & _
               "Open the Dealwatch folder and double-click 'Start Dealwatch.vbs' once. " & _
               "The desktop icon will remember the new place.", vbExclamation, "Dealwatch"
        WScript.Quit 1
    End If
    Remember project
End If

shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File """ & _
          project & "\launcher\start.ps1""", 0, False

Function IsProject(folder)
    IsProject = False
    If folder = "" Then Exit Function
    IsProject = fso.FileExists(folder & "\launcher\start.ps1") And fso.FileExists(folder & "\Start Dealwatch.vbs")
End Function

Function ReadRemembered()
    ReadRemembered = ""
    If Not fso.FileExists(pathFile) Then Exit Function
    Dim f, text
    Set f = fso.OpenTextFile(pathFile, 1, False, -1)   ' -1 = Unicode (keeps non-English letters)
    If Not f.AtEndOfStream Then text = f.ReadAll Else text = ""
    f.Close
    text = Replace(text, ChrW(&HFEFF), "")
    text = Replace(Replace(text, vbCr, ""), vbLf, "")
    ReadRemembered = Trim(text)
End Function

Sub Remember(folder)
    Dim f
    Set f = fso.CreateTextFile(pathFile, True, True)  ' True = Unicode
    f.Write folder
    f.Close
End Sub

Function FindProject()
    Dim roots, r, found
    roots = Array(shell.SpecialFolders("Desktop"), shell.SpecialFolders("MyDocuments"), _
                  shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\Downloads", _
                  shell.ExpandEnvironmentStrings("%USERPROFILE%"))
    For Each r In roots
        If fso.FolderExists(r) Then
            found = Search(fso.GetFolder(r), 0)
            If found <> "" Then
                FindProject = found
                Exit Function
            End If
        End If
    Next
    FindProject = ""
End Function

Function Search(folder, depth)
    Search = ""
    On Error Resume Next   ' skip folders we may not open
    If IsProject(folder.Path) Then
        Search = folder.Path
        Exit Function
    End If
    If depth >= MAX_DEPTH Then Exit Function
    Dim sf, name, hit
    For Each sf In folder.SubFolders
        name = LCase(sf.Name)
        If name <> "node_modules" And name <> ".git" And name <> ".venv" And name <> "appdata" _
           And Left(name, 1) <> "." And name <> "$recycle.bin" Then
            hit = Search(sf, depth + 1)
            If hit <> "" Then
                Search = hit
                Exit Function
            End If
        End If
    Next
End Function
