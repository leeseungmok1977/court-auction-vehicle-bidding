# ============================================================================
#  One-time registration (run elevated): daily 12:00 job-result report.
#  Runs tools\daily_ops_report.py, which writes docs\daily-reports\YYYY-MM-DD.md.
#
#  Settings and why:
#   - Daily trigger 12:00               : user instruction (2026-09-16).
#   - LogonType S4U                     : runs without logon and WITHOUT storing a
#                                         password (an unattended update reboot on
#                                         2026-09-15 left nobody logged on).
#   - StartWhenAvailable                : if the PC was off at 12:00, run when back.
#   - ExecutionTimeLimit 30 min         : the report takes about a minute; never hang.
#   - RestartCount 3 / 10 min, IgnoreNew: retry transient ssh/git failures, never twice.
#   - python.exe resolved to a full path: S4U has no interactive PATH guarantees.
#
#  Usage (from an elevated PowerShell):
#    powershell -ExecutionPolicy Bypass -File tools\register_daily_report_task.ps1 -User "DESKTOP\name"
#  Result also written to %LOCALAPPDATA%\naechaget\register_report_result.txt
#  Remove: Unregister-ScheduledTask -TaskName naechaget-daily-report -Confirm:$false
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ============================================================================
param(
    [Parameter(Mandatory = $true)][string]$User,
    [string]$At = '12:00',
    [string]$Python = '',
    [switch]$RunNow
)
$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$script   = Join-Path $root 'tools\daily_ops_report.py'
$taskName = 'naechaget-daily-report'
$outDir   = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out      = Join-Path $outDir 'register_report_result.txt'

try {
    $p = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "not elevated - run this from an administrator PowerShell"
    }
    if (-not (Test-Path $script)) { throw "report script not found: $script" }
    if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
    if (-not (Test-Path $Python)) { throw "python not found: $Python" }

    $action    = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $script) -WorkingDirectory $root
    $trigger   = New-ScheduledTaskTrigger -Daily -At $At
    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited
    $settings  = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force `
        -Description 'naechaget: daily 12:00 job-result report -> docs/daily-reports/YYYY-MM-DD.md (tools/daily_ops_report.py)' | Out-Null

    if ($RunNow) { Start-ScheduledTask -TaskName $taskName }

    $t = Get-ScheduledTask -TaskName $taskName
    $i = $t | Get-ScheduledTaskInfo
    $lines = @(
        "OK registered $taskName",
        ("user={0} logonType={1} runLevel={2}" -f $t.Principal.UserId, $t.Principal.LogonType, $t.Principal.RunLevel),
        ("python={0}" -f $Python),
        ("trigger={0} at={1} next={2}" -f $t.Triggers[0].CimClass.CimClassName, $t.Triggers[0].StartBoundary, $i.NextRunTime),
        ("timeLimit={0} restartCount={1} restartInterval={2} multipleInstances={3} startWhenAvailable={4}" -f $t.Settings.ExecutionTimeLimit, $t.Settings.RestartCount, $t.Settings.RestartInterval, $t.Settings.MultipleInstances, $t.Settings.StartWhenAvailable),
        ("state={0} runNow={1}" -f $t.State, [bool]$RunNow)
    )
    $lines | Set-Content -Path $out
    $lines | ForEach-Object { Write-Host $_ }
} catch {
    ("FAIL {0}" -f $_.Exception.Message) | Set-Content -Path $out
    Write-Host ("FAIL {0}" -f $_.Exception.Message)
    exit 1
}
