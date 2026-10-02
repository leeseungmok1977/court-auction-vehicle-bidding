---
order: 2026-10-02-15
from: backend-engineer
ticket: AUD-18
result: done
verified: 재현
handoff:
  - to: qa-engineer
    why: "AUD-18 반증 검수 — 워크트리 agent-a19bd3bb07a85daa4 의 미커밋 diff(코드 8파일 + 수집URL정의서) 와 tests/test_aud18_detail_key.py(47개). scratchpad/aud18/work 의 replay.py·compare_bytes.py·compare_daily_keys.py·maint_cli.py 로 '같은 자리 1,599행 요청 바이트 불변 · 다음 매일 갱신 +1 요청(예약 시) · 외부 요청 0' 을 다시 확인하고 §10 '깨 볼 곳'을 시도. 통과하면 Steward 가 배포(오너 승인 10-02) → 06:30 전에 redetail-key 미리보기 → --ids 적용(§9)"
---

# AUD-18 — 상세 조회 키를 매각물건 번호로 바로잡고, 받은 상세가 우리 물건일 때만 저장 (backend-engineer, 지시서 2026-10-02-15)

> 작성 22:58~23:55 · 기준 `6687944` · 워크트리 `.claude/worktrees/agent-a19bd3bb07a85daa4`(**미커밋**). 커밋·push·배포·ssh 0, 법원·엔카·케이카 요청 0,
> 메인 저장소 data/·8765 무접촉. 데이터: Steward 10-02 17:15 서버 백업 사본 `scratchpad/aud18/live_1002.db`(md5 a86dff1e — 읽기만, 모든 재현은 복사본에서, 전후 md5 동일)
> 와 라이브 응답 JSON 2건(읽기만 — 차대번호·등록번호는 테스트로 옮기지 않았다).
> 경로: 지시서 `output` 칸 이름을 따랐다(인계 메시지의 `…-aud18-backend.md` 와 다름). 워크트리 격리로 메인 저장소 `reports/` 에 쓰기가 막혀
> **이 파일은 워크트리 `reports/` 에 있다** — Steward 가 메인 저장소 `reports/` 로 옮겨야 순환계가 읽는다.

## [요약]
1. **키**: 상세를 묻는 다섯 경로(매일 갱신 분석·`_reanalyze`·`review_daily_anomalies`·`analyze_single`·`refresh_lagged_floors`)가 이제 `dspslGdsSeq` 에 **매각물건 번호**를 보낸다. 출처 순서 ⑴ 목록 행 maemulSer 를 저장한 값 ⑵ doc_id 끝 두 자리(형식 검사 통과 시) ⑶ item_no(예전 식 그대로). 수동 `/run` 은 원래 목록 행을 넘기던 그대로다.
2. **확인**: 받은 상세는 저장(행·사진 폴더·분석) **전에** 사건·법원·매각물건 번호가 보낸 값과 같고 목적물 목록에 `dspslObjctSeq == item_no` 인 원소가 정확히 하나 있을 때만 쓴다. `[0]` 고정을 없앴다(일괄매각). 아니면 아무것도 쓰지 않고 anomaly_log `detail-mismatch` + 매일 갱신 실행 기록 `⚠상세 불일치 N 보류`(ops_health 경고).
3. **기호**: `parse_detail` 의 요항 주행거리 보조 추출이 매각물건 번호가 아니라 **목적물 번호**로 기호를 고른다(53697: 3 → 기아 237,768 / 4 → 벤츠 254,047).
4. **복구**: `python -m web.maint redetail-key`(미리보기 → `--ids … --apply` → 멱등). 사본 기준 대상 3행 — 53697_4(옆 물건 상세, target_wrong) · 53697_5·101080_2(상세없음, target_missing). 다음 매일 갱신의 분석 단계가 **기존 상한·지연 안에서** 다시 받는다(별도 요청 없음). 상세없음 2행은 예약 없이도 같은 런에서 복귀한다(코드·재현 확인 — §6).
5. **새로 확인한 피해**: 53697_4 는 배기량·연료·비고만이 아니라 **최저가도 옆 물건 것**이었다. 저장 기일내역 5,000,000→3,500,000→2,450,000→**1,715,000**(스타렉스 매각물건), floor_checked_at 2026-10-01 06:49:45 — 최저가 재조회(REC-1)가 item_no 로 물어 옆 매각물건 기일내역을 썼다. 실제 이번 회차 최저가는 **2,538,000**(라이브). 화면이 법정 최저가보다 82.3만 원 낮게 보이고 있었다(그 금액으로 쓰면 무효 입찰). 수정본 재현에서 2,538,000 으로 바로잡힌다.
6. **스키마 변경 있음** — vehicles 에 TEXT 열 2개(`maemul_ser`·`detail_seq`), `init_db` ALTER 가드(기존 마이그레이션 방식), 기존 행 값 NULL. **템플릿이 쓰는 dict 키 변경 없음**(frontend 반영 불필요).
7. 테스트: 새 47개 — HEAD 코드에 대면 44 빨강·3 초록(초록 3개는 '바뀌면 안 되는 것' 회귀 가드). 전체 스위트(사본 트리·netguard) HEAD **3,042 passed** → 수정본 **3,089 passed · 1 skipped · 5 xfailed · 0 failed**, 네트워크 시도 0.

