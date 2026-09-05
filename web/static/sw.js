/* 경매로 내차GET — 서비스워커
 * 전략: 정적자산(캐시우선+백그라운드갱신), 페이지(네트워크우선→오프라인 폴백).
 * 라이브 데이터 앱이라 페이지는 항상 최신을 우선하고, 오프라인일 때만 안내 페이지.
 * 버전 올리면 이전 캐시 자동 정리. */
const CACHE = 'naechaget-v3';
const PRECACHE = ['/static/offline.html', '/static/icons/icon-192.png'];

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

  // 페이지/그 외 GET: 네트워크 우선(항상 최신), 실패 시 캐시→오프라인 안내
  e.respondWith(
    fetch(req).catch(() => caches.match(req).then((r) => r || caches.match('/static/offline.html')))
  );
});
