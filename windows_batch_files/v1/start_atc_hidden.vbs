' start_atc_hidden.vbs
' Launch Manual Receiving ATC completely hidden (no console window).

Option Explicit

Dim WshShell
Set WshShell = CreateObject("WScript.Shell")

' 0 = hidden window, False = don't wait
Dim baseDir, logPath, cmd
baseDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
logPath = baseDir & "\\atc_run.log"

cmd = """" & baseDir & "\\atc_env\\Scripts\\python.exe"" """ & baseDir & "\\manual_receiving_atc.py""" & """" & " > """" & logPath & """" & " 2>&1"

WshShell.Run cmd, 0, False