## 1. 설계
- **두 번호**(Steward 라이브 검증): 요청 `dspslGdsSeq` = 목록 `maemulSer` = 매각물건 번호. 응답 `gdsDspslObjctLst[].dspslObjctSeq` = 목록 `mokmulSer` = 앱 `item_no` = 목적물 번호. doc_id 끝 두 자리 = (매각물건, 목적물).
- **키 해석** `web/service.py::detail_request_seq` → `(값, 'stored'|'doc_id'|'item_no')`, raw 는 `_detail_raw`. doc_id 해석 `_docid_seqs` 의 검사: 23자 · 앞 7자 == court_code · 다음 14자 == 사건번호로 만든 saNo(`list_parser.sano_from_case_no`, `case_no_from_sano` 의 역) · 끝 두 자리 숫자(첫째 0 아님) · **둘째 자리 == item_no**(지시 외 추가 — 해석이 이 행 목적물과 맞을 때만. 사본 1,621/1,621 만족, 강화 방향). item_no 대체는 예전 식 `item_no or "1"` 그대로(같은 자리 행 바이트 불변의 근거).
- **저장**: `VehicleItem.maemul_ser`(목록 파서가 채움) → `_listing_rec` 이 값이 있을 때만 싣는다(빈 값으로 저장값을 지우지 않음) → `upsert_listing` 이 신규·갱신 모두 덮는다(`_LISTING_KEEP` 아님). 분석이 확인한 키는 `detail_seq`(분석만 쓴다 — `_LISTING_KEEP` 에 넣음). 수동 `/run` 은 `_analyze_item` 이 목록 값을 함께 저장.
- **응답 확인** `src/parse/detail_parser.py::detail_identity` · 목적물 고르기 `_pick_object_index`/`pick_vehicle_object` · 확인한 하나로 줄이기 `narrow_to_object`(얕은 사본, 원본 불변). `_analyze_item` 은 확인 → 줄인 응답으로 `parse_detail`·`save_item_folder`(detail.json 도 확인한 목적물). 불일치는 `DetailMismatch` 예외 — 다섯 호출부가 모두 따로 잡는다(§3).
- **C.4-5**: 불일치는 정상 JSON 이라 '비정상 응답'으로 세지 않지만 **연속 실패 카운터를 0 으로 되돌리지도 않는다** — 예전엔 같은 응답을 성공으로 보고 0 으로 되돌렸으니 그보다 약해지지 않는다(테스트: [비정상, 불일치, 비정상, 비정상] → 3번째 비정상에서 중단, HEAD 는 안 멈춤). 메시지에 '차단' 없음(`_is_block` 문자열 판정 회피). 지연·재시도·차단중단·상한 코드 무변경.

