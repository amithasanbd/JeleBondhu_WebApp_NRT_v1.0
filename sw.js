/* JeleBondhu service worker: app shell cache-first, advisory bundle network-first with offline fallback. */
const BUILD='__BUILD__';
const SHELL=__SHELL__;
const CACHE='jb-shell-'+BUILD, DATA='jb-data';
// Cache only the tiny fisher-mode core on install. The dashboard/bathymetry,
// species catalog and research graphics are cached lazily on first use:
// do not download >1 MB of optional assets to every low-bandwidth phone.
const CORE=['./fisher.html','./assets/css/app.css','./assets/js/icons.js',
            './assets/js/i18n.js','./assets/js/core.js','./assets/js/fisher.js',
            './assets/img/icon-96.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>Promise.all(CORE.map(u=>c.add(u).catch(()=>null)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('jb-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
const isData=u=>/\/(live|demo)\//.test(u.pathname);
function timeout(ms,p){return new Promise((res,rej)=>{const t=setTimeout(()=>rej(new Error('timeout')),ms);p.then(v=>{clearTimeout(t);res(v)},e=>{clearTimeout(t);rej(e)})})}
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);if(u.origin!==location.origin)return;
  if(isData(u)){
    e.respondWith((async()=>{
      const c=await caches.open(DATA);
      try{const net=await timeout(7000,fetch(r));if(net.ok)c.put(r,net.clone());return net}
      catch(err){const hit=await c.match(r);if(hit){const h=new Headers(hit.headers);h.set('x-jb-from-cache','1');return new Response(await hit.blob(),{status:200,headers:h})}
        return new Response('offline',{status:503})}
    })());return}
  e.respondWith((async()=>{
    const hit=await caches.match(r,{ignoreSearch:true});
    const fetcher=fetch(r).then(async n=>{if(n.ok){const c=await caches.open(CACHE);c.put(r,n.clone())}return n}).catch(()=>null);
    return hit||(await fetcher)||new Response('offline',{status:503});
  })());
});
self.addEventListener('message',e=>{const d=e.data||{};if(d.type==='warm'&&Array.isArray(d.urls)){e.waitUntil(caches.open(DATA).then(c=>Promise.all(d.urls.map(u=>{const url=new URL(u,self.location.href);if(url.origin!==location.origin)return null;return fetch(url).then(r=>{if(r.ok)return c.put(url,r)}).catch(()=>null)}))))}});
