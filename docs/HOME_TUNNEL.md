# 집 회선 경유 엔카 터널 (F안)

## 왜
2026-09-07경부터 엔카(`api.encar.com`)가 **AWS 서버 IP를 HTTP 407로 차단**해 시세 수집이 멈췄다
(한국 가정용 회선에서는 정상). Elastic IP를 바꾸면 사이트 도메인·DNS까지 흔들리고 다시 차단될 수 있어,
**서버는 그대로 두고 엔카 요청만 집 회선으로 내보내는** 구조를 택했다.

```
EC2 앱 ──ENCAR_PROXY=http://127.0.0.1:18080──► sshd(EC2, 127.0.0.1:18080)
        ◄──────── 역방향 SSH 터널(-R) ────────  집 PC ssh
집 PC home_proxy.py(127.0.0.1:8888, encar.com만 허용) ──► api.encar.com  (집 IP로 나감)
```
- 사이트 IP·DNS·법원 수집은 영향 없음. 요청 수·지연(C.4)도 그대로.
- 터널이 꺼져 있으면 엔카 단계만 `error`로 건너뛰고(매일 6:30 `encar_health`), 대시보드에 지연 배너가 뜬다.
  그동안은 DB의 **동급 시세 참조**(`reuse_market_prices`)로 공백을 메운다(정직 표기 "동급 참조").

## PC 쪽 (한 번만)
1. `tools/home_tunnel.bat` 더블클릭 → 프록시 창(최소화)과 터널 창이 뜬다. 터널 창에 `tunnel connecting...` 후
   조용히 대기하면 연결된 것.
2. **시스템 시작 시 자동 시작(필수)** — 관리자 PowerShell에서 한 번:
   ```
   powershell -ExecutionPolicy Bypass -File tools\register_home_tunnel_task.ps1 -User "DESKTOP-RQDGDAH\14ZB95N"
   ```
   작업 `naechaget-home-tunnel`이 등록된다(2026-09-16 등록 완료). 창 없는 루프 `tools\home_tunnel_service.ps1`을 돌린다.
   - **왜 "로그온할 때"가 아니라 "시스템 시작 시"인가**: 2026-09-15 03:01에 Windows 업데이트가 PC를 자동 재시작했고
     아무도 로그온하지 않아 터널이 다시 켜지지 않았다. 06:30 갱신이 연결 오류로 건너뛰어져 **시세가 2일 지연**됐다.
     로그온 트리거는 무인 재시작 뒤에는 절대 돌지 않는다.
   - **S4U(로그온 여부와 관계없이, 암호 저장 없이)**: ssh·https 같은 외부 TCP 연결은 된다. 안 되는 것은 Windows 인증 공유폴더뿐.
   - **실행 시간 제한 0**: 기본값 72시간이면 사흘마다 터널이 조용히 죽는다. 실패 시 1분 간격 재시작, 중복 실행 금지.
   - **`home_tunnel.bat`을 그대로 쓰지 않는 이유**: 콘솔이 없으면 `timeout /t 15`가 즉시 실패해 재접속 루프가
     지연 없이 서버에 ssh를 연타한다. 서비스 스크립트는 `Start-Sleep 15`와 `BatchMode=yes`를 쓴다.
   - 서비스 스크립트는 8888이 이미 열려 있으면 프록시를 새로 띄우지 않고, 다른 18080 ssh가 돌고 있으면 60초씩 기다린다
     — `home_tunnel.bat`을 같이 더블클릭해도 둘이 싸우지 않는다.
   - 로그: `%LOCALAPPDATA%\naechaget\home_tunnel.log`(1MB에서 교체). 해제: `Unregister-ScheduledTask -TaskName naechaget-home-tunnel -Confirm:$false`
   - 권장: Windows 업데이트 **사용 시간**에 새벽(예: 03:00~09:00)을 넣어 06:30 갱신 직전 재시작을 피한다.
3. 전제: 이 PC에 `python`·`ssh`(Windows OpenSSH)가 PATH에 있고, `%USERPROFILE%\Downloads\naechaget.pem`이 있다.
   (이미 배포에 쓰는 것과 동일)

## 서버 쪽 (완료됨)
- `src/collect/encar.py::new_session` — `ENCAR_PROXY` 환경변수가 있으면 엔카 세션에만 프록시 적용.
- systemd drop-in `/etc/systemd/system/naechaget.service.d/proxy.conf`:
  `Environment=ENCAR_PROXY=http://127.0.0.1:18080`
- sshd 기본값(AllowTcpForwarding yes)으로 `-R 127.0.0.1:18080` 바인딩 가능. 외부에 열리지 않는다.

## 확인
서버에서:
```
cd ~/app && .venv/bin/python -c "from web import service; print(service.encar_health())"
# {'state': 'ok', 'code': 200}  ← 터널 정상.  {'state': 'error', ...} ← PC 터널 꺼짐.  'blocked' ← 집 IP도 차단(드묾)
```

## 주의
- **매일 06:30(KST) 갱신 시각에 PC가 켜져 있어야** 그날 시세 분석이 돈다. 절전에 들어가도 터널이 끊기니
  이 PC의 절전 진입 시간을 확인할 것(깨어나면 30초 안에 끊김을 감지해 재접속한다). 꺼져 있으면 그날은 건너뛰고
  동급 참조로 보완하며, 다음 날 다시 시도한다(상한 80건/일).
- 터널 포트가 EC2에 남아 있으면(비정상 종료) `ExitOnForwardFailure`로 ssh가 종료되고 15초 뒤 재시도한다.
- 프록시는 127.0.0.1 바인딩 + encar.com 허용목록이라 다른 용도로 쓰이지 않는다.
