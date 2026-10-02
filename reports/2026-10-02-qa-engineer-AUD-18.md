---
order: 2026-10-02-16
from: qa-engineer
ticket: AUD-18
result: done
verified: 재현
handoff:
  - to: backend-engineer
    why: "AUD-18 배포 뒤 후속(비차단·배포를 막지 않음) — N1 review_daily_anomalies 의 불일치가 max_recheck(20) 예산을 쓰지 않음(합성 이상 30건 전부 불일치 → 요청 30, HEAD 20) 1줄 수정 + N3 변이 생존 3건(M8·M12·M13)에 회귀 테스트. 재현 절차는 이 보고서 '비차단' 절"
---

# AUD-18 반증 검수 — 판정 **deployable** · must_fix 0 (qa-engineer, 지시서 2026-10-02-16)

> 작성 2026-10-02 23:50 ~ 10-03 00:45. 대상: 워크트리 `.claude/worktrees/agent-a19bd3bb07a85daa4` 미커밋 diff —
> `git diff` md5 **3be697011c9f13e291e35d51ade89aed**(검수 시작·끝 동일) + `tests/test_aud18_detail_key.py` md5 5fc63524.
> 담당 보고서 §2 의 파일별 md5 10개 전부 일치. 기준 커밋 6687944, 메인 HEAD 는 그 뒤 **74ae8b7**(검수 중 Steward 문서 커밋 1개 추가) —
> `git diff --name-only 6687944..HEAD` = backlog.md·보고서 2개, **코드 변경 0**.
> 실험은 전부 scratchpad 사본 트리(`qa18/tree_head` = 메인 HEAD 추적 파일, `qa18/tree_new` = 워크트리 추적+미추적 파일)와
> 운영 사본 `aud18/live_1002.db` 의 **복사본**에서. 원본 md5 a86dff1e 전후 동일. 워크트리 추적 파일 수정 0, 커밋·push·배포·ssh 0,
> 메인 data/ 는 읽기만(응답_L1·L3 json, PGJ*.xml), 8765 무접촉.
> **외부 요청 0**: 모든 스크립트에 소켓·DNS 가드(시도 기록 0), 스위트 netguard 기록 파일 없음, 브라우저 캡처는 루프백 밖 요청 전부 abort(차단 목록 0건 — 시도 자체가 없었다).
> 라이브 JSON 의 차대번호·등록번호 4개 문자열이 diff·새 테스트·담당 보고서에 있는지 대조 → 0건.

## 판정

**deployable.** 가장 큰 위험(정상 상세를 막아 새 차 분석이 멈추는 것)을 실제 응답 4종·합성 38종으로 깨 보려 했으나 깨지지 않았다.
같은 자리 행의 요청 바이트는 **다섯 경로 전부** 전송 계층에서 HEAD 와 같았고(담당과 다른 방법), 53697_4 는 예약 + 모의 매일 갱신 뒤
2,538,000 · 3,498cc · 0001001 · '관리상태 보통'으로 바로잡히고 나머지 1,618행은 HEAD 런과 비교해 변화 0 이었다.
비차단 7건 — N1(최종 검토 예산이 불일치에 안 걸림, 현재 영향 0)은 배포 뒤 1줄 수정, N2(롤백 뒤 낡은 확인 표지)는 §9 롤백 절차에 한 줄을 더한다(아래 '§9 에 더할 주의').

## must_fix — 없음

## 비차단

