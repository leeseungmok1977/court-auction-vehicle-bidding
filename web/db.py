"""SQLite 저장소 (운영 웹도구).

물건(vehicles): 법원경매 상세 + 엔카 시세 + 산정 결과 + 사용자 선택(관심/메모/최종입찰가) 병합.
수집이력(runs): 백그라운드 수집 실행 상태.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from src.paths import DATA_DIR

DB_PATH = DATA_DIR / "auction.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id            TEXT PRIMARY KEY,   -- folder_key: 사건번호_물건번호
    case_no       TEXT,
    item_no       TEXT,
    court         TEXT,
    court_code    TEXT,
    location      TEXT,
    match_label   TEXT,
    maker         TEXT,
    model         TEXT,
    year          INTEGER,
    mileage_km    INTEGER,
    displacement_cc INTEGER,
    fuel_code     TEXT,
    appraisal_value INTEGER,
    min_sale_price  INTEGER,
    fail_count    INTEGER,
    sale_date     TEXT,
    accident_grade TEXT,
    accident_hits  TEXT,   -- json
    insurance_history TEXT, -- json
    doc_id        TEXT,
    appraisal_ecdoc_id TEXT,
    spec_remark   TEXT,          -- 매각물건명세 요약(법원 제공)
    inspection_to TEXT,          -- 자동차검사 유효기간 만료일 (감정요항 파싱)
    condition_level TEXT,        -- 상태 등급: unknown/fair/poor (감정요항 파싱)
    condition_flags TEXT,        -- json: 상태·검사 플래그
    photo_order   TEXT,          -- json: 사진 파일명 순서(정면·측면·실내… 비전 분류)
    photo_count   INTEGER,
    folder_key    TEXT,
    -- 시세
    market_platform TEXT,
    encar_total   INTEGER,
    sample_count  INTEGER,
    mean_price    INTEGER,
    median_price  INTEGER,
    min_price     INTEGER,
    market_confidence INTEGER,      -- 시세 신뢰도 점수 0~100
    market_confidence_label TEXT,   -- 높음 / 보통 / 낮음
    market_cv     REAL,             -- 변동계수(가격 흩어짐)
    market_vs_appraisal REAL,       -- 시세중앙값 / 감정가 (괴리 감지)
    comps         TEXT,             -- json: 중앙값 산출에 쓴 개별 동급 매물(감사용)
    actual_price  INTEGER,          -- 사용자가 실측 확인한 시세 (캘리브레이션)
    actual_price_at TEXT,
    -- 케이카 2차 소스 교차검증
    kcar_median   INTEGER,          -- 케이카 동급 중앙값
    kcar_sample   INTEGER,          -- 케이카 표본수
    cross_source_status TEXT,       -- single / agree / diverge
    cross_source_rel REAL,          -- 두 소스 상대편차 (0.05=5%)
    kcar_checked_at TEXT,
    -- 산정
    repair_cost   INTEGER DEFAULT 500000,
    upper_bid     INTEGER,
    lower_bound   INTEGER,
    judgment      TEXT,
    breakdown     TEXT,    -- json
    status        TEXT,    -- 완료 / 미매핑 / 오류
    -- 낙찰결과 (매각기일 이후)
    auction_result    TEXT,     -- 낙찰 / 유찰 / 변경 / 취하 / 미확정
    winning_price     INTEGER,  -- 낙찰가
    dxdy_history      TEXT,     -- json (회차별 기일·결과·낙찰가)
    result_checked_at TEXT,
    result_source     TEXT,     -- detail(잠정) / result_search(권위·확정)
    -- 사용자 선택
    starred       INTEGER DEFAULT 0,
    memo          TEXT DEFAULT '',
    final_bid     INTEGER,
    collected_at  TEXT,
    analyzed_at   TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    status      TEXT,      -- running / done / error
    scanned     INTEGER DEFAULT 0,
    processed   INTEGER DEFAULT 0,
    target      INTEGER DEFAULT 0,
    message     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 낙찰 결과 영구 히스토리(append-only) — 라이브 vehicles 갱신·만료와 무관하게 누적.
-- 예상낙찰가 할인모델(전역·유찰·모델별) 학습·백테스트의 durable 데이터셋.
CREATE TABLE IF NOT EXISTS sale_results (
    id            TEXT PRIMARY KEY,   -- court_code|case_no|item_no
    court_code    TEXT,
    case_no       TEXT,
    item_no       TEXT,
    maker         TEXT,
    model         TEXT,
    model_key     TEXT,               -- 정규화 그룹키(maker|model) — 모델별 할인율 집계용
    year          INTEGER,
    mileage_km    INTEGER,
    fuel_code     TEXT,
    median_price  INTEGER,            -- 분석 당시 시세중앙값(스냅샷)
    min_sale_price INTEGER,
    fail_count    INTEGER,
    encar_total   INTEGER,            -- 인기 프록시(동모델 전체 매물수, 스냅샷)
    market_confidence_label TEXT,
    winning_price INTEGER,            -- 실제 낙찰가
    ratio         REAL,               -- winning_price / median_price (할인율)
    sale_date     TEXT,
    recorded_at   TEXT
);
"""

