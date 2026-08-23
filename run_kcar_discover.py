"""케이카 2차 소스 — 발견용 도구.

  자동 발견:  python run_kcar_discover.py [검색어]
      자유검색 후 /search/list* 응답의 엔드포인트·필드·매핑을 자동 캡처.
  수동 캡처:  python run_kcar_discover.py --manual [검색어]
      보이는 브라우저로 직접 모델 필터 매물목록까지 이동 → 실제 필터 API(파라미터)를 기록.
      (자유검색이 모델 필터를 안 해서 필터 API를 직접 확인해야 할 때)

출력을 붙여넣어 주면 매핑/필터 API를 실데이터로 확정한다(추측 금지, C.4-3).
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.collect import kcar  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    manual = "--manual" in args
    dom = "--dom" in args
    args = [a for a in args if a not in ("--manual", "--dom")]
    kw = args[0] if args else "쏘렌토"
    try:
        if dom:
            kcar.discover_autocomplete(kw)
        elif manual:
            kcar.discover_manual(kw)
        else:
            print(f"[케이카 발견] 검색어='{kw}' — 실제 API 응답을 가로챕니다(지연 준수)…\n")
            kcar.discover(kw)
            print("\n※ 매칭>0 엔드포인트가 없으면: python run_kcar_discover.py --manual "
                  + kw + " 로 모델 필터 API를 직접 캡처하세요.")
    except Exception as e:  # noqa: BLE001
        print(f"[중단] {type(e).__name__}: {e}")
        print("차단(403/429/CAPTCHA)이면 잠시 후 재시도하세요.")
