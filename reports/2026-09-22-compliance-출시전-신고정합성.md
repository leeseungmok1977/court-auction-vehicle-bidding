# 출시 전 신고 정합성 검토 — 2026-09-22 배포분 vs Play 제출 답안

> 지시 번호 2026-09-22-02 · 담당 compliance-officer · 대상 9/27 정식 출시 신청
> 범위: `docs/STORE_SUBMISSION_ANSWERS.md`(2026-09-11 제출 확정본) vs 2026-09-22 배포분
> **이 문서는 리스크 식별과 실행 로드맵이며 법적 판단이 아니다. 최종 판단은 사람(변호사)에게 위임한다.**
> 나는 Play Console 화면에 접근할 수 없다 — 콘솔에 실제로 저장된 답안이 아니라 **저장소 문서에 기록된 답안**과 대조했다.

---

## 0. 판정 요약

| # | 항목 | 판정 | 심각도 | 마감 |
|---|---|---|---|---|
| 1 | 콘텐츠 등급 §3 "사용자 간 상호작용 = 아니오" vs 공유 버튼 | **문제 없음** | 낮음 | — |
| 2 | 데이터 안전 "수집·공유 없음" vs og·공유·색인 | **문제 없음** | 낮음 | — |
| 2★ | 데이터 안전 "수집 없음" vs **방문자 집계** | **신고 갱신 필요** (또는 기능 되돌리기 택일) | **높음** | 9/25 |
| 3 | 개인정보처리방침 문구 | **갱신 필요** | 중간 | 9/24 |
| 4 | 콘텐츠 등급 설문 재제출 | **문제 없음**(재제출 불요) | 낮음 | — |
| 5-1 | 스토어 긴 설명의 적중률 수치 vs 라이브 값 | **확인 필요** | 중간 | 9/24 |
| 5-2 | 데이터 안전 부속 항목(암호화·삭제요청) | 2★ 결정에 종속 | 중간 | 9/25 |
| 5-3 | og:image 썸네일의 번호판 노출 | **확인 필요** | 중간 | 9/26 |
| 5-4 | 홈 화면 앱 이름(v1 빌드 = `내차GET`) | **확인 필요**(신고 항목 아님) | 낮음 | 9/26 |

**출시 차단 요인은 2★ 하나다.** 나머지는 병렬로 처리 가능하다.

---

## 1. 인용한 근거 (어디서 본 것인지)

기억으로 쓴 문장은 이 보고서에 없다. 아래는 2026-09-22에 직접 열어 확인한 것이다.

| 부호 | 출처 | 확인한 문언(원문) |
|---|---|---|
| **G1** | Play Console Help, *Online Interaction or Content Exchange* (`support.google.com/googleplay/android-developer/answer/7021383`) | "Users can freely exchange content they have created. This includes the ability to communicate between users, comment on provided content, share photos, or exchange any other type of content created by users." / **"developers should only consider their app's native services and not consider sharing that is accomplished by using secondary apps (such as Facebook or Twitter)."** |
| **G2** | Play Console Help, *Provide information for Google Play's Data safety section* (`answer/10787469`) | **"'Collect' means transmitting data from your app off a user's device."** — "This includes data transmitted by libraries, SDKs, and webviews where your app controls the behavior." |
| **G3** | 같은 문서, 면제 조항 | 면제는 세 가지뿐 — (a) 기기 내 처리만 하고 기기를 떠나지 않는 데이터, (b) 종단간 암호화, (c) **일시적 처리**: "accessing and using it while the data is only stored in memory and retained for no longer than necessary to service the specific request in real-time" |
| **G4** | 같은 문서, 데이터 유형 표 | **App interactions**: "Information about how a user interacts with the app. For example, **the number of times they visit a page**, screenshots taken, or sections they tap on" / **Device or other IDs**: "IMEI number, MAC address, Widevine Device ID, Firebase installation ID, or advertising identifier" / **Approximate location**: "Approximate location that is inferred, such as via IP address or Access Point Name, must be disclosed here." |
| **G5** | 같은 문서, 공유 면제 | "User-initiated action or prominent disclosure and user consent. Transferring user data to a third party based on a specific user-initiated action, where the user reasonably expects the data to be shared" |
| **G6** | Play Console Help, *User Data* 정책 (`answer/10144311`) | "comprehensively disclose how your app accesses, collects, uses, and shares user data" / "The developer is responsible for the accuracy of the label and keeping this information up-to-date" / "the section must be consistent with the disclosures made in the app's privacy policy" |
| **G7** | Play Console Help, 콘텐츠 등급 설문 (`answer/188189`, `answer/9898843`) | "All app updates where there has been a change to your content or features that would affect the responses to the questionnaire." / **"Misrepresentation of your app's content may result in its removal or suspension."** |

