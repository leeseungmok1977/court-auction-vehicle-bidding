# One-time registration (no admin needed): naechaget-db-backup-pull, daily 09:10.
# Interactive logon (runs while the owner is logged on; StartWhenAvailable catches up after sleep or
# reboot), launched through tools\run_hidden.vbs so no console window flashes (ops-snapshot lesson).
# 09:10: after the server backup at 04:15 and the 06:30 daily update, before the 12:00 daily report.
#
#   powershell -ExecutionPolicy Bypass -File tools\register_db_backup_pull_task.ps1
#   Remove: Unregister-ScheduledTask -TaskName naechaget-db-backup-pull -Confirm:$false
#
# ASCII only on purpose (Windows PowerShell 5.1 + Korean repo path).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$vbs  = Join-Path $root 'tools\run_hidden.vbs'
$ps1  = Join-Path $root 'tools\pull_db_backup.ps1'
$user = ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME)

$act  = New-ScheduledTaskAction -Execute 'wscript.exe' -WorkingDirectory $root `
          -Argument ('//B //Nologo "{0}" "{1}"' -f $vbs, $ps1)
$trig = New-ScheduledTaskTrigger -Daily -At '09:10'
$set  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
          -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
$prin = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'naechaget-db-backup-pull' -Action $act -Trigger $trig -Principal $prin `
    -Settings $set -Force -Description 'naechaget: pull newest server DB backup to data\backups (AUD-08)' | Out-Null
$i = Get-ScheduledTask -TaskName 'naechaget-db-backup-pull' | Get-ScheduledTaskInfo
Write-Host ("OK naechaget-db-backup-pull next=" + $i.NextRunTime)