## 2. 바꾼 파일 (md5 = 워크트리 = 스위트를 돌린 사본 트리)
| 파일 | +/− | md5 | 내용 |
|---|---|---|---|
| `src/parse/detail_parser.py` | +136/−11 | c174cf89 | `_seq`·`_pick_object_index`·`pick_vehicle_object`·`detail_identity`·`narrow_to_object`, `_vehicle_obj(result, item_no)`, `parse_detail(…, item_no=None)` 기호 키 = 목적물 번호, `DetailInfo.object_seq` |
| `src/parse/list_parser.py` | +18 | 1f67e29a | `sano_from_case_no`, `VehicleItem.maemul_ser`(기본 '') |
| `web/service.py` | +245/−20 | 3f483d9b | 키 해석·`DetailMismatch`·`_log_detail_mismatch`, `_analyze_item` 확인·줄이기·`detail_seq`, 다섯 경로, `detail_mismatch_total`·실행 기록 조각, `redetail_key` |
| `web/db.py` | +9/−1 | 177f3beb | ALTER 열 2개, `_LISTING_KEEP` 에 `detail_seq` |
| `web/maint.py` | +22 | f33d6e21 | `redetail-key` 명령(인자 규칙은 reprice-accidents 와 같음) |
| `web/app.py` | +6/−1 | 11876e41 | 관리자 `/admin/anomalies` 범례 2개, `/vehicle/{id}/analyze` 불일치 안내 1종(관리자 전용) |
| `src/pipeline.py` | +12/−3 | c3d89ec2 | 검증 CLI 도 같은 확인·줄이기 |
| `src/collect/courtauction_detail.py` | +8/−3 | 4f0f9b3e | 데모 `main` 도 같은 확인·줄이기 |
| `docs/수집URL정의서.md` | +9/−2 | 170733f5 | L1 표 두 번호 뜻 · L3 '두 번호는 다를 수 있다'·목적물 고르기·기호 |
| `tests/test_aud18_detail_key.py` | 새 718줄 | 5fc63524 | 47개 |

## 3. 상세 요청 경로 전수 (전부 찾았다는 근거)
`grep -rn "fetch_detail(" web src tools scripts`(정의 제외) → **4곳**: `web/service.py::_analyze_item` · `web/service.py::refresh_lagged_floors` · `src/pipeline.py::run` · `src/collect/courtauction_detail.py::main`. `_analyze_item` 의 호출부 `grep "_analyze_item("` → **5곳**: `_run_collection`(목록 행 그대로 — 변경 없음, 테스트로 고정) · `_reanalyze` · `daily_update` 분석 · `review_daily_anomalies` · `analyze_single` → 넷 모두 `_detail_raw(v)`. `refresh_lagged_floors` 도 `_detail_raw(v)`. `"maemulSer": v.get("item_no")` 식은 web·src 에서 0(테스트가 고정). 0표본 재조회(`requery_missing_market` → `recompute_all_market`)는 법원 상세를 부르지 않는다(엔카만 — grep 확인). tools·scripts 0곳. 새 테스트 `test_상세_요청_경로_전수…` 가 호출 위치 4곳 목록과 각 함수의 `detail_identity(` 호출을 고정한다(새 경로가 생기면 빨강).

## 4. 옛 응답 모양(목적물 번호 없음)과 빈 응답의 규칙 — 근거
- 실제 응답은 기일정보·목적물 모두에 csNo·cortOfcCd·dspslGdsSeq·dspslObjctSeq 가 있다(라이브 2건·픽스처 detail_sample.json 모두). 키가 빠진 모양은 축소 픽스처·합성 응답뿐.
- **있는데 다르면 불일치, 없는 키는 비교하지 않는다.** 사건·법원은 요청을 되돌려 주는 `dspslGdsDxdyInfo` 만 본다 — csBaseInfo·사진·감정요항(사건 단위)의 값은 중복·병합 사건에서 무엇인지 원문을 본 적이 없어 비교하지 않는다(모르는 값으로 정상 상세를 막지 않음, C.4-3).
- 목적물: 번호가 있으면 `== item_no` 하나(없으면 not_found·둘이면 duplicate). **번호가 아예 없으면 목적물이 1개이고 dspslGdsSeq == item_no 일 때만**(legacy) — 두 번호가 같으면 갈릴 여지가 없다(사본 1,599행이 그 꼴). 그 밖은 고르지 않는다. 목적물이 없는 응답은 불일치가 아니다 → 기존 빈 응답 규칙('상세없음'/'종결')이 그대로 처리.
- `parse_detail(resp)` 를 item_no 없이 부르면(데모·기존 단위 테스트) 목적물이 하나일 때만 그것, 여럿이면 차량 필드를 비운다. 기존 테스트 전부 통과.

