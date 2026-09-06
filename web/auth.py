"""사용자 인증·등급 (MONETIZATION_SPEC TASK-M04 뼈대).

지금은 인증 미구현 — 모든 요청을 **익명 tier=1(무료)** 로 취급한다.
- M05(Google Sign-In): 세션 쿠키/Bearer로 uid를 얻어 db.get_user(uid)로 교체.
- M11+: require_tier로 실제 기능·응답을 등급별로 게이팅.
원칙: 등급 판정은 **항상 서버(DB)** 에서만 한다 — 앱이 주장하는 등급은 신뢰하지 않는다.
"""
from __future__ import annotations

from web import db

ANON = {"id": None, "email": None, "tier": 1, "anonymous": True}


def current_user(request) -> dict:
    """요청의 사용자(dict) 반환. 현재는 세션 미연결이라 익명(tier=1).
    M05에서 세션 검증 → uid → db.get_user(uid)로 대체."""
    # TODO(M05): uid = verify_session(request); u = db.get_user(uid); return u or dict(ANON)
    _ = db  # M05에서 사용
    return dict(ANON)


def user_tier(request) -> int:
    return int((current_user(request) or ANON).get("tier") or 1)


def require_tier(request, need: int) -> bool:
    """등급 충족 여부(서버 권위). M11+에서 라우트/기능 게이팅에 사용. 지금은 정의만."""
    return user_tier(request) >= int(need)