코드 근거(저장소 실측):

| 부호 | 위치 | 사실 |
|---|---|---|
| **C1** | `web/templates/detail.html:87-96` | `_share()`는 `location.href`와 `data-share-title` 문자열만 쓴다. **서버 요청 0건**, 네트워크 호출 없음 |
| **C2** | `web/templates/detail.html:14-17`, `web/templates/report.html:13-22` | og 값은 차명·연식·법원·사건번호·최저매각가·유찰횟수·매각기일·주행거리 + 첫 사진 썸네일. 예상낙찰가·시세·적중률 **없음** |
| **C3** | `web/app.py:176-221` | robots는 `/static/frame.html`·`/run/`·`/api/`·`/admin` Disallow. sitemap은 기일 미도래 + 낙찰·종결 아님만 |
| **C4** | `tools/daily_ops_report.py:378-415` | 원격 읽기 전용 스크립트가 `/var/log/nginx/access.log*`를 읽어 `_days[date][ip] += 1`로 **IP별 페이지뷰를 집계**하고, 출력은 `visitors`/`bounce_pct`/`deep_pct` 숫자뿐 |
| **C5** | `docs/daily-reports/2026-09-22.md:38-45` | 집계 결과가 저장소 문서에 기록됨(9/21 방문자 59, 9/22 31) |
| **C6** | `web/templates/privacy.html:43` | "웹서버 인프라 로그로만 사용합니다 — **분석**·프로필 연결·외부 제공이 없고 14일 후 자동 삭제되므로 … 스토어에 '수집 없음'으로 신고했습니다" |
| **C7** | `web/templates/detail.html:188-190`, `web/templates/report.html:1032` | 목록상 주소(채무자 주소)는 `is_admin`일 때만 렌더 → 검색 색인·og로 새지 않음 |
| **C8** | 저장소 전체 grep | `gtag`·GTM·plausible 등 **제3자 분석 스크립트 0건**(2026-09-11 실측이 오늘도 유효) |

---

## 2. 판정 1 — 공유 버튼 vs "사용자 간 상호작용 = 아니오"

**판정: 문제 없음. 답안을 바꿀 필요가 없다.** 심각도 낮음.

**근거.** G1은 이 문항이 묻는 것을 *"이용자가 만든 콘텐츠를 자유롭게 주고받는 것"*으로 정의하고, 예시를 이용자 간 통신·댓글·사진 공유로 든다. 그리고 판단 범위를 **명시적으로 잘라 준다** — "developers should only consider their app's **native services** and **not consider sharing that is accomplished by using secondary apps**". 우리 공유 버튼은 정확히 후자다: OS 공유 시트가 링크를 **다른 앱**(카톡·메시지)으로 넘기고, 앱 안에는 그 링크를 받아 남에게 보여주는 면이 없다. 더해서 공유되는 대상은 *이용자가 만든 콘텐츠*가 아니라 **우리가 게시한 법원 공시 사실의 URL**이다. G1의 두 요건(native + user-created) 모두 불성립이다.

즉 의뢰인의 직관("앱 안에서 사용자끼리 콘텐츠를 주고받는 기능을 묻는 것")은 정책 문언으로 뒷받침된다. 이건 내 해석이 아니라 인용된 문장 그대로다.

