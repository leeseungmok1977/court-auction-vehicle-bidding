# ============================================================================
#  Bake the agent dashboard into one self-contained HTML file and upload it to
#  the production server, so the owner can read it from the office PC.
#
#    local: python tools/export_dashboard_snapshot.py
#        -> web/static/ops/<128-bit random>.html   (gitignored; the name IS the key)
#    scp  : ubuntu@43.202.126.180:/home/ubuntu/app/web/static/ops/
#    read : https://naechaget.co.kr/static/ops/<name>.html
#
#  Why a snapshot instead of a live tunnel into this PC:
#   - The office only needs "is the company running well", not live control.
#     A 5 minute lag costs nothing.
#   - If the key leaks, what leaks is a 5 minute old status page, NOT a route
#     into this PC.
#   - docs/MONETIZATION_SPEC.md section 7.3 already decided admin surfaces are
#     not opened on the public domain. A live proxy would contradict that.
#   - The existing reverse tunnel is NOT reused. It runs with
#     ExitOnForwardFailure=yes, so one stale forward would kill the whole
#     tunnel and stop the encar price pipeline with it (that already cost two
#     days of stale prices on 2026-09-15).
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI,
#  so Korean comments get mangled in headless scheduled runs.
#  Log: %LOCALAPPDATA%\naechaget\snapshot.log (rotated at 1 MB).
# ============================================================================
$ErrorActionPreference = 'Continue'

$proj = Split-Path -Parent $PSScriptRoot
$key   = Join-Path $env:USERPROFILE 'Downloads\naechaget.pem'
$target = 'ubuntu@43.202.126.180'
$remote = '/home/ubuntu/app/web/static/ops/'

$logDir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'snapshot.log'

function Write-Log([string]$msg) {
    try {
        if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) { Move-Item -Force $log "$log.1" }
        Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
    } catch { }
}

Set-Location $proj
$env:PYTHONIOENCODING = 'utf-8'

# 1) bake
$out = & python tools\export_dashboard_snapshot.py 2>&1
if ($LASTEXITCODE -ne 0) { Write-Log ("bake FAILED: " + ($out -join ' | ')); exit 1 }

$nameFile = Join-Path $proj 'data\ops_snapshot_name.txt'
if (-not (Test-Path $nameFile)) { Write-Log 'bake produced no name file'; exit 1 }
$name = (Get-Content $nameFile -Raw).Trim()
$src  = Join-Path $proj ("web\static\ops\" + $name)
if (-not (Test-Path $src)) { Write-Log ("baked file missing: " + $src); exit 1 }
$kb = [int]((Get-Item $src).Length / 1KB)

# The page reloads only this JSON every 30s (17KB instead of the whole 53KB page),
# so the office view stays about a minute behind instead of five. Ship both in ONE
# scp call - a separate call would mean a second SSH handshake every minute.
$srcJson = [IO.Path]::ChangeExtension($src, '.json')
if (-not (Test-Path $srcJson)) { Write-Log ("baked json missing: " + $srcJson); exit 1 }

# 2) upload. No mkdir here on purpose - the directory is created once during
#    setup. If it is gone, the scp error is the signal, and silently recreating
#    it would hide that someone removed the page deliberately.
if (-not (Test-Path $key)) { Write-Log ("ssh key missing: " + $key); exit 1 }
$scpOut = & scp -i $key -o BatchMode=yes -o ConnectTimeout=20 $src $srcJson ($target + ':' + $remote) 2>&1
if ($LASTEXITCODE -ne 0) { Write-Log ("scp FAILED (" + $kb + "KB): " + ($scpOut -join ' | ')); exit 1 }

Write-Log ("published " + $name + " + json (" + $kb + "KB)")
exit 0
