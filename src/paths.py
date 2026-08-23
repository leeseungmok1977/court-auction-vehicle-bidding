"""데이터 저장 루트(외부화).

로컬 개발은 프로젝트 내 ``./data``, 배포(영속 볼륨)는 환경변수 ``DATA_DIR``로
마운트 경로를 가리킨다. SQLite DB·물건 폴더(사진·감정요항)가 모두 이 아래 저장되므로,
배포 시 반드시 영속 디스크를 ``DATA_DIR``로 지정해야 데이터가 유지된다.
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR: Path = (
    Path(os.environ["DATA_DIR"]).expanduser().resolve()
    if os.environ.get("DATA_DIR")
    else _ROOT / "data"
)