| # | 무엇 | 근거(재현) | 처방 |
|---|---|---|---|
| N1 | **최종 검토의 max_recheck(20)가 불일치에는 걸리지 않는다** — `review_daily_anomalies` 가 `DetailMismatch` 를 `continue` 로 넘겨 `reviewed` 를 올리지 않는다. HEAD 에선 같은 응답이 '성공'으로 예산을 썼다 | **합성** `qa18/p7/review_cap.py`: 이상 행 30 · 응답 전부 옆 매각물건 → 수정본 요청 **30**, HEAD **20**(HEAD 는 그 20건을 남의 값으로 'resolved' 저장). 오류 응답은 HEAD 도 예산을 안 썼다(기존 성질). **현재 영향 0**: 사본 이상 행 0 · 실행 기록 82건 중 검토 조각 0 · 감사기록 통틀어 quarantined 21·resolved 3 | 예산 판정에 불일치를 넣는다 — `if out["reviewed"] + out["mismatch"] >= max_recheck: break`. 1줄 + 테스트 1개 |
| N2 | **롤백 뒤 재배포하면 `detail_seq` 가 낡아 `redetail-key` 가 오염 행을 '확인됨'으로 건너뛴다** | **재현** `qa18/p4/rollback2.py`: 수정본 런 뒤(53697_4 바로잡힘·detail_seq '3') 옛 코드 최저가 재조회 → 키 4 로 물어 최저가 2,538,000→**1,715,000**(담당 §9 ⑵ 확인), 옛 코드 단건 분석 → 2,497cc·스타렉스 비고로 다시 오염, detail_seq 는 '3' 그대로 → 재배포 뒤 미리보기 `targets 0 · verified 1` | §9 롤백 절차에 `UPDATE vehicles SET detail_seq=NULL` 한 줄(열은 남겨도 됨 — 옛 코드는 이 열을 모른다) |
| N3 | **변이 생존 3건 = 테스트가 지키지 않는 동작 3개** (동작 자체는 코드상 맞음 — 아래 P5·P7 에서 내 스크립트로 확인) | `qa18/p10/mutate.py` 21개 중 생존: **M8** `detail_mismatch_total` 이 최저가 재조회 불일치를 빼도 초록 · **M12** 최저가 재조회에서 불일치가 연속 실패 카운터를 0 으로 되돌려도 초록 · **M13** `_analyze_item` 에서 `narrow_to_object` 를 빼도 초록(일괄매각 응답을 분석 경로로 통과시키는 테스트가 없다) | 테스트 3개: ⑴ 최저가 재조회만 불일치인 매일 갱신 → '⚠상세 불일치 1 보류' ⑵ 최저가 재조회 [비정상,불일치,비정상,비정상] → 4번째에서 중단 ⑶ 목적물 2개 응답을 단건 분석에 → 저장 배기량 = 고른 목적물 값 |
| N4 | 관리자 범례 새 두 줄이 390 에서 **단어 중간 줄바꿈 2곳을 더한다** — '기존 행 유/지', '매일 갱신/에'(기존 '등/록'·'법원/의'·1440 '마지/막' 위에) | **확인** 캡처 + 글자별 줄 위치 측정(`capture_result.json`) | AUD-17(범례 `word-break: keep-all`)에 묶는다. 관리자 전용 |
| N5 | 12:00 일일 리포트 파서가 '⚠상세 불일치 N 보류' 를 `unknown` 에 모은다 | **확인** `tools/daily_ops_report.parse_daily_message` → unknown | 알려진 AUD-17 — 확인만 |
| N6 | 응답의 순번이 실수(1.0)로 오면 거부된다(`_seq` 가 '1.0' 을 숫자로 안 봄) | **합성**. 실제 응답 4종은 모두 정수 | 정보용 — 실제로 본 적 없음 |
| N7 | `redetail-key --ids` 에 없는 id 를 넣어도 rc 0(`not_found` 에만 나옴) | **확인** CLI | 적용 출력의 `applied`·`not_found` 를 눈으로 본다(§9 주의 2) |

참고: 첫 전체 스위트는 23:53 시작 → 자정을 넘겨 **5 failed**(`test_ux3_sort_rules` 3·`test_ux_batch_qa_adversarial` 2) — 기존 **TEST-5**(날짜 경계) 그대로다.
두 파일 단독 재실행(자정 뒤) HEAD·수정본 모두 60/60, 두 번째 전체 실행 0 failed(아래 P7). 오늘 밤 배포 전 스위트를 자정 근처에 돌리면 같은 5개가 다시 빨갛다.

## 1~10 결과