_JSON_COLS = {"accident_hits", "insurance_history", "breakdown", "dxdy_history", "comps",
              "condition_flags", "photo_order"}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout: 분석 스레드의 쓰기와 상태 폴링의 읽기가 겹칠 때 잠금 대기
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")      # 읽기가 쓰기에 막히지 않도록
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    conn = connect()
    with conn:
        conn.executescript(_SCHEMA)
        # 마이그레이션: 기존 DB에 신규 열 추가
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(vehicles)").fetchall()}
        for col in ("location", "match_label", "auction_result",
                    "dxdy_history", "result_checked_at"):
            if col not in cols:
                conn.execute(f"ALTER TABLE vehicles ADD COLUMN {col} TEXT")
        if "winning_price" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN winning_price INTEGER")
        if "market_confidence" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN market_confidence INTEGER")
        if "market_confidence_label" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN market_confidence_label TEXT")
        if "market_cv" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN market_cv REAL")
        if "market_vs_appraisal" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN market_vs_appraisal REAL")
        if "comps" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN comps TEXT")
        if "actual_price" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN actual_price INTEGER")
        if "actual_price_at" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN actual_price_at TEXT")
        if "result_source" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN result_source TEXT")
        if "kcar_median" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN kcar_median INTEGER")
        if "kcar_sample" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN kcar_sample INTEGER")
        if "cross_source_status" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN cross_source_status TEXT")
        if "cross_source_rel" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN cross_source_rel REAL")
        if "kcar_checked_at" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN kcar_checked_at TEXT")
        if "spec_remark" not in cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN spec_remark TEXT")
        for col in ("inspection_to", "condition_level", "condition_flags", "photo_order"):
            if col not in cols:
                conn.execute(f"ALTER TABLE vehicles ADD COLUMN {col} TEXT")
    conn.close()


def _encode(rec: dict) -> dict:
    out = dict(rec)
    for c in _JSON_COLS:
        if c in out and not isinstance(out[c], str):
            out[c] = json.dumps(out[c], ensure_ascii=False)
    return out


def _decode(row: sqlite3.Row) -> dict:
    d = dict(row)
    for c in _JSON_COLS:
        if d.get(c):
            try:
                d[c] = json.loads(d[c])
            except (TypeError, json.JSONDecodeError):
                pass
    return d


def upsert_vehicle(rec: dict) -> None:
    rec = _encode(rec)
    cols = list(rec.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols
                       if c not in ("id", "starred", "memo", "final_bid", "actual_price", "actual_price_at"))
    sql = (f"INSERT INTO vehicles ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT(id) DO UPDATE SET {updates}")
    conn = connect()
    with conn:
        conn.execute(sql, [rec[c] for c in cols])
    conn.close()


# 목록 갱신 시 보존할 열 (분석 결과·사용자 선택·상태)
_LISTING_KEEP = {
    "id", "status", "starred", "memo", "final_bid", "collected_at",
    "median_price", "mean_price", "min_price", "sample_count", "encar_total",
    "market_confidence", "market_confidence_label", "market_cv", "market_vs_appraisal",
    "comps", "actual_price", "actual_price_at",
    "kcar_median", "kcar_sample", "cross_source_status", "cross_source_rel", "kcar_checked_at",
    "market_platform", "upper_bid", "lower_bound", "judgment", "breakdown",
    "repair_cost", "mileage_km", "displacement_cc", "fuel_code", "accident_grade",
    "accident_hits", "insurance_history", "appraisal_ecdoc_id", "spec_remark", "photo_count",
    "inspection_to", "condition_level", "condition_flags", "photo_order",
    "analyzed_at", "match_label",
    "auction_result", "winning_price", "dxdy_history", "result_checked_at", "result_source",
}


