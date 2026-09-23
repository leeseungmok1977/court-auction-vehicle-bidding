# -*- coding: utf-8 -*-
"""소프트캡 배율이 **코드가 아니라 `config.yaml`** 에서 온다 (PANEL-03).

3회차부터 7회차까지 주간 패널이 `SOFT_CAP_RATIO = 1.10` 하드코딩을 반복 지적했고
티켓은 0건이었다. 값 자체는 그대로 두고 **자리만** 옮긴다 — 이 배율은 실측이 아니라
가정이라 ① 근거를 적을 자리가 필요하고 ② 바꾸는 데 배포가 필요해서는 안 된다.
`config.yaml` 머리말이 정한 원칙이 그것이다: "흐름/코드 수정 없이 이 파일만 조정한다".

★ 마지막 두 테스트가 진짜 장치다. **같은 종류의 사고가 이미 한 번 났다** —
  `config.yaml:57` 의 기록: "2026-09-16: 승인값이 코드에만 반영되고 여기엔 300이
  남아 매일 300회에서 멈췄다(대기 213→282 증가)". 같은 숫자를 두 자리에 두면 갈리고,
  갈린 것을 **아무도 모른 채로 며칠이 간다.** 그래서 배선을 사람이 아니라 테스트가 센다.
"""
from pathlib import Path

import pytest
import yaml

from web import service

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(monkeypatch):
    """load_config 를 갈아끼운다 — 실제 config.yaml 을 건드리지 않기 위해서다."""
    def _set(data):
        monkeypatch.setattr(service, "load_config", lambda *a, **k: data)
    return _set


def test_config_값이_실제로_산정에_쓰인다(cfg):
    """손으로 검산한 값: 20,000,000 × 1.50 = 30,000,000."""
    cfg({"soft_cap_ratio": 1.50})
    assert service.soft_cap(20_000_000) == 30_000_000


def test_키가_없으면_코드_기본값으로_떨어진다(cfg):
    """손으로 검산한 값: 20,000,000 × 1.10 = 22,000,000."""
    cfg({})
    assert service.soft_cap(20_000_000) == 22_000_000


@pytest.mark.parametrize("bad", ["abc", None, "", {}, []])
def test_설정이_깨져도_산정이_멈추지_않는다(cfg, bad):
    """설정 파일 하나가 망가졌다고 **예상낙찰가 전체가 죽으면** 안 된다.

    캡이 없으면 캡을 안 씌우는 게 아니라 기본값으로 씌운다 — 캡은 비현실 추정을
    막는 방어선이라, 조용히 사라지는 쪽이 조용히 기본값을 쓰는 쪽보다 위험하다."""
    cfg({"soft_cap_ratio": bad})
    assert service.soft_cap(20_000_000) == 22_000_000


@pytest.mark.parametrize("med", [None, 0])
def test_시세가_없으면_캡도_없다(cfg, med):
    cfg({"soft_cap_ratio": 1.10})
    assert service.soft_cap(med) is None


# ── 드리프트 감시 ──────────────────────────────────────────────────────────
def _raw_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def test_config_yaml_에_키가_살아_있다():
    """키가 지워지면 외부화가 **조용히 무효**가 된다 — 코드 기본값으로 돌아가고
    아무도 눈치채지 못한다. 그때 이 테스트가 운다."""
    raw = _raw_config()
    assert "soft_cap_ratio" in raw, (
        "config.yaml 에서 soft_cap_ratio 가 사라졌다 — PANEL-03 외부화가 무효가 된다")
    r = float(raw["soft_cap_ratio"])
    assert 1.0 <= r <= 1.5, (
        f"soft_cap_ratio={r} 는 상식 범위를 벗어난다. 1.0 미만이면 캡이 시세보다 낮아져 "
        f"예상낙찰가가 전부 눌리고, 1.5 초과면 방어선 구실을 못 한다. 오타(11.0·0.11)를 의심하라")


def test_실제_config_가_산정까지_연결돼_있다(monkeypatch):
    """★ 배선을 끝에서 끝까지 센다. 위 테스트들은 load_config 를 갈아끼우므로
    **진짜 파일이 진짜로 읽히는지**는 증명하지 못한다. 여기서만 증명된다.

    ⚠ 그냥 비교하면 이 테스트는 **아무것도 증명하지 못한다** — config 값(1.10)과
      코드 기본값(1.10)이 같아서, 배선이 끊겨 상수를 쓰더라도 똑같이 통과한다.
      (이 함정을 처음 쓸 때 실제로 밟았다.) 그래서 **코드 기본값만 엉뚱한 값으로
      바꿔치고** 잰다. 그래도 config 값이 나오면 파일이 실제로 읽힌 것이다."""
    r = float(_raw_config()["soft_cap_ratio"])
    monkeypatch.setattr(service, "SOFT_CAP_RATIO", 9.99)   # 배선이 끊겼다면 이게 나온다
    expected = int(round(20_000_000 * r / 100_000) * 100_000)
    assert service.soft_cap(20_000_000) == expected, (
        "config.yaml 의 soft_cap_ratio 가 산정에 도달하지 않는다 — "
        "코드 기본값이 대신 쓰였다. 값을 고쳐도 화면이 안 바뀐다는 뜻이다")
