/** 정적 빌드용 Tailwind 설정 — Stripe(핀테크·정제) 디자인 시스템(DESIGN.md) 적용.
 *  라이트 테마: 화이트 캔버스 · 인디고 primary · 딥네이비 잉크 · hairline 보더 · thin 타이포.
 *  주의: 판정/사고등급 색상 클래스는 web/app.py의 _bcls/_acc에서 생성되므로
 *  content에 app.py도 포함해 스캐너가 해당 클래스를 수집하도록 한다. */
module.exports = {
  content: [
    "./web/templates/**/*.html",
    "./web/app.py",
  ],
  theme: {
    extend: {
      colors: {
        // 표면(라이트)
        background: "#f6f9fc",     // 페이지 캔버스(cool off-white)
        surface: "#ffffff",        // 카드/패널
        low: "#ffffff",            // 사이드바
        line: "#e3e8ee",           // hairline 보더
        "line-input": "#cdd7e3",   // 입력 보더(약간 진하게)
        // 브랜드 인디고(CTA·링크·포커스에만 — Stripe 규칙: 본문/숫자엔 쓰지 않음)
        primary: "#533afd",
        "primary-deep": "#4434d4",
        "primary-soft": "#665efd",
        "primary-subtle": "#eef0ff",
        // 잉크(딥네이비 — 순검정 금지)
        txt: "#0d253d",
        "txt-2": "#273951",
        mut: "#5e6c85",           // 보조 텍스트 — off-white(#f6f9fc) 위 소형 글씨도 WCAG 4.5:1 통과(구 #64748d=4.49)
        // 강조 표면·그라데이션 스톱
        "brand-dark": "#1c1e54",   // 딥네이비 강조 표면
        cream: "#f5e9d4",
        ruby: "#ea2261",
        magenta: "#f96bee",
      },
      fontFamily: {
        // 이모지는 어느 Pretendard에도 없다 — PretendardFull 앞에 두지 않으면
        // 이모지 하나 때문에 원본 765KB를 받아본다(3회차 실측).
        sans: ["Pretendard", "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji",
               "PretendardFull", "Malgun Gothic", "sans-serif"],
        // JetBrains Mono에는 한글 글리프가 없다. 숫자용 mono를 한글이 섞인 자리에
        // 쓰면 글자마다 OS 폰트로 폴백해 자간이 벌어진다("광 주 지 법").
        // 스택에 Pretendard를 넣어 한글은 본문과 같은 서체로 떨어지게 한다.
        mono: ["JetBrains Mono", "Pretendard", "PretendardFull", "Malgun Gothic", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,55,112,0.08)",
        lift: "0 8px 24px rgba(0,55,112,0.08), 0 2px 6px rgba(0,55,112,0.04)",
      },
    },
  },
};
