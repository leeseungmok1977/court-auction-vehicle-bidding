"""pytest 루트 설정.

① 프로젝트 루트를 import 경로에 추가해 `src.*` 임포트를 가능하게 한다.
② **테스트가 운영 DB를 읽지 못하게 막는다.** 4회차 품질 감사에서 400건 중 11건이
   `data/auction.db`에 닿는 것이 확인됐고, 그 안에 3회차 P0 회귀 가드가 들어 있었다
   (`DATA_DIR`를 빈 디렉터리로 두면 11 failed). 회귀 가드의 실행 여부가 그날
   운영자 PC의 데이터 상태에 달려 있으면 가드가 아니다.
③ 모듈 전역 캐시를 테스트마다 비운다. `_reduction_cache`·`_multi_lot_cache`는
   키가 없거나 약해서 앞 테스트의 결과가 뒤 테스트로 새어 나간다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _isolate_db_and_caches(tmp_path, monkeypatch):
    """모든 테스트를 빈 임시 DB + 빈 캐시에서 시작시킨다.

    개별 테스트가 자기 DB_PATH를 다시 monkeypatch하는 것은 그대로 동작한다
    (이 픽스처는 '기본값'을 안전한 쪽으로 바꿀 뿐이다).
    """
    from web import db, service

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "autouse.db", raising=False)
    db.init_db()          # 빈 스키마 — 테이블이 없으면 조회가 OperationalError로 죽는다
    for name, empty in (("_bt_cache", {"t": 0.0, "data": None, "key": None}),
                        ("_reduction_cache", {"key": None, "data": None}),
                        ("_multi_lot_cache", {"ids": None}),
                        ("_config_cache", None)):
        if not hasattr(service, name):
            continue
        if name == "_config_cache":
            continue          # config는 파일 mtime 기반이라 오염되지 않는다
        monkeypatch.setattr(service, name, dict(empty), raising=False)
    yield
