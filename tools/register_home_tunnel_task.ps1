# ============================================================================
#  One-time registration (run elevated): Task Scheduler task that keeps the home
#  tunnel up from system startup, whether or not anyone is logged on.
#
#  Why these settings (2026-09-16 incident: Windows Update rebooted the PC at 03:01,
#  nobody logged on, the tunnel never came back, market data went stale for 2 days):
#   - Trigger AtStartup (+1 min for network)  : a logon trigger never fires after an
#                                               unattended update reboot.
#   - LogonType S4U                           : runs without logon and WITHOUT storing
#                                               a password. Outbound TCP (ssh/https)
#                                               works; only Windows-auth shares don't.
#   - ExecutionTimeLimit = 0                  : default is 72 h, which would silently
#                                               kill the tunnel every three days.
#   - Restart on failure, IgnoreNew instances : self-heal, never run twice.
#
#  Usage (from an elevated PowerShell):
#    powershell -ExecutionPolicy Bypass -File tools\register_home_tunnel_task.ps1 -User "DESKTOP\name"
#  Result is also written to %LOCALAPPDATA%\naechaget\register_result.txt
#  Remove: Unregister-ScheduledTask -TaskName naechaget-home-tunnel -Confirm:$false
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ============================================================================
param(
    [Parameter(Mandatory = $true)][string]$User,
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$service  = Join-Path $root 'home_tunnel_service.ps1'
$taskName = 'naechaget-home-tunnel'
$outDir   = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out      = Join-Path $outDir 'register_result.txt'

try {
    $principalCheck = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principalCheck.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "not elevated - run this from an administrator PowerShell"
    }
    if (-not (Test-Path $service)) { throw "service script not found: $service" }

    $psExe  = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $action = New-ScheduledTaskAction -Execute $psExe `
        -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $service) `
        -WorkingDirectory $root

    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT1M'

    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force `
        -Description 'naechaget: keep the Encar home tunnel (EC2 18080 -> PC 8888) up from startup, no logon needed. See docs/HOME_TUNNEL.md' | Out-Null

    if ($StartNow) { Start-ScheduledTask -TaskName $taskName }

    $t = Get-ScheduledTask -TaskName $taskName
    $lines = @(
        "OK registered $taskName",
        ("user={0} logonType={1} runLevel={2}" -f $t.Principal.UserId, $t.Principal.LogonType, $t.Principal.RunLevel),
        ("trigger={0} delay={1}" -f $t.Triggers[0].CimClass.CimClassName, $t.Triggers[0].Delay),
        ("timeLimit={0} restartCount={1} restartInterval={2} multipleInstances={3}" -f $t.Settings.ExecutionTimeLimit, $t.Settings.RestartCount, $t.Settings.RestartInterval, $t.Settings.MultipleInstances),
        ("state={0} startNow={1}" -f $t.State, [bool]$StartNow)
    )
    $lines | Set-Content -Path $out
    $lines | ForEach-Object { Write-Host $_ }
} catch {
    ("FAIL {0}" -f $_.Exception.Message) | Set-Content -Path $out
    Write-Host ("FAIL {0}" -f $_.Exception.Message)
    exit 1
}
