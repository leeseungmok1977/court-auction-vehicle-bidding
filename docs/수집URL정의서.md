# 수집 URL 정의서 (실측 기반) — v1.0

- 대상: 대법원 법원경매정보 `www.courtauction.go.kr` (WebSquare 프레임워크 SPA)
- 작성 근거: 화면 정의(XML) + 실제 응답 분석 (추측 없음, 설계서 C.4-3 준수)
- 확인일: 2026-08-17
- 세션: `GET /` → `GET /pgj/index.on` 진입 시 서버가 `WMONID, SID, cortAuctnLgnMbr, JSESSIONID` 쿠키 발급. 이후 요청에 자동 전달(하드코딩 금지)

> ⚠️ robots.txt 없음(404). 준법 규칙(요청 간 5~10초 지연, 소량, 403/429/CAPTCHA 시 중단)은 그대로 준수한다.

---

## 공통 요청 헤더

| 헤더 | 값 |
|---|---|
| Content-Type | `application/json;charset=UTF-8` |
| Accept | `application/json` |
| Referer | `https://www.courtauction.go.kr/pgj/index.on` |
| Origin | `https://www.courtauction.go.kr` |
| X-Requested-With | `XMLHttpRequest` |
| User-Agent | 일반 브라우저 UA |

응답 공통 envelope: `{ "status", "message", "timestamp", "errors", "data", "token" }` — 실데이터는 `data` 아래.

---

## L1. 자동차·중기 물건목록 조회 (FLOW-01)

- **URL**: `POST /pgj/pgjsearch/searchControllerMain.on`
- **화면**: `PGJ154M01.xml`(검색폼) → `PGJ154M02.xml`(결과)
- **요청 Body** (JSON):

```json
{
  "dma_pageInfo": { "pageNo": 1, "pageSize": 40, "bfPageNo": "", "startRowNo": "",
                    "totalCnt": "", "totalYn": "", "groupTotalCount": "" },
  "dma_srchGdsDtlSrchInfo": {
    "cortAuctnSrchCondCd": "0004603",   // [고정] 물건검색 구분: 자동차·중기
    "lclDspslGdsLstUsgCd": "30000",     // [고정] 용도 대분류: 자동차
    "cortStDvs": "1", "statNum": 1, "pgmId": "PGJ154M02", "lafjOrderBy": "",
    "cortOfcCd": "",   // [가변] 법원사무소 코드 (전체=빈값)
    "jdbnCd": "",      // [가변] 담당계
    "csNo": "",        // [가변] 사건번호(예: 2025타경103470)
    "aeeEvlAmtMin": "", "aeeEvlAmtMax": "",             // [가변] 감정평가액 범위
    "rletLwsDspslPrcMin": "", "rletLwsDspslPrcMax": "", // [가변] 최저매각가 범위
    "flbdNcntMin": "", "flbdNcntMax": "",               // [가변] 유찰횟수 범위
    "gdsVendNm": "",   // [가변] 제조사명
    "carMdlNm": "",    // [가변] 자동차명
    "carMdyrMin": "", "carMdyrMax": "",                 // [가변] 연식 범위
    "fuelKndCd": "",   // [가변] 연료 코드
    "grbxTypCd": "",   // [가변] 변속기 코드
    "mclDspslGdsLstUsgCd": "", "sclDspslGdsLstUsgCd": "", // 용도 중/소분류
    "dspslDxdyYmd": "", "sideDvsCd": ""
  }
}
```

- **페이지네이션**: `dma_pageInfo.pageNo` 증가. 총건수는 응답 `data.dma_pageInfo.groupTotalCount` (확인 시점 자동차 전체 **573건**)
- **응답**: `data.dlt_srchResult` (배열, 페이지당 최대 pageSize) + `data.dma_pageInfo`

### L1 응답 필드 ↔ A.5 '물건' 열 매핑