### P1 정상 상세를 거부하지 않는가 — 깨지지 않음
- **실제 응답 전부(확인)**: 라이브 2(53697 seq3 · 101080 seq1, 정수 그대로) + 메인 `data/응답_L3_detail.json`·`응답_L3_detail2.json`(08-17 원형) + `tests/fixtures/detail_sample.json`. 저장소·data/ 를 더 찾았으나 L3 원형 응답은 이 다섯뿐(물건 폴더 detail.json 은 파싱 요약이라 번호가 없다). 파일마다 24가지: 보낸 매각물건 `'3'·3·' 3 '·'03'` × item_no `'4'·4·'04'·' 4'` 16 + 사건·법원 공백 1 + 응답 순번을 문자열·앞자리 0·공백으로 바꾼 3 = **통과 기대 20 → 20 통과**, 대조군(매각물건+1·목적물+1·법원·사건 바꿈) 4 → 4 거부. 5파일 **120/120 기대대로**. 줄인 응답의 차량 값 = item_no 로 고른 값(53697: 3498·0001001·254,047 / 101080: 0·0001002·104,115).
- **합성 38종**(`qa18/p1/identity_synth.py`): 키 누락(dx csNo·cortOfcCd·dspslGdsSeq·dx 블록·목적물 dspslGdsSeq) 전부 통과 · 목적물 번호 없음 1개+두 번호 같음 → legacy 통과 / 두 번호 다름 → 거부 · 일괄 [1,2] item 2 → 둘째(B) · 없음·중복·타입만 다른 중복 → 거부 · 다른 매각물건 섞임 → 거부 · 빈 목록·data null·{}·None → 통과(기존 '상세없음' 규칙) · csNo 정수·공백 → 통과 · csNo 표시형식('2025타경…')·법원코드 소문자 → 거부 · 두 자리 번호 10·12/13 → 통과. 37 기대대로 + 정보용 1(N6).
- **목록 maemulSer = doc_id 첫째 자리 — 담당 '추정'에 근거 보강(확인)**: 메인 `data/PGJ158M02.xml`(법원 화면 정의)의 예시 데이터 행 `docid …67` = `maemulSer "6"` · `mokmulSer "7"` — 두 번호가 **다른** 행 1건이 법원 소스에 있다. 같은 화면 JS 는 상세를 `dspslGdsSeq = getCellData(index,'maemulSer')` 로 연다(PGJ154M02·PGJ158M02·PGJ111M01 모두). PGJ154M03 은 화면의 목록번호(`tbx_mokSer`)에 `dspslObjctSeq` 를 넣는다 → 응답 목적물 번호 = 목록 mokmulSer. `data/응답_L1.json` 40/40 행 docid 끝 = (maemulSer, mokmulSer)(모두 같은 꼴이라 순서 증거는 아님).
- **내일 06:30 예상 불일치 수: 0 (추정)**. 근거: ⑴ 같은 자리 입찰예정 506행(10-03 기준) — 보내는 바이트가 HEAD 와 같다(P2 확인)·응답 모양은 실제 4종과 같다 ⑵ 다른 자리 3행 — 라이브 2건이 통과(확인) ⑶ 새 행(최근 일 4~44대)과 AUD-02 '@' 새 행(약 30) — 목록 maemulSer 를 저장해 묻는다 = 법원 화면이 쓰는 키(확인) ⑷ 최종 검토 대상 0행(확인). 남은 위험(미검증): '(중복)'·'(병합)' 사건의 응답 csNo 가 보낸 값과 다를 가능성(사본 16행·전부 지난 기일) · 한 매각물건에 같은 목적물 번호 2개. 터지면 저장하지 않고 '⚠상세 불일치 N 보류'(ops_health 경고, P8) — 조용한 오염이 아니라 보이는 보류다. 새 행이면 '미분석'(주행거리·사진 없음)이라 공개 목록에서 숨는다.

### P2 같은 자리 행 요청 바이트 불변 — 독립 재확인 일치
- 방법(담당과 다름): 진짜 `requests.Session` + `requests.adapters.HTTPAdapter.send` 가로채기로 **전송 직전 바이트**를 잡고, 다섯 경로를 각 트리에서 실제로 돌렸다(`qa18/p2/wire.py`). 응답은 `{}`.

