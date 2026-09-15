"""당시 출시가 수집 — 상한·순서·중단 사유 (2026-09-16 사용자 지시).

실측(운영 DB): 코드 기본 상한은 승인값 2,400으로 올라가 있었지만 config.yaml 에 `newcar_daily_cap: 300`
이 남아 매일 갱신이 설정값을 우선했다. 9/13·9/15 모두 캐시에 쌓인 행이 정확히 300 — 하루 3~19대만
처리되는 사이 새 물건이 들어와 대기가 213 → 282대로 오히려 늘었다. 게다가 수집기는 중단 사유를 계산하고도
실행 기록에 남기지 않아 '진행 중인 백필'처럼 보였다.

조치:
  1. 설정 상한을 승인값 2,400으로(코드값과 같게 — 다시 어긋나지 않게 테스트로 고정).
  2. 수집을 매일 갱신의 **맨 뒤**로. 요청 사이 5초라 2,400회면 최대 3시간 20분인데, 앞에 두면
     사진 정렬·낙찰결과·오늘의 추천이 그만큼 늦어진다.
  3. 긴 수집을 시작하기 **전에** 앞 단계 요약을 먼저 기록 — 서버가 재시작되면 마지막 메시지 뒤에
     '(서버 재시작으로 중단됨)'만 붙으므로, 진행 메시지만 남아 있으면 앞 단계 건수가 사라진다.
  4. 끝나면 중단 사유(예산 소진·차단·오류)를 실행 기록에 남긴다.
"""
from pathlib import Path

from web import service

ROOT = Path(__file__).resolve().parents[1]


def _daily_body() -> str:
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    i = src.index("def daily_update(")
    return src[i:src.index("def photo_autosort_run", i)]


def test_config_cap_matches_the_approved_code_cap():
    """승인값이 코드에만 반영되고 설정엔 300이 남아 매일 300회에서 멈췄다 — 둘이 다시 갈리면 실패."""
    assert service.load_config().get("newcar_daily_cap") == service.NEWCAR_DAILY_CAP == 2400


def test_release_price_collection_runs_last():
    body = _daily_body()
    nc = body.index("newcar_collect(")
    for earlier in ("photo_autosort_run(", "update_results(", "review_daily_anomalies(", "refresh_daily_picks("):
        assert body.index(earlier) < nc, f"{earlier} 가 출시가 수집보다 뒤에 있다 — 긴 수집이 이 단계를 늦춘다"


def test_summary_is_recorded_before_the_long_collection_starts():
    """재시작돼도 앞 단계 건수가 남도록, 긴 수집 전에 요약을 먼저 기록한다."""
    body = _daily_body()
    interim = body.index('message=f"{_base} · 출시가 수집 중"')
    assert interim < body.index("newcar_collect("), "요약 기록이 수집보다 뒤에 있다"


def test_final_record_carries_the_stop_reason():
    body = _daily_body()
    assert "newcar_stop_label(newcar)" in body
    assert "'·' + _why" in body, "중단 사유가 실행 기록 문장에 붙지 않는다"


def test_stop_reason_labels_are_short_and_parseable():
    """사유는 매일 12시 리포트가 한 조각으로 읽는다 — 구분자(' · ', '·', ')')가 섞이면 안 된다."""
    assert service.newcar_stop_label({"stopped": "요청 예산 2400 소진"}) == "예산 2400 소진"
    assert service.newcar_stop_label({"stopped": "차단: 보배드림 차단 상태코드 403 — 중단"}) == "⚠차단 HTTP 403"
    assert service.newcar_stop_label({"stopped": "차단: 알 수 없음"}) == "⚠차단"
    assert service.newcar_stop_label({"stopped": None}) == ""
    assert service.newcar_stop_label({}) == ""
    odd = service.newcar_stop_label({"stopped": "오류: timeout (read) · x"})
    assert odd.startswith("⚠오류") and ")" not in odd and "(" not in odd and "·" not in odd
