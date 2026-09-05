# 주간 사진분류 '점검+준비' 자동화 (안전판) — Windows 작업 스케줄러에서 매주 1회 실행
# 순수 파이썬만 사용(헤드리스 Claude·SSH·권한생략 없음). 위험 없음.
#   미분류 확인 → 있으면 prep(몽타주 준비) + 데스크톱 알림 + 마커파일 생성.
#   그 다음 비전 분류는 사용자가 Claude에서 /classify-photos 실행(몽타주 준비돼 있어 빠름).
# 등록:  schtasks /Create /TN "NaechaGet-PhotoClassify" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"C:\Users\14ZB95N\법원경매조회 및 분석\run_photo_classify_check.ps1\"" /SC WEEKLY /D SUN /ST 08:17 /F
# 해제:  schtasks /Delete /TN "NaechaGet-PhotoClassify" /F
$ErrorActionPreference = "Continue"
$proj = "C:\Users\14ZB95N\법원경매조회 및 분석"
Set-Location $proj
$env:PYTHONIOENCODING = "utf-8"
$workDir = Join-Path $proj "data\_photo_work"
if (-not (Test-Path $workDir)) { New-Item -ItemType Directory -Force -Path $workDir | Out-Null }
$log = Join-Path $workDir "weekly_check.log"
$marker = Join-Path $workDir "NEEDS_CLASSIFY.txt"
function Log($m) { "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))  $m" | Tee-Object -FilePath $log -Append }

Log "===== 주간 미분류 점검 ====="
$statusOut = & python scripts\photo_classify.py status 2>&1
$statusOut | ForEach-Object { Log "  $_" }
$unc = 0
foreach ($line in $statusOut) { if ("$line" -match 'UNCLASSIFIED=(\d+)') { $unc = [int]$Matches[1] } }

if ($unc -le 0) {
    if (Test-Path $marker) { Remove-Item $marker -Force }
    Log "미분류 0건 — 조치 불필요"
    Log "===== 완료 =====`n"
    exit 0
}

Log "미분류 $unc 건 → 몽타주 준비(prep)"
$prepOut = & python scripts\photo_classify.py prep 2>&1
$prepOut | ForEach-Object { Log "  $_" }

# 마커파일 + 데스크톱 알림
"미분류 $unc 건 · $([DateTime]::Now.ToString('yyyy-MM-dd HH:mm'))`nClaude에서 /classify-photos 를 실행하세요(몽타주 준비 완료)." |
    Set-Content -Path $marker -Encoding UTF8
try {
    & msg.exe * "경매로 내차GET: 사진 미분류 $unc 건 준비 완료 — Claude에서 /classify-photos 실행하세요."
} catch { Log "msg 알림 실패(무시): $_" }
Log "===== 완료 (분류 대기 $unc 건, /classify-photos 실행 필요) =====`n"