| 경로 | 행 | 같은 자리 동일 | 바뀐 행 |
|---|---|---|---|
| analyze_single | 1,621 | **1,599/1,599** | 12(입찰예정 3 + 지난 기일 9) · 다른 자리 '(중복)/(병합)' 10행은 item_no 그대로 |
| _reanalyze(모든 행 '미분석' 사본) | 1,621 | 1,599/1,599 | 같은 12 |
| review_daily_anomalies(전 행 이상 강제) | 1,621 | 1,599/1,599 | 같은 12 |
| refresh_lagged_floors(sale_date ≥ 10-02, 담당과 같은 모수) | 520 | **517/517** | 3(53697_4 4→3 · 53697_5 5→4 · 101080_2 2→1) |
| daily_update 분석 단계(오늘 10-03 창) | 509 | 506/506 | 같은 3 |

- 경로별 POST·GET 수, 요청 URL 3종 HEAD = 수정본. `dspslGdsSeq` 는 두 트리 모두 문자열("1"). 빈 응답에서 끝난 DB 상태도 다섯 경로 모두 HEAD 와 행 차이 0(§10 ⑦).

### P3 53697_4 바로잡힘 — 확인(모의)
- `qa18/p3/sim.py`: 10-03 06:30 매일 갱신 1회(목록 509행·13쪽 합성, 법원 대역 — 53697 seq3·101080 seq1 은 라이브 JSON 그대로). 실제 CLI 로 `redetail-key` 를 먼저 적용한 사본과 아닌 사본.

| | 상세 POST | 53697_4 | 53697_5 · 101080_2 |
|---|---|---|---|
| HEAD | 9 | 2,497cc·0001002·1,715,000(그대로) | 상세없음 · 상세없음 |
| 수정본(예약 없음) | 9 | 그대로 | **완료 · 완료**(목록 재등장 복구 → 새 키) |
| 수정본 + 예약 | **10**(+1 = 53697 seq3) | **3,498cc · 0001001 · 2,538,000**(하한 2,538,000) · 비고 '전반적인 사용스크래치 있고, 관리상태 보통…' · maemul_ser 3 · detail_seq 3 | 완료(4/4) · 완료(0cc·0001002·104,115km·8,800,000·1/1) |

- 목록 최저가를 3,626,000(한 회차 지연 값)으로 바꿔도 결과 2,538,000 같음. 불일치 0 · ⚠ 조각 없음.
- **다른 행 변화 0**: HEAD 런 결과와 수정본+예약 런 결과를 행별 비교(maemul_ser·detail_seq·시각 열 제외) → 다른 행은 정확히 3행. 나머지 1,618행 0.
- 런 뒤 미리보기 → 대상 0(verified 3). 입찰예정 509행 전부 maemul_ser 저장.
- accident_grade 는 여전히 accident(기호5 '부식' — AUD-19 범위, 담당 §12 와 같음).

### P4 스키마·롤백 — 확인
- 수정본 `init_db`(미리보기 CLI 가 부름) → vehicles 에 TEXT 2열, 1,621행 전부 NULL. vehicles·anomaly_log·runs·settings 값 비교 → 기존 값 변화 0.
- 그 DB(수정본 런까지 돈 것)에 **옛 코드**: 모의 매일 갱신 rc 0(POST 7) · 화면 `/`·`/vehicles`·`/vehicle/{일반}`·`/vehicle/2025타경53697_4`·`/watchlist`·관리자 `/admin/anomalies` 전부 200 → **열을 남긴 채 롤백 가능**. 옛 코드는 detail.json 을 다시 읽지 않아 새 키 `object_seq` 도 무해(grep).
- 담당 §9 ⑴(예약 뒤 06:30 전 롤백): 옛 코드가 '미분석' 3행을 옛 키로 다시 받음 — 두 행은 HEAD 단독 런과 열 차이 0(상세없음 그대로), 53697_4 는 키 4 로 다시 물어 매각물건 4 응답을 저장(대역 법원이라 값은 합성 — 실제 법원이면 배포 전과 같은 스타렉스 값, 추정) → **맞다**. ⑵(06:30 뒤 롤백): 옛 최저가 재조회가 키 4 로 1,715,000 을 다시 씀 → **맞다**. 더할 것: N2.

