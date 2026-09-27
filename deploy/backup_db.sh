#!/usr/bin/env bash
# 운영 DB 매일 백업 — AUD-08 (오너 승인 2026-09-27).
#
#   deploy/backup_db.sh           # 백업 1회: 온라인 백업 → 무결성 검사 → gzip → 14일 넘은 것 삭제
#   deploy/backup_db.sh verify    # 복구 시험: 가장 새 백업을 풀어 무결성·행 수를 운영 DB 와 대조
#
# cron(서버, KST): 15 4 * * * /home/ubuntu/app/deploy/backup_db.sh >> /home/ubuntu/backups/backup.log 2>&1
#   04:15 인 이유 — 06:30 매일 갱신 전, 사람이 안 쓰는 시각. 백업 API 는 쓰는 중에도 일관된 사본을 만든다.
#
# 왜 파이썬인가: 서버에 sqlite3 명령줄 도구가 없다(2026-09-27 실측). 표준 라이브러리 backup() 이면 충분하다.
# 왜 이것만으로는 부족한가: 같은 인스턴스 안의 사본은 인스턴스·디스크를 잃으면 함께 사라진다 —
#   집 PC 가 매일 내려받는다(tools/pull_db_backup.ps1, 예약 작업 naechaget-db-backup-pull).
set -euo pipefail

SRC="${SRC:-/home/ubuntu/app/data/auction.db}"
DST="${DST:-/home/ubuntu/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$DST"

if [ "${1:-}" = "verify" ]; then
  LATEST="$(ls -1t "$DST"/auction-*.db.gz 2>/dev/null | head -1 || true)"
  [ -n "$LATEST" ] || { echo "$(date -Iseconds) verify FAIL: 백업 파일 없음"; exit 1; }
  TMP="$(mktemp /tmp/restore-XXXXXX.db)"
  gunzip -c "$LATEST" > "$TMP"
  python3 - "$TMP" "$SRC" "$(basename "$LATEST")" <<'PY'
import sqlite3, sys
bak, live, name = sys.argv[1], sys.argv[2], sys.argv[3]
b = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
l = sqlite3.connect(f"file:{live}?mode=ro", uri=True)
ok = b.execute("pragma integrity_check").fetchone()[0]
tables = [r[0] for r in b.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
print(f"복구 시험 {name}: integrity={ok} · 테이블 {len(tables)}개")
for t in tables:
    nb = b.execute(f'select count(*) from "{t}"').fetchone()[0]
    try:
        nl = l.execute(f'select count(*) from "{t}"').fetchone()[0]
    except sqlite3.Error:
        nl = None
    print(f"  {t}: 백업 {nb} · 운영 {nl}")
if ok != "ok":
    sys.exit("integrity_check 실패")
PY
  rm -f "$TMP"
  exit 0
fi

TS="$(date +%Y%m%d)"
TMP="$DST/.auction-$TS.db.tmp"
OUT="$DST/auction-$TS.db.gz"
rm -f "$TMP"
python3 - "$SRC" "$TMP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
d = sqlite3.connect(dst)
s.backup(d)
ok = d.execute("pragma integrity_check").fetchone()[0]
n = d.execute("select count(*) from vehicles").fetchone()[0]
d.close(); s.close()
if ok != "ok":
    sys.exit(f"integrity_check 실패: {ok}")
print(f"vehicles={n} integrity=ok")
PY
gzip -c "$TMP" > "$OUT.new"
mv "$OUT.new" "$OUT"
rm -f "$TMP"
find "$DST" -maxdepth 1 -name 'auction-*.db.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Iseconds) ok $(basename "$OUT") $(stat -c %s "$OUT")B"
