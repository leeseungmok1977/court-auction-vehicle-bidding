# Daily standup + on-duty dispatch (tools/org_runtime.py standup --dispatch N).
#
# Launched hidden by tools/run_hidden.vbs from the naechaget-org-standup task when it is
# registered with -Interactive (tools/register_org_heartbeat_task.ps1).
#
# claude is NOT passed here on purpose: on this PC it lives only inside the VS Code
# extension folder, whose name carries the version (anthropic.claude-code-<ver>-win32-x64).
# org_runtime._claude_cmd finds the newest one itself, so an extension update does not
# silently break the on-duty Steward.
#
# The daily cap is enforced twice: -Dispatch here AND the contract table
# (docs/org-contracts.md section 1, 'daily dispatch cap'). Raising either is an owner decision.
#
# ASCII only on purpose (Windows PowerShell 5.1 + Korean repo path).
param([int]$Dispatch = 3)
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)          # repo root
$env:PYTHONIOENCODING = 'utf-8'

$dir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'org_standup.log'

$ts  = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$out = & python tools\org_runtime.py standup --dispatch $Dispatch 2>&1 | Out-String
$code = $LASTEXITCODE
Add-Content -Path $log -Value ("[{0}] standup --dispatch {1} exit={2}`r`n{3}" -f $ts, $Dispatch, $code, $out.Trim()) -Encoding UTF8

if ((Get-Item $log).Length -gt 524288) {
    $tail = Get-Content $log -Tail 4000
    $tail | Set-Content $log -Encoding UTF8
}
exit $code
