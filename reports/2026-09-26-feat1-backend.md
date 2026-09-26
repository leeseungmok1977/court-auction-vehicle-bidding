# FEAT-1 가격대 필터 — 서버 쪽 (2026-09-26-12 / backend-engineer)

- 기준 커밋: `bfc7708` (작업 트리에 **커밋하지 않음** — 커밋·배포 금지 준수). 템플릿(`vehicles.html`) 미수정.
- 바뀐 파일: `web/service.py` · `web/db.py` · `web/app.py` · `tests/test_price_band_filter.py`(신규). DB 스키마 변경 **없음**(열 추가·마이그레이션 없음).
- 측정 조건: 전부 conftest 격리 tmp DB(운영 `data/auction.db` 읽기·쓰기 없음). 라이브·EC2 요청 없음.
- 전체 pytest(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest -q`): **변경 전 1,312 passed(602초) → 변경 후 1,361 passed(600초, 0 failed)** — +49 전부 이 작업(`tests/test_price_band_filter.py`).
  ⚠ '변경 전' 실행은 편집 시작 전에 띄웠으나 실행 중(10분)에 편집이 겹쳤다. 결과가 지시서의 "지금 1,312"와 같아 그대로 쓴다.

## [요약]

최저매각가 5구간 필터를 SQL WHERE 조각 + 한 쿼리 COUNT 로 넣었다. 구간 정의는 `service.PRICE_BANDS` 한 곳이다.
`/vehicles` 와 `/api/vehicles/count` 가 같은 규칙으로 `price=` 를 받고, 잘못된 값(화이트리스트 밖·빈값·**중복**)은
필터 없음으로 떨어진다(500 없음). 목록 페이지 요청당 쿼리는 **SQL 경로 +1**(구간별 COUNT), 파이썬 경로(segment·bucket·
usepick·picks) **+0**, count API **+0**. 신규 테스트 49건 전부 초록, WHERE 조각을 지운 변이체로 **10건 빨간불**(반증 성립).

## 1. 바꾼 것 (앵커·함수명)

| 파일 | 앵커 | 내용 |
|---|---|---|
| `web/service.py` | `PRICE_BANDS` (주석 `# ── 가격대 필터(FEAT-1…`, `vehicle_segment` 바로 아래) | 순서 있는 튜플 `(key, lo, hi, label)` 5개 + `PRICE_BAND_KEYS` · `PRICE_BAND_LABELS` |
| `web/service.py` | `price_band_range(key)` | key → `(lo, hi)`, hi `None`=상한 없음. 화이트리스트 밖·빈값·문자열 아님 → `None` |
| `web/service.py` | `price_band_key(min_sale_price)` | 최저가 → key. NULL·숫자 아님 → `None`(SQL 조각과 같은 규칙) |
| `web/service.py` | `price_band_counts(rows)` · `filter_price_band(rows, key)` | 파이썬 경로용 집계·필터. 반환 모양은 `db.count_by_price_band` 와 같음 |
| `web/db.py` | `_vehicles_where(...)` (신설) | `list_vehicles` 의 WHERE 조립을 분리. 끝에 조각 `min_sale_price >= ?` / `min_sale_price < ?`(각각 `price_min`·`price_max` 가 `is not None` 일 때). NULL 은 비교가 NULL(거짓)이라 자동 제외 |
| `web/db.py` | `list_vehicles(..., price_min=None, price_max=None)` | 키워드 인자 2개 추가(끝). 기존 호출부·정렬·`hide_incomplete` 무변경 |
| `web/db.py` | `count_by_price_band(bands, **filters)` (신설) | `CASE WHEN … THEN key END AS band, COUNT(*) … GROUP BY band` **한 쿼리**. 반환 `{key: n (모든 key, 없으면 0), None: 구간 밖 행 수(=최저가 NULL)}`. `price_min/price_max` 를 넘기면 `TypeError` |
| `web/app.py` | `_price_key(request, price)` (신설, `USEPICK_VALUES` 아래) | 파라미터 정규화. `request.query_params.getlist("price")` 가 2개 이상이면 `""` |
| `web/app.py` | `vehicles()` — `price: str = ""` 인자, 주석 `# 가격대(FEAT-1)` 블록, `_sql_filters`·`_sql_price`·`_band_basis`·`band_counts`·`price_bands` | SQL 경로: WHERE 조각 + `db.count_by_price_band`. 파이썬 경로: 가격만 뺀 나머지 필터를 통과한 행(`_band_basis`)에서 집계 후 파이썬으로 거름 |
| `web/app.py` | `vehicles()` — `_filters` 딕셔너리 `"price": price`, `qs_no_price = _qs("price")`, 템플릿 컨텍스트 `"price"·"price_bands"·"qs_no_price"` | `qs`(페이지네이션·정렬 링크)는 price 를 **유지** |
| `web/app.py` | `vehicles_count()` — `request: Request` · `price: str = ""` 인자 | `/vehicles` 와 같은 규칙(SQL 경로 WHERE / 파이썬 경로 마지막에 파이썬 필터) |

usepick 블록 재배선(확인된 사실 — 코드): 갈래 판정(`personal_use_tier`)을 **가격대 적용 전 모수**(`_band_basis`)에서 한 번만 하고,
① 구간별 건수 = 그 갈래로 거른 행(가격 제외) ② 갈래 칩 `use_counts` = 가격대 적용 후 행 — 두 패싯이 서로를 반영한다.
같은 dict 객체를 공유하므로 `use_tier`/`use_saving` 부착은 그대로 카드에 실린다. 갈래 판정 횟수는 이전과 같다(모수가 커지지 않음 —
전에도 segment·bucket 뒤의 전 행에 대해 판정했다).

## 2. 프론트(frontend-engineer)가 쓸 명세

### 2.1 URL 파라미터
- `price=<key>` — `/vehicles`, `/api/vehicles/count` 둘 다. key 는 아래 5개만.
- 화이트리스트 밖·빈값(`price=`)·**중복**(`price=a&price=b`, 같은 값 2개 포함) → 필터 없음, 200. 500 없음.
- 구간을 고르면 `min_sale_price IS NULL` 행은 **목록에서 빠진다**(어느 구간에도 안 속함). 가격대를 안 고르면 이전과 같다.
- 다른 모든 필터(judgment·maker·q·cond·upcoming·date·court·promising·segment·bucket·usepick·picks·all·sort)와 AND 로 겹친다.

### 2.2 상수 (`from web import service`)
```python
service.PRICE_BANDS == (
    # key          lo            hi            label
    ("0-500",      0,            5_000_000,    "~500만"),
    ("500-1000",   5_000_000,    10_000_000,   "500~1,000만"),
    ("1000-2000",  10_000_000,   20_000_000,   "1,000~2,000만"),
    ("2000-3000",  20_000_000,   30_000_000,   "2,000~3,000만"),
    ("3000-",      30_000_000,   None,         "3,000만~"),
)
service.PRICE_BAND_KEYS    # ("0-500", "500-1000", "1000-2000", "2000-3000", "3000-")
service.PRICE_BAND_LABELS  # {"0-500": "~500만", ...}
```
반열림 `[lo, hi)` — **정확히 5,000,000 은 '500~1,000만'**, 정확히 30,000,000 은 '3,000만~'. 축은 **최저매각가**(감정가·시세 아님).
템플릿·JS 에 경계·라벨을 다시 적지 말 것 — 컨텍스트 `price_bands` 를 그대로 돌린다.

### 2.3 `vehicles.html` 컨텍스트 변수 (신규 3개, 기존 변수 무변경)
| 변수 | 형 | 값 |
|---|---|---|
| `price` | `str` | 선택된 key 또는 `""`(정규화 후 — 잘못된 입력은 여기서 이미 `""`) |
| `price_bands` | `list[dict]` | `PRICE_BANDS` 순서 그대로 **항상 5개**: `{"key": "1000-2000", "label": "1,000~2,000만", "count": 144}`. 0건 구간도 `count: 0` 으로 있음 |
| `qs_no_price` | `str` | 현재 필터에서 `price` 만 뺀 쿼리스트링(`_qs("price")`, 기존 `qs_no_bucket` 관례). 셀렉트 옵션 href·해제 칩용. 빈 문자열일 수 있다(`{% if qs_no_price %}?{{ qs_no_price }}{% endif %}` 관례) |
| `qs` (기존) | `str` | **price 포함** — 페이지네이션·정렬 링크가 가격대를 잃지 않는다 |

`count` 의 의미(패싯 규칙): **가격대만 뺀 나머지 현재 필터**를 전부 적용한 상태에서 그 구간에 드는 건수. 그래서
① 선택된 구간의 `count == total` ② `sum(count) + (최저가 NULL 건수) == 가격대 없는 같은 필터의 total` ③ 다른 구간의 `count` 는
"그 구간으로 바꾸면 나올 총수". usepick 페이지에서는 `use_counts`(갈래 칩)가 가격대를 반영하고 `price_bands` 가 갈래를 반영한다.

셀렉트 예(참고 — 템플릿은 프론트 몫, 여기서는 손대지 않았다):
```jinja
<select onchange="location.href=this.value">
  <option value="/vehicles{% if qs_no_price %}?{{ qs_no_price }}{% endif %}" {% if not price %}selected{% endif %}>가격대 전체</option>
  {% for b in price_bands %}
  <option value="/vehicles?price={{ b.key }}{% if qs_no_price %}&{{ qs_no_price }}{% endif %}" {% if price == b.key %}selected{% endif %}>{{ b.label }} ({{ b.count }})</option>
  {% endfor %}
</select>
```
`(필터 적용)` 표기(`{% if judgment or maker or q or result %}`)에 `or price` 를 더할지는 프론트 판단.

### 2.4 `/api/vehicles/count`
`GET /api/vehicles/count?price=<key>&…` → `{"total": n}`. `/vehicles` 의 `total` 과 항상 같다(테스트 15개 조합으로 대조).

## 3. 테스트 — `tests/test_price_band_filter.py` 신규 49건(파라미터 확장 포함), 전부 초록

| 항목 | 테스트 |
|---|---|
| 상수 형태·연속성·라벨 | `test_price_bands_single_source_shape` |
| 화이트리스트(abc·`0-500;DROP TABLE vehicles`·빈값·공백·None·숫자·리스트) | `test_price_band_range_whitelist` |
| 경계값 14건(0·4,999,999·**5,000,000**·…·30,000,000·10⁹·None·""·abc·True) | `test_price_band_key_boundaries` |
| SQL 조각: 구간마다 정확한 id 집합·NULL 제외·`price_min=0` 도 값 | `test_list_vehicles_band_filter_boundary_and_null_excluded` |
| 파이썬 술어 == SQL 조각(구간 5개 전부) | `test_python_predicate_agrees_with_sql_fragment` |
| COUNT 가 **한 쿼리**(execute 1회, CASE·GROUP BY 포함)·합+NULL==총수·구간마다 목록 건수와 일치 | `test_count_by_price_band_is_one_query_and_sums_to_total` |
| 0건 구간도 key 존재(기아: 0·2·0·2·0 + NULL 1) | `test_count_by_price_band_keeps_zero_bands_and_other_filters` |
| 잘못된 key 7종 → 200·필터 무시·테이블 무사 | `test_invalid_price_param_is_ignored_not_500` |
| `/vehicles` 총수 == count API — SQL 경로 4·파이썬 경로(segment) 2·picks 1 | `test_list_total_equals_count_api` |
| usepick·bucket 경로 8조합 총수 일치 (대시보드 패리티 픽스처 BT 차용) | `test_usepick_and_bucket_paths_agree_with_count_api` |
| usepick 패싯: 갈래 칩 == 총수 == 선택 구간 count, 구간 표는 가격 무관, 행 전부 그 구간 | `test_usepick_facets_are_consistent_with_price` |
| 기존 필터 회귀(기아 5건 그대로, +가격대 2/0) | `test_maker_filter_regression_with_and_without_price` |
| 템플릿 컨텍스트 계약(SQL 경로·파이썬 경로·가격 없음) — `TemplateResponse` 스파이로 실제 컨텍스트 검사 | `test_template_context_contract_*`, `test_template_context_when_no_price` |
| 반증(메모리 변이체) — 조각 두 줄을 `pass` 로 바꾼 `_vehicles_where` 는 13행 전부 반환, 원본은 2행 | `test_where_fragments_are_load_bearing` |

### 반증 — 파일 수준(지시서 요구: 바이트 백업·복원·md5)
스크립트로 `web/db.py` 를 바이트 백업 → 앵커 두 문장(`where.append("min_sale_price >= ?"); params.append(int(price_min))` ·
`where.append("min_sale_price < ?"); params.append(int(price_max))`)을 `pass` 로 치환 → 이 테스트 파일 실행 → `finally` 복원.

| | md5 |
|---|---|
| 원본(변이 전) | `44a0eba08742a162777f0096dbe7b6bc` |
| 변이체 | `436bae59184683dcc8fb4c014215a53c` |
| 복원 후 | `44a0eba08742a162777f0096dbe7b6bc` (= 원본, RESTORED OK) |

변이체 결과: **10 failed, 30 passed**(usepick 테스트 추가 전 40건 기준). 실패 10건은 건수로 역산하면 경계·NULL(1)·술어일치(1)·
COUNT일치(1)·총수일치 SQL 경로(4)·제조사회귀(1)·컨텍스트 SQL 경로(1)·앵커 검사(1) = 10 — **추정**(개별 이름은 `-rN` 로 출력을
줄여 기록하지 못했다; 변이체를 다시 만들지 않았다). 파이썬 경로 테스트는 SQL 조각과 무관해 초록이 맞다.

## 4. 요청당 DB 쿼리 수 (확인된 사실 — `db.connect` 프록시로 `execute` 호출 수 측정, 워밍업 1회 후 2회째 기록, tmp DB 13행)

| 요청 | execute 수(변경 후) | 그중 구간별 COUNT 쿼리 | 변경 전 상당 |
|---|---|---|---|
| `/vehicles` | 6 | 1 | 5 → **+1** |
| `/vehicles?price=1000-2000` | 6 | 1 | 5 → +1 |
| `/vehicles?maker=현대&price=3000-` | 8 | 1 | 7 → +1 (제조사 변형 조회 2회는 기존) |
| `/vehicles?segment=commercial` (파이썬 경로) | 5 | 0 | 5 → **+0** |
| `/vehicles?segment=commercial&price=1000-2000` | 5 | 0 | 5 → +0 |
| `/api/vehicles/count` (모든 변형) | 1 | 0 | 1 → +0 |

'변경 전 상당'은 `count_by_price_band` 가 이 변경에서 **유일하게 추가된 DB 호출**이라는 코드 근거로 뺀 값(추정 아님 — 그 외 쿼리 호출을 추가하지 않았다).
SQL 경로에서는 목록 자체가 구간으로 줄어 `SELECT *` 행 수는 오히려 감소한다(예: 라이브 383건 → 1,000~2,000만 144건).

## 5. 못 한 것 · 알려 둘 것

1. **템플릿 미반영** — 지시대로 `vehicles.html` 은 손대지 않았다. 컨텍스트는 이미 들어가지만 화면에는 아무것도 안 보인다(프론트 몫).
2. **라벨 어휘가 기존 '가격대 층'과 다르다(확인된 사실).** 같은 파일 `_price_band`(정확도 층, **시세** 축)·`last_month_sale_stats` 는
   `500만 이하`·`2,000만 이상` 을 쓰고, 2026-09-23 교차검수가 "가격대 어휘는 한 벌"이라 적어 두었다. 이번 스펙의 `~500만`·`3,000만~` 은
   지시서 원문 그대로 넣었다 — 축(최저매각가 vs 시세)과 용도(필터 vs 층)가 다르지만 **한 화면에 두 어휘가 보일 수 있다**(목록 상단 셀렉트 vs
   카드의 정확도 층 문구). 디자인 검수 때 물을 것. 값을 바꾸려면 `PRICE_BANDS` 의 label 한 곳만 바꾸면 된다.
3. `/api/vehicles/count` 의 **기존** 패리티 틈 2개는 건드리지 않았다(범위 밖): `promising` 파라미터를 받지 않음, `upcoming` 음수 클램프 없음
   (`/vehicles` 는 `up < 0 → 0`). 지금도 그 조합은 두 수가 다를 수 있다 — 별도 티켓 권고.
4. `sort=expected`·`picks=1` 경로는 500 없음·총수 일치만 확인했다(백테스트 표본 없는 tmp DB 라 picks 는 0건 — 공허 통과에 가깝다. usepick·bucket 은
   대시보드 패리티 픽스처(BT+66행)로 실제 행이 있는 상태에서 검증했다).
5. 운영 DB 로 실측하지 않았다(지시: 운영 DB 쓰기 금지 — 읽기도 하지 않았다). 라이브 분포 383건 수치는 지시서 인용.
6. 프론트가 `price` 를 셀렉트가 아닌 폼 hidden 으로 실을 때 **같은 이름을 두 번 넣지 말 것** — 중복은 필터 없음으로 떨어진다(2.1).