def upsert_listing(rec: dict) -> None:
    """목록 갱신용 upsert. 신규는 status='미분석', 기존은 목록 필드(가격·기일 등)만 갱신하고
    분석 결과·사용자 선택·상태는 보존한다."""
    rec = _encode(rec)
    cols = list(rec.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in _LISTING_KEEP)
    sql = (f"INSERT INTO vehicles ({','.join(cols)}, status) "
           f"VALUES ({placeholders}, '미분석') "
           f"ON CONFLICT(id) DO UPDATE SET {updates}")
    conn = connect()
    with conn:
        conn.execute(sql, [rec[c] for c in cols])
    conn.close()


def get_vehicle(vid: str) -> Optional[dict]:
    conn = connect()
    row = conn.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()
    conn.close()
    return _decode(row) if row else None


def list_vehicles(judgment: Optional[str] = None, maker: Optional[str] = None,
                  q: Optional[str] = None, starred: Optional[bool] = None,
                  sort: str = "sale_date", upcoming_days: Optional[int] = None,
                  status: Optional[str] = None, result: Optional[str] = None,
                  cond: Optional[str] = None, hide_incomplete: bool = False,
                  date: Optional[str] = None) -> list[dict]:
    where, params = [], []
    if date:                         # 특정 매각기일(달력에서 날짜 클릭)
        where.append("sale_date = ?"); params.append(date)
    if cond == "insp_expired":       # 자동차검사 유효기간 경과
        where.append("inspection_to IS NOT NULL AND inspection_to <> '' "
                     "AND inspection_to < date('now','localtime')")
    elif cond == "damaged":          # 외관·상태 손상 언급
        where.append("condition_level IN ('fair','poor')")
    if judgment:
        where.append("judgment=?"); params.append(judgment)
        if judgment == "입찰 검토 가능":
            # 실제 입찰 가능만: 매각기일이 지나지 않았고(미래·오늘) + 낙찰/종결 아님.
            # (지난 기일 유찰='다음 기일 미정', 이미 낙찰된 물건이 '검토 가능'에 섞이는 신뢰 문제 방지)
            where.append("sale_date >= date('now','localtime')")
            where.append("(auction_result IS NULL OR auction_result NOT IN ('낙찰','종결'))")
    if maker == MAKER_UNKNOWN:
        where.append("(maker='' OR maker IS NULL)")
    elif maker:
        variants = _maker_variants(maker)   # 정규화 기준 같은 브랜드 원문 표기 전부
        if variants:
            where.append("maker IN (%s)" % ",".join("?" * len(variants)))
            params += variants
        else:
            where.append("maker=?"); params.append(maker)
    if status == "pending":                       # 분석 대기(미분석·미매핑)
        where.append("status IN ('미분석','미매핑')")
    elif status:
        where.append("status=?"); params.append(status)
    # 목록 뷰에서만: 평가 불가한 물건 숨김(정보 채워지면 자동 재노출).
    #  - '상세없음'(법원 상세 조회불가), 또는
    #  - 아직 시세 미산출(median NULL)이면서 주행거리·사진이 없는 물건.
    #  단, 시세가 산출된 '완료' 물건은 사진/주행이 없어도 유지. 내부 재분석은 이 필터를 안 씀.
    if hide_incomplete and status not in ("상세없음", "pending"):
        where.append("NOT (COALESCE(status,'')='상세없음' OR "
                     "(median_price IS NULL AND "
                     "(mileage_km IS NULL OR COALESCE(photo_count,0)=0)))")
    if result:
        where.append("auction_result=?"); params.append(result)
    if starred:
        where.append("starred=1")
    if upcoming_days is not None:
        where.append("sale_date >= date('now','localtime') "
                     "AND sale_date <= date('now','localtime',?)")
        params.append(f"+{int(upcoming_days)} day")
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(model LIKE ? ESCAPE '\\' OR maker LIKE ? ESCAPE '\\' "
                     "OR case_no LIKE ? ESCAPE '\\' OR court LIKE ? ESCAPE '\\')")
        params += [like, like, like, like]
    sql = "SELECT * FROM vehicles"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sort_cols = {"sale_date": "sale_date", "min_sale_price": "min_sale_price",
                 "upper_bid": "upper_bid DESC", "median_price": "median_price DESC",
                 "fail_count": "fail_count DESC",
                 "mileage": "mileage_km IS NULL, mileage_km",   # 짧은 주행거리순(NULL 뒤로)
                 "inspection": "inspection_to IS NULL, inspection_to"}
    sql += f" ORDER BY {sort_cols.get(sort, 'sale_date')}"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_decode(r) for r in rows]


