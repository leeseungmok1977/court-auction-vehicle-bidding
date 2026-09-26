# FEAT-2 연식 하한·주행거리 상한 필터 — 서버 쪽 (2026-09-27-27 / backend-engineer)

- 기준 커밋: `66205d9` (작업 트리에 **커밋하지 않음** — 커밋·배포·라이브 요청 금지 준수). 템플릿(`vehicles.html`) 미수정.
- 바뀐 파일: `web/service.py` · `web/db.py` · `web/app.py` · `tests/test_feat2_year_km_filter.py`(신규). DB 스키마 변경 **없음**(열 추가·마이그레이션 없음 — `year`·`mileage_km` 기존 열만 읽는다).
- 측정 조건: 전부 conftest 격리 tmp DB(운영 `data/auction.db` **쓰기 없음**; 읽기는 `mode=ro` 로 열 타입 확인 1회 — 아래 §5-4). 라이브·EC2 요청 없음.
- 전체 pytest(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest -q`): **변경 후 1,685 passed, 2 xfailed, 0 failed(1,046초 = 17분 26초)** — 지시서의 "지금 1,554 passed + 2 xfailed" 대비 정확히 +131 이 전부 이 작업(`tests/test_feat2_year_km_filter.py` 131건). 변경 전 스위트는 따로 돌리지 않았다(지시서 수치를 기준으로 삼음 — 1,554+131=1,685 로 일치).

## [요약]

연식 하한(`year_min`)·주행거리 상한(`km_max`) 셀렉트 두 축을 FEAT-1 골격 그대로 넣었다. 옵션 정의는 `service.YEAR_MIN_OPTIONS`·
`KM_MAX_OPTIONS` 한 곳이고, SQL WHERE 조각 2개(`year >= ?` · `mileage_km > 0 AND mileage_km <= ?`)와 축마다 **한 쿼리**
COUNT(누적 옵션이라 `SUM(CASE WHEN … THEN 1 ELSE 0 END)` 열 4개 + 미상 1개)를 쓴다. `/vehicles` 와 `/api/vehicles/count` 가 같은 규칙으로
받고, 잘못된 값(화이트리스트 밖·`2018.0`·빈값·**중복**)은 필터 없음으로 떨어진다(500 없음). 패싯 규칙은 축 3종(가격대·연식·주행거리)이
**서로를 반영**한다 — 각 축의 옵션 건수는 자기 축만 빼고 나머지 두 축까지 얹은 모수에서 센다. 주행거리 미상(NULL·0 이하) 건수를
`km_unknown_excluded` 로 컨텍스트에 준다. 신규 테스트 131건 전부 초록, WHERE 조각을 지운 파일 변이체로 **28건 빨간불**(반증 성립).
목록 페이지 요청당 쿼리는 **SQL 경로 +2**(축별 COUNT 1개씩; 가격대 포함 축 COUNT 3개), 파이썬 경로 **+0**, count API **+0**.

## 1. 바꾼 것 (앵커·함수명)

| 파일 | 앵커 | 내용 |
|---|---|---|
| `web/service.py` | `YEAR_MIN_OPTIONS` · `KM_MAX_OPTIONS` (주석 `# ── 연식 하한·주행거리 상한 필터(FEAT-2…`, `filter_price_band` 바로 아래) | 순서 있는 튜플 `(key, value, label)` 4개씩 + `YEAR_MIN_KEYS`·`YEAR_MIN_LABELS`·`KM_MAX_KEYS`·`KM_MAX_LABELS` |
| `web/service.py` | `year_min_value(key)` · `km_max_value(key)` (공용 `_option_value`) | key → int 값. **문자열 정확 일치**(int 파싱 아님): 화이트리스트 밖·빈값·`"2018.0"`·`" 2018"`·`"02018"`·`"2019"`·문자열 아님 → `None` |
| `web/service.py` | `year_min_match(year, ymin)` · `km_max_match(km, kmax)` · `km_unknown(km)` (공용 `_as_int`) | SQL 조각과 같은 파이썬 술어. NULL·bool·숫자 아님 → False; km 은 `0 < km <= kmax`; 미상 = NULL 또는 ≤0 |
| `web/service.py` | `year_min_counts(rows)` · `km_max_counts(rows)` · `filter_year_min(rows, key)` · `filter_km_max(rows, key)` | 파이썬 경로용 누적 집계·필터. 반환 모양은 `db.count_by_year_min`·`count_by_km_max` 와 같음(`{key: n, None: 미상 수}`) |
| `web/db.py` | `_vehicles_where(..., year_min=None, km_max=None)` | 가격대 조각 뒤에 조각 2개: `year >= ?` / `mileage_km > 0 AND mileage_km <= ?`(각각 `is not None` 일 때). 주석에 NULL·0 판정 근거 |
| `web/db.py` | `list_vehicles(..., year_min=None, km_max=None)` | 키워드 인자 2개 추가(끝). 기존 호출부·정렬·`hide_incomplete` 무변경 |
| `web/db.py` | `_count_cumulative(options, cond_sql, unknown_sql, axis, **filters)` (신설) · `count_by_year_min(options, **filters)` · `count_by_km_max(options, **filters)` | **한 쿼리**: `SELECT SUM(CASE WHEN year >= ? THEN 1 ELSE 0 END) AS c0, … , SUM(CASE WHEN year IS NULL OR year <= 0 THEN 1 ELSE 0 END) AS unknown_n FROM vehicles WHERE …`. 반환 `{key: n (모든 key, 없으면 0), None: 미상 수}`. 자기 축(`year_min`/`km_max`)을 필터로 넘기면 `TypeError`, 다른 두 축은 받는다. `count_by_price_band` 도 `year_min`·`km_max` 를 받는다(`**filters` → `_vehicles_where`) |
| `web/app.py` | `_single_key(request, name, value, resolve)` (신설, `USEPICK_VALUES` 아래) · `_price_key` (이것을 쓰도록 축약) · `_year_min_key` · `_km_max_key` | 파라미터 정규화 공용 헬퍼. `getlist(name)` 2개 이상이면 `""`, `resolve(value) is None` 이면 `""` |
| `web/app.py` | `_apply_axes(rows, price, year_min, km_max, skip="")` (신설) | 파이썬 경로의 축 3종 필터. `skip` 축만 빼고 적용 — 패싯 규칙을 축마다 같은 한 함수로 |
| `web/app.py` | `vehicles()` — `year_min: str = ""`·`km_max: str = ""` 인자, 주석 `# 연식 하한·주행거리 상한(FEAT-2)`, `_sql_year`·`_sql_km`, `year_counts`·`km_counts`·`year_options`·`km_options`·`km_unknown_excluded` | SQL 경로: WHERE 조각 + `db.count_by_year_min`/`count_by_km_max`(각각 나머지 두 축 얹음). 파이썬 경로: `_apply_axes(_band_basis, skip=축)` 로 센다. usepick 갈래 칩 `use_counts` 는 축 3종 적용 후 행 |
| `web/app.py` | `vehicles()` — `_filters` 에 `"year_min": year_min, "km_max": km_max`, `qs_no_year_min = _qs("year_min")`, `qs_no_km_max = _qs("km_max")`, 템플릿 컨텍스트 7개 | `qs`(페이지네이션·정렬·UX-5 요약·검색 저장)는 두 키를 **유지**. `qs_no_price`·`qs_no_date`·`qs_no_q` 등 기존 `qs_no_*` 도 두 키를 보존 |
| `web/app.py` | `vehicles_count()` — `year_min`·`km_max` 인자 | `/vehicles` 와 같은 규칙(SQL 경로 WHERE / 파이썬 경로 마지막에 `_apply_axes`) |

usepick 블록(확인된 사실 — 코드): FEAT-1 재배선 그대로. 갈래 판정은 축 3종 적용 **전** 모수(`_band_basis`)에서 한 번만 하고, ① 축별 건수 = 그 갈래로
거른 행에서 자기 축만 빼고 센다 ② 갈래 칩 `use_counts` = 축 3종 적용 후 행. 갈래 판정 횟수는 이전과 같다.

## 2. 프론트(frontend-engineer)가 쓸 명세

### 2.1 URL 파라미터
- `year_min=<key>` · `km_max=<key>` — `/vehicles`, `/api/vehicles/count` 둘 다. key 는 아래 4개씩만(**문자열 그대로**: `2018`, `100000`).
- 화이트리스트 밖(`2019`·`abc`·`2018.0`·`1e5`·`100,000`)·빈값(`year_min=`)·**중복**(`year_min=2018&year_min=2020`, 같은 값 2개 포함)·앞뒤 공백 → 필터 없음, 200. 500 없음. (hidden 으로 실을 때 **같은 이름을 두 번 넣지 말 것** — FEAT-1 과 같은 규칙.)
- `year_min` 을 고르면 `year IS NULL` 또는 `year <= 0` 행은 **목록에서 빠진다**. `km_max` 를 고르면 `mileage_km IS NULL` 또는 `mileage_km <= 0` 행이 빠지고 그 수가 `km_unknown_excluded` 다.
- 다른 모든 필터(judgment·maker·q·cond·upcoming·date·court·promising·segment·bucket·usepick·picks·all·sort·**price**)와 AND 로 겹친다. 정렬은 모수를 바꾸지 않는다.

### 2.2 상수 (`from web import service`)
```python
service.YEAR_MIN_OPTIONS == (
    # key      value  label
    ("2015",   2015,  "2015년 이후"),
    ("2018",   2018,  "2018년 이후"),
    ("2020",   2020,  "2020년 이후"),
    ("2022",   2022,  "2022년 이후"),
)
service.KM_MAX_OPTIONS == (
    ("50000",   50_000,   "5만km 이하"),
    ("100000",  100_000,  "10만km 이하"),
    ("150000",  150_000,  "15만km 이하"),
    ("200000",  200_000,  "20만km 이하"),
)
service.YEAR_MIN_KEYS   # ("2015", "2018", "2020", "2022")     service.YEAR_MIN_LABELS  # {"2018": "2018년 이후", …}
service.KM_MAX_KEYS     # ("50000", "100000", "150000", "200000")  service.KM_MAX_LABELS  # {"100000": "10만km 이하", …}
```
경계(원문): 연식 **`year >= 값`** — 정확히 2018 은 '2018년 이후'에 **포함**. 주행 **`mileage_km > 0 AND mileage_km <= 값`** — 정확히 100,000 은
'10만km 이하'에 **포함**. **누적 옵션**이다: '2018년 이후 (N)' 의 N 은 2020·2022년 이후를 포함한 수라 옵션 count 의 합은 총수가 아니다.
템플릿·JS 에 경계·라벨·연도를 다시 적지 말 것 — 컨텍스트 `year_options`·`km_options` 를 그대로 돌린다. 라벨 뒤 `(N)` 은 프론트가 붙인다(FEAT-1 관례).

### 2.3 `vehicles.html` 컨텍스트 변수 (신규 7개, 기존 변수 무변경 — `price_bands` 의 count 는 이제 두 축을 반영)
| 변수 | 형 | 값 |
|---|---|---|
| `year_min` | `str` | 선택된 key(`"2018"`) 또는 `""`(정규화 후 — 잘못된 입력은 여기서 이미 `""`) |
| `km_max` | `str` | 선택된 key(`"100000"`) 또는 `""` |
| `year_options` | `list[dict]` | `YEAR_MIN_OPTIONS` 순서 그대로 **항상 4개**: `{"key": "2018", "label": "2018년 이후", "count": 279}`. 0건도 `count: 0` 으로 있음 |
| `km_options` | `list[dict]` | `KM_MAX_OPTIONS` 순서 그대로 **항상 4개**: `{"key": "100000", "label": "10만km 이하", "count": 147}` |
| `km_unknown_excluded` | `int` | **주행거리 축만 뺀 현재 모수**(다른 필터·가격대·연식 전부 적용)에서 `mileage_km IS NULL OR <= 0` 인 건수. `km_max` 를 골랐으면 정확히 이만큼이 목록에서 빠져 있다(그 외 빠진 것은 상한 초과분). 안 골랐을 때도 같은 값을 준다('고르면 빠질 건수' — 툴팁용). **"주행거리 미상 N건 제외" 문구는 `km_max` 가 있을 때만 그릴 것**(안 골랐을 땐 제외된 게 아니다) |
| `qs_no_year_min` | `str` | 현재 필터에서 `year_min` 만 뺀 쿼리스트링(`_qs("year_min")`, `qs_no_price` 관례). 셀렉트 옵션 href·해제 칩용. 빈 문자열일 수 있다 |
| `qs_no_km_max` | `str` | `km_max` 만 뺀 쿼리스트링 |
| `qs` (기존) | `str` | **year_min·km_max 포함** — 페이지네이션·정렬 링크·UX-5 요약 줄·검색 저장이 두 키를 잃지 않는다. `qs_no_price`·`qs_no_date`·`qs_no_q` 등 기존 `qs_no_*` 도 두 키를 보존한다(테스트로 고정) |

`count` 의 의미(패싯 규칙, 축 3종 공통): **자기 축만 뺀 나머지 현재 필터**(가격대·다른 축 포함)를 전부 적용한 모수에서 그 옵션에 드는 건수. 그래서
① 선택된 옵션의 `count == total` ② 다른 옵션의 `count` 는 "그 옵션으로 바꾸면 나올 총수" ③ 축을 바꿔도 **그 축의** 셀렉트 숫자는 그대로(자기 축은
모수에서 빠지므로), **다른 축의** 숫자는 바뀐다 ④ 항등식은 합이 아니라 `count[가장 작은 하한] + 미상 + 그보다 오래된 행 == 축 없는 총수`
(누적). usepick 페이지에서는 `use_counts`(갈래 칩)가 축 3종을 반영하고 축별 옵션이 갈래를 반영한다.

셀렉트 예(참고 — 템플릿은 프론트 몫, 여기서는 손대지 않았다):
```jinja
<select onchange="location.href=this.value">
  <option value="/vehicles{% if qs_no_year_min %}?{{ qs_no_year_min }}{% endif %}" {% if not year_min %}selected{% endif %}>연식 전체</option>
  {% for o in year_options %}
  <option value="/vehicles?year_min={{ o.key }}{% if qs_no_year_min %}&{{ qs_no_year_min }}{% endif %}" {% if year_min == o.key %}selected{% endif %}>{{ o.label }} ({{ o.count }})</option>
  {% endfor %}
</select>
{# km 도 같은 꼴(km_options·km_max·qs_no_km_max). 요약 줄(UX-5 _cs.parts)에는 price 와 같은 방식으로 라벨을 넣고,
   km_max 가 있으면 '주행거리 미상 {{ km_unknown_excluded }}건 제외' 를 요약 줄·툴팁에 #}
```
`has_filter`(필터 초기화 칩 표시 조건)에 `or year_min or km_max` 를 더하는 것은 프론트 몫.

### 2.4 `/api/vehicles/count`
`GET /api/vehicles/count?year_min=<key>&km_max=<key>&…` → `{"total": n}`. `/vehicles` 의 `total` 과 항상 같다(테스트 20조합 + usepick·bucket 10조합으로 대조).

## 3. 테스트 — `tests/test_feat2_year_km_filter.py` 신규 131건(파라미터 확장 포함), 전부 초록

| 항목 | 테스트 |
|---|---|
| 상수 형태(키=값 문자열·오름차순·라벨) | `test_options_single_source_shape` |
| 화이트리스트 거부 14+14종(`abc`·`2018.0`·`1e5`·`100,000`·빈값·공백·`02018`·`+2018`·범위 밖 `2019`·주입 문자열·None·int·list·bool) / 정확 키 수용 | `test_year_min_value_whitelist_rejects` · `test_km_max_value_whitelist_rejects` · `test_option_value_accepts_exact_keys` |
| 술어 경계 15+13건(**정확히 2018 포함**·**정확히 100,000 포함**·NULL·0·음수·문자열 숫자·bool) + 미상 규칙 6건 | `test_year_min_match_boundaries` · `test_km_max_match_boundaries` · `test_km_unknown_rule` |
| SQL 조각: 옵션마다 정확한 id 집합·NULL/0 제외·누적 포함 관계·20만 초과는 '범위 밖'·두 축+가격대 조합 | `test_list_vehicles_year_min_boundary_and_null_excluded` · `…km_max_boundary_and_unknown_excluded` · `test_list_vehicles_both_axes_and_price` |
| 파이썬 술어 == SQL 조각(옵션 4+4 + 조합 16) · 잘못된 key 는 같은 객체 · 집계 모양 | `test_python_predicate_agrees_with_sql_fragment` |
| COUNT 가 **한 쿼리**(execute 1회, `SUM(CASE WHEN` 5개, GROUP BY 없음)·옵션마다 목록 건수와 일치·항등식·미상 항이 실제 미상 수(3) | `test_count_by_year_min_is_one_query_and_matches_lists` · `test_count_by_km_max_is_one_query_and_matches_lists` |
| 0건 옵션도 key 존재(기아+≤5만: 4개 전부 0, 미상 1) · 다른 축 얹기 | `test_count_keeps_zero_options_and_other_filters` |
| 자기 축 TypeError · 다른 두 축 수용 · 가격대 COUNT 가 새 두 축을 받음 | `test_count_rejects_own_axis_but_accepts_the_other_two` |
| 잘못된 값 19종 → 200·필터 무시·테이블 무사(목록·count API 둘 다) | `test_invalid_params_are_ignored_not_500` |
| `/vehicles` 총수 == count API — SQL 경로 14·파이썬 경로(segment) 4·picks 1 | `test_list_total_equals_count_api` |
| 기존 필터 회귀(기아 6건 그대로·FEAT-1 가격대 그대로) | `test_existing_filters_regression_with_and_without_axes` |
| 템플릿 컨텍스트 계약(SQL 경로·파이썬 경로·선택 없음) — `TemplateResponse` 스파이로 실제 컨텍스트 검사: 7개 변수·선택 옵션 count==total·축 3종 상호 반영·`qs`/`qs_no_*` 보존 | `test_template_context_contract_sql_path` · `…_python_path` · `test_template_context_when_no_selection` |
| 패싯 예측: 다른 옵션 count == 그 옵션으로 바꾼 총수(연식·주행 각 4옵션, 제조사+다른 축 걸린 채) · 자기 축 바꿔도 자기 셀렉트 숫자 불변 | `test_facet_counts_predict_switch_totals` |
| `km_unknown_excluded` == 모수의 미상 수 == 빠진 행 − 상한 초과분 · 페이지 행에 미상 없음 | `test_km_unknown_excluded_is_exactly_what_the_filter_drops` |
| 요청당 쿼리: SQL 경로 `SUM(CASE` 2 + `GROUP BY band` 1 / 파이썬 경로 0 / count API 1 | `test_sql_path_adds_exactly_two_facet_queries_and_python_path_none` |
| usepick·bucket 경로 10조합 총수 일치(자체 픽스처: 추천 행 8개에 연식·주행 다르게) · 픽스처 자기 유효성 | `test_usepick_and_bucket_paths_agree_with_count_api` · `test_use_fixture_is_not_void` |
| usepick 패싯: 갈래 칩 == 총수 == 선택 옵션 count, 자기 축 표는 불변, 다른 축 표는 변함, 행 전부 조건 만족 | `test_usepick_facets_are_consistent_with_year_and_km` |
| 반증(메모리 변이체) — 조각 두 줄을 `pass` 로 바꾼 `_vehicles_where` 는 15행 전부 반환, 원본은 2행. 조각 **하나씩** 지운 변이체도 각각 정확한 누수 집합 | `test_where_fragments_are_load_bearing` |

### 반증 — 파일 수준(지시서 요구: 바이트 백업·복원·md5)
스크립트(scratchpad `mutate_feat2.py`)로 `web/db.py` 를 바이트 백업 → 앵커 두 문장(`where.append("year >= ?"); params.append(int(year_min))` ·
`where.append("mileage_km > 0 AND mileage_km <= ?"); params.append(int(km_max))`)을 `pass` 로 치환 → 이 테스트 파일 실행 → `finally` 복원.

| | md5 |
|---|---|
| 원본(변이 전) | `51554ba53440bed6cac1d44b4ca53401` |
| 변이체 | `e910b34cffd175aaf8866a8a598e0faa` |
| 복원 후 | `51554ba53440bed6cac1d44b4ca53401` (= 원본, RESTORED OK) |

변이체 결과: **28 failed, 103 passed**(확인된 사실 — `-rf` 로 이름 전부 기록). 실패 28건 = SQL 경계 3 · 술어일치 1 · COUNT 2 · 0건옵션 1 · 축거부 1 ·
총수일치 SQL 경로 15 · 기존회귀 1 · 컨텍스트 SQL 경로 1 · 패싯예측 1 · km_unknown 1 · 앵커 검사 1. 파이썬 경로(segment·usepick·bucket·picks)·
상수·화이트리스트·술어 단위 테스트는 SQL 조각과 무관해 초록이 맞다.

## 4. 요청당 DB 쿼리 수 (확인된 사실 — `db.connect` 프록시로 `execute` 호출 수 측정, 테스트 `test_sql_path_adds_exactly_two_facet_queries_and_python_path_none`)

| 요청 | 축별 COUNT 쿼리 | 변경 전(FEAT-1) 대비 |
|---|---|---|
| `/vehicles` (SQL 경로, 축 선택 무관) | 3 (`GROUP BY band` 1 + `SUM(CASE WHEN` 2) | **+2** |
| `/vehicles?segment=…` (파이썬 경로) | 0 | +0 |
| `/api/vehicles/count` (모든 변형) | 0 (execute 1회) | +0 |

세 축의 모수가 서로 다를 수 있어(각각 자기 축만 뺀 필터) 한 쿼리로 합치지 않았다 — 축을 아무것도 안 골랐을 땐 세 모수가 같아 합칠 수 있지만
(추정: 목록 페이지 1회당 SQLite 집계 2회, 1,400행 규모에서 수 ms) 분기 하나가 늘어 테스트 계약이 흐려지는 쪽을 택하지 않았다. 필요하면 별도 티켓.

## 5. 못 한 것 · 알려 둘 것

1. **템플릿 미반영** — 지시대로 `vehicles.html` 은 손대지 않았다. 컨텍스트는 이미 들어가지만 화면에는 아무것도 안 보인다(프론트 몫).
   `has_filter`·`_cs.parts`(UX-5 요약)·큰글씨 접힌 머리·검색 저장 라벨(`vehicles.html` 의 `ncSaveSearch` 안 `p.get('price')`+`PB` 맵 관례 —
   확인된 사실)에 두 키를 더해야 한다. 검색 저장의 `qs` 는 서버 `qs` 를 그대로 쓰므로 두 키는 이미 실린다(라벨만 프론트 몫).
2. **라벨 `(N)` 의 의미가 누적**이다(확인된 사실 — 스펙 원문 "2018년 이후 (N)"). '2018년 이후 (279)' 옆에 '2020년 이후 (167)' 이 있으면 사용자가
   구간(2018~2019 = 112)으로 읽을 수 있다. 디자인 검수 때 물을 것(가격대는 배타 구간이라 합이 총수였다).
3. `km_unknown_excluded` 는 **안 골랐을 때도 값을 준다**(같은 모수). 프론트가 `km_max` 없이 "제외" 라고 쓰면 거짓이 된다 — §2.3 에 명시.
   연식 미상 수(`year IS NULL OR <= 0`)는 지시서 계약에 없어 컨텍스트로 주지 않았다(`db.count_by_year_min(...)[None]` 에는 있다. 필요하면 한 줄).
4. 운영 DB 는 `mode=ro` 로 **열 타입만** 1회 읽었다(쓰기 없음): `year` integer 1,296 / null 122(0 이하 0건, 최소값 1) · `mileage_km` integer 1,100 /
   null 318(0 이하 4건). 텍스트 타입 행이 없어 `year >= ?` 가 텍스트 비교로 새는 경우는 없다(SQLite 는 TEXT > INTEGER 라 텍스트 연식이 있었다면
   모든 하한을 통과했을 것 — 파서 `_to_int` 가 막고 있다). 라이브 분포 425건 수치는 지시서 인용.
5. `/api/vehicles/count` 의 **기존** 패리티 틈 2개(FEAT-1 보고 §5-3: `promising` 미수신·`upcoming` 음수 클램프 없음)는 그대로다(범위 밖).
6. picks 경로는 500 없음·총수 일치만 확인했다(tmp DB 라 유망 0건 — 공허 통과에 가깝다. usepick·bucket 은 자체 픽스처 추천 8행으로 실제 행이 있는 상태에서
   축별 건수·갈래 칩·행 조건까지 검증했다).
7. `_price_key` 를 공용 `_single_key` 로 축약했다(동작 동일 — FEAT-1 테스트 103건 초록으로 확인). 캡처는 화면 변경이 없어 찍지 않았다(HEAD `66205d9`, dirty: 위 4파일).
