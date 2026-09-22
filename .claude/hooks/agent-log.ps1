# 서브에이전트 시작·종료를 한 줄씩 기록한다. tools/agent_dashboard.py 가 읽는다.
#
# 왜 훅인가: 세션 기록(.jsonl) 파싱은 Claude Code 문서가 명시적으로 권장하지 않는다 —
#   "The entry format is internal to Claude Code and changes between versions, so scripts
#    that parse these files directly can break on any release."
#   훅은 문서화된 인터페이스이고, 무엇보다 **'지금 실행 중'을 지어내지 않고 알 수 있다**:
#   시작 기록은 있는데 종료 기록이 없는 것이 곧 가동 중이다.
#
# ★ 이 스크립트는 세션을 절대 막으면 안 된다. 훅이 죽거나 느리면 작업이 멈춘다.
#   그래서 전부 try/catch 로 감싸고 무슨 일이 있어도 exit 0 한다. 기록을 한 줄 잃는 것이
#   작업을 세우는 것보다 낫다.
#
# 입력(stdin JSON, 공식 문서 확인): session_id · prompt_id · transcript_path · cwd ·
#   scratchpad_dir · permission_mode · effort · hook_event_name, 그리고 서브에이전트에서는
#   agent_id · agent_type 이 추가된다. 작업 설명(description)은 **오지 않는다** — 그 라벨은
#   세션 기록에만 있고, 대시보드는 과거 이력을 거기서 백필한다.

try {
    # ★ [Console]::In.ReadToEnd() 를 쓰면 안 된다. 콘솔 **입력 인코딩**(한국어 Windows 는 cp949)
    #   으로 디코딩해서 UTF-8 로 들어온 한글이 깨진다. 2026-09-23 실측: cwd 의
    #   '법원경매조회 및 분석' 이 '踰뺤썝寃쎈ℓ議고쉶 諛?遺꾩꽍' 이 됐고 '?' 자리는 글자가 아예
    #   소실됐다 — 되돌릴 수 없는 손상이다. 표준 입력 스트림을 UTF-8 로 직접 읽는다.
    $reader = New-Object System.IO.StreamReader(
        [Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))
    $raw = $reader.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $o = $raw | ConvertFrom-Json

    # 프로젝트 루트: .claude/hooks → .claude → 루트. 환경변수에 기대지 않는다.
    $root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $dir  = Join-Path $root 'data'                      # data/ 는 git 제외
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $path = Join-Path $dir 'agent-events.jsonl'

    $line = [pscustomobject]@{
        ts    = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
        event = [string]$o.hook_event_name
        agent = [string]$o.agent_type
        aid   = [string]$o.agent_id
        sid   = [string]$o.session_id
        cwd   = [string]$o.cwd
    } | ConvertTo-Json -Compress

    # 동시에 두 에이전트가 시작·종료하면 파일이 잠길 수 있다. 짧게 몇 번만 다시 시도하고
    # 안 되면 포기한다 — 여기서 오래 붙들고 있으면 세션이 그만큼 멈춘다.
    for ($i = 0; $i -lt 5; $i++) {
        try {
            Add-Content -Path $path -Value $line -Encoding utf8 -ErrorAction Stop
            break
        } catch {
            Start-Sleep -Milliseconds 40
        }
    }
} catch {
    # 조용히 삼킨다. 훅 실패로 작업을 세우지 않는다.
}
exit 0