## 5. 감정요항 '기호' 사용처 전수
`grep slice_for_symbol|is_multi_symbol|_mileage_from_text|item_no=` → 고친 곳은 `parse_detail` 한 곳(매각물건 번호를 넘기던 것 → `item_no` 또는 고른 목적물의 `dspslObjctSeq`, 모르면 넘기지 않아 다물건 글이면 값 없음). 이미 목적물 번호(item_no)를 쓰던 곳: `_appraisal_signals`(분석·재교정·백필) · `backfill_multilot_mileage`. 키 없이 읽어 다물건 글에서 값을 만들지 않는 곳: `backfill_mileage_from_files` · `parse_appraisal` 의 mileage — 손대지 않음. `_analyze_item` 의 `getattr(detail, "item_no", None) or item.item_no` 는 늘 None 이던 앞부분을 걷어 `item.item_no` 로(값 동일). 사고 판정 범위(`grade_accident`)는 지시대로 손대지 않음 — §12.

## 6. 복구 장치 — `redetail-key`
- 대상: 매각기일 ≥ 오늘 · 매각 안 끝남 · 받을 키 있음 · **새 키 ≠ 예전 키(item_no)** · 이미 분석 대기(미분석·미매핑) 아님 · 새 키로 확인한 상세(`detail_seq`) 아님. 사유 target_wrong(상세 있음) / target_missing(상세없음). 건너뜀 past·closed·no_key·same_key·queued·verified.
- 적용 = status '미분석' + anomaly_log `requeued` 한 줄. 상세 값은 지우지 않는다(다시 받으면 덮이고, 그 전까지 화면은 지금 그대로). `--apply` 는 `--ids` 와 함께만(reprice-accidents 규칙), `--apply --dry-run` 거부.
- 멱등: 예약 뒤 queued, 다시 받은 뒤 verified 로 빠진다(재현: 3 → 0 → 0).
- '상세없음' 2행은 예약 없이도: 목록에 다시 보이면 `db.mark_disappeared` 가 '미분석'으로 되돌리고(완전 스캔·관측 80%↑일 때) 같은 런 분석 단계가 묻는다 — 사본의 두 행 analyzed_at 10-02 06:37 이 그 순환(예전 키라 빈 응답). 테스트·재현 모두 복귀 확인. 완전 스캔이 아닌 날을 대비해 명령은 두 행도 함께 예약한다.

## 7. 운영 DB 사본 재현 (`scratchpad/aud18/work/` — 복사본·소켓 가드·법원/엔카 대역, 원본 md5 전후 a86dff1e)
| 항목 | 결과 |
|---|---|
| 요청 바이트 — `analyze_single` 경로, 1,621행 전부(HEAD vs 수정본, 실제 `fetch_detail` + 가짜 세션) | 끝 두 자리 같은 **1,599/1,599 동일**. 바뀐 행 **12**(입찰예정 3: 53697_4 4→3 · 53697_5 5→4 · 101080_2 2→1 / 지난 기일 9). '(중복)·(병합)' 10행은 item_no 그대로(사건번호 형식 밖) |
| 요청 바이트 — 최저가 재조회 경로, 입찰예정 520행 강제 대상 | 같은 자리 **517/517 동일**, 바뀐 3행 = 위 입찰예정 3행 |
| 키 출처(사본 그대로) | doc_id 1,605 · item_no 16(전부 '(중복)·(병합)', 모두 지난 기일) · 저장값 0. 입찰예정 520 = doc_id 520 |
| 키 출처(다음 매일 갱신 재현 뒤) | 입찰예정 520 = **저장값 520** · 그 밖 doc_id 1,085 · item_no 16 |
| 복구 미리보기 | 대상 3(target_wrong 1 · target_missing 2), past 1,101 · same_key 517 · 그 밖 0 → 적용 3 → 다시 0(queued 3) |
| 다음 매일 갱신 재현(목록 520행 합성, 가짜 법원은 매각물건 번호로 찾음 — 53697_4 seq3·101080_2 seq1 은 라이브 JSON) | HEAD: 상세 요청 9 · 분석 3 · 두 행 상세없음 그대로 / 수정본: 9 · 5 · 두 행 복귀 / 수정본+예약: **10 · 6 · 세 행 복구**, 불일치 0, ⚠ 조각 없음 |
| 요청 키 다중집합 대조 | 수정본 vs HEAD: 다른 것은 상세없음 2행의 키뿐(5→4·2→1). 예약 시 +1 = (53697, '3') |
| 53697_4 (예약 + 재현 뒤) | 2,497cc·0001002·1,715,000·스타렉스 비고 → **3,498cc·0001001·2,538,000**·'관리상태 보통' 비고, maemul_ser 3·detail_seq 3. accident_grade 는 여전히 accident(기호5 '부식' — §12) |
| 101080_2 | 상세없음 → 완료(코란도 2019, 104,115km, 최저가 8,800,000) |
| 명령 리허설(`maint_cli.py`, `python -m web.maint redetail-key` 그대로) | ① 미리보기 3 ② `--apply` 만 rc 2 ③ `--ids … --apply` 3 ④ 0 |
| 외부 요청 | 재현 소켓 가드 0건 · 스위트 netguard 기록 파일 없음(netguard.py md5 e3c7b9b6 불변) |