### P5 AUD-02 '@' 행 결합 — 확인(합성)
- 같은 사건번호를 다른 법원(B000214)에 합성 2행(매각물건 1 에 목적물 1·2 일괄). 수정본: `…_1@B000214` 는 (saNo, **B000214**, '1') 로 묻고 쏘나타 1,999cc, 형제 `…_2` 는 같은 키로 아반떼 1,598cc — 각자 제 목적물. 기존 B000250 행 영향 없음. **HEAD 는 '@' 행에 아반떼 1,598cc·40,000km([0] 고정)를 저장하고 `_2` 는 상세없음** — 일괄매각 '@' 행에서 수정본이 바로잡는 것을 보였다.
- 키 해석 직접 호출: '@' 행 저장값 없음 → doc_id('…34'→'3', '…11'→'1') · 저장값 '3' → stored · doc 앞 7자 ≠ court_code → item_no · 저장값 ' 03 '·'abc'·'0' → 무시하고 doc_id · '10' → stored · '(중복)' → item_no.

### P6 redetail-key — 확인
- 실제 CLI(`python -m web.maint redetail-key`, 사본 DATA_DIR): ① 미리보기 rc 0 · 대상 **3**(target_wrong 1·target_missing 2) · past 1,112 · same_key 506(10-03 기준 — 담당 1,101/517 은 10-02 기준, 11행 날짜 이동) ② `--apply` 단독 rc 2 ③ `--apply --dry-run` rc 2 ④ `--ids`(빈 값) rc 2 ⑤ same_key 행 + 없는 id → applied 0 · not_found 표시 · rc 0(N7) ⑥ `--ids 3행 --apply` → applied 3 · requeued 3줄 ⑦ 다시 미리보기 0(queued 3) ⑧ 같은 적용 반복 0. 미리보기는 행 데이터 쓰기 0(표별 값 비교) — 단 `init_db` 로 열은 더한다(배포 뒤엔 이미 있음).
- **매일 갱신 도중 실행**(같은 DB 파일·두 프로세스, `qa18/p3/conc.py`): A 목록 단계 중 적용 → CLI rc 0(잠금 대기 포함 5초) · 같은 런에서 3행 모두 바로잡힘. B 분석 대상이 정해진 뒤 적용 → CLI rc 0 · applied 1(나머지 둘은 그 순간 verified/queued) · **53697_4 는 '미분석'·2,497cc·1,715,000 인 채 런이 끝남**(다음 런까지 그대로, 최저가 재조회 대상에서도 빠진다). 두 경우 모두 'database is locked' 0.

### P7 C.4 — 확인 (N1 하나)
- 외부 요청 호출 위치: 두 트리 모두 24곳 · `fetch_detail(` 4곳(1:1 교체). diff 에서 sleep·지연 상수·상한·예산·`_is_block`·`_check_block`·재시도 변경 0 — 바뀐 것은 최저가 재조회의 `consecutive_fail = 0` 이 확인 통과 안으로 들어간 것뿐.
- **[비정상, 불일치, 비정상, 비정상]**(`qa18/p7/counter.py`): 수정본은 매일 분석·최저가 재조회·_reanalyze 세 경로 모두 **4번째 요청에서 중단**('비정상 응답 3회 연속'), HEAD 는 불일치가 카운터를 0 으로 되돌려 5번째까지 간다. `_is_block(DetailMismatch(...))` = False, 메시지 '상세 불일치: …'(‘차단’ 없음).
- 예산: N1(최종 검토). 수동 /run 은 scan_limit 로, _reanalyze 는 대상 수(사본 18행)로 묶여 있다(불일치·빈 응답·오류 모두 기존과 같은 처리).
- **전체 스위트**(사본 트리 · `PYTHONPATH=…/scratchpad/netguard -p netguard` · `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`): 2회차 00:12:46–00:27:10 **3,089 passed · 1 skipped · 5 xfailed · 0 failed**, netguard 기록 파일 없음. 1회차는 자정을 넘겨 TEST-5 5개 빨강(위 참고). 수집 수 HEAD 3,048 → 3,095(**+47**, 감소 0). 최신 메인 backlog(74ae8b7)로 backlog 읽는 테스트 11파일 348 passed · 2 xfailed. 알려진 흔들림 `test_second_link_during_slow_navigation_keeps_skeleton` 은 두 회차 모두 초록.

