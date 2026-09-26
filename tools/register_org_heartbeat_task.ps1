# ============================================================================
#  One-time registration (run elevated): the org's heartbeat.
#
#  Registers two tasks. Both names contain 'naechaget' so tools/agent_dashboard.py
#  shows them in its schedule table without any change.
#
#   naechaget-org-heartbeat : every hour     -> org_runtime.py scan
#                             Reads reports/ front matter, rhythm, backlog; writes
#                             orders/ and data/org-bus.jsonl. NO LLM call, no cost.
#   naechaget-org-standup   : daily 08:45    -> org_runtime.py standup --dispatch N
#                             Writes docs/standups/YYYY-MM-DD.md, then wakes the
#                             on-duty Steward (headless claude -p) for at most N
#                             auto-dispatchable orders. The daily cap and the on/off
#                             switch live in docs/org-contracts.md section 1.
#
#  Why 08:45: before the owner's working day, and clear of the 12:00 daily report,
#  Sat 09:20 panel routine and Sat 13:00 weekly report (docs/ORG.md section 4).
#
#  Settings follow tools/register_daily_report_task.ps1 (S4U, StartWhenAvailable,
#  IgnoreNew, full paths). Standup gets a 90 min limit: 3 dispatches x 25 min + scan.
#
#  Usage (elevated PowerShell):
#    powershell -ExecutionPolicy Bypass -File tools\register_org_heartbeat_task.ps1 -User "DESKTOP\name"
#    ... -Dispatch 0         # standup briefing only, never call claude
#    ... -RunNow             # run both once right away
#  Result: %LOCALAPPDATA%\naechaget\register_org_result.txt
#  Remove:
#    Unregister-ScheduledTask -TaskName naechaget-org-heartbeat -Confirm:$false
#    Unregister-ScheduledTask -TaskName naechaget-org-standup   -Confirm:$false
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ============================================================================
param(
    [Parameter(Mandatory = $true)][string]$User,
    [string]$StandupAt = '08:45',
    [int]$Dispatch = 3,
    [string]$Python = '',
    [string]$Claude = '',
    [switch]$RunNow
)
$ErrorActionPreference = 'Stop'

$root   = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$script = Join-Path $root 'tools\org_runtime.py'
$outDir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out    = Join-Path $outDir 'register_org_result.txt'

try {
    $p = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "not elevated - run this from an administrator PowerShell"
    }
    if (-not (Test-Path $script)) { throw "runtime not found: $script" }
    if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
    if (-not (Test-Path $Python)) { throw "python not found: $Python" }

    # S4U has no interactive PATH guarantee: resolve claude now and pass the full path.
    if ($Dispatch -gt 0) {
        if (-not $Claude) {
            $c = Get-Command claude.cmd -ErrorAction SilentlyContinue
            if (-not $c) { $c = Get-Command claude -ErrorAction SilentlyContinue }
            if ($c) { $Claude = $c.Source }
        }
        if (-not $Claude -or -not (Test-Path $Claude)) {
            throw "claude not found - pass -Claude <full path> or -Dispatch 0 for briefing only"
        }
    }

    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited

    # --- heartbeat: hourly scan -------------------------------------------------
    $hbArgs  = ('"{0}" scan' -f $script)
    $hbAct   = New-ScheduledTaskAction -Execute $Python -Argument $hbArgs -WorkingDirectory $root
    $hbTrig  = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
                 -RepetitionInterval (New-TimeSpan -Hours 1)
    $hbSet   = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                 -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
                 -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'naechaget-org-heartbeat' -Action $hbAct -Trigger $hbTrig `
        -Principal $principal -Settings $hbSet -Force `
        -Description 'naechaget: hourly org scan -> orders/ + data/org-bus.jsonl (tools/org_runtime.py scan, no LLM)' | Out-Null

    # --- standup: daily briefing + on-duty dispatch ------------------------------
    $suArgs = ('"{0}" standup --dispatch {1}' -f $script, $Dispatch)
    if ($Claude) { $suArgs = ('"{0}" --claude "{1}" standup --dispatch {2}' -f $script, $Claude, $Dispatch) }
    $suAct  = New-ScheduledTaskAction -Execute $Python -Argument $suArgs -WorkingDirectory $root
    $suTrig = New-ScheduledTaskTrigger -Daily -At $StandupAt
    $suSet  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 90) `
                -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'naechaget-org-standup' -Action $suAct -Trigger $suTrig `
        -Principal $principal -Settings $suSet -Force `
        -Description 'naechaget: daily standup -> docs/standups/YYYY-MM-DD.md, then on-duty dispatch (tools/org_runtime.py)' | Out-Null

    if ($RunNow) {
        Start-ScheduledTask -TaskName 'naechaget-org-heartbeat'
        Start-ScheduledTask -TaskName 'naechaget-org-standup'
    }

    $lines = @("OK registered naechaget-org-heartbeat, naechaget-org-standup",
               ("user={0} python={1}" -f $User, $Python),
               ("claude={0} dispatch={1} standupAt={2}" -f $Claude, $Dispatch, $StandupAt))
    foreach ($n in 'naechaget-org-heartbeat', 'naechaget-org-standup') {
        $i = Get-ScheduledTask -TaskName $n | Get-ScheduledTaskInfo
        $lines += ("{0} next={1}" -f $n, $i.NextRunTime)
    }
    $lines | Set-Content -Path $out -Encoding ascii
    $lines | ForEach-Object { Write-Host $_ }
} catch {
    ("FAILED: " + $_.Exception.Message) | Set-Content -Path $out -Encoding ascii
    Write-Host ("FAILED: " + $_.Exception.Message)
    exit 1
}
