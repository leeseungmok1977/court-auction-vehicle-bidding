---
name: get-design-system
description: >
  "GET" 브랜드 앱 시리즈(경매로 내차GET 등)의 공통 디자인 시스템. 새 GET 앱의 UI를
  만들거나(대시보드·목록·상세·달력 등), 기존 화면을 브랜드에 맞게 개편하거나, 색상·타이포·
  컴포넌트·아이콘·반응형 레이아웃을 결정할 때 이 스킬을 참조해 시각적 정체성을 동일하게 유지한다.
---

# GET 시리즈 디자인 시스템

> **1호 앱**: 경매로 내차GET (법원·공공 경매 분석). 이 스킬은 그 앱에서 확립한 디자인을
> 새 "GET" 앱에 **그대로 재현**하기 위한 규격서다. 화면이 달라도 **브랜드 톤은 한 앱처럼** 보여야 한다.

## 0. 대원칙 (먼저 읽기)

1. **데이터 신뢰가 디자인보다 우선.** 화면에 예쁜 숫자를 위해 **없는 데이터를 만들지 않는다.** 근거 없는
   확신 UI(가짜 정확도·가짜 코멘트·가짜 등급)를 넣지 않는다. 불확실은 범위/신뢰도/표본수로 **정직하게** 표현.