## 8. 테스트
새 `tests/test_aud18_detail_key.py` 47개(합성 값만 — 사건번호·법원코드·차대번호 모두 지어낸 것). 새 함수 import 는 테스트 안에서 하게 해 HEAD 에서 테스트별로 빨강이 나게 했다: HEAD 코드 + 이 파일 = **44 빨강 · 3 초록**(초록 = 같은 자리 행 요청 바이트 2건·불일치 없으면 조각 없음 — 회귀 가드라 HEAD 에서도 초록이 맞다). 행동 빨강 예: 보낸 키 `'4'`≠`'3'` · `'5'`≠`'4'` · 기호 237,000≠254,000 · '3회 연속' 중단 안 함 · 정의서 위반 식 잔존. 전체 스위트(사본 트리 · `-p netguard` · `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`): HEAD 3,042 passed · 1 skipped · 5 xfailed(23:11–23:26) → 수정본 **3,089 passed · 1 skipped · 5 xfailed · 0 failed**(23:28–23:44).

## 9. 배포 순서 · 롤백 · 다음 매일 갱신
- **배포**: qa 통과 → 커밋·push → EC2 DB 백업(서버 사본 `/home/ubuntu/backups`) → pull·재시작(기동 `init_db` 가 열 2개 추가 — 기존 값 NULL) → **06:30 전에** `python -m web.maint redetail-key`(미리보기, 사본 기준 3행) → `python -m web.maint redetail-key --ids 2025타경53697_4,2025타경53697_5,2026타경101080_2 --apply`(미리보기에 나온 id 로).
- **06:30 런에서 생길 일**: 목록 요청 수 불변, 입찰예정 행 전부에 maemul_ser 저장(사본 520). 최저가 재조회 요청 수 불변(대상 선정·하루 60 상한 무변경, 키만 3행에서 다름). 분석 단계 상세 요청 **+1**(53697_4 — 예약했을 때), 53697_5·101080_2 는 이미 매일 묻던 행이라 +0 — 이번엔 상세를 받아 목록에 돌아온다. 소요 +5~10초(추정). AUD-02 '@' 새 행(약 30대)은 이 수정과 무관하게 같은 요청 수이고, 목록에서 maemul_ser 를 받은 뒤 처음부터 올바른 키로 분석된다.
- **배포 뒤 확인(읽기 전용)**: `SELECT id,status,displacement_cc,fuel_code,min_sale_price,maemul_ser,detail_seq FROM vehicles WHERE id IN ('2025타경53697_4','2025타경53697_5','2026타경101080_2')` → 53697_4 = 3498·0001001·2538000·3·3 · `SELECT action,count(*) FROM anomaly_log WHERE ts>=date('now','localtime') AND action IN ('detail-mismatch','requeued') GROUP BY action` → requeued 3, detail-mismatch 0 기대 · 실행 기록에 '⚠상세 불일치' 없음 · `redetail-key` 미리보기 → 대상 0(verified 3).
- **롤백**: `git revert` → 배포·재시작. 열 2개는 남겨도 된다(옛 코드는 이름을 부르지 않고, upsert 는 실린 열만 쓴다 — DROP 불필요). 영향: ⑴ 예약 뒤·06:30 전 롤백이면 세 행이 '미분석'인 채 옛 키로 다시 받는다 — 53697_4 는 다시 스타렉스 상세, 두 행은 다시 상세없음(배포 전과 같은 상태, 더 나빠지지 않음) ⑵ 06:30 뒤 롤백이면 바로잡힌 값은 남지만 옛 최저가 재조회가 53697_4 를 다시 대상으로 잡는 날(백오프 3일) item_no 로 물어 옆 매각물건 최저가를 다시 쓴다.

