---
order: 2026-09-27-39
from: insight
ticket: AUDIT-1
result: blocked
verified: 미검증
handoff:
  - to: steward
    why: "17건 건별 표·오늘 기준 재계산이 실행 권한 거부로 미실행 — §4 SQL 1)·3)을 실행 가능한 세션(오너 동석)에서 돌려 08-24 기일 3건(10-08 종결 전환)부터 판정한다. 헤드리스 읽기전용 python/sqlite3 권한은 09-29 에 이미 올라간 오너 결정 항목의 재발"
---

# AUDIT-1 r2 — A-08(가칭 DATA-06) 결과 미확인 17건 원인 분류 (지시서 2026-09-27-39)

> 작성: 당직 Steward가 대신 씀(`insight`는 Write 권한이 없다, 프로토콜 §4). 본문은 insight 보고를 요약·정리한 것이고,
> Steward가 직접 재현한 것은 **[S 재현]** 으로 표시했다. 머리말 `verified: 미검증` 은 **핵심 주장(건수·건별 분류)을 DB로
> 재현하지 못했다**는 뜻이다. 코드 근거는 재현했다(§2).

## [요약]
핵심 산출물(17건 건별 표, 오늘 09-30 기준 재계산, 원인 3분류 배정)은 **나오지 않았다.** 데이터가 없어서가 아니다.
헤드리스 실행에서 `python -c`·`sqlite3`·`gunzip`이 모두 승인 요청으로 떨어졌다. insight와 당직 Steward 둘 다 막혔다.
그 대신 코드에서 원인 경로 3종을 확인했다. 실행 가능한 세션에서 그대로 돌릴 쿼리 5종도 남겼다.
**시한**: 08-24 기일 3건은 `mark_aged_out(days=45)`로 **2026-10-08경** '종결' 전환된다. 이 수치는 PM의 09-27 재현값이고 오늘 기준으로는 미확인이다.

## 1. 데이터 출처·조건
| 항목 | 값 | 확인 |
|---|---|---|
| 로컬 DB | `data/auction.db`, mtime 2026-09-23 15:27:52 (+09:00), 4,661,248 B | insight가 `ls`로 확인 |
| 더 최신 사본 | `data/backups/auction-20260929.db.gz` (09-29 09:10) 외 09-27·09-28 | 존재만 확인. 압축 해제 거부 |
| `data/vehicles.db` | 0 B, 미사용 | insight 확인 |
| 외부 요청 | 0건 | — |

**실행 차단 [S 재현]**: 당직 Steward가 `python -c "import sqlite3; …mode=ro…"`를 실행했다. 결과는 "requires approval" 거부였다(2026-09-30).
insight가 기록한 거부 목록은 `python -c`, `python -m`, `git`, `pytest`, `gunzip`, 리다이렉션이다.
선행 사례 `reports/2026-09-27-insight-2026-09-27-03.md`(09-29)가 있어 이번이 **세 번째 관측**이다.

## 2. 확인된 사실 — 코드 (함수명·앵커로 지시)
| # | 사실 | 근거 | 재현 |
|---|---|---|---|
| 1 | 45일 경과 시 결과 NULL·유찰·기타·미확정 → '종결' 전환, `result_checked_at` 기록 | `web/db.py` `def mark_aged_out(days: int = 45)` | [S 재현] 정의 존재 |
| 2 | 이 전환은 **매일** 돈다. `daily_update` → `update_results(run_id=run_id, finalize=False)` → 첫머리 `db.mark_aged_out(days=recency_days)`, `recency_days = 45` | `web/service.py` `update_results` | [S 재현] |
| 3 | 매칭: `rmap.get((_sa_no_from_docid(v["doc_id"]), str(v.get("item_no"))))` → `if not row:` `continue` (흔적 없음) | `update_results` | [S 재현] |
| 4 | `doc_id`가 없거나 21자 미만이면 saNo를 복원하지 못한다. 그러면 `targets`에서 **조회 시도 없이** 빠진다 | `_sa_no_from_docid` `return d[7:21] if len(d) >= 21 else None` | [S 재현] |
| 5 | `court_code`가 비면 `courts` 그룹에 들어가지 않아 조회하지 않는다 | `update_results` `if bo:` `courts.setdefault` | [S 재현] |
| 6 | 법원코드 충돌 가드는 `new_court`가 있을 때만 동작한다. 비어 있으면 검사하지 않고 병합한다 | `web/db.py` `upsert_listing` `if vid and new_court:` | [S 재현] 앵커 존재. "이 경로로 충돌 id가 생긴다"는 **추정** |
| 7 | ops_health 낙찰결과 신호는 `max(result_checked_at)` 신선도만 본다. 정체 건수·최고령 경과일은 세지 않는다 | `web/ops_health.py` `# ⑤ 낙찰결과` | insight 확인. Steward 미재현 |
| 8 | **부수 발견 — 죽은 코드**: `update_results` 끝의 `if blocked: … raise` 다음이 무조건 `return updated`다. 그래서 그 아래 `if finalize and run_id:` → `status="done"`·완료 메시지 블록에는 **도달하지 못한다** | `update_results` 끝 `return updated` 두 번 | [S 재현] |

