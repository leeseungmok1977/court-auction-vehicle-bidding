# ============================================================================
#  Headless home tunnel loop (Plan F) - for Task Scheduler "run whether user is
#  logged on or not". Same tunnel as home_tunnel.bat, but safe without a console:
#    EC2 127.0.0.1:18080 --(ssh -R)--> this PC 127.0.0.1:8888 (home_proxy.py) --> encar.com
#
#  Why not reuse home_tunnel.bat:
#   - `timeout /t 15` fails instantly when there is no console, so the retry loop
#     would hammer the server with ssh attempts (no delay at all).
#   - It opens windows; a no-logon task runs in session 0 with no desktop.
#
#  Guards:
#   - Starts home_proxy.py only if 127.0.0.1:8888 is not already listening.
#   - If another ssh with "18080" is already running (e.g. someone double-clicked
#     home_tunnel.bat), waits instead of starting a duplicate.
#   - 15 s between reconnects, BatchMode=yes so ssh never hangs on a prompt.
#  Log: %LOCALAPPDATA%\naechaget\home_tunnel.log (rotated at 1 MB).
#
#  ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ============================================================================
$ErrorActionPreference = 'Continue'

$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$proxyPy = Join-Path $root 'home_proxy.py'
$key     = Join-Path $env:USERPROFILE 'Downloads\naechaget.pem'
$target  = 'ubuntu@43.202.126.180'
$ssh     = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'

$logDir = Join-Path $env:LOCALAPPDATA 'naechaget'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'home_tunnel.log'

function Write-Log([string]$msg) {
    try {
        if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) {
            Move-Item -Force $log "$log.1"
        }
        Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
    } catch { }
}

function Resolve-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $fallback) { return $fallback }
    return $null
}

function Test-ProxyUp {
    return [bool](Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue)
}

function Start-ProxyIfDown {
    if (Test-ProxyUp) { return }
    $py = Resolve-Python
    if (-not $py) { Write-Log "ERROR python not found - proxy not started"; return }
    Start-Process -FilePath $py -ArgumentList ('"{0}"' -f $proxyPy) -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
    Write-Log ("proxy start requested -> listening={0}" -f (Test-ProxyUp))
}

function Get-OtherTunnel([int]$ownPid) {
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match '18080' -and $_.ProcessId -ne $ownPid }
}

Write-Log ("service start (user={0}, key exists={1})" -f $env:USERNAME, (Test-Path $key))

$sshArgs = @(
    '-N',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'BatchMode=yes',
    '-i', ('"{0}"' -f $key),
    '-R', '127.0.0.1:18080:127.0.0.1:8888',
    $target
)

while ($true) {
    Start-ProxyIfDown

    $other = Get-OtherTunnel 0
    if ($other) {
        Write-Log ("another tunnel already running (pid {0}) - waiting 60s" -f (($other | Select-Object -ExpandProperty ProcessId) -join ','))
        Start-Sleep -Seconds 60
        continue
    }

    Write-Log "tunnel connecting"
    $p = Start-Process -FilePath $ssh -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
    # While connected, keep the proxy alive (the loop would otherwise only notice on ssh exit).
    while (-not $p.HasExited) {
        Start-Sleep -Seconds 30
        Start-ProxyIfDown
    }
    Write-Log ("tunnel closed (exit {0}) - retry in 15s" -f $p.ExitCode)
    Start-Sleep -Seconds 15
}
