' Launch a PowerShell script with NO console window (wscript keeps no console).
' Used by the naechaget-ops-snapshot scheduled task: an Interactive-logon task
' shows a console flash every minute even with -WindowStyle Hidden. S4U would
' avoid that but needs an admin shell (docs/OPS_DASHBOARD.md). ASCII only.
Dim sh, ps1
If WScript.Arguments.Count < 1 Then WScript.Quit 2
ps1 = WScript.Arguments(0)
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, True