| 응답 필드 | 의미 | A.5 물건 열 |
|---|---|---|
| `saNo` / `printCsNo`(뒤부분) | 사건번호(20자리 / 표시용) | 사건번호 |
| `mokmulSer` / `maemulSer` | 물건/목적물 순번 | 물건번호 |
| `jiwonNm` / `boCd` | 법원명 / 법원사무소코드 | 법원 |
| `jejosaNm` | 제조사 | 제조사 |
| `carNm` | 차명 | 모델 |
| `carYrtype` | 연식(0=미상) | 연식 |
| `fuelKindcd` | 연료(코드) | 연료 |
| `bsgFormCd` | 변속기(코드) | 변속기 |
| `gamevalAmt` | 감정평가액 | 감정가 |
| `minmaePrice` | 최저매각가 | 최저매각가 |
| `yuchalCnt` | 유찰횟수 | 유찰횟수 |
| `maeGiil`(YYYYMMDD) | 매각기일 | 매각기일 |
| `dspslUsgNm` | 매각용도명 | (참고) |
| `convAddr` | 소재지(표시) | (참고) |
| `docid` | 상세조회 키 | 폴더링크(내부) |

주행거리는 목록에 없음 → **L3 상세에서 확정**.

---

## L3. 물건 상세 조회 (FLOW-02) — 사진·감정요항 포함

- **URL**: `POST /pgj/pgj15B/selectAuctnCsSrchRslt.on`
- **화면**: `PGJ154M03.xml`
- **요청 Body** (JSON): 목록 행에서 `csNo=saNo`, `cortOfcCd=boCd`, `dspslGdsSeq=maemulSer` 사용

```json
{ "dma_srchGdsDtlSrch": {
    "csNo": "20250130104467", "cortOfcCd": "B000210", "dspslGdsSeq": "1",
    "pgmId": "PGJ154M03", "srchInfo": {} } }
```

- **응답**: `data.dma_result` (하위 객체 다수)

### L3 응답 필드 ↔ 물건 상세

| 위치 | 필드 | 의미 |
|---|---|---|
| `dma_result.gdsDspslObjctLst[0]` | `drvnDistIndctCtt` | **주행거리(km)** |
| " | `carDsplcCtt` | 배기량(cc) |
| " | `carVidCtt` | 차대번호(VIN) |
| " | `objctRegNo` | 자동차등록번호 |
| " | `gdsVendNm`/`carMdlNm`/`carDelvYr` | 제조사/차명/출고연식 |
| " | `fuelKndCd`/`grbxTypCd` | 연료/변속기 코드 |
| " | `storgPlcRdnmAddr`/`storgPlcAllLtnoAddr` | 보관장소 |
| `dma_result.dspslGdsDxdyInfo` | `aeeEvlAmt` | 감정가 |
| " | `flbdNcnt` | 유찰횟수 |
| " | `dspslDxdyYmd` | 매각기일 |
| " | `fst/scnd/thrd/fothPbancLwsDspslPrc` | **회차별 최저매각가**(→ 기일이력) |
| " | `dspslGdsSpcfcEcdocId` | 감정평가서/명세서 **전자문서 ID**(→ L4) |
| `dma_result.aeeWevlMnpntLst[].aeeWevlMnpntCtt` | 감정평가 요항 텍스트 | **사고 판정 근거** |
| `dma_result.csPicLst[]` | `picFile`(base64), `picTitlNm`, `picFileUrl` | **현황 사진(응답 내장)** |
| `dma_result.picDvsIndvdCnt[]` | 사진 구분별 개수 | 참고 |

**중요(사고 판정)**: 요항 텍스트에는 보험개발원 사고이력 리포트가 정형구로 포함됨
(`전손 보험사고 : N건`, `침수 보험사고 : N건`, `내차 피해 : N회` 등).
값이 `0건`이어도 단어가 나타나므로 **단순 키워드 매칭은 오탐** → `parse_insurance_history()`로
카운트를 파싱해 판정한다. (침수/전손 건수>0=보류, 내차/상대차 피해>0 또는 훼손 표현=사고)

**사진**: `csPicLst[].picFile`이 base64(실제 바이트는 GIF)로 **응답에 내장** → 별도 다운로드 불필요.
파일명은 `.jpg`로 오는 경우가 있으나 실제 GIF이므로 magic 바이트로 확장자 판별.

---

## L4. 감정평가서 PDF (전자문서) — 조사 중

- 키: L3 응답의 `dspslGdsDxdyInfo.dspslGdsSpcfcEcdocId` (전자문서 ID)
- 상태: 별도 전자문서 뷰어 경로 확인 필요(문서가 이미지/뷰어 기반일 수 있음 — 설계서 A.7 제약).
  단, 핵심 감정 내용(주행거리·색상·관리상태·사고이력)은 **L3 요항 텍스트로 이미 확보**되어
  PDF 없이도 사고 판정·산정이 가능하다. PDF는 보강 자료.