## 10. qa 가 깨 볼 곳
① 일괄매각 실제 응답(매각물건 하나에 목적물 둘 이상) — 합성으로만 시험(사본 예: 2026타경30359_1·_2, 지난 기일) ② 중복·병합 사건 응답의 `dspslGdsDxdyInfo.csNo` 가 보낸 값을 되돌려 주는지 — 다르면 '저장 안 함 + ⚠'(조용한 오염은 아님) ③ 목적물 번호 10 이상(doc_id 23자 규칙 밖) — 저장값 없으면 item_no 로 묻고 두 번호가 다르면 불일치로 막힘 ④ 목록 maemulSer 빈 값·숫자 아님 ⑤ `[비정상, 불일치, …]` 연속 카운터·차단 문자열 ⑥ 06:30 런 도중 `redetail-key --apply` ⑦ 빈 응답(상세없음)에서 예전과 같은 결과인지 ⑧ 관리자 단건 분석의 불일치 안내(`/vehicle/{id}?an=…`) ⑨ 롤백 리허설(§9).

## 11. 확인 · 추정 · 미검증
- **확인**: §7 전부(사본 복사본·라이브 JSON 2건으로 재현), §3 전수 grep, 테스트 결과, 53697_4 최저가 오염(사본 기일내역 vs 라이브 seq3), 외부 요청 0.
- **추정**: 목록 maemulSer == doc_id 첫째 자리(라이브 2건 + 22/22 둘째 자리 == item_no 에서 나온 해석 — 재현의 목록 합성이 이 해석을 썼으므로 '저장값≠doc_id 0' 은 동어반복이다) · 53697_4 의 저장 주행거리 254,047 은 옛 코드가 스타렉스 응답에서 구조화 값이 비어 '기호4'(벤츠)를 집은 결과(값이 우연히 맞음) · 06:30 런 +1 요청·+5~10초.
- **미검증**: 일괄매각·중복/병합·두 자리 목적물 번호의 실제 응답, 서버 06:30 런의 실제 분석 대상 수(재현의 '오늘'은 시스템 날짜 10-02 — 실제 런은 10-03).

## 12. 범위 밖 관찰(고치지 않음)
1. **다물건 감정요항 전체 글로 도는 판정 두 개**(제외 범위와 같은 부류) — 53697_4 라이브 글 실측: `grade_accident` 전체 글 accident['부식'](기호5 스타렉스) vs 기호4 구간 none · `condition_adjustment` 전체 글 **+2,200,000원**(관리·외관 불량 + 시동·운행 불가 — 기호1·3·5) vs 기호4 구간 +250,000원(검사 경과). `calculator.calculate` 가 요항 전체로 `condition_adjustment` 를 불러 **상한가에 남의 차 상태 비용이 들어간다**. 저장 신호(`_appraisal_signals`)는 기호 구간으로 잘라 옳아서 두 경로가 갈린다. 판정·금액이 바뀌므로 Steward 가 올릴 '다물건 사고 낱말 범위' 티켓에 함께 묶기를 권고. 영향 상한(추정 — 사본에 요항 원문 없음): 입찰예정 520 중 다물건 사건 42행 · accident 18 · 근거가 자유서술 낱말뿐 **12**(`accident_proxy.py`).
2. 12:00 일일 리포트(`tools/daily_ops_report.py`)는 '⚠상세 불일치 N 보류' 조각을 unknown 으로 모은다(AUD-02 조각과 같은 처지 — tools 변경은 범위 밖).
3. 지난 기일 행 중 옆 물건 상세가 남았을 수 있는 행: (중복)_7·_8(doc 끝 27·38, 예전 키 7·8 로 받은 '완료') 등 — 지시대로 손대지 않음(다시 목록에 나오면 사건번호 복원·저장값으로 바로잡힌다).
4. 화면 변경은 관리자 전용 문자열 셋(범례 2·안내 1)뿐 — 디자인 검수 필요 여부는 Steward 판단. backlog AUD-18 상태 칸·changelog 는 Steward 몫(손대지 않음).

스크래치 `scratchpad/aud18/work/`: replay.py · compare_bytes.py · compare_daily_keys.py · summarize_daily.py · key_src.py · key_src_after.py · maint_cli.py · cond_scope.py · accident_proxy.py · run_suite.py · sync_tree.py · head_suite.log · new_suite1.log · head_red.log · replay_*_{bytes,daily}.json.
