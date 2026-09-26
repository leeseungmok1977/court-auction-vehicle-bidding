# Hourly org scan (tools/org_runtime.py scan). No LLM call, no cost.
#
# Launched hidden by tools/run_hidden.vbs from the naechaget-org-heartbeat task when it is
# registered with -Interactive (tools/register_org_heartbeat_task.ps1). An Interactive task
# that runs python.exe directly flashes a console window every hour - the owner asked us to
# stop exactly that on 2026-09-26 (ops-snapshot). wscript + this file keeps it invisible.
#
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI, and the repo
# path contains Korean characters - so no path literals here, only $PSScriptRoot.
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)          # repo root
$env:PYTHONIOENCODING = 'utf-8'

$dir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'org_heartbeat.log'

$ts  = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$out = & python tools\org_runtime.py scan 2>&1 | Out-String
$code = $LASTEXITCODE
Add-Content -Path $log -Value ("[{0}] scan exit={1}`r`n{2}" -f $ts, $code, $out.Trim()) -Encoding UTF8

# keep the log small: hourly forever would grow without bound
if ((Get-Item $log).Length -gt 262144) {
    $tail = Get-Content $log -Tail 2000
    $tail | Set-Content $log -Encoding UTF8
}
exit $code