- **#8 영향 (추정·미검증)**: 수동 실행(`finalize=True`)으로 부르면 run이 `done`으로 닫히지 않을 수 있다. insight는 "메시지가 비어 있을 것"으로 적었다. 실제 runs 테이블 상태는 확인하지 않았다. 이번 지시서 범위 밖이라 백로그 티켓화 대상으로만 남긴다.
- **Steward 추가 관찰 (코드, 미검증)**: `court_list = list(courts.keys())[:max_courts]`에서 상한 밖 법원은 조용히 빠진다. 법원당 `max_pages=min(15, …)`(약 600건)를 넘는 법원도 뒤쪽 결과가 잘린다. 둘 다 결과가 '응답에 없음'(ⓐ)처럼 보이지만 실제 원인은 **조회 상한**이다. 분류할 때 따로 봐야 한다.

## 3. 인용 — PM 09-27 재현치 (이번에 재실행 못 함)
출처는 `reports/2026-09-27-audit-merged.md` A-08(라이브 사본 `mode=ro`)이다.
- `sale_date<'2026-09-27'` AND `auction_result` 빈 행: **17건**. 그중 `result_checked_at IS NULL` **15건**, NOT NULL **2건**
- 최고령 매각기일 **2026-08-24, 3건** (S1은 2건으로 셌다). 08-24에 45일을 더하면 **10-08**이다
- 17건 안에 `2025타경53062_1`(PANEL-60 대상)과 충돌 id `2026타경50391_1`이 있다
  - 로컬 사본에 두 문자열이 있는지는 insight가 Grep으로 확인했다
  - 매치 수(2·5)는 행 수가 **아니다**. freelist 잔존 때문이고, 선행 사례에서 같은 방법을 폐기했다

## 4. 원인 3분류 — 해석·추정 (건별 배정 없음)
| 분류 | 메커니즘 | 신뢰도 |
|---|---|---|
| ⓐ 결과조회 응답에 없음 | 조회는 했지만 그날 법원 응답에 saNo+물건번호 행이 없다. 원인은 미게시일 수도 있고 §2의 조회 상한(`max_courts`·15페이지) 절단일 수도 있다 | 중간 |
| ⓑ 매칭키 불일치 | ① `court_code` 결측으로 조회하지 않음 ② `doc_id` 결측·짧음으로 대상에서 빠짐 ③ saNo·item_no 표기 형식 차이(이 경우는 추정) | ①②는 코드로 확인. 해당 행이 실제로 있는지는 미확인 |
| ⓒ 충돌 id | 법원코드 없는 id 스킴이라 먼저 들어온 법원의 `court_code`로 조회한다. 그러면 영구히 매칭되지 않는다. DATA-04(A-01)와 뿌리가 같다 | 메커니즘은 코드로 확인. 건별 배정은 미확인 |
| NOT NULL 2건 | 상세 재수집 경로가 `result_checked_at`은 찍고 `_resolve_auction_result`가 `None`을 돌려주는 조합이라는 가설이다 | 낮음. 쿼리 4)로 확정해야 한다 |