**확인 필요.** 나는 콘솔의 실제 한국어 문항을 볼 수 없다. IARC 설문 문항은 "앱에서 사용자가 서로 소통하거나 콘텐츠를 교환할 수 있나요?" 계열로 뜨는데, **제출 화면에서 해당 문항의 도움말(물음표)을 한 번 펼쳐 G1과 같은 '보조 앱 제외' 문구가 있는지 눈으로 확인**하라. 있으면 그대로 두면 된다. 문구가 다르면(예: '보조 앱 제외' 언급 없이 "콘텐츠를 공유할 수 있나요"로만 물으면) 과다 신고 원칙에 따라 '예'로 바꾸는 쪽이 안전하다 — 단 '예'로 바꾸면 등급이 올라갈 수 있으므로(대개 '상호작용 가능' 표시가 붙고 등급 자체는 유지되는 경우가 많으나 **나는 이 결과를 실측하지 않았다**) 바꾸기 전에 설문을 저장만 하고 예상 등급을 확인하라.

**완화.** 앱 내 댓글·게시판·메모 공유 기능은 넣지 말 것. 넣는 순간 이 판정은 즉시 뒤집힌다.

---

## 3. 판정 2 — 데이터 안전 "수집·공유 없음"

### 3.1 og 메타 · 공유 버튼 · 검색 색인 → 문제 없음 (심각도 낮음)

- **og·sitemap·robots**: 전부 **서버가 밖으로 내보내는 정보**이지 이용자에게서 받는 정보가 아니다. G2의 "collect = transmitting data **from your app off a user's device**"에 해당하는 사건이 없다. 신고 영향 없음.
- **공유 버튼**: C1대로 서버로 아무것도 보내지 않는다. 설령 '전송'으로 본다 해도 G5의 사용자 개시 행위 면제에 정면으로 들어맞는다(이용자가 버튼을 눌러 자기가 고른 앱으로 보낸다). **수집·공유 어느 쪽도 아니다.**
- **제3자 스크립트**: C8대로 여전히 0건. §0 실측표의 해당 행은 오늘도 참이다.

### 3.2 ★ 방문자 집계 → 신고 갱신 필요 (심각도 높음)

**여기가 오늘 유일하게 깨진 전제다.**

2026-09-11 답안이 '수집 없음'으로 성립한 논리는 `STORE_SUBMISSION_ANSWERS.md:69`에 적혀 있다 — 요지는 ① IP가 언급되는 곳은 위치 카테고리뿐인데 우리는 위치를 추론하지 않는다, ② IP는 '기기 또는 기타 ID' 예시에 없다, ③ 그래서 **매칭되는 데이터 유형이 없다**, ④ 접근로그는 "분석 도구에 투입·프로필 연결·외부 제공이 전혀 없는 웹서버 인프라 로그"다.

①②는 오늘도 유효하다(G4 원문 확인 — Approximate location은 "inferred … via IP address"를 요구하고 우리는 추론하지 않는다, Device IDs 예시에 IP 없음). **깨진 것은 ③과 ④다.**

- C4가 하는 일은 IP를 키로 **페이지뷰를 묶어 세는 것**이다. 산출물은 일별 방문자 수, 1페이지만 보고 나간 비율, 3페이지 이상 본 비율이다.
- G4의 **App activity → App interactions** 정의는 "Information about how a user interacts with the app. For example, **the number of times they visit a page**"다. 우리가 내는 지표가 이 예시와 사실상 같은 문장이다. "매칭되는 데이터 유형이 없다"는 ③의 전제가 여기서 성립하지 않는다.
- ④ "분석에 투입하지 않는다"는 서술은 C4·C5로 **사실과 달라졌다**. 우리는 그 로그로 분석을 하고 결과를 리포지토리 문서에 남기고 있다.
- 면제 검토(G3): (a) 기기 내 처리 아님(서버 로그다), (b) 종단간 암호화 아님, (c) 일시적 처리 아님 — nginx 로그는 **14일 보존**이고 G3은 "in memory … retained for no longer than necessary to service the specific request in real-time"을 요구한다. **세 면제 모두 불성립이다.**
- TWA라서 빠져나갈 구멍도 없다. G2는 "webviews where your app controls the behavior"까지 수집 범위로 명시하고, `docs/APP_LAUNCH_CHECKLIST.md:181`도 이미 같은 경고를 적어 두었다("TWA라도 웹에서 수집하는 데이터까지 신고 책임이 개발자에게 있음").

