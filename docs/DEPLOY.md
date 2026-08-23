# 배포 가이드 (Railway / Render)

이 앱은 **FastAPI + SQLite + 로컬 사진 파일 + 백그라운드 수집**이라, 서버리스(Vercel)가
아니라 **영속 디스크와 상시 프로세스를 지원하는 호스트**가 맞다.

- ❌ **Vercel 부적합**: 파일시스템이 읽기전용/임시라 SQLite가 유지되지 않고, `data/` 사진(수 GB)을
  서빙할 수 없으며, 백그라운드 수집(상시 프로세스)이 불가.
- ✅ **권장**: Railway / Render / Fly.io / 소형 VPS (영속 볼륨 + 상시 프로세스).

배포 준비는 코드에 반영됨:
- 서버 바인딩: `Procfile` = `uvicorn web.app:app --host 0.0.0.0 --port $PORT`
- 데이터 경로 외부화: 환경변수 **`DATA_DIR`** → 영속 볼륨 마운트 경로 (DB + 사진 저장). 미지정 시 `./data`.
- Python 버전: `runtime.txt` (3.12).

---

## A. Render (Blueprint)

1. GitHub 저장소를 Render에 연결(New → Blueprint) → 루트의 `render.yaml` 자동 인식.
2. Blueprint가 다음을 생성: 웹 서비스 + 영속 디스크(`/var/data`, 5GB) + `DATA_DIR=/var/data`.
   - ⚠️ **영속 디스크는 유료 플랜(starter+)에서만 지원**(무료 플랜은 디스크 없음 → SQLite 소실).
3. 배포 완료 후 **데이터 시딩**(아래 C) → 앱이 물건·사진을 표시.

## B. Railway

1. New Project → Deploy from GitHub repo.
2. **Volume 추가**: 서비스에 볼륨을 붙이고 마운트 경로 지정(예: `/data`).
3. **Variables**: `DATA_DIR=/data`, (선택) `PYTHONIOENCODING=utf-8`.
4. Start Command은 `Procfile` 자동 사용(`uvicorn ... --host 0.0.0.0 --port $PORT`).
5. 배포 후 **데이터 시딩**(아래 C).

---

## C. 데이터 시딩 (중요)

새 볼륨은 **비어 있다**. 앱은 뜨지만 물건 목록이 비고 사진도 없다. 로컬 `data/`를 볼륨으로 옮겨야 한다.

- **DB(작음, 2MB)**: `data/auction.db` → 볼륨의 `$DATA_DIR/auction.db` 로 업로드.
  이것만 넣어도 목록·분석·시세·판정이 모두 표시된다(사진 제외).
- **사진(큼, ~1.2GB)**: `data/<사건번호_물건>/photos/…` 전체 → 볼륨의 같은 구조로 업로드.
  - ⚠️ `data/_photo_work/`(몽타주 ~700MB)는 분류 작업용이라 **업로드 불필요**.

옮기는 방법(플랫폼별):
- **Render**: 유료 인스턴스의 **SSH** 접속 후 `rsync`/`scp`, 또는 임시 관리 업로드.
- **Railway**: `railway` CLI 또는 볼륨 접근 수단으로 복사.
- **대안**: 서버에서 수집을 재실행해 점진 재구축(외부 사이트 접근 → C.4 지연·상한 준수, 느림).

> 사진이 커서 부담되면: **1단계는 DB만 시딩**(목록·분석 동작) → 사진은 이후 동기화하거나
> 오브젝트 스토리지(S3/R2)로 분리하는 방안(추가 작업)을 검토.

---

## D. ⚠️ 준법·접근 제어 (배포 전 확인)

`docs/compliance-review.md` 기준:
- **엔카/케이카 시세를 불특정 다수에 공개(상용)**하는 것은 HIGH 리스크로 **보류** 상태다.
  공개 URL로 배포하면 이 시세가 그대로 노출된다.
- 따라서 **개인용/비공개 접근**(로그인·IP 허용목록·비공개 링크)으로 제한하거나,
  공개 서비스화는 준법 정리(대체 시세 소스·제휴, 개인정보 마스킹, 전자상거래 표시의무, 변호사 확인) 이후 진행 권장.
- 결제·회원 기능은 현재 **비활성**(MON-01/02 blocked) 유지.

---

## E. 로컬 실행 (참고)

```
python run_web.py           # http://127.0.0.1:8000
```
CSS 변경 시 `npm run build:css` 후 서버 재시작. (배포에는 빌드된 `web/static/app.css`가 커밋되어 있어 노드 빌드 불필요.)
