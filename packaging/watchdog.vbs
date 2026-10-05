' watchdog.vbs
'
' Launches ClinicEMR.exe and keeps it running: if the server process ever
' crashes or is closed while the computer stays on, this script notices
' within a few seconds and starts it again automatically, so the front-desk
' never has to know what a "process" is or ever launch anything by hand.
'
' This script (not ClinicEMR.exe itself) is what goes in the Windows
' Startup folder, so it takes over the auto-restart job that on a normal
' server you'd hand to Task Scheduler / systemd. Deliberately kept simple
' as a .vbs so no extra software or scheduled-task setup is needed.
'
' Runs completely invisibly (no window, no taskbar icon, no console).

Dim shell, fso, exePath, installDir, checkCommand

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' This .vbs lives in the same installation folder as ClinicEMR.exe.
installDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = installDir & "\ClinicEMR.exe"

Do While True
    If Not IsRunning("ClinicEMR.exe") Then
        If fso.FileExists(exePath) Then
            ' 0 = hidden window, False = don't wait for it to exit here.
            ' No extra flags: this is also how it starts fresh at boot, and
            ' the app opening the browser itself is exactly what makes
            ' "starts automatically" feel automatic to reception staff.
            shell.Run """" & exePath & """", 0, False
            ' Give the app a little breathing room to fully start before we
            ' check on it again.
            WScript.Sleep 5000
        End If
    End If
    ' Poll every 10 seconds. Cheap, and more than fast enough for a small
    ' clinic that just wants the app back up quickly if it ever falls over.
    WScript.Sleep 10000
Loop

Function IsRunning(processName)
    Dim wmi, processes
    IsRunning = False
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name = '" & processName & "'")
    If processes.Count > 0 Then
        IsRunning = True
    End If
End Function