**실행용 쿼리 원문** (읽기 전용이다. `sqlite3.connect("file:<사본>?mode=ro", uri=True)`로 연다. 가능하면 `auction-20260929.db.gz` 해제본을 쓴다):
```sql
-- 1) 대상 집합 + 도달 예정일
SELECT id, case_no, court, court_code, sale_date, result_checked_at, result_source,
       auction_result, judgment,
       CAST(julianday('now','localtime') - julianday(sale_date) AS INTEGER) AS days_elapsed,
       date(sale_date, '+45 day') AS aged_out_due
FROM vehicles
WHERE sale_date < date('now','localtime')
  AND (auction_result IS NULL OR auction_result = '')
ORDER BY sale_date ASC;

-- 2) 요약 카운트 (17/15 재현)
SELECT COUNT(*) AS total,
       SUM(CASE WHEN result_checked_at IS NULL THEN 1 ELSE 0 END) AS never_checked,
       MIN(sale_date) AS oldest_sale_date
FROM vehicles
WHERE sale_date < date('now','localtime')
  AND (auction_result IS NULL OR auction_result = '');

-- 3) 게이트별 사전분류 (update_results 대상 선정 재현)
SELECT id, case_no, court_code, doc_id, sale_date, auction_result, result_checked_at,
       CASE
         WHEN court_code IS NULL OR court_code = '' THEN 'ⓑ-court_code 없음(대상 제외)'
         WHEN doc_id IS NULL OR length(doc_id) < 21 THEN 'ⓑ-doc_id 부족(saNo 복원 불가)'
         WHEN case_no LIKE '%중복%' OR id LIKE '%중복%' THEN 'ⓒ-(중복) id'
         ELSE '판정불가(응답 비교 필요, ⓐ 또는 ⓑ 세부)'
       END AS gate_classification
FROM vehicles
WHERE sale_date < date('now','localtime')
  AND (auction_result IS NULL OR auction_result = '')
ORDER BY sale_date ASC;

-- 4) 이례 2건 추적
SELECT id, case_no, court, sale_date, result_checked_at, result_source, auction_result, dxdy_history
FROM vehicles
WHERE sale_date < date('now','localtime')
  AND (auction_result IS NULL OR auction_result = '')
  AND result_checked_at IS NOT NULL;

-- 5) 사건번호 충돌 흔적
SELECT * FROM anomaly_log WHERE message LIKE '%사건번호 충돌%' ORDER BY created_at DESC LIMIT 50;
```
⚠ 컬럼명(`court`·`dxdy_history`·`anomaly_log.message` 등)은 insight가 코드를 읽고 쓴 것이다. 스키마와 대조하지 않았다. 실행 전에 `PRAGMA table_info(vehicles)`로 확인한다.

## 5. 10-08 전에 손써야 할 것 (제안, 실행 안 함)
1. **쿼리 1)·3)을 먼저 돌린다.** 오너가 있는 세션에서 한다. 08-24 3건의 id·법원·`doc_id`·`court_code`를 확인한다.
   - ⓑ①②이면 매칭 보정 대상이다(backend)
   - ⓐ이면 재조회 대상이다. 외부 요청이므로 C.4 승인 지점에 해당한다
   - ⓒ이면 DATA-04 설계와 묶는다
2. 10-08 전에 판정하지 못하면 3건은 '종결'로 넘어가 다시 찾지 않는다. 되돌리려면 DB 수동 수정이 필요하다. 수동 수정은 오너 승인 사항이다.
3. DATA-06 본안(ops_health·일일 리포트에 미확인 건수와 최고령 경과일 표시, 전환 7일 전 경고)은 backend 몫이다. 이 보고의 handoff에는 넣지 않았다. insight가 steward만 지목했다.

## 6. [승인 요청] (오너)
- **헤드리스 당직의 읽기 전용 `python`/`sqlite3` 실행 허용 여부**: 09-29에 이미 올라간 항목이고 이번이 재발(3번째 관측)이다. 허용하지 않으면 `insight(자동: 예)`는 "숫자를 센다"는 역할을 당직에서 구조적으로 못 한다.
- 08-24 3건 처리 방식(재조회·보정·종결 방치)은 1)·3) 결과를 본 뒤 결정한다. 시한은 10-08이다.
