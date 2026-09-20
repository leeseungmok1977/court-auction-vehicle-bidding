// 경매차량 사진 몽타주 비전 분류 워크플로 (classify-photos 루틴용)
// 사용: Workflow({scriptPath: "scripts/photo_classify_workflow.js", args: {base, total}})
//   base  = data/_photo_work 절대경로 (prep가 만든 args.json의 base)
//   total = 몽타주 개수 (args.json의 total)
// 반환: {results:[{idx,order,confident,note}], count, batches}
//   → task 출력파일을 `python scripts/photo_classify.py ingest <output>` 로 results.json 추출
export const meta = {
  name: 'classify-photos-bulk',
  description: '경매차량 사진 몽타주를 비전 분류해 전면·측면·후면 우선 order 산출',
  phases: [{ title: 'Classify', detail: '몽타주 배치별 비전 분류(병렬)' }],
}

const base = args.base
const total = args.total
const BATCH = 32                                  // 배치당 몽타주 수(≈15배치 유지)
const idxs = Array.from({ length: total }, (_, i) => String(i + 1).padStart(4, '0'))
const batches = []
for (let i = 0; i < idxs.length; i += BATCH) batches.push(idxs.slice(i, i + BATCH))

const SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          idx: { type: 'string', description: '몽타주 인덱스(0001 등, zero-pad 4)' },
          order: { type: 'array', items: { type: 'integer' }, description: '셀 번호 우선순위(모든 셀 1..N 각 1회)' },
          confident: { type: 'boolean' },
          note: { type: 'string' },
          // 화물차일 때만 채운다(선택). 승용차·건설장비·선박이면 생략.
          // 법원 차명에 형식이 안 적힌 물건이 많아 모델명만으로는 카고와 탑차를 못 가르고,
          // 섞인 시세는 틀린 시세가 된다. 사진에는 적재함이 그대로 찍혀 있다(2026-09-20).
          truck_form: {
            type: 'string',
            enum: ['카고(화물)트럭', '윙바디/탑'],
            description: '1톤급 화물차의 적재함 형태. 평판(짐칸이 열린 트럭)=카고, 박스(냉동·탑차·윙바디)=윙바디/탑. 크레인·덤프·탱크로리·파워게이트 등 특장 장비가 달렸거나 확실하지 않으면 생략',
          },
        },
        required: ['idx', 'order', 'confident'],
      },
    },
  },
  required: ['results'],
}

const prompt = (batch) => `당신은 중고차 경매 사진을 정렬하는 비전 분류기입니다.
아래 각 몽타주 PNG를 Read 도구로 반드시 하나씩 열어 확인하세요(건너뛰지 말 것). 각 몽타주는 한 차량의 경매 사진들을 격자로 배치했고, 각 셀 좌상단에 파란 배지로 번호(1,2,3…N)가 있습니다.

각 몽타주마다 셀 번호를 다음 우선순위로 재배열한 order 배열을 만드세요:
  1) 전면(정면) 외관 → 2) 측면 외관 → 3) 후면 외관 → 4) 나머지 외관·실내(대시보드·시트·트렁크·적재함)
그리고 다음은 반드시 맨 뒤로: 지도(소재지 지도), 서류/문서 스캔, 표/텍스트 이미지, 빈·무관 이미지.
규칙:
- order 에는 그 몽타주의 모든 셀 번호(1..N)를 각각 정확히 한 번씩 포함(누락·중복 금지).
- 앞의 3개가 전면→측면→후면이 되게. 순수 측면/후면 컷이 없으면 가장 가까운 각도(전측면·후측면)로 대체.
- 전면/측면/후면 중 명확한 컷이 없으면(예: 건설장비·선박·전면위주만) confident=false, note에 짧은 이유.

추가로, **포터·봉고 같은 1톤급 화물차**라면 적재함 형태를 truck_form 에 적으세요(그 외 차종은 생략):
  - '카고(화물)트럭' : 짐칸이 열린 평판 트럭(옆·뒤가 낮은 문짝이거나 그물망·천막만 덮인 것)
  - '윙바디/탑'      : 짐칸이 박스인 것(냉동탑차·내장탑차·윙바디 — 옆면이 벽으로 막힌 상자)
  ⚠ 정면 사진만으로는 알 수 없습니다. 측면·후면 컷에서 짐칸이 보일 때만 적고, 안 보이거나
    애매하면 **생략하세요**(틀린 형식은 틀린 시세로 이어집니다 — 모르면 비워 두는 편이 낫습니다).
  ⚠ **특장 장비가 달렸으면 둘 중 어느 쪽도 아닙니다 — 생략하세요.** 크레인, 사다리차, 고소작업대,
    탱크로리, 청소차, 살수차, 덤프(짐칸이 기울어 올라가는 것), 파워게이트(뒤에 달린 리프트),
    활어차 등. 겉모습이 평판이어도 장비가 붙으면 값이 완전히 달라져 일반 카고 시세로 매기면
    틀립니다. 실제로 이번 배치에 크레인 달린 포터가 있습니다 — 그걸 '카고'라고 답하면 안 됩니다.
    이 경우 note 에 무슨 장비인지 짧게 적어 주세요.

분류할 몽타주(각각 Read로 열 것):
${batch.map((ix) => `- idx ${ix}: ${base}/${ix}.png`).join('\n')}

각 몽타주에 대해 {idx, order(정수 배열), confident, note(짧게)} 를 만들어 results 배열로 반환하세요. idx는 위 파일명 그대로.`

phase('Classify')
const out = await parallel(
  batches.map((batch, bi) => () =>
    agent(prompt(batch), { label: `classify:${bi + 1}/${batches.length}`, phase: 'Classify', schema: SCHEMA })
      .then((r) => (r && r.results) ? r.results : [])
  )
)
const results = out.filter(Boolean).flat()
return { results, count: results.length, batches: batches.length }