**반대 논거도 적어 둔다(약하다고 보지만 숨기지 않는다).** 집계는 앱이 보내는 것이 아니라 **웹서버가 자기 인프라 로그를 사후에 읽는 것**이고, IP는 우리 스크립트 메모리에서만 키로 쓰이며 저장물은 숫자뿐이다(C4). 모든 HTTP 서비스가 이 기준이면 전부 신고 대상이 된다는 §2.2의 지적도 여전히 일리가 있다. 다만 **G3의 면제 문언이 '메모리 + 실시간 요청 처리에 필요한 시간'으로 좁게 적혀 있어**, 14일 보존 로그를 사후 분석하는 우리 형태를 덮어 주지 않는다. 그리고 이 문서 스스로 세운 원칙이 답을 정한다 — `STORE_SUBMISSION_ANSWERS.md:6` "**과소 신고는 정책 위반, 과다 신고는 위반 아님 → 애매하면 신고하는 쪽으로.**" G7은 허위 신고의 결과를 "removal or suspension"이라고 적는다. 비대칭이 명백하다.

**판정: 아래 둘 중 하나를 9/25까지 택하라. 어느 쪽이든 5일 안에 끝난다.**

**선택지 A — 신고를 갱신한다 (권장).** 방문자 지표를 계속 쓰고 싶다면 이쪽이다.

| 콘솔 항목 | 바꿀 값 |
|---|---|
| 데이터를 수집·공유하나요? | **예** |
| 데이터 유형 | **앱 활동 → 앱 상호작용**(App activity → App interactions) 1개만 |
| 수집됨 / 공유됨 | 수집 **예** / 공유 **아니요**(제3자 전송 0건, C8) |
| 처리 목적 | **분석(Analytics)** + 필요시 **사기 방지·보안·법규 준수** |
| 필수 여부 | **수집이 필수**(이용자가 끌 수 없음) |
| 일시적으로만 처리되나요 | **아니요**(14일 보존) |
| 전송 중 암호화 | **예**(전 구간 HTTPS, certbot) |
| 데이터 삭제 요청 방법 | **예** — 14일 자동 삭제 + `koreanplus@gmail.com` 요청 경로 |

대가: 스토어의 `선언된 데이터 수집 없음` 배지가 사라지고 "앱 활동 수집" 표시가 뜬다. **정책 위반은 아니다.** 위치·기기ID·개인정보는 여전히 전부 '아니요'로 남는다.

**선택지 B — 기능을 되돌리고 배지를 지킨다.** `tools/daily_ops_report.py`의 방문자 블록(378~415행)을 제거하고, 이미 게시된 `docs/daily-reports/2026-09-22.md`의 방문자 표도 지운다. 이 경우 §2.2의 원래 논리가 복원되어 '수집 없음'을 유지할 수 있다. 다만 **nginx가 IP를 14일 기록한다는 사실 자체는 그대로**이므로, 논리는 "매칭되는 유형 없음"이라는 §2.2의 기존 해석에 계속 의존한다(그 해석 자체의 리스크는 낮음~중간으로 남는다). 지표를 잃는 대가가 크다면 A가 낫다.

**권고: A.** 지표는 이 프로젝트가 지금 가장 필요로 하는 것이고(오늘 배포 전체가 유입 개선이다), 배지 하나 때문에 허위 신고 리스크를 안는 것은 수지가 맞지 않는다.

---

## 4. 판정 3 — 개인정보처리방침 갱신 필요 (심각도 중간)

**판정: 갱신 필요.** G6이 방침과 데이터 안전 신고의 **일관성**을 명시적으로 요구한다("the section must be consistent with the disclosures made in the app's privacy policy"). 그리고 C6의 문장은 지금 **사실과 다르다**.

고칠 곳은 `web/templates/privacy.html` 두 군데다.

**(1) §1 자동수집 행의 괄호 설명(43행)** — 현재 "분석·프로필 연결·외부 제공이 없고"라고 적혀 있는데 분석을 시작했다. 선택지 A를 택한 경우 대체 문구 초안:

> 웹서버 접속 로그를 이용해 **일별 방문자 수·페이지 조회 깊이 등 집계 통계**를 산출합니다. 통계는 숫자로만 보관하고 IP는 개별 저장·프로필 연결·외부 제공을 하지 않으며, 원본 로그는 14일 후 자동 삭제됩니다. Google Play '데이터 안전'에는 **앱 활동(앱 상호작용) 수집**으로 신고했습니다(제3자 공유 없음).

선택지 B를 택한 경우: "분석" 단어를 지우지 말고 그대로 두되, 실제로 분석을 하지 않는 상태를 유지해야 한다.

**(2) §2 이용 목적(50~55행)** — "서비스 운영·품질 개선" 항목에 **"이용 현황 통계 산출(방문자 수·페이지 조회 깊이)"**를 한 줄 추가.

**(3) 공유 기능** — 방침 갱신 **불요**(선택 사항). 공유는 개인정보를 처리하지 않는다(C1). 굳이 넣는다면 §1 아래 참고 문구로 "공유 기능은 현재 보고 있는 페이지 주소와 제목만 이용자가 선택한 앱으로 전달하며, 서비스가 수집·보관하지 않습니다" 한 줄이면 충분하다. 과다 고지는 위반이 아니므로 넣어도 무방하다.

**(4) 시행일** — 본문을 고쳤으면 `updated` 값을 올려라. 안 올리면 "언제 바뀐 방침인지" 다툼이 생긴다.

