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
#
#  Usage WITHOUT admin (added 2026-09-27 - the Claude session cannot raise UAC):
#    powershell -ExecutionPolicy Bypass -File tools\register_org_heartbeat_task.ps1 -Interactive
#    Interactive logon: runs only while the owner is logged on (StartWhenAvailable catches up),
#    launched through tools\run_hidden.vbs -> tools\org_heartbeat.ps1 / org_standup.ps1 so no
#    console window flashes (the ops-snapshot lesson). Running the elevated S4U form later
#    replaces these tasks in place (-Force), same task names.
#  Result: %LOCALAPPDATA%\naechaget\register_org_result.txt
#  Remove:
#    Unregister-ScheduledTask -TaskName naechaget-org-heartbeat -Confirm:$false
#    Unregister-ScheduledTask -TaskName naechaget-org-standup   -Confirm:$false
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ============================================================================
param(
    [string]$User = '',
    [switch]$Interactive,
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
    if (-not $User) { $User = ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME) }
    if (-not $Interactive) {
        $p = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw "not elevated - run this from an administrator PowerShell (or pass -Interactive)"
        }
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
        # 2026-09-27: on this PC claude exists only inside the VS Code extension folder
        # (versioned name). Take the newest; org_runtime re-resolves it if an update moves it.
        if (-not $Claude) {
            $ext = Join-Path $env:USERPROFILE '.vscode\extensions'
            $cand = Get-ChildItem -Path $ext -Directory -Filter 'anthropic.claude-code-*' -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $exe = Join-Path $_.FullName 'resources\native-binary\claude.exe'
                    $m = [regex]::Match($_.Name, '^anthropic\.claude-code-(\d+(\.\d+)*)')
                    if ($m.Success -and (Test-Path $exe)) { [pscustomobject]@{ V = [version]$m.Groups[1].Value; P = $exe } }
                } | Sort-Object V -Descending | Select-Object -First 1
            if ($cand) { $Claude = $cand.P }
        }
        if (-not $Claude -or -not (Test-Path $Claude)) {
            throw "claude not found - pass -Claude <full path> or -Dispatch 0 for briefing only"
        }
    }

    $logon = 'S4U'
    if ($Interactive) { $logon = 'Interactive' }
    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType $logon -RunLevel Limited
    $vbs = Join-Path $root 'tools\run_hidden.vbs'

    # --- heartbeat: hourly scan -------------------------------------------------
    $hbArgs  = ('"{0}" scan' -f $script)
    $hbAct   = New-ScheduledTaskAction -Execute $Python -Argument $hbArgs -WorkingDirectory $root
    if ($Interactive) {
        $hbAct = New-ScheduledTaskAction -Execute 'wscript.exe' -WorkingDirectory $root `
                   -Argument ('//B //Nologo "{0}" "{1}"' -f $vbs, (Join-Path $root 'tools\org_heartbeat.ps1'))
    }
    # First scan 1 minute after registration, then hourly. Starting at today 00:05 left the
    # dashboard with no scan for up to 55 minutes right after the owner registered (2026-09-27 review).
    $hbTrig  = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
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
    if ($Interactive) {
        # run_hidden.vbs passes only the .ps1 path, so the dispatch cap is org_standup.ps1's
        # default (3) - the same value as the contract table. -Dispatch 0 is not supported here.
        if ($Dispatch -ne 3) { throw "-Interactive uses org_standup.ps1 default dispatch 3 - edit that file to change it" }
        $suAct = New-ScheduledTaskAction -Execute 'wscript.exe' -WorkingDirectory $root `
                   -Argument ('//B //Nologo "{0}" "{1}"' -f $vbs, (Join-Path $root 'tools\org_standup.ps1'))
    }
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