### P8 ops_health — 확인
- `ops_health._runs_signal`: 실행 기록에 '⚠상세 불일치 2 보류' → **warn · 'done(경고 포함)'**, 조각 없으면 ok. 조각이 '분석 N' 뒤에 붙어도 `parse_analyzed` 는 그대로 6.
- 12:00 리포트 `parse_daily_message` → unknown(N5, AUD-17).

### P9 화면(관리자 전용 문자열 3개) — 확인
- `screenshots/aud18-qa/`(`BASELINE.txt` 에 기준 한 줄 — 워크트리 미커밋·diff md5·DB 사본 md5). before = HEAD 코드(127.0.0.1:8041), after = 수정본(8042), **같은 DB 사본**. 불일치 안내는 실제 라우트(`POST /vehicle/{id}/analyze`, 법원 대역)로 만든 문구 그대로 — 303 → `?an=법원 상세가 이 물건과 달라 저장하지 않았습니다(매각물건 4≠3, 목적물 4 없음). 관리자 무결성 검토 기록에 남겼습니다.`, 행 값 변화 0.
- md5 — 범례 1440 ab79cc45 → 788191fc · 390 fc0dd2e9 → 072c0554 · 안내 1440 49591088 → c0e8f5e9 · 390 d291af18 → 05a05618. 22장 중 같은 md5 0.
- 프레임 안: 범례 1440 y 74–108 · 390 y 74–210(x 32–358) · 안내 1440 y 96–146 · 390 y 80–166(x 16–374) — 모두 뷰포트 안.
- 단어 중간 줄바꿈: 범례 N4. **안내 문구는 1440·390 모두 0**. 관리자 범례 화면의 390 가로 스크롤(scrollWidth 476)은 before 도 476(표 폭, 기존).
- 공개 4화면(수정본) 1440·390 모두 200, 가로 넘침 0. 화면 템플릿·CSS 변경 0 이라 `build:css` 불필요.
- ⚠ 1차 캡처의 before 2장(1440·390)이 **스플래시 화면**이었다(파일명 ≠ 화면) — 세션 스플래시를 끄고 다시 찍었다. 위 md5 는 다시 찍은 것.

### P10 변이 시험 — 21개 중 18 잡힘
잡힘: 키 우선순위 뒤집기(M1, 6 빨강) · 목적물 비교 제거(M2, 9) · 불일치에도 저장(M3, 5) · 사건·법원 비교 제거(M4, 2) · doc_id 두 자리 순서 뒤집기(M5, 11) · 매일 분석 불일치가 카운터 0(M6) · 메시지에 '차단'(M7) · 지난 기일도 예약(M9) · 목록 빈 값으로 저장값 지움(M10) · 최저가 재조회가 불일치에도 씀(M11) · 기호에 매각물건 번호(M14) · `--apply` 단독 허용(M15) · 매각물건 비교 제거(M16) · legacy 아무 하나나(M17) · verified 무시(M18) · detail_seq 저장 안 함(M19) · doc_id 법원 검사 제거(M20) · 최종 검토가 item_no 로(M21). **생존 3: M8·M12·M13**(N3).

## §9 배포 순서에 더할 주의
1. **redetail-key 는 06:30 런의 분석 단계가 대상을 정하기 전에.** 그 뒤에 적용하면 53697_4 가 '미분석'·옛 값(1,715,000)인 채 하루를 넘기고 최저가 재조회 대상에서도 빠진다(P6 B). 늦었으면 관리자 화면 '다시 분석'(analyze_single — 새 키로 묻는다).
2. 적용 출력에서 `applied: 3` · `not_found: []` 를 눈으로 본다 — 오타 id 도 rc 0 이다(N7).
3. 06:30 실행 기록에 '⚠엔카 blocked' 가 있으면(`daily_update` 의 엔카 차단 조기 감지 — `encar_health` 가 blocked 일 때만) 분석 단계가 통째로 건너뛰어져 예약한 3행이 '미분석'으로 남는다. 그날은 바로잡히지 않은 것이다('error' 등 다른 상태는 분석이 돈다).
4. **롤백**: `git revert` 와 함께 `UPDATE vehicles SET detail_seq=NULL`(N2). 열 DROP 은 불필요.
5. 배포 전 스위트를 자정 근처에 돌리면 TEST-5 의 5개가 빨갛다 — 두 파일만 다시 돌려 초록이면 AUD-18 과 무관.

