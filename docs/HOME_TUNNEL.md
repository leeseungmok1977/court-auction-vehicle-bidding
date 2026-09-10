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
2. **로그온 시 자동 시작(권장)** — 작업 스케줄러:
   - 작업 만들기 → 트리거 "로그온할 때" → 동작 "프로그램 시작" → `tools\home_tunnel.bat` 경로
   - "사용자가 로그온할 때만 실행", "가장 높은 권한" 불필요
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
- **매일 06:30(KST) 갱신 시각에 PC가 켜져 있어야** 그날 시세 분석이 돈다. 꺼져 있으면 그날은 건너뛰고
  동급 참조로 보완하며, 다음 날 다시 시도한다(상한 80건/일).
- 터널 포트가 EC2에 남아 있으면(비정상 종료) `ExitOnForwardFailure`로 ssh가 종료되고 15초 뒤 재시도한다.
- 프록시는 127.0.0.1 바인딩 + encar.com 허용목록이라 다른 용도로 쓰이지 않는다.
