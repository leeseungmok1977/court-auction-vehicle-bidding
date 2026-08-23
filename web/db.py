"""SQLite 저장소 (운영 웹도구).

물건(vehicles): 법원경매 상세 + 엔카 시세 + 산정 결과 + 사용자 선택(관심/메모/최종입찰가) 병합.
수집이력(runs): 백그라운드 수집 실행 상태.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path("data") / "auction.db"

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
    photo_count   INTEGER,
    folder_key    TEXT,
    -- 시세
    market_platform TEXT,
    encar_total   INTEGER,
    sample_count  INTEGER,
    mean_price    INTEGER,
    median_price  INTEGER,
    min_price     INTEGER,
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
"""

_JSON_COLS = {"accident_hits", "insurance_history", "breakdown", "dxdy_history"}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    # timeout: 분석 스레드의 쓰기와 상태 폴링의 읽기가 겹칠 때 잠금 대기
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
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
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("id", "starred", "memo", "final_bid"))
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
    "market_platform", "upper_bid", "lower_bound", "judgment", "breakdown",
    "repair_cost", "mileage_km", "displacement_cc", "fuel_code", "accident_grade",
    "accident_hits", "insurance_history", "appraisal_ecdoc_id", "photo_count",
    "analyzed_at", "match_label",
    "auction_result", "winning_price", "dxdy_history", "result_checked_at",
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
                  status: Optional[str] = None, result: Optional[str] = None) -> list[dict]:
    where, params = [], []
    if judgment:
        where.append("judgment=?"); params.append(judgment)
    if maker:
        where.append("maker=?"); params.append(maker)
    if status:
        where.append("status=?"); params.append(status)
    if result:
        where.append("auction_result=?"); params.append(result)
    if starred:
        where.append("starred=1")
    if upcoming_days is not None:
        where.append("sale_date >= date('now','localtime') "
                     "AND sale_date <= date('now','localtime',?)")
        params.append(f"+{int(upcoming_days)} day")
    if q:
        where.append("(model LIKE ? OR case_no LIKE ? OR court LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql = "SELECT * FROM vehicles"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sort_cols = {"sale_date": "sale_date", "min_sale_price": "min_sale_price",
                 "upper_bid": "upper_bid DESC", "median_price": "median_price DESC",
                 "fail_count": "fail_count DESC"}
    sql += f" ORDER BY {sort_cols.get(sort, 'sale_date')}"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_decode(r) for r in rows]


def update_fields(vid: str, **fields) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    conn = connect()
    with conn:
        conn.execute(f"UPDATE vehicles SET {sets} WHERE id=?", [*fields.values(), vid])
    conn.close()


def counts_by_judgment() -> dict:
    conn = connect()
    rows = conn.execute(
        "SELECT judgment, COUNT(*) c FROM vehicles GROUP BY judgment").fetchall()
    conn.close()
    return {(r["judgment"] or "미분류"): r["c"] for r in rows}


def distinct_makers() -> list[str]:
    conn = connect()
    rows = conn.execute(
        "SELECT DISTINCT maker FROM vehicles WHERE maker<>'' ORDER BY maker").fetchall()
    conn.close()
    return [r["maker"] for r in rows]


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