한국 개인정보보호법 관점도 덧붙인다(참고, 법적 판단 아님): IP·접속기록의 개인정보 해당 여부는 국내 법령에 명시 규정이 없고 해석이 갈린다는 것이 공개 자료들의 공통된 서술이다([보안뉴스 해설](https://www.boannews.com/media/view.asp?idx=35078), [디지털데일리 SW법 바로알기](https://m.ddaily.co.kr/page/view/2014040309102201354)). 다만 **우리 방침은 이미 §1에 접속 로그(IP·시각·요청)를 수집 항목으로 적어 두었으므로** 국내법 고지 측면의 공백은 크지 않다. 문제는 "분석하지 않는다"는 **부가 서술의 진실성**이다. 그 문장 하나만 고치면 된다.

---

## 5. 판정 4 — 콘텐츠 등급 설문 (심각도 낮음)

**판정: 문제 없음 — 재제출 불요.**

G7은 재제출 의무를 "**설문 응답에 영향을 주는** 콘텐츠·기능 변경이 있는 모든 업데이트"로 한정한다. 오늘 변경을 §3 문항표 전체에 대조하면:

| 문항 | 오늘 변경의 영향 |
|---|---|
| 사용자 간 상호작용 | 판정 1대로 **영향 없음**(G1 보조 앱 제외) |
| 사용자 위치 공유 | 영향 없음 — 위치 미수집, IP를 위치로 변환하지 않음(G4) |
| 개인정보를 제3자와 공유 | 영향 없음 — 방문자 집계는 **우리 서버 내부**이고 제3자 전송 0건(C8). 판정 2★에서 '수집'으로 바뀌어도 **'공유'는 아니다** |
| 디지털 구매 / 광고 포함 / 도박 / 폭력·성·언어·약물 | 오늘 변경과 무관 |

즉 **어떤 답도 바뀌지 않으므로 새 설문을 낼 필요가 없다.** 단 판정 1의 '확인 필요'(콘솔 문항 도움말 확인)를 먼저 하고, 거기서 답이 바뀌면 그때는 재제출 대상이 된다.

---

## 6. 판정 5 — 그 밖에 9/27 전에 손볼 것

### 5-1. 스토어 긴 설명의 적중률 수치 — 확인 필요 (중간)

`docs/STORE_LISTING.md:31`은 "평균 오차 ±9.3% · 오차 ±20% 이내 적중 96% (검증 표본 157건, 2026년 9월 기준)"을 광고 문구로 싣는다. 오늘 적중률 화면에 설명 블록을 추가했고, 데이터는 매일 누적된다(9/22 낙찰결과 197건 반영, `docs/daily-reports/2026-09-22.md:27`). **나는 라이브 `/accuracy`의 현재 값을 확인하지 않았다 — 단정하지 않는다.**

G7의 "Misrepresentation of your app's content may result in its removal or suspension"은 등급 설문만이 아니라 등록정보 전반에 걸리는 리스크다. 국내에서는 표시·광고의 공정화에 관한 법률상 실증 책임 문제도 별도로 있다(변호사 확인 사항).

**할 일:** 출시 신청 직전 `https://naechaget.co.kr/accuracy`를 열어 세 숫자(평균 오차·적중률·표본수)를 읽고, 등록정보 문구와 다르면 **라이브 값으로 교체 + 기준 시점을 "2026년 9월 22일 기준"처럼 날짜까지** 적어라. 등록정보 텍스트 수정은 재빌드 없이 콘솔에서 즉시 반영된다.

### 5-2. 데이터 안전 부속 항목 — 2★ 결정에 종속 (중간)

선택지 A를 택하면 "전송 중 암호화 = 예", "삭제 요청 방법"을 새로 채워야 한다(현재 답안은 "해당 없음 — 수집 없음", `STORE_SUBMISSION_ANSWERS.md:49`). 값은 §3.2 표에 적어 두었다. 선택지 B면 손댈 것 없다.

### 5-3. og:image 썸네일의 번호판 — 확인 필요 (중간)

C2대로 og:image는 물건의 **첫 번째 사진 썸네일**이다. 오늘부터 이 이미지가 카카오·페이스북·검색엔진 캐시에 **박제**된다(우리가 페이지를 내려도 캐시는 남는다). 저장소 전체 grep 결과 **번호판 마스킹·모자이크 로직은 존재하지 않는다**. 사진은 법원이 공개한 감정평가 사진이지만, 그것을 "법원 사이트에서 열람"에서 "메신저·검색 캐시에 박제"로 바꾸는 것은 **공개 범위의 확대**다. 자동차 번호판의 개인정보성은 다툼이 있는 영역이며 이 판단은 변호사 몫이다.

**나는 실제 사진에 번호판이 식별 가능하게 찍혀 있는지 확인하지 않았다.** 할 일: 물건 3~5건의 첫 사진을 열어 번호판이 읽히는지 눈으로 보라. 읽힌다면 완화 선택지는 (a) og:image를 첫 사진 대신 **앱 아이콘/브랜드 이미지 고정**으로 돌리기 — `detail.html:16`·`report.html:21`의 조건을 지우면 끝, 1줄 변경 (b) 정면 사진 대신 번호판이 안 나오는 각도(실내·측면)를 고르기 (c) 그대로 두기(법원 공시 자료라는 근거로). **출시 자체를 막는 사안은 아니다.** 다만 사진 썸네일은 유입에 큰 기여를 하므로 (a)는 마지막 수단으로 두라.

참고로 **채무자 주소는 안전하다** — C7대로 목록상 주소는 관리자에게만 렌더되므로 검색 색인·og 어디에도 나가지 않는다. 오늘 색인을 연 것 때문에 새는 개인 식별정보는 확인되지 않았다.

### 5-4. 홈 화면 앱 이름 — 확인 필요 (낮음, 신고 항목 아님)

`docs/APP_LAUNCH_CHECKLIST.md:45`에 따르면 v1(버전코드 1) 빌드는 `short_name`이 `내차GET`이던 시점에 만들어져 홈 화면에 `내차GET`으로 뜬다. 스토어 이름은 `경매로 내차GET`이다. 신고 정합성 문제는 아니지만, 프로덕션 승격 전 재빌드를 한다면 이 김에 맞추는 편이 낫다(설치 후 이름이 다르면 이용자 혼란·리뷰 이슈).

### 5-5. 문제없음으로 확인한 것 (기록)

- **robots.txt의 `Disallow: /admin`·`/run/`**(C3)은 보안장치가 아니라 색인 제어일 뿐이지만, 실제 보호는 `_require_admin`의 404 응답이 하고 있다(`web/app.py:89-93`). **문제 없음.**
- **sitemap이 끝난 경매를 제외**하고(C3), **og 제목에 `[매각 종료]` 접두를 붙이며**(C2), **예상낙찰가·시세·적중률을 카드에 싣지 않은 것**은 "캐시되어 박제되는 값은 거짓이 된다"는 판단에서 나온 설계다. 소비자 오인 리스크를 스스로 줄인 조치이며, 이 보고서는 이를 **유지할 것**을 권고한다. 나중에 카드에 예상낙찰가를 넣자는 제안이 오면 이 항목을 근거로 반대하라.
- **`/terms` 404**는 무료 v1에서 필수가 아니다(기존 판단 유지). **결제 도입 시에는 사실상 필수**이며, 그때는 `docs/compliance-review.md` §4 전자상거래 표시의무 체크리스트가 함께 걸린다.
- **billing 활성화·유료 시세 노출은 여전히 불가**다. `docs/compliance-review.md` §5·§6.7의 조건이 충족되지 않았고, 오늘 배포로 달라진 것이 없다. 이 보고서는 그 결론을 바꾸지 않는다.

---

## 7. 5일 실행 계획

| 날짜 | 할 일 | 어디서 | 누가 |
|---|---|---|---|
| **9/23** | 2★ 선택지 **A/B 결정**(권고 A). 판정 1의 콘솔 문항 도움말 눈으로 확인 | Play Console 콘텐츠 등급 설문 화면 | 오너 |
| **9/24** | A면 `privacy.html` 43행·§2 수정 + `updated` 갱신 → 배포 / B면 `daily_ops_report.py:378-415` 제거 + 9/22 리포트 방문자 표 삭제 | 저장소 → EC2 배포 | 개발 |
| **9/24** | 라이브 `/accuracy` 값 확인 → 등록정보 긴 설명 수치·기준일 교체 | Play Console 스토어 등록정보 | 오너 |
| **9/25** | A면 데이터 안전 폼 갱신(§3.2 표 그대로 입력) 후 저장·제출 | Play Console 앱 콘텐츠 → 데이터 안전 | 오너 |
| **9/26** | og:image 번호판 육안 확인(물건 3~5건) → 필요 시 조치. 앱 이름 확인 | 실기기/브라우저 | 오너 |
| **9/26** | `docs/STORE_SUBMISSION_ANSWERS.md` **변경 이력에 오늘 결정 추기** — 다음 사람이 §2.2만 읽고 옛 논리를 재사용하지 않도록 | 저장소 | 개발 |
| **9/27** | 방침 URL 200 확인 → 프로덕션 승격 신청 | Play Console | 오너 |

---

## 8. 한계와 위임

- 나는 **Play Console 화면을 보지 못했다.** 콘솔에 실제 저장된 답안이 `docs/STORE_SUBMISSION_ANSWERS.md`와 다르면 이 보고서의 대조 전제가 흔들린다. 9/23에 콘솔 답안과 이 문서를 먼저 맞춰 보라.
- 인용한 정책 문언은 2026-09-22에 위 URL에서 직접 확인한 것이다. **Google 도움말은 예고 없이 개정된다** — 출시 신청일에 판정 1·2의 두 문장(G1의 "secondary apps", G3의 면제 3종)을 다시 열어 확인하라.
- 판정 5-1·5-3은 **내가 실측하지 않은 값에 달려 있다.** 확인 전까지 "문제 없음"으로 취급하지 말라.
- **이 문서는 "합법"을 단정하지 않는다.** 데이터 안전 신고의 최종 책임은 G2·G6가 명시하듯 전적으로 개발자에게 있고, Google은 대신 판단해 주지 않는다("Google's review cannot make determinations on behalf of developers"). 수집 해당 여부·개인정보 해당 여부·표시광고 실증의 최종 법적 판단은 **변호사에게 위임한다.**

---

## 변경 이력
- **2026-09-22** 최초 작성. 2026-09-22 배포분(공유 버튼·og 카드·robots/sitemap·홈 개편·방문자 집계) 5개 항목 판정. 결론: 출시 차단 요인은 방문자 집계로 인한 데이터 안전 신고 불일치 1건.
