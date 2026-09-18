/* 경매로 내차GET — 서비스워커
 * 전략: 정적자산(캐시우선+백그라운드갱신), **홈만** 캐시우선+배경갱신(신선도 TTL),
 *       나머지 페이지(네트워크우선→오프라인 폴백).
 * 라이브 데이터 앱이라 페이지는 기본적으로 최신을 우선한다. 홈만 예외인 이유는 아래.
 * 버전 올리면 이전 캐시 자동 정리. */
const CACHE = 'naechaget-v8';
const PRECACHE = ['/static/offline.html', '/static/icons/icon-192.png'];

/* 홈만 캐시 우선으로 두는 이유(2026-09-18 실측).
 * 앱은 이미 speculation rules 로 홈을 미리 받고 있다(운영 로그: 앱 시작 직후 /, /vehicles,
 * /calendar 가 같은 초에 도착). 그런데 아래 페이지 분기가 **모든 문서 요청을 fetch 로 직행**시켜,
 * 미리 받아 둔 결과를 쓰지 않고 매번 서버를 다시 기다렸다. 그래서 탭을 누를 때마다 TTFB 가
 * 그대로 체감에 들어갔다(운영 warm-cache 9회 중앙값 320ms).
 * → 홈 문서만 캐시를 먼저 돌려주고 배경에서 갱신한다. 사용자는 기다리지 않고, 화면은 곧 최신이 된다.
 *
 * ⚠ 신선도: 홈에는 추천 물건·시세·KPI 가 있다. 오래된 화면을 보여주지 않도록 TTL 을 둔다.
 *   TTL 안이면 캐시를 쓰고 배경 갱신, TTL 밖이면 **캐시를 쓰지 않고** 네트워크를 기다린다.
 *   매일 갱신은 하루 한 번이라 10분 창에서 숫자가 달라질 일은 사실상 없다.
 * ⚠ 앱 시작 주소(/?src=pwa)와 탭의 홈(/)은 주소가 다르지만 **같은 화면**이다. 캐시 키를 '/'로
 *   통일해 실행 중 확보한 문서를 탭 전환에서 그대로 쓴다(매니페스트는 건드리지 않는다).
 * ⚠ 홈 외 화면(/vehicles·/calendar·상세)은 기존 네트워크 우선 그대로다 — 목록·달력은 이미
 *   빠르고(TTFB 0.02~0.27초), 필터·페이지 조합마다 내용이 달라 캐시가 맞지 않는다. */
const HOME_KEY = '/';
const HOME_TTL = 10 * 60 * 1000;   // 10분
const STAMP = 'x-sw-cached-at';

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

/* 홈 문서를 시각 도장과 함께 저장한다.
 * ⚠ 인자는 **이 함수 전용 복제본**이어야 한다. Response 본문은 한 번만 읽을 수 있어서,
 *   페이지로 돌려준 응답을 여기서 다시 복제하려 하면 이미 소비된 뒤라 실패한다
 *   (2026-09-18 실측: "Response body is already used" — 이 오류가 조용히 삼켜져
 *    홈 캐시가 한 번도 저장되지 않았다). 복제는 반드시 호출부에서 fetch 직후에 뜬다. */
async function putHome(resp) {
  try {
    const body = await resp.arrayBuffer();
    const c = await caches.open(CACHE);
    const h = new Headers(resp.headers);
    h.set(STAMP, String(Date.now()));
    await c.put(HOME_KEY, new Response(body, { status: resp.status, statusText: resp.statusText, headers: h }));
  } catch (err) {
    // 침묵시키지 않는다 — 이 저장이 조용히 실패해 온 것을 오래 못 봤다(위 주석).
    console.warn('[sw] 홈 캐시 저장 실패', err);
  }
}

async function homeFirst(e, req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(HOME_KEY);
  const age = hit ? Date.now() - Number(hit.headers.get(STAMP) || 0) : Infinity;
  if (hit && age < HOME_TTL) {
    // 즉시 캐시로 응답하고, 배경에서 최신을 받아 다음 진입에 대비한다.
    e.waitUntil(fetch(req).then((r) => (r && r.ok ? putHome(r) : null)).catch(() => {}));
    return hit;
  }
  try {
    const net = await fetch(req);
    // 복제는 여기서 즉시 — 아래 return 으로 본문이 페이지에 넘어가면 더는 복제할 수 없다.
    if (net && net.ok) { const copy = net.clone(); e.waitUntil(putHome(copy)); }
    return net;
  } catch (err) {
    return hit || (await caches.match('/static/offline.html'));
  }
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // POST(폼 제출 등)는 항상 네트워크
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;       // 외부(엔카·케이카 등)엔 개입 안 함

  // 정적 자산: 캐시 우선 + 백그라운드 갱신(빠른 로딩·오프라인 안전)
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.open(CACHE).then(async (c) => {
      const hit = await c.match(req);
      const net = fetch(req).then((r) => { if (r && r.ok) c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }

  // 사진(원격 대용량)·기타: 네트워크만(캐시로 용량 낭비 방지)
  if (url.pathname.startsWith('/photo/')) return;

  // 홈 문서(앱 시작 /?src=pwa 포함): 캐시 우선 + 배경 갱신 + 신선도 TTL
  if (req.mode === 'navigate' && url.pathname === '/') {
    e.respondWith(homeFirst(e, req));
    return;
  }

  // 그 밖의 페이지/GET: 네트워크 우선(항상 최신), 실패 시 캐시→오프라인 안내
  e.respondWith(
    fetch(req).catch(() => caches.match(req).then((r) => r || caches.match('/static/offline.html')))
  );
});