## 배포 뒤 확인 SQL — 대조
- 담당 ① `SELECT id,status,displacement_cc,fuel_code,min_sale_price,maemul_ser,detail_seq FROM vehicles WHERE id IN (…3행)` → 모의 결과 53697_4 = (완료, 3498, 0001001, 2538000, 3, 3) — **맞다**(최저가 기대값은 10-12 기일 전까지만 유효).
- 담당 ② `… ts>=date('now','localtime') … GROUP BY action` → requeued 3 · detail-mismatch 0 — 맞다. 단 **적용을 자정 전에 하고 다음 날 확인하면 requeued 가 0 으로 보인다** — 날짜를 적용일로 고정해 쓴다(`ts >= '2026-10-03'`).
- 담당 ③ '⚠상세 불일치' 없음 · ④ 미리보기 대상 0(verified 3) — 모의에서 그대로 나왔다.
- **더할 것(읽기 전용)** — 담당의 '추정'(목록 maemulSer = doc_id 첫째 자리)을 실데이터 500여 행으로 처음 확인하는 질의:
  `SELECT count(*) up, sum(maemul_ser IS NOT NULL) with_key, sum(maemul_ser IS NOT NULL AND length(doc_id)=23 AND maemul_ser<>substr(doc_id,22,1)) key_ne_doc FROM vehicles WHERE sale_date>=date('now','localtime')` → with_key ≈ up(목록에 나온 행), **key_ne_doc 0** 기대.
  `SELECT vehicle_id, note FROM anomaly_log WHERE action='detail-mismatch' AND ts>='2026-10-03'` → 0행 기대. 있으면 note 의 사유(사건≠ 이면 중복·병합 계열)를 본다.

## 확인 · 합성 · 추정 · 미검증
- **확인**: 실제 응답 5파일 120/120 · 전송 계층 바이트 5경로(1,599/1,599 ×3 · 517/517 · 506/506) · 요청 수·URL 동일 · CLI 8단계 · 스키마/롤백 화면 200 · 롤백 ⑴⑵ · 카운터 3경로 · ops_health warn · 캡처·md5·프레임 · 스위트 3,089/0 failed · 변이 18/21 · 법원 화면 소스의 두 번호 뜻(PGJ158M02 예시 행·화면 JS) · 외부 요청 0.
- **합성**(대역 법원 위 모의): P3 수치(53697_4 의 값은 라이브 JSON 이라 실제 응답 그대로, 다른 행 응답은 합성) · P5 '@' 일괄 · N1 · 동시 실행 A/B.
- **추정**: 06:30 불일치 0 · 목록 maemulSer = doc_id 첫째 자리(근거 보강 — 법원 예시 1행, 실데이터 확인은 위 추가 SQL).
- **미검증**: 중복·병합 사건의 실제 응답 csNo · 실제 일괄매각 응답 · 두 자리 목적물 번호의 docid 형식 · 서버 06:30 실제 대상 수 · 서버 시간대(확인 SQL 의 localtime 이 KST 라는 가정).

## 산출물
- 캡처: `C:/Users/14ZB95N/법원경매조회 및 분석/screenshots/aud18-qa/`(PNG 22장·`BASELINE.txt`·`capture_result.json`)
- 스크립트·로그(scratchpad `qa18/`): `p1/identity_real.py`·`identity_synth.py` · `p2/wire.py`·`wire_floor.py`(+ `wire_*.json`) · `p3/sim.py`·`sim_slow.py`·`conc.py`·`cli_*.json`·`sim_*.json` · `p4/rollback2.py`·`smoke.py` · `p7/counter.py`·`review_cap.py` · `p9/prep.py`·`capture.py` · `p10/mutate.py`·`mutate.log` · `suite_new.log`(자정 넘김)·`suite_new2.log`(0 failed)
