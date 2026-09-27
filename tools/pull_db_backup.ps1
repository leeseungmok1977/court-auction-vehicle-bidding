# Pull the newest server DB backup to this PC once a day (AUD-08, owner approved 2026-09-27).
#
# Why: the server backup (deploy/backup_db.sh, cron 04:15) lives on the same EC2 disk. If the
# instance or its disk is lost, that copy goes with it. This PC keeps an off-instance copy.
#
# Launched hidden by tools/run_hidden.vbs from the task naechaget-db-backup-pull
# (tools/register_db_backup_pull_task.ps1). Copies into data\backups\ (git-ignored: data/).
# Keeps the newest 14 files. Log: %LOCALAPPDATA%\naechaget\db_backup_pull.log
#
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and the repo path
# contains Korean characters - no path literals, only $PSScriptRoot.
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)          # repo root

$logDir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'db_backup_pull.log'
function Write-Log($m) { Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8 }

$key    = Join-Path $env:USERPROFILE 'Downloads\naechaget.pem'
$target = 'ubuntu@43.202.126.180'
$dst    = Join-Path (Get-Location) 'data\backups'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
if (-not (Test-Path $key)) { Write-Log ("ssh key missing: " + $key); exit 1 }

$name = (& ssh -i $key -o BatchMode=yes -o ConnectTimeout=20 $target "ls -1t /home/ubuntu/backups/auction-*.db.gz 2>/dev/null | head -1" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $name -or $name -notmatch 'auction-\d{8}\.db\.gz$') { Write-Log ("no backup on server or ssh failed: " + $name); exit 1 }

$local = Join-Path $dst (Split-Path $name -Leaf)
if (Test-Path $local) { Write-Log ("already have " + (Split-Path $name -Leaf)); exit 0 }

$out = & scp -i $key -o BatchMode=yes -o ConnectTimeout=30 ($target + ':' + $name) $local 2>&1
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $local) -or (Get-Item $local).Length -lt 1024) {
    Write-Log ("scp FAILED: " + ($out -join ' | '))
    if (Test-Path $local) { Remove-Item $local -Force }
    exit 1
}
Write-Log ("pulled " + (Split-Path $local -Leaf) + " " + (Get-Item $local).Length + "B")

# keep the newest 14
Get-ChildItem -Path $dst -Filter 'auction-*.db.gz' | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item -Force
exit 0
