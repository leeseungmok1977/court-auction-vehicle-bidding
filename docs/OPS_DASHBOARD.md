# 에이전트 현황판 — 집에서 보기 / 회사에서 보기

> 2026-09-23 오너 요청. 서버는 **집 개인 PC**, 보는 곳은 **회사 PC**.
> 화면 자체의 설계 원칙은 `tools/agent_dashboard.py` 의 docstring 에 있다.
>
> ⚠ **이 문서에는 열쇠를 적지 않는다.** 접속 토큰과 스냅샷 파일명이 곧 자물쇠인데,
> 저장소에 적으면 안전장치를 스스로 무력화하는 것이다. 값은 `data/` 에만 있다(git 제외).

## 1. 집 PC 에서 (실시간)

```
python tools/agent_dashboard.py                    # 127.0.0.1 전용 — 열쇠 없음
python tools/agent_dashboard.py --host 0.0.0.0     # 같은 망에 열기 — 열쇠 강제
```

로그온 시 자동 실행: 예약 작업 `naechaget-agent-dashboard` → `tools/start_agent_dashboard.cmd`.

- 기본값은 **이 PC 전용**이다. `--host` 로 밖에 열 때만 열쇠를 요구하고, 열쇠를 안 주면
  막지 않고 **대신 만들어 준다** — 인증 없이 여는 경로를 두지 않기 위해서다.
- 열쇠: `data/dashboard_token.txt` (git 제외). 주소는 `http://<IP>:8765/?k=<열쇠>`.
- 열쇠를 바꾸려면 그 파일을 지우고 재기동하면 새로 발급된다.
- 같은 망의 다른 기기에서 보려면 방화벽 인바운드 규칙이 따로 필요하다(관리자 권한):
  ```powershell
  New-NetFirewallRule -DisplayName "NaechaGet Agent Dashboard 8765" -Direction Inbound `
    -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet -Profile Any
  ```
  **회사 PC 는 다른 망이라 이 규칙으로는 안 된다** — §2 를 쓴다.

## 2. 회사 PC 에서 (1분 갱신 스냅샷)

집 PC 의 `127.0.0.1` 은 밖에서 닿지 않는다. 길은 둘이었다.

| | ㉮ 실시간 중계 | ㉯ 산출물만 올리기 ← **채택** |
|---|---|---|
| 방식 | 기존 역방향 SSH 터널로 운영 서버가 집 PC 안을 중계 | 화면을 HTML 한 장으로 구워 운영 서버에 올림 |
| 신선도 | 실시간(초 단위) | **최대 1분 지연** — 화면이 30초마다 스스로 받아 온다 |
| 열쇠가 샜을 때 | **집 PC 로 가는 통로**가 열림 | 5분 지난 현황판 한 장 |

㉯ 를 택한 이유:
1. 회사에서 보려는 것은 *회사가 잘 돌아가나*이지 실시간 조작이 아니다. 5분 지연은 손해가 없다.
2. `docs/MONETIZATION_SPEC.md` §7.3 이 **관리 화면을 공개 주소로 열지 않기로** 이미 결정했다.
   ㉮ 는 그 결정과 정면으로 어긋난다.
3. ★ **기존 터널에 포워딩을 덧붙이지 않는다.** 그 ssh 는 `ExitOnForwardFailure=yes` 라
   새 포트가 하나라도 서버에 남아 있으면 **터널 전체가 죽는다.** 그러면 엔카 시세 수집이
   같이 멈춘다 — 2026-09-15 에 실제로 터널이 안 켜져 시세가 **이틀 지연**된 적이 있다.
   편의 기능 때문에 돈 버는 파이프라인을 위태롭게 하지 않는다.

### 구성

```
집 PC  python tools/export_dashboard_snapshot.py
         → web/static/ops/<128비트 난수>.html   (첫 그림이 박혀 있어 즉시 뜬다 · 56KB)
         → web/static/ops/<같은 난수>.json     (데이터만 · 24KB)
       scp → ubuntu@43.202.126.180:/home/ubuntu/app/web/static/ops/   (둘을 한 번에)
회사 PC  https://naechaget.co.kr/static/ops/<그 파일명>.html
         └ 화면이 30초마다 같은 폴더의 .json 만 받아 다시 그린다