def update_fields(vid: str, **fields) -> None:
    if not fields:
        return
    fields = _encode(fields)   # comps 등 JSON 컬럼 직렬화
    sets = ",".join(f"{k}=?" for k in fields)
    conn = connect()
    with conn:
        conn.execute(f"UPDATE vehicles SET {sets} WHERE id=?", [*fields.values(), vid])
    conn.close()


def counts_by_judgment() -> dict:
    conn = connect()
    rows = conn.execute(
        "SELECT judgment, COUNT(*) c FROM vehicles GROUP BY judgment").fetchall()
    d = {(r["judgment"] or "미분류"): r["c"] for r in rows}
    # '입찰 검토 가능'은 실제 입찰 가능(미래 기일 + 미낙찰/미종결)만 카운트 —
    # 지난 기일 유찰(다음 기일 미정)·이미 낙찰 물건이 검토가능 KPI에 잡히는 신뢰 문제 방지.
    # (list_vehicles(judgment='입찰 검토 가능') 필터와 동일 기준 → KPI=목록 일치)
    biddable = conn.execute(
        "SELECT COUNT(*) c FROM vehicles WHERE judgment='입찰 검토 가능' "
        "AND sale_date >= date('now','localtime') "
        "AND (auction_result IS NULL OR auction_result NOT IN ('낙찰','종결'))").fetchone()["c"]
    d["입찰 검토 가능"] = biddable
    conn.close()
    return d


def top_makers(limit: int = 8) -> list:
    """물건 수 상위 제조사(정규화 표기, 미래 기일 기준) — 브랜드 바로가기용 [(maker, n)]."""
    conn = connect()
    rows = conn.execute(
        "SELECT maker, COUNT(*) c FROM vehicles "
        "WHERE maker IS NOT NULL AND maker <> '' "
        "AND sale_date >= date('now','localtime') GROUP BY maker").fetchall()
    conn.close()
    from collections import Counter
    agg: Counter = Counter()
    for r in rows:
        agg[_canon_maker(r["maker"])] += r["c"]
    agg.pop("", None)
    return agg.most_common(limit)


def sale_date_counts(start_iso: str, end_iso: str) -> dict:
    """[start,end] 구간의 매각기일별 물건 수 {YYYY-MM-DD: n} — 경매 달력용."""
    conn = connect()
    rows = conn.execute(
        "SELECT sale_date, COUNT(*) c FROM vehicles "
        "WHERE sale_date >= ? AND sale_date <= ? AND sale_date IS NOT NULL "
        "GROUP BY sale_date", (start_iso, end_iso)).fetchall()
    conn.close()
    return {r["sale_date"]: r["c"] for r in rows}


MAKER_UNKNOWN = "(제조사 미상)"   # 제조사 빈값/NULL 물건을 격리하는 드롭다운 센티넬