2. **오프라인 안전.** CDN 금지. 폰트·아이콘·로고는 **로컬 번들**(정적 Tailwind 빌드, self-host). PWA/터널/폐쇄망에서 동일하게 렌더.
3. **모바일 우선, 설치형 지향.** 실제 폰에서는 앱이 **화면을 꽉 채운다**. 데스크톱 브라우저에서만 폰 목업으로 감싼다.
4. **절제된 고급함.** 순검정(#000)·형광색 금지. 딥네이비 잉크 + hairline 보더 + 넉넉한 라운드 + 얇은 그림자.
   강조 1순위는 **오렌지(GET)**, 액션은 **인디고**. 색을 남발하지 않는다.

---

## 1. 브랜드 아이덴티티

### 네이밍 규칙
- **앱명 패턴**: `[도메인 한국어] + GET` — 예: **경매로 내차GET**. 다음 앱도 `…GET`으로 끝난다.
- **영문 태그라인**: `AI [Domain]` (uppercase, tracking 넓게) — 예: `AI COURT AUCTION`. 헤더 브랜드 아래 보조로.
- **한 줄 설명**: "법원·공공 경매 분석"처럼 도메인 한 줄.

### 워드마크(로고 타이포)
- 앞부분은 **딥네이비 잉크**(`text-txt`), **`GET`만 오렌지**(`text-amber-500`).
- ```html
  <span class="font-extrabold tracking-tight">경매로 내차<span class="text-amber-500">GET</span></span>
  ```
- `GET`는 항상 대문자·오렌지. 색을 인디고 등으로 바꾸지 않는다(아이콘 강조색과 일치).

### 앱 아이콘
- **딥네이비 라운드 스퀘어** 바탕 + **오렌지 포인트**. 풀블리드(모서리까지 네이비가 차서 설치 시 흰 귀퉁이 없음).
- 세트: `favicon.ico`, 64/180/192/512 PNG, **maskable**(안전영역 고려). `manifest`의 `name`/`short_name`은 앱명만.

---

## 2. 색상 토큰 (정확한 값)

정적 Tailwind `theme.extend.colors`에 아래를 넣는다. **라이트 캔버스 + 딥네이비 잉크 + 인디고 액션**이 기본.

```js
colors: {
  background: "#f6f9fc",     // 페이지 캔버스(cool off-white)
  surface:    "#ffffff",     // 카드/패널
  low:        "#ffffff",     // 사이드바
  line:       "#e3e8ee",     // hairline 보더
  "line-input":"#cdd7e3",    // 입력 보더
  primary:    "#533afd",     // 인디고 — CTA·링크·포커스 전용(본문/숫자엔 금지)
  "primary-deep":"#4434d4",
  "primary-soft":"#665efd",
  "primary-subtle":"#eef0ff",
  txt:   "#0d253d",          // 잉크(딥네이비, 순검정 금지)
  "txt-2":"#273951",
  mut:   "#64748d",          // 보조 텍스트
  "brand-dark":"#1c1e54",    // 딥네이비 강조 표면
}
```

### 딥네이비 히어로 그라데이션 (시그니처)
브랜드의 얼굴. 예상값·핵심 지표를 담는 큰 카드에 사용.
```html
style="background:linear-gradient(150deg,#16305e 0%,#0f2247 55%,#0b1730 100%)"
```
- 위 카드 안 텍스트는 **흰색**, 라벨은 `text-white/60`, 강조 숫자·게이지·범위바는 **오렌지(amber)**.

### 오렌지(강조) 스케일
- 아이콘/GET: `#f3b63e` 계열. Tailwind: `amber-500`(#f59e0b) 텍스트, `amber-400`(#fbbf24) 게이지/포인트, `amber-300` 밝은 강조.
- 네이비 위에서는 amber-400/300, 흰 바탕에서는 amber-500.

### 시맨틱 색 (상태/판정)
| 의미 | 색 |
|---|---|
| 긍정·안정·양호 | emerald(`emerald-500/600`, bg `emerald-50`) |
| 주의·임박 | amber |
| 위험·경고 | rose(`rose-500/600`, bg `rose-50`) |
| 정보·중립 액션 | indigo(primary) |
| 비활성·과거 | slate/`mut`, bg `slate-100` |

> 순검정·형광·무지개 팔레트 금지. 한 화면에서 강조색은 **오렌지 1 + 시맨틱 최소**로.

---

## 3. 타이포그래피

- **폰트: Pretendard**(self-host, 300~700). fallback `Malgun Gothic, sans-serif`. 코드/수치표는 `JetBrains Mono` 옵션.
- **숫자에는 `tabular-nums`** — 가격·D-day·% 세로 정렬. 큰 지표는 `font-extrabold tracking-tight`.
- 위계(대략):
  - 히어로 핵심 숫자: `text-3xl~4xl font-extrabold`
  - 섹션 헤더: `text-base~lg font-bold text-txt`
  - 카드 제목: `text-sm font-bold`
  - 라벨/보조: `text-xs text-mut`, 태그라인 `uppercase tracking-[0.12em]`
- **줄바꿈 규칙(중요)**: 섹션 헤더는 제목+부제 한 줄. 제목에 `whitespace-nowrap`, 부제는 `hidden sm:inline`으로
  좁은 화면에서 **단어 중간에 줄이 끊기지 않게** 한다. ("유망 물건 — 신뢰도 → …"가 조각나 보이던 버그 방지)

---

## 4. 아이코노그래피

- **UI 아이콘**: Material Symbols(로컬 폰트/서브셋). 원형 배경 뱃지에 담아 KPI·칩에 사용.
- **브랜드 로고(제조사 등)**: [simple-icons](https://simpleicons.org)(MIT) SVG를 **로컬 번들**(`static/brands/*.svg`).
  없는 브랜드는 **이니셜 배지**(브랜드색 배경 + 약자)로 폴백. 미보유 로고를 임의 제작·유추하지 않는다(단, 공개 CI를 손수 벡터화하는 건 허용 — 예: 벤츠 삼각별).
- 아이콘 원형 배지 레시피: `w-9 h-9 rounded-full bg-primary-subtle text-primary grid place-items-center`.

---

## 5. 레이아웃 & 반응형

### 정보 구조(IA)
- **모바일**: 하단 탭바 = 주 내비(예: 홈/목록/달력/관심). **햄버거 없음.** 상단 헤더 = **앱 브랜드**(워드마크+태그라인).
  → 첫 화면 헤더에 "대시보드" 같은 페이지명 대신 **브랜드**를 노출.
- **데스크톱**: 좌측 **사이드바**(브랜드+메뉴) + 콘텐츠 상단에 **페이지 타이틀**(`hidden lg:block`).
- 하단 탭바는 `position:fixed`가 아니라 **flex 자식(shrink-0)**으로 둔다 → 모바일 브라우저에서 **잘림 없음**.
  스크롤 컨테이너는 `overflow-y-auto` + 적당한 하단 패딩.

### 폰 목업(데스크톱 전용)
데스크톱 방문자에게만 모바일 미리보기 프레임을 씌운다. **실제 폰에서는 절대 프레임을 씌우지 않는다.**
```js
// 파싱 시점 innerWidth는 viewport meta 이전이라 부정확 → matchMedia + screen.width로 판정
var isDesktop = matchMedia("(min-width: 900px) and (pointer: fine) and (hover: hover)").matches;
var bigScreen = !window.screen || (window.screen.width || 0) >= 900;
if (!standalone && !framed && isDesktop && bigScreen) location.replace(FRAME_URL);
```
- 프레임: 네이비 배경 위 흰 라운드 카드(`border-radius:32px`, 베젤/노치 장식 없이 깔끔), 떠있는 힌트 칩.

### 도형·엘리베이션
- 카드 라운드 `rounded-2xl`(히어로/주요), 칩/버튼 `rounded-full` 또는 `rounded-xl`.
- 그림자: `card`(`0 1px 3px rgba(0,55,112,.08)`) 기본, `lift`(`0 8px 24px …`) 강조. **무거운 그림자 금지.**
- 보더는 항상 **hairline**(`border border-line`).

---

## 6. 시그니처 컴포넌트 레시피

### 6.1 딥네이비 히어로 카드 (핵심 지표)
```html
<div class="rounded-2xl p-5 text-white shadow-lift"
     style="background:linear-gradient(150deg,#16305e 0%,#0f2247 55%,#0b1730 100%)">
  <span class="text-[11px] uppercase tracking-[0.12em] text-amber-400 font-semibold">AI 예측</span>
  <div class="mt-1 text-3xl font-extrabold tabular-nums">1,010<span class="text-lg font-bold">만원</span></div>
  <div class="text-xs text-white/60">시세 대비 −18% · 신뢰도 82%</div>
  <!-- 오렌지 IQR 범위바 -->
  <div class="mt-3 h-1.5 rounded-full bg-white/15">
    <div class="h-full rounded-full bg-amber-400" style="width:64%"></div>
  </div>
</div>
```

### 6.2 KPI 카드
```html
<div class="rounded-2xl border border-line bg-surface p-4 shadow-card">
  <div class="flex items-center justify-between">
    <span class="w-9 h-9 rounded-full bg-primary-subtle text-primary grid place-items-center">
      <span class="material-symbols-rounded">gavel</span></span>
    <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600">입찰 준비</span>
  </div>
  <div class="mt-3 text-2xl font-extrabold text-txt tabular-nums">128</div>
  <div class="text-xs text-mut">검토 가능 · 기일순</div>
</div>
```
구성: **아이콘 원형 + 상태 pill(우상단) + 큰 숫자 + 서브메트릭**.

### 6.3 프리미엄 사진 목록 카드(모바일)
- 상단 풀폭 사진(`h-40`) + 좌상단 **D-day**/우상단 **유찰회수** 배지 + 하단 **그라데이션 오버레이**(연식·주행·상태).
- 본문: `최저입찰가` + `감정가 대비 %`, `AI 예상낙찰가`(강조), **신뢰도 progress bar**.
```html
<article class="rounded-2xl overflow-hidden border border-line bg-surface shadow-card">
  <div class="relative h-40">
    <img class="w-full h-full object-cover" src="…">
    <span class="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-rose-500 text-white text-xs font-bold">D-3</span>
    <span class="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-black/55 text-white text-xs">유찰 2회</span>
    <div class="absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/70 to-transparent text-white text-xs">
      2021 · 3.4만km · 무사고</div>
  </div>
  <div class="p-3">
    <div class="flex justify-between text-sm"><span class="text-mut">최저입찰가</span>
      <span class="font-bold tabular-nums">840만원 <span class="text-mut text-xs">감정 62%</span></span></div>
    <div class="flex justify-between text-sm"><span class="text-mut">AI 예상낙찰가</span>
      <span class="font-extrabold text-primary tabular-nums">1,010만원</span></div>
    <div class="mt-2 h-1.5 rounded-full bg-line"><div class="h-full rounded-full bg-emerald-500" style="width:82%"></div></div>
  </div>
</article>
```

### 6.4 상태 pill / 테마 칩
- pill: `text-[11px] font-semibold px-2 py-0.5 rounded-full` + 시맨틱 bg/text.
- 탐색 칩: `rounded-full border border-line px-3 py-1.5 text-sm`(선택 시 `bg-primary text-white border-primary`).

### 6.5 섹션 헤더
```html
<div class="flex items-baseline gap-2">
  <h3 class="text-base font-bold text-txt whitespace-nowrap">유망 물건</h3>
  <span class="text-xs text-mut hidden sm:inline">신뢰도 → 예상 여유 큰 순</span>
</div>
```

### 6.6 브랜드 헤더(모바일) / 사이드바(데스크톱)
```html
<!-- 모바일: 브랜드가 곧 헤더 -->
<a href="/" class="flex lg:hidden items-center gap-2">
  <img src="/static/icons/icon-192.png" class="w-9 h-9 rounded-xl">
  <span class="leading-tight">
    <span class="block font-extrabold text-txt">경매로 내차<span class="text-amber-500">GET</span></span>
    <span class="block text-[10px] uppercase tracking-[0.12em] text-mut">AI Court Auction</span>
  </span>
</a>
<!-- 데스크톱: 페이지 타이틀 별도 -->
<h2 class="hidden lg:block text-lg font-bold text-txt">{% block pagetitle %}{% endblock %}</h2>
```

---

## 7. 데이터 신뢰 표현 규칙 (재확인)

- **예상값은 항상 근거·범위와 함께.** 예: "예상 낙찰가(최저가 기반 · 실측 오차 ±8%)", 입찰밴드(보수/균형/공격 = 확률 25/50/75).
- 정확도(MAE 등)는 **정직한 백테스트(LOO 등)** 로만 표기. 표본 적으면 "유사 낙찰 N건 참고"처럼 **표본 수 노출**.
- 미확정은 임의 채우지 말고 "다음 기일 미정" 등 **사실대로**. 과거 지난 기일을 현재처럼 보이게 하지 않는다.
- 벤치마킹 앱(경쟁사)·디자인 시안의 **가짜 데이터 UI(가짜 권리분석·감정평가 코멘트·차량이력·타이어 트레드% 등)는 이식하지 않는다.**

---

## 8. Do / Don't

**Do**
- 딥네이비 잉크 + 인디고 액션 + 오렌지 GET 강조, hairline 보더, `rounded-2xl`, `tabular-nums`.
- 정적 Tailwind 빌드(`npm run build:css`) — arbitrary 클래스(`w-10`, `text-[9px]`, `bg-white/[0.08]`, `tracking-[0.12em]`)는 **빌드 후에만** 적용됨. 서버 재시작으로 `css_v` 캐시버스트.
- 폰트·아이콘·로고 로컬 번들. 오프라인에서 동일 렌더 확인.

**Don't**
- 순검정(#000)·형광색·무지개 팔레트, 무거운 그림자, CDN 링크.
- 실제 폰에 폰 프레임 씌우기, 하단 탭바 `fixed`(잘림), 햄버거+하단탭 중복.
- 근거 없는 확신 UI·가짜 데이터. `GET`를 오렌지 외 색으로.

---

## 9. 새 GET 앱 부트스트랩 체크리스트

1. `tailwind.config.js` 색상 토큰(§2) 복사 + Pretendard/Material Symbols/simple-icons 로컬 번들.
2. `base.html`: 모바일 브랜드 헤더 + 하단 탭바(flex 자식) + 데스크톱 사이드바 + 페이지타이틀 블록 + 폰 프레임 리다이렉트(§5).
3. 앱명 `[도메인]GET`, 태그라인 `AI [Domain]`, 아이콘 세트(네이비/오렌지·maskable·풀블리드)·manifest.
4. 핵심 지표 화면은 딥네이비 히어로(§6.1) + KPI 카드(§6.2)로 구성.
5. 목록은 프리미엄 사진 카드(§6.3), 상태는 시맨틱 pill.
6. 모든 예측/지표는 신뢰 규칙(§7) 준수 — 근거·범위·표본수.
7. `npm run build:css` 후 서버 재시작, 실제 모바일 + 데스크톱 양쪽 렌더 확인.

> 참조 구현: `경매로 내차GET` 리포지토리의 `web/templates/base.html·dashboard.html·vehicles.html·detail.html·calendar.html`,
> `web/static/`(icons·brands·frame.html), `tailwind.config.js`. 새 앱은 이 파일들을 **출발점으로 복제**한다.
