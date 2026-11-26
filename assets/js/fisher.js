/* Fisher-lite page: icon-first, three taps, one big answer. Loads ~25 KB (manifest + lite + reasons). */
(async function(){
const $=s=>document.querySelector(s);
const main=$('#main');
const S={port:JB.store.get('jb_port'),vessel:JB.store.get('jb_vessel')||'mechanized',dep:0};
let B=null,reasons=null,fresh='fresh',offline=false;
const BOATS=[['small','b_small','boat_small'],['mechanized','b_mech','boat_mech'],['trawler','b_trawl','boat_trawl']];

function banners(){
  const m=B.m,out=[];
  if(m.mode!=='live')out.push(`<div class="bn demo">${JBI('warn')}<span>${JB.t('demo_banner')}</span></div>`);
  if(offline)out.push(`<div class="bn info">${JBI('info')}<span>${JB.t('offline')}</span></div>`);
  if(fresh==='aging')out.push(`<div class="bn warn">${JBI('clock')}<span>${JB.t('aging_banner')}</span></div>`);
  if(fresh==='stale')out.push(`<div class="bn bad">${JBI('clock')}<span>${JB.t('stale_banner')}</span></div>`);
  if(fresh==='expired')out.push(`<div class="bn bad">${JBI('clock')}<span>${JB.t('expired_banner')}</span></div>`);
  if(B.verify==='failed')out.push(`<div class="bn bad">${JBI('shield')}<span>${JB.t('integrity_bad')}</span></div>`);
  if(B.verify==='unavailable')out.push(`<div class="bn info">${JBI('shield')}<span>${JB.t('integrity_na')}</span></div>`);
  $('#banners').innerHTML=out.join('');
}
function chrome(){
  document.documentElement.lang=JB.lang;
  $('#appname').textContent=JB.t('app');$('#tag').textContent=JB.t('tag');$('#langbtn').textContent=JB.t('lang');
  $('#fullink').innerHTML=JBI('map')+' '+JB.t('full');
}
function pname(id){const p=B.m.ports[id];return JB.lang==='bn'?p.name_bn:p.name_en}

async function render(){
  chrome();banners();
  const ports=B.m.ports,deps=B.m.depart_offsets_h;
  let h=`<div class="step"><span class="num">${JB.num(1)}</span>${JBI('port')} ${JB.t('step_port')}</div><div class="grid2" id="ports">`;
  for(const id in ports)h+=`<button class="big-btn ${S.port===id?'on':''}" data-port="${id}">${JBI('port')}<span>${pname(id)}</span></button>`;
  h+=`</div><div class="step"><span class="num">${JB.num(2)}</span>${JB.t('step_boat')}</div><div class="grid3">`;
  for(const [v,ic,k] of BOATS)h+=`<button class="big-btn ${S.vessel===v?'on':''}" data-vessel="${v}">${JBI(ic)}<span>${JB.t(k)}</span><small>${JB.t(k+'_s')}</small></button>`;
  h+=`</div><div id="when"></div><div id="res"></div>`;
  main.innerHTML=h;
  main.querySelectorAll('[data-port]').forEach(b=>b.onclick=()=>{S.port=b.dataset.port;JB.store.set('jb_port',S.port);render()});
  main.querySelectorAll('[data-vessel]').forEach(b=>b.onclick=()=>{S.vessel=b.dataset.vessel;JB.store.set('jb_vessel',S.vessel);render()});
  if(!S.port){return}
  let lite;
  try{lite=await B.get(`lite/${S.vessel}__${S.port}.json`)}catch(e){$('#res').innerHTML=`<div class="bn bad">${JB.t(B?'err_load':'no_bundle')}</div>`;banners();return}
  banners();
  const when=$('#when');
  let w=`<div class="step"><span class="num">${JB.num(3)}</span>${JBI('clock')} ${JB.t('step_when')}</div><div class="grid3">`;
  lite.departs.forEach((d,i)=>{w+=`<button class="big-btn ${S.dep===i?'on':''}" data-dep="${i}"><span>${d.offset_h===0?JB.t('now'):JB.num(d.offset_h)+' '+JB.t('later')}</span><small>${JB.fmtWhen(JB.parseBDT(d.depart_bdt))}</small></button>`});
  when.innerHTML=w+'</div>';
  when.querySelectorAll('[data-dep]').forEach(b=>b.onclick=()=>{S.dep=+b.dataset.dep;render()});
  const d=lite.departs[Math.min(S.dep,lite.departs.length-1)];
  const L=d.overall,E=JB.effClass(L,fresh),downgraded=E!==L;
  const p=B.m.ports[S.port];
  let r=`<div class="result ${E}"><div class="glyph">${JBI(JB.GLYPH[E])}</div><div class="word">${JB.t(E)}</div>`;
  r+=`<div class="sub">${downgraded?JB.t(fresh==='expired'?'expired_banner':'stale_banner'):(JB.lang==='bn'?d.headline_bn:d.headline_en)}</div></div>`;
  // why
  const reasonsHtml=[];
  if(!downgraded&&d.why&&d.why.length){
    for(const w of d.why){const c=reasons.codes[w.bit];reasonsHtml.push(`<li><span class="sev ${c.severity}"></span><span>${c[JB.lang]}</span></li>`)}
  }
  if(!downgraded&&!B.m.bmd_verified&&d.bmd_pending>0)reasonsHtml.unshift(`<li><span class="sev unknown"></span><span>${JB.t('bmd_unver')}</span></li>`);
  if(reasonsHtml.length)r+=`<div class="card" style="margin-top:10px"><b>${JBI('info')} ${JB.t('why')}</b><ul class="reasons">${reasonsHtml.join('')}</ul></div>`;
  if(d.jatka_active)r+=`<div class="bn warn" style="border-radius:12px;margin-top:8px">${JBI('fish')}<span>${JB.t('jatka')}</span></div>`;
  // zones
  if(!downgraded&&(E==='S'||E==='C')){
    r+=`<div class="step" style="margin-top:16px">${JBI('fish')} ${JB.t('zones')}</div>`;
    if(!d.zones.length)r+=`<p class="muted">${JB.t('nozones')}</p>`;
    d.zones.forEach((z,i)=>{const b=JB.bearing(p.lat,p.lon,z.lat,z.lon);
      r+=`<div class="fz"><div class="arrow" style="transform:rotate(${b.toFixed(0)}deg)">${JBI('arrow','fill')}</div><div><b>${i+1}. ${JB.dirWord(b)}</b> · ${JB.num(z.dist_nm)} ${JB.t('dist')}<br><span class="muted small">${JBI('clock')} ${JB.num(z.trip_h)} ${JB.t('hrs')} (${JB.t('trip')}) · ${z.lat.toFixed(2)}°N ${z.lon.toFixed(2)}°E${z.ground&&z.ground.length?' · '+z.ground.join(', '):''}</span><br><span class="badge ${z.kind==='safe'?'S':'C'}">${JB.t(z.kind==='safe'?'S':'C')}</span></div></div>`});
  }
  // hazards next 24 h at port entry
  const hz=lite.hazard24,V=B.m.vessels[S.vessel].hazards;
  if(hz){
    const lv=(v,k)=>v==null?'':(v<=V[k].safe?'ok':v<V[k].stop?'mid':'bad');
    const lvVis=v=>v==null?'':(v>=V.visibility_km.safe?'ok':v>V.visibility_km.stop?'mid':'bad');
    r+=`<div class="step" style="margin-top:16px">${JBI('wave')} ${JB.t('h24')}</div><div class="hz">
      <div class="${lv(hz.max_wave_m,'wave_height_m')}">${JBI('wave')}<br>${JB.num(hz.max_wave_m,1)} m<small>${JB.t('wave')}</small></div>
      <div class="${lv(hz.max_wind_ms,'wind_speed_ms')}">${JBI('wind')}<br>${JB.num(hz.max_wind_ms,0)} m/s<small>${JB.t('wind')}</small></div>
      <div class="${lvVis(hz.min_vis_km)}">${JBI('eye')}<br>${hz.min_vis_km==null?'–':JB.num(hz.min_vis_km,0)+' km'}<small>${JB.t('vis')}</small></div>
      <div class="${hz.thunder_24h?'bad':'ok'}">${JBI('bolt')}<br>${hz.thunder_24h?JB.t('yes'):JB.t('no')}<small>${JB.t('thunder')}</small></div></div>`;
  }
  // Seven-day meteorological OUTLOOK ONLY. These are not seven-day PFZ or
  // verified departure-clearance predictions. Empty/missing fields show a dash.
  if(lite.outlook7&&lite.outlook7.length){
    const bn=JB.lang==='bn';
    r+=`<div class="step" style="margin-top:16px">${JBI('wave')} ${bn?'আগামী ৭ দিনের সাগরের আবহাওয়া':'Next 7 days: marine weather'}</div>`;
    r+=`<p class="small muted">${bn?'শুধু আবহাওয়ার পূর্বাভাস। মাছের অবস্থান, যাত্রার অনুমতি বা নিরাপত্তার নিশ্চয়তা নয়।':'Weather outlook only — not a fishing-location prediction or travel clearance.'}</p>`;
    r+=`<div class="week-grid">`;
    for(const v of lite.outlook7){
      const hours=v.hours_covered<24?` · ${JB.num(v.hours_covered)}h`:'';
      const th=v.thunder_predicted==null?'–':v.thunder_predicted?(bn?'হ্যাঁ':'Yes'):(bn?'না':'No');
      r+=`<div class="week-day"><b>${bn?'দিন':'Day'} ${JB.num(v.day)}${hours}</b>`+
        `<span>🌊 ${JB.num(v.max_wave_m,1)} m</span>`+
        `<span>💨 ${JB.num(v.max_wind_ms,1)} m/s</span>`+
        `<span>👁 ${JB.num(v.min_visibility_km,1)} km</span>`+
        `<span>⚡ ${th}</span></div>`;
    }
    r+=`</div>`;
  }
  // actions
  r+=`<div class="act"><button class="pri" id="bListen">${JBI('speaker')} ${JB.t('listen')}</button><button id="bShare">${JBI('share')} ${JB.t('share')}</button><button id="bRefresh">${JBI('refresh')} ${JB.t('refresh')}</button></div>`;
  // footer info
  const age=B.age(),bmdTxt=B.m.bmd_verified?JB.t('bmd_ok'):JB.t('bmd_unver');
  r+=`<p class="small" style="margin-top:14px">${JBI('shield')} <b>${JB.t('official')}</b></p>
      <p class="small muted">${JBI('clock')} ${JB.t('data_age')}: ${JB.fmtDT(new Date(B.m.analysis_time))} (${JB.fmtAge(age)} ${JB.t('ago')})<br>${bmdTxt}</p>
      <p class="disc">${JB.t('disc')}</p>`;
  $('#res').innerHTML=r;JB.warmCache(B);
  // speak / share text
  const zt=(!downgraded&&d.zones.length)?d.zones.slice(0,2).map((z,i)=>{const b=JB.bearing(p.lat,p.lon,z.lat,z.lon);return JB.lang==='bn'?`এলাকা ${i+1}: ${JB.dirWord(b)} দিকে ${JB.num(z.dist_nm)} নটিক্যাল মাইল।`:`Zone ${i+1}: ${JB.dirWord(b)}, ${z.dist_nm} NM.`}).join(' '):'';
  const head=downgraded?JB.t('stale_banner'):(JB.lang==='bn'?d.headline_bn:d.headline_en);
  const text=`${JB.t('app')} ${pname(S.port)}: ${JB.t(E)}. ${head} ${zt} ${JB.t('official')}`;
  $('#bListen').onclick=()=>{if(!JB.speak(text))alert(JB.lang==='bn'?'এই ফোনে কথা শোনার সুবিধা নেই।':'Speech is not available on this device.')};
  $('#bShare').onclick=async()=>{try{if(navigator.share){await navigator.share({text})}else{await navigator.clipboard.writeText(text);alert(JB.t('copied'))}}catch(e){}};
  $('#bRefresh').onclick=()=>load();
}
async function load(){
  try{
    B=await JB.pickBase();
    reasons=await B.get('reasons.json');
    offline=!navigator.onLine;fresh=B.freshness();
    await render();
  }catch(e){
    console.error(e);
    chrome();main.innerHTML=`<div class="bn bad" style="border-radius:12px">${JBI('warn')}<span>${JB.t(B?'err_load':'no_bundle')}</span></div><div class="act"><button class="pri" onclick="location.reload()">${JBI('refresh')} ${JB.t('refresh')}</button></div>`;
  }
}
$('#langbtn').onclick=()=>{JB.setLang(JB.lang==='bn'?'en':'bn');B?render():chrome()};
JB.setLang(JB.lang);
if(window.speechSynthesis)speechSynthesis.getVoices();
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
window.addEventListener('online',()=>load());window.addEventListener('offline',()=>{offline=true;B&&banners()});
setInterval(()=>{if(B){const f=B.freshness();if(f!==fresh){fresh=f;render()}}},60000);
await load();
})();
