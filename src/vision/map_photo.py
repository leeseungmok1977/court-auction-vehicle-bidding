"""법원이 사진으로 제공하는 '지도(지적도·위치도)'를 차량 사진과 가려낸다.

법원은 차량 보관장소를 **주소 대신 지도 이미지로** 주는 경우가 많고, 그 이미지가
`data/<key>/photos/` 안에 차량 사진과 섞여 들어온다. 확장자로는 구분되지 않는다.

지도와 차량 사진은 통계적으로 다르다:
  · 지도는 **평평한 색 몇 개**로 칠해진다(파스텔 필지·도로) → 색이 소수 빈에 몰린다
  · 지도는 밝다 → 밝고 채도 낮은 픽셀 비율이 높다
  · 지도는 선이 얇아 평균 엣지 강도가 낮다 (사진은 질감·그림자로 높다)

⚠ 밝기(pale) 하나로는 못 가른다. 실측에서 하늘이 넓은 차량 사진이 pale 0.40~0.41로
   지도(0.43~0.49)와 겹쳤다. 그래서 **색 집중도(top)와 엣지**를 함께 본다.

정답 6장으로 검증한 경계(전부 정확히 갈림):
  pale grey  top edge  실제
  0.41 0.51 0.51 12.4  차량(지게차)   → 제외
  0.40 0.42 0.51  9.5  차량(덤프트럭) → 제외
  0.43 0.25 0.73  5.5  지도(마곡동)   → 포함
  0.49 0.21 0.73  6.8  지도(양촌읍)   → 포함
  0.56 0.28 0.71  6.2  지도(평택)     → 포함
  0.60 0.17 0.85  3.4  지도           → 포함
"""
from __future__ import annotations

import os
from typing import Optional

PALE_MIN = 0.40      # 밝고 옅은 바탕 비율
TOP_MIN = 0.60       # 상위 24개 색 빈이 차지하는 비율(평평함)
EDGE_MAX = 10.0      # 평균 엣지 강도 — 사진은 이보다 크다
_EXTS = (".jpg", ".jpeg", ".png", ".gif")


def map_features(path: str) -> Optional[dict]:
    """이미지 한 장의 지도 판정 특징. 열 수 없으면 None."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:          # 비전 의존성이 없는 환경(테스트 러너 등)
        return None
    try:
        with Image.open(path) as im:
            arr = np.asarray(im.convert("RGB").resize((192, 192), Image.BILINEAR),
                             dtype=np.int16)
    except Exception:            # noqa: BLE001 — 깨진 파일이 수집을 멈추면 안 된다
        return None
    flat = arr.reshape(-1, 3)
    mx, mn = flat.max(1), flat.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    q = flat // 12
    counts = np.bincount(q[:, 0] * 484 + q[:, 1] * 22 + q[:, 2])
    grey = arr.mean(2)
    return {
        "pale": float(((mx > 195) & (sat < 0.25)).mean()),
        "top": float(np.sort(counts)[-24:].sum() / len(flat)),
        "edge": float((np.abs(np.diff(grey, 1, 1)).mean()
                       + np.abs(np.diff(grey, 1, 0)).mean()) / 2),
    }


def is_map_features(ft: Optional[dict]) -> bool:
    if not ft:
        return False
    return (ft["pale"] >= PALE_MIN and ft["top"] >= TOP_MIN
            and ft["edge"] <= EDGE_MAX)


def is_map_photo(path: str) -> bool:
    return is_map_features(map_features(path))


def detect_map_photos(folder: str) -> list:
    """물건 폴더의 photos/ 에서 지도로 판정된 파일명을 순서대로 돌려준다."""
    pdir = os.path.join(folder, "photos")
    if not os.path.isdir(pdir):
        return []
    out = []
    for name in sorted(os.listdir(pdir)):
        if name.lower().endswith(_EXTS) and is_map_photo(os.path.join(pdir, name)):
            out.append(name)
    return out