## L2/L6 (페이지네이션 / 기일내역)

- **L2 페이지네이션**: L1과 동일 엔드포인트, `dma_pageInfo.pageNo`만 증가.
- **L6 기일내역**: L3 응답의 회차별 최저가(`*PbancLwsDspslPrc`)로 상당 부분 대체 가능.

---

---

## E. SK엔카 동급 시세 (E1~E3 / FLOW-03)

> ⚠️ **준법 경고**: `api.encar.com/robots.txt` = `User-agent: * / Disallow: /` (전면 금지).
> 아래 자동 수집은 **사용자의 명시적 지시(2026-08-17)** 하에 소량·저속으로만 수행한다.
> robots 준수를 원하면 이 경로를 비활성화하고 케이카만 사용하거나 수동 캡처(Part B)로 대체.

- **URL**: `GET https://api.encar.com/search/car/list/general`
- **파라미터**:
  - `count=true`
  - `q=` 검색식 (실측 문법):
    `(And.Hidden.N._.(C.CarType.Y._.(C.Manufacturer.기아._.ModelGroup.모하비.))_.Year.range(202000..202312).)`
    - `CarType`: `Y`=국산, `N`=수입 / `Manufacturer`·`ModelGroup`=엔카 표기
    - `Year.range(YYYYMM..YYYYMM)`: 첫등록 기준 범위 (선택)
    - ⚠️ 제조사만: `..._.Manufacturer.기아.))` (평면) / 모델 포함: `(C.Manufacturer.기아._.ModelGroup.모하비.)` (이중중첩 `(C.ModelGroup...)`은 400)
  - `sr=|ModifiedDate|<offset>|<limit>` (정렬|필드|오프셋|개수)
- **응답**: `{ "Count": N, "SearchResults": [ ... ] }`

### E 응답 필드 ↔ 시세 매칭

| 응답 필드 | 의미 | 용도 |
|---|---|---|
| `Manufacturer`/`Model`/`Badge` | 제조사/모델/등급 | 매칭 키 |
| `FormYear` | 연식(YYYY, 문자열) | **연식 ±1년 매칭** |
| `Year` | 첫등록(YYYYMM) | q Year.range 필터 |
| `Mileage` | 주행거리(km) | **±30% 매칭** |
| `Price` | 가격(**만원**) | 원 환산 ×10000 → 통계 |
| `FuelType` | 연료 | 참고 |

동급 필터 후 평균/중앙값/최저/표본수 산출 → 입찰가 산정(A.6)에 median 투입.
**모델 매핑**(경매 차명↔엔카 ModelGroup)은 `config.yaml: model_mapping`. 미매핑 시 알림.

## K. 케이카 (K1~K3) — 엔드포인트 확인, 재현 보류

- **준법**: `www.kcar.com` robots `Allow: /`(상세만 Disallow), `market.kcar.com` robots `Disallow:`(전체 허용),
  `market-api.kcar.com`/`api.kcar.com` robots 404(없음) → **엔카와 달리 수집 허용**.
- **검색 API(확인)**: `POST https://market-api.kcar.com/api/v1/cc/search/`
  (Nuxt 번들 `searchCcList` → `getAxiosForC2C().post("/api/v1/cc/search/", setParam(param))`,
  C2C base=`market-api.kcar.com`, withCredentials)
- **상태**: 빈 body POST 시 404(static) → 요청 파라미터 구조/세션 토큰 필요. 마켓 SPA(`market.kcar.com`,
  Nuxt3 단일 번들)에서 실제 검색 요청 1건을 **Part B로 캡처(K1)** 하면 즉시 재현 가능.
- 관련 카운트 API: `/api/v1/ds/getMnuftrListCount`, `getModelGrpListCount`, `getGrdListCount` (제조사/모델/등급 파셋).
- **현 시점 시세는 엔카로 충족**. 케이카는 2차 표본 보강용(플랫폼 가중 0.95).

---

## 미해결 / 후속 확인

- [ ] 연료/변속기 코드(`fuelKndCd`, `grbxTypCd`) → 한글명 공통코드 테이블 (예: `0001002`)
- [ ] 감정평가서 PDF(L4) 전자문서 다운로드 경로
- [ ] 케이카(K) 검색 API 엔드포인트 확정 (Nuxt 번들 분석)
- [ ] 엔카 robots 정책에 대한 최종 운영 방침 (수동 캡처 병행 여부)