```

**왜 둘로 쪼갰나**: 한 장에 데이터를 박아 두면 갱신할 때마다 56KB 전체가 오간다.
데이터만 따로 내보내면 **24KB** 만 움직이므로 1분 간격으로 올려도 부담이 없고,
화면은 첫 그림을 박혀 있는 값으로 즉시 그려 느린 회선에서도 빈 화면을 보이지 않는다.
**보안 성격은 그대로다** — 여전히 정적 파일 두 장이고, 집 PC 로 들어오는 길은 없다.

- **서버 설정을 건드리지 않는다.** 앱이 이미 `/static` 을 서빙하고(`web/app.py:37`),
  배포는 `git pull` 이라 **추적되지 않는 이 파일은 배포해도 지워지지 않는다.**
- 색인 차단은 서버(robots)가 아니라 **파일 안의 `noindex,nofollow` 메타**로 한다.
- 주소는 `python tools/export_dashboard_snapshot.py --print-url` 로 확인한다.
- 자동 갱신: 예약 작업 `naechaget-ops-snapshot` (**1분**) → `tools/publish_dashboard_snapshot.ps1`.
  로그 `%LOCALAPPDATA%\naechaget\snapshot.log`. 한 사이클 **실측 2.7~3.2초**
  (굽기 2.1초 + 전송 0.8초)라 1분 간격에 57초가 남는다. `MultipleInstances=IgnoreNew` 로
  겹침도 막아 뒀다.
- 스냅샷 화면은 **나이를 초 단위로 적고**(`… 기준 · 7초 전 갱신`), 새 자료를 받을 때마다
  맥박이 한 번 뛴다. **3분 넘게 새 자료가 안 오면 붉게 굳고 "집 PC 가 새 자료를 안 올리고
  있다"고 적는다.** 집 PC 가 꺼졌는데 옛 숫자를 '지금'처럼 보여주면 안 되기 때문이다.
- 실측(2026-09-23): 공개본에서 JSON 폴링 발생 확인, 기준 시각이 **08:37 → 08:38 로 스스로
  앞당겨짐**, JS 오류 0건. 로컬 대시보드(127.0.0.1)도 같은 HTML 을 쓰므로 함께 확인했다.

### 한계 (감추지 않는다)

- **매분 PowerShell 창이 깜빡였다(2026-09-25 오너 신고).** Interactive 계정으로 도는 작업은 `-WindowStyle Hidden` 이 있어도
  콘솔이 한순간 보인다. 관리자 없이 막는 처방: 작업 동작을 `wscript.exe //B //Nologo toolsun_hidden.vbs <ps1>` 로 감쌌다
  (wscript 는 콘솔이 없어 창이 생기지 않는다). **적용 시 함정**: 동작을 바꾸는 .ps1 을 BOM 없는 UTF-8 로 쓰면
  PowerShell 5.1 이 ANSI 로 읽어 **한글 경로가 깨진 채 등록**된다 — 실제로 2분간 실패(`0x8007010B`)했고 UTF-8 **BOM** 으로
  다시 써서 복구했다. S4U 로 올리면(아래) 래퍼 없이도 창이 안 뜨고 로그오프 후에도 돈다.
- **로그온 중에만 갱신된다.** S4U 등록이 권한 부족(`Access is denied`)으로 실패해
  현재는 로그온 상태에서만 돈다. 로그오프·재부팅 후 미로그온 구간에는 화면이 낡는다.
  올리려면 **관리자 PowerShell** 에서 한 번:
  ```powershell
  $t = Get-ScheduledTask -TaskName 'naechaget-ops-snapshot'
  $p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
  Set-ScheduledTask -TaskName 'naechaget-ops-snapshot' -Principal $p
  ```
- 집 PC 가 꺼져 있으면 갱신이 멈춘다. 화면은 **마지막으로 구운 시각을 그대로 보여주므로**
  낡은 것을 새것으로 착각하지는 않는다.
- 내용은 조직·호출 이력·배포 이력·물건 수다. **대화 내용은 애초에 수집하지 않는다**
  (시각·도구명·에이전트명·짧은 작업 라벨뿐).

### 되돌리기

```powershell
Unregister-ScheduledTask -TaskName 'naechaget-ops-snapshot' -Confirm:$false
ssh -i $env:USERPROFILE\Downloads\naechaget.pem ubuntu@43.202.126.180 "rm -rf /home/ubuntu/app/web/static/ops"
```
주소만 바꾸려면 `data/ops_snapshot_name.txt` 를 지우고 다시 구운 뒤, 서버의 옛 파일을 지운다.