def _canon_maker(raw: str) -> str:
    """원문 제조사 표기를 대표 브랜드로 정규화. 불확실하면 원문 유지(오병합 방지).

    실 DB 142개 표기를 대상으로 그룹 검증 완료. 승용 브랜드 간·중장비와의 오병합 없음.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower().replace(" ", "").replace("(", "").replace(")", "")
    # 1) 건설기계·인프라코어: '현대건설기계'·'현대인프라코어'가 '현대'로 오병합되는 것 차단
    if "건설기계" in low or "인프라코어" in low:
        return s
    # 2) 대표 브랜드 규칙(부분일치, 첫 매치 우선 — 충돌·구체 항목을 위에)
    for keys, canon in _MAKER_RULES:
        if any(k in low for k in keys):
            return canon
    return s


_MAKER_RULES = [
    (("타타대우",), "타타대우"),                                   # '대우'보다 먼저
    (("쌍용", "kgm", "케이지모빌리티", "kg모빌리티", "kgn"), "KG모빌리티(쌍용)"),  # 'kgm'∋'gm' → GM보다 먼저
    (("제네시스", "genesis"), "제네시스"),                          # '현대'보다 먼저(별도 마르크)
    (("현대", "hyundai"), "현대"),
    (("기아", "kia"), "기아"),
    (("메르세데스", "벤츠", "benz", "다임러", "daimler", "mercedes"), "벤츠"),
    (("미니", "mini"), "미니"),                                   # 'bmw'보다 먼저(별도 마르크)
    (("비엠더블유", "bmw"), "BMW"),
    (("아우디", "audi"), "아우디"),
    (("폭스바겐", "폭스바켄", "volkswagen"), "폭스바겐"),
    (("포르쉐", "porsche"), "포르쉐"),
    (("랜드로버", "landrover"), "랜드로버"),
    (("재규어", "제규어", "재규", "jaguar"), "재규어"),
    (("르노삼성",), "르노삼성"),
    (("르노코리아",), "르노코리아"),
    (("르노", "renault"), "르노"),
    (("쉐보레", "chevrolet", "지엠", "제너럴모터스", "gm", "대우"), "쉐보레(GM대우)"),
    (("만트럭", "man"), "MAN"),
    (("스카니아", "scania"), "스카니아"),
    (("볼보", "volvo"), "볼보"),
    (("포드", "ford"), "포드"),
    (("지프", "jeep", "fca"), "지프"),
    (("크라이슬러", "chrysler"), "크라이슬러"),
    (("스텔란티스", "stellantis"), "스텔란티스"),
    (("푸조", "peugeot"), "푸조"),
    (("링컨", "lincoln"), "링컨"),
    (("테슬라", "tesla"), "테슬라"),
    (("토요타", "도요타", "toyota"), "토요타"),
    (("닛산", "nissan"), "닛산"),
    (("혼다", "honda"), "혼다"),
    (("벤틀리", "밴틀리", "bentley"), "벤틀리"),
    (("페라리", "ferrari"), "페라리"),
    (("마세라티", "maserati"), "마세라티"),
    (("byd",), "BYD"),
    (("두산",), "두산"),
]


def _maker_variants(value: str) -> list[str]:
    """정규화 기준 같은 브랜드에 속하는 원문 maker 표기 전부(필터 확장용)."""
    target = _canon_maker(value)
    conn = connect()
    allm = [r["maker"] for r in conn.execute(
        "SELECT DISTINCT maker FROM vehicles WHERE maker<>''").fetchall()]
    conn.close()
    return [m for m in allm if _canon_maker(m) == target]


def distinct_makers() -> list[str]:
    """대표 브랜드(정규화)만 물건 많은 순으로. 제조사 미상이 있으면 센티넬 추가."""
    conn = connect()
    rows = conn.execute("SELECT maker, COUNT(*) c FROM vehicles GROUP BY maker").fetchall()
    conn.close()
    agg: dict[str, int] = {}
    unknown = 0
    for r in rows:
        m = r["maker"]
        if not m:
            unknown += r["c"]; continue
        c = _canon_maker(m)
        if not c or len(c) < 2 or c.isdigit():
            continue        # 노이즈(단일문자·숫자 등) 제외 — 전체 목록에는 남음
        agg[c] = agg.get(c, 0) + r["c"]
    out = [k for k, _ in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))]
    if unknown:
        out.append(MAKER_UNKNOWN)
    return out


# --- runs ---
def create_run(target: int) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO runs (started_at, status, target) VALUES (datetime('now','localtime'), 'running', ?)",
            (target,))
    rid = cur.lastrowid
    conn.close()
    return rid


def update_run(rid: int, **fields) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    conn = connect()
    with conn:
        conn.execute(f"UPDATE runs SET {sets} WHERE id=?", [*fields.values(), rid])
        # 하트비트: 다른 프로세스(웹/CLI/스케줄러)가 실행 여부를 판별할 수 있게
        conn.execute("INSERT INTO settings (key, value) VALUES ('run_heartbeat', datetime('now','localtime')) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.close()


def latest_run() -> Optional[dict]:
    conn = connect()
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def clear_orphaned_runs() -> int:
    """서버 시작 시 호출 — 프로세스 재시작으로 미완결된 'running' 런을 '중단'으로 정리.
    (스레드가 죽으면 finally가 상태를 못 지워 좀비 'running' 레코드가 남아 '진행 중'이 고착됨)"""
    conn = connect()
    with conn:
        cur = conn.execute(
            "UPDATE runs SET status='error', finished_at=datetime('now','localtime'), "
            "message=COALESCE(message,'')||' (서버 재시작으로 중단됨)' WHERE status='running'")
    n = cur.rowcount
    conn.close()
    return n


def total_vehicles() -> int:
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM vehicles").fetchone()["c"]
    conn.close()
    return n


def upcoming_count(days: int = 30) -> int:
    conn = connect()
    n = conn.execute(
        "SELECT COUNT(*) c FROM vehicles WHERE sale_date >= date('now','localtime') "
        "AND sale_date <= date('now','localtime', ?)", (f"+{int(days)} day",)).fetchone()["c"]
    conn.close()
    return n


def pending_count() -> int:
    """분석 대기(미분석/미매핑) 건수."""
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM vehicles WHERE status IN ('미분석','미매핑')").fetchone()["c"]
    conn.close()
    return n


def won_count() -> int:
    """낙찰(매각) 건수."""
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM vehicles WHERE auction_result='낙찰'").fetchone()["c"]
    conn.close()
    return n


def clear_rescheduled_results() -> int:
    """재조정으로 매각기일이 미래가 된 유찰/기타 물건의 낡은 결과를 비운다(낙찰은 보존)."""
    conn = connect()
    with conn:
        cur = conn.execute(
            "UPDATE vehicles SET auction_result=NULL, winning_price=NULL, result_checked_at=NULL "
            "WHERE auction_result IN ('유찰','기타') "
            "AND sale_date > date('now','localtime')")
    n = cur.rowcount
    conn.close()
    return n


def clear_detailless_market() -> int:
    """상세(주행거리·사진)가 전혀 없는데 시세만 붙은 물건의 시세/산정을 제거(데이터 일관성).
    낙찰결과는 보존."""
    conn = connect()
    with conn:
        cur = conn.execute(
            "UPDATE vehicles SET median_price=NULL, mean_price=NULL, min_price=NULL, "
            "sample_count=NULL, encar_total=NULL, market_platform=NULL, match_label=NULL, "
            "market_confidence=NULL, market_confidence_label=NULL, market_cv=NULL, "
            "upper_bid=NULL, lower_bound=NULL, judgment=NULL, breakdown=NULL, "
            "status=CASE WHEN sale_date IS NOT NULL AND sale_date < date('now','localtime') "
            "THEN '종결' ELSE '미분석' END "
            "WHERE median_price IS NOT NULL AND mileage_km IS NULL "
            "AND (photo_count IS NULL OR photo_count=0)")
    n = cur.rowcount
    conn.close()
    return n


def mark_aged_out(days: int = 45) -> int:
    """매각기일이 너무 오래 지나(매각결과검색에서 만료) 확인 불가한 물건을 '종결'로 표시.
    낙찰/종결은 제외 → 이후 재조회 대상에서 빠져 과도한 재스캔을 막는다."""
    conn = connect()
    with conn:
        cur = conn.execute(
            "UPDATE vehicles SET auction_result='종결', result_checked_at=datetime('now','localtime') "
            "WHERE sale_date < date('now','localtime', ?) "
            "AND (auction_result IS NULL OR auction_result IN ('유찰','기타','미확정'))",
            (f"-{int(days)} day",))
    n = cur.rowcount
    conn.close()
    return n


# --- settings (key-value) ---
def set_setting(key: str, value: str) -> None:
    conn = connect()
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.close()


def get_setting(key: str, default=None):
    conn = connect()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def get_all_settings() -> dict:
    conn = connect()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# --- 낙찰 결과 히스토리 (append-only 누적) ---
_SALE_COLS = ("id", "court_code", "case_no", "item_no", "maker", "model", "model_key",
              "year", "mileage_km", "fuel_code", "median_price", "min_sale_price",
              "fail_count", "encar_total", "market_confidence_label", "winning_price",
              "ratio", "sale_date", "recorded_at")


def record_sale_result(rec: dict) -> None:
    """확정 낙찰 1건을 히스토리에 기록(멱등: 같은 id면 갱신). 학습 데이터 누적용."""
    if not rec.get("id") or not rec.get("winning_price") or not rec.get("median_price"):
        return
    row = {k: rec.get(k) for k in _SALE_COLS}
    cols = list(row.keys())
    ph = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
    conn = connect()
    with conn:
        conn.execute(
            f"INSERT INTO sale_results ({','.join(cols)}) VALUES ({ph}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}", [row[c] for c in cols])
    conn.close()


def list_sale_results() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM sale_results").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_sale_results() -> int:
    conn = connect()
    n = conn.execute("SELECT COUNT(*) c FROM sale_results").fetchone()["c"]
    conn.close()
    return n
