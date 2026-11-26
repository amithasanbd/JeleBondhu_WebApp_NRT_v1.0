/* JeleBondhu dashboard: Triple-Filter advisory, transparent drivers, rules, evidence, provenance. */
(async function(){
const $=s=>document.querySelector(s);
const COL={S:'#1b9a57',C:'#e8a200',N:'#d2352d',U:'#6a7786',R:'rgba(160,176,190,.55)'};
const GL={S:'✓',C:'!',N:'✕',U:'?'};
const S={port:JB.store.get('jb_port')||'cox_bazar',vessel:JB.store.get('jb_vessel')||'mechanized',dep:0,layer:'class',tab:'advice',sel:-1};
let B,M,RS,cells,prov,warn,hazard,adv,fresh='fresh',map,stn,geo={},valid=null,species=null,climate=null;
const TABS=[['advice','tab_advice'],['why','tab_why'],['haz','tab_haz'],['rules','tab_rules'],['evi','tab_evi'],['data','tab_data']];
const LAYERS=[['class','L_class'],['pai','L_pai'],['s','L_s'],['u','L_u'],['sst','L_sst'],['chl','L_chl'],['sss','L_sss'],['cur','L_cur'],['depth','L_depth'],['thesis','L_thesis']];
const RAMP=['#26397b','#1f7fa8','#22b0a0','#9bd85f','#f4e04d'];
function ramp(t){t=Math.max(0,Math.min(1,t));const x=t*(RAMP.length-1),i=Math.min(RAMP.length-2,Math.floor(x)),f=x-i;const a=RAMP[i],b=RAMP[i+1];const p=h=>[1,3,5].map(k=>parseInt(h.substr(k,2),16));const A=p(a),Bc=p(b);return 'rgb('+A.map((v,k)=>Math.round(v+(Bc[k]-v)*f)).join(',')+')'}
const pname=id=>{const p=M.ports[id];return JB.lang==='bn'?p.name_bn:p.name_en};
const vname=id=>M.vessels[id]['label_'+JB.lang];
const dep=()=>adv.departs[Math.min(S.dep,adv.departs.length-1)];
const eff=l=>JB.effClass(l,fresh);

/* ------------------------------------------------------------- banners */
function banners(){
  const o=[];
  if(M.mode!=='live')o.push(`<div class="bn demo">${JBI('warn')}<span>${JB.t('demo_banner')}</span></div>`);
  if(!navigator.onLine||B.fromCache)o.push(`<div class="bn info">${JBI('info')}<span>${JB.t('offline')}</span></div>`);
  if(fresh==='aging')o.push(`<div class="bn warn">${JBI('clock')}<span>${JB.t('aging_banner')}</span></div>`);
  if(fresh==='stale')o.push(`<div class="bn bad">${JBI('clock')}<span>${JB.t('stale_banner')}</span></div>`);
  if(fresh==='expired')o.push(`<div class="bn bad">${JBI('clock')}<span>${JB.t('expired_banner')}</span></div>`);
  if(B.verify==='failed')o.push(`<div class="bn bad">${JBI('shield')}<span>${JB.t('integrity_bad')}: ${B.errors.join(', ')}</span></div>`);
  if(B.verify==='unavailable')o.push(`<div class="bn info">${JBI('shield')}<span>${JB.t('integrity_na')}</span></div>`);
  if(cells&&cells.mode!=='frozen')o.push(`<div class="bn warn">${JBI('info')}<span>${JB.t('exp_banner')}</span></div>`);
  if(!M.bmd_verified)o.push(`<div class="bn warn">${JBI('shield')}<span>${JB.t('bmd_unver')}</span></div>`);
  $('#banners').innerHTML=o.join('');
}
function chrome(){
  document.documentElement.lang=JB.lang;
  $('#appname').textContent=JB.t('app');$('#tag').textContent=JB.t('tag');$('#langbtn').textContent=JB.t('lang');$('#litelink').innerHTML=JBI('fish')+' '+JB.t('lite');
  $('#lb_port').textContent=JB.t('port');$('#lb_vessel').textContent=JB.t('vessel');$('#lb_dep').textContent=JB.t('depart');$('#lb_layer').textContent=JB.t('layer');
  $('#selPort').innerHTML=Object.keys(M.ports).map(id=>`<option value="${id}" ${id===S.port?'selected':''}>${pname(id)}</option>`).join('');
  $('#selVessel').innerHTML=Object.keys(M.vessels).map(id=>`<option value="${id}" ${id===S.vessel?'selected':''}>${vname(id)}</option>`).join('');
  $('#selLayer').innerHTML=LAYERS.map(([k,t])=>`<option value="${k}" ${k===S.layer?'selected':''}>${JB.t(t)}</option>`).join('');
  $('#tabs').innerHTML=TABS.map(([k,t])=>`<button data-tab="${k}" class="${S.tab===k?'on':''}">${JB.t(t)}</button>`).join('');
  $('#tabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{S.tab=b.dataset.tab;chrome();panel()});
  $('#foot').innerHTML=`<p>${JB.t('disc')}</p><p class="tiny">Copernicus Marine Service (CMEMS) · Open-Meteo (CC BY 4.0) · GEBCO Compilation Group · Bangladesh Meteorological Department (human-verified bulletin) · JeleBondhu M.Sc. thesis (BMU). ${JB.t('app')} ${M.app_release} · ${M.bundle_id}</p>`;
  banners();
}
function fillDeps(){$('#selDep').innerHTML=adv.departs.map((d,i)=>`<option value="${i}" ${i===S.dep?'selected':''}>${d.offset_h===0?JB.t('now'):JB.num(d.offset_h)+' '+JB.t('later')} · ${JB.fmtWhen(JB.parseBDT(d.depart_bdt))}</option>`).join('')}

/* ------------------------------------------------------------- map layers */
function q(a,p){const v=a.filter(x=>isFinite(x)).sort((x,y)=>x-y);return v.length?v[Math.min(v.length-1,Math.floor(p*v.length))]:0}
function updateMap(){
  const d=dep(),n=stn.n,col=new Array(n).fill(null),gl=new Array(n).fill(null);
  const L=S.layer;let vals=null,unit='',scale=1,miss=-1;
  const wet=cells.wet;
  if(L==='class'){
    for(let i=0;i<n;i++){const l=d.c[i];if(l==='L')continue;const e=eff(l);col[i]=COL[e]||COL.R;gl[i]=GL[e]||null;if(l==='R'){col[i]=COL.R;gl[i]=null}}
  }else{
    const src={pai:[cells.pai,.01,-1],s:[d.s,.01,-1],u:[d.u,.01,-1],sst:[cells.sst,.1,-1],chl:[cells.chl,.01,-1],sss:[cells.sss,.1,-1],cur:[cells.cur,.01,-1],depth:[cells.depth,1,0],thesis:[cells.thesis_pai||[],.001,-1]}[L];
    vals=new Array(n);for(let i=0;i<n;i++){const v=src[0][i];vals[i]=(wet[i]&&v!==undefined&&v!==src[2]&&d.c[i]!=='L')?v*src[1]:NaN}
    let lo=q(vals,.02),hi=q(vals,.98);if(L==='s'||L==='u'||L==='pai'||L==='thesis'){lo=Math.min(lo,0);hi=Math.max(hi,1)}if(hi<=lo)hi=lo+1;
    for(let i=0;i<n;i++)if(isFinite(vals[i]))col[i]=ramp((vals[i]-lo)/(hi-lo));
    S._rng=[lo,hi];
  }
  map.setCells(col,gl);
  // legend
  let lg='';
  if(L==='class'){const cnt={};for(const ch of d.c)cnt[ch]=(cnt[ch]||0)+1;
    lg=['S','C','N','U','R'].map(k=>`<div class="li"><span class="sw" style="background:${COL[k]}"></span>${GL[k]||''} ${JB.t(k)} <b>${JB.num(cnt[k]||0)}</b></div>`).join('')}
  else{lg=`<b>${JB.t('L_'+L)}</b><div class="grad" style="background:linear-gradient(90deg,${RAMP.join(',')})"></div><div class="row" style="justify-content:space-between"><span>${JB.num(S._rng[0],2)}</span><span>${JB.num(S._rng[1],2)}</span></div>`}
  $('#legend').innerHTML=lg;
  map.setZones(d.zones&&eff(d.overall)!=='U'&&['S','C'].includes(eff(d.overall))?d.zones.filter(z=>z.kind==='safe'||z.kind==='caution'):[]);
  const p=M.ports[S.port];map.setPort({lat:p.lat,lon:p.lon,entry:p.entry,label:pname(S.port)});
}

/* ------------------------------------------------------------- panels */
function reasonRows(bits,withN){return bits.map(b=>{const c=RS.codes[b.bit??b];const extra=b.n?` <span class="muted small">(${JB.num(Math.round((b.share||0)*100))}%)</span>`:'';return `<li><span class="sev ${c.severity}"></span><span><b class="tiny muted">${c.filter}</b> ${c[JB.lang]}${extra}</span></li>`}).join('')}
const sevOK=(cl,c)=>c.code!=='JATKA_RISK'&&(cl==='N'?c.severity==='bad':cl==='U'?c.severity==='unknown':cl==='C'?(c.severity==='warn'||c.severity==='bad'):false);
function topWhy(d){
  const sel=d.overall;const cnt={};let tot=0;
  for(let i=0;i<d.c.length;i++)if(d.c[i]===sel){tot++;const m=d.rb[i];for(let b=0;b<31;b++)if((m>>>b)&1&&sevOK(sel,RS.codes[b]))cnt[b]=(cnt[b]||0)+1}
  return Object.entries(cnt).map(([b,n])=>({bit:+b,n,share:n/Math.max(1,tot)})).sort((a,b)=>b.n-a.n).slice(0,5);
}
function panel(){const f={advice:pAdvice,why:pWhy,haz:pHaz,rules:pRules,evi:pEvi,data:pData}[S.tab];$('#panel').innerHTML=f();({advice:aAdvice,why:aWhy,haz:aHaz,rules:aRules,evi:aEvi,data:aData}[S.tab]||(()=>{}))()}

function pAdvice(){
  const d=dep(),L=d.overall,E=eff(L),down=E!==L,p=M.ports[S.port];
  const head=down?JB.t(fresh==='expired'?'expired_banner':'stale_banner'):JB.t('head_'+L);
  let h=`<div class="verdict ${E}"><div class="glyph">${JBI(JB.GLYPH[E])}</div><div><div class="big">${pname(S.port)} · ${vname(S.vessel)}</div><div class="big" style="font-size:1.5rem">${E==='S'?JB.t('S_long'):JB.t(E)}</div><div class="small">${head}</div></div></div>`;
  const tot=d.c.length-(d.counts.L||0)-(d.counts.R||0);
  h+=`<h3>${JB.t('cnt')}</h3><div class="row" style="gap:4px">`+['S','C','N','U'].map(k=>`<span class="badge ${k}">${JB.t(k)} ${JB.num(d.counts[k])}</span>`).join('')+`<span class="badge R">${JB.t('R')} ${JB.num(d.counts.R)}</span></div>`;
  h+=`<div class="bar" style="margin-top:6px;display:flex">`+['S','C','N','U'].map(k=>`<i style="width:${100*d.counts[k]/Math.max(1,tot)}%;background:${COL[k]}"></i>`).join('')+`</div>`;
  if(!down&&L!=='S'){const w=topWhy(d);if(w.length)h+=`<h3>${JB.t('top_reasons')}</h3><ul class="reasons">${reasonRows(w)}</ul>`}
  if(!M.bmd_verified&&d.bmd_pending>0)h+=`<div class="bn warn" style="border-radius:10px">${JBI('shield')}<span>${JB.t('bmd_unver')} (${JB.num(d.bmd_pending)} ${JB.lang==='bn'?'স্টেশন আটকানো':'stations held back'})</span></div>`;
  if(d.jatka_active)h+=`<div class="bn warn" style="border-radius:10px">${JBI('fish')}<span>${JB.t('jatka')}</span></div>`;
  const zs=(!down&&['S','C'].includes(E))?d.zones.filter(z=>z.kind==='safe'||z.kind==='caution'):[];
  const pend=(!down&&d.zones_pending)?d.zones_pending:[];
  h+=`<h3>${JBI('fish')} ${JB.t('zones')}</h3>`;
  if(!zs.length)h+=`<p class="muted">${JB.t('nozones')}</p>`;
  zs.forEach((z,i)=>{const b=JB.bearing(p.lat,p.lon,z.lat,z.lon);h+=zoneBtn(z,i,b)});
  if(pend.length)h+=`<details class="note"><summary>${JB.lang==='bn'?'যাচাই-সাপেক্ষে এলাকা (পরামর্শ নয়, শুধু পর্যালোচকদের জন্য)':'Held-back zones (NOT advice, for reviewers only)'}</summary>`+pend.map((z,i)=>zoneBtn(z,i,JB.bearing(p.lat,p.lon,z.lat,z.lon),true)).join('')+`</details>`;
  h+=`<p class="small muted">${JBI('clock')} ${JB.t('data_age')}: ${JB.fmtDT(new Date(M.analysis_time))} (${JB.fmtAge(B.age())} ${JB.t('ago')})<br>${JB.t('rule_order')}</p>`;
  return h;
}
function zoneBtn(z,i,b,held){return `<button class="zone" data-cell="${z.i}"><span class="n" ${held?'style="background:#6a7786"':''}>${held?'·':i+1}</span><span class="arrow" style="transform:rotate(${b.toFixed(0)}deg)">${JBI('arrow','fill')}</span><span><b>${JB.dirWord(b)}</b> · ${JB.num(z.dist_nm)} ${JB.t('dist')} · ${JB.num(z.trip_h)} ${JB.t('hrs')}<br><span class="small muted">PAI ${JB.num(z.pai)} · S ${JB.num(z.S)} · U ${JB.num(z.U)} · ${JB.num(z.depth_m)} m${z.ground&&z.ground.length?' · '+z.ground.join(', '):''}</span></span></button>`}
function aAdvice(){document.querySelectorAll('[data-cell]').forEach(b=>b.onclick=()=>pick(+b.dataset.cell,true))}

function bar(v,max,lab){const p=Math.max(0,Math.min(1,v/(max||1)))*100;return `<div class="row" style="flex-wrap:nowrap;gap:8px"><div class="bar" style="flex:1"><i style="width:${p}%"></i></div><b style="min-width:3.2em;text-align:right">${lab}</b></div>`}
const COMP_NAMES={sst_thermal:'SST thermal suitability',sst_front:'SST front',convergence:'Convergence',current_speed:'Current speed',sss_band:'Salinity band',depth_habitat:'Depth habitat',chl:'Chlorophyll',npp:'Primary production',no3:'Nitrate',po4:'Phosphate',chl_front:'Chl front',mld_shallow:'Shallow mixed layer',sss_hydro:'Salinity (hydrography)',mld_hydro:'MLD (hydrography)',zos_anom:'Sea-level anomaly',sst_anom:'SST anomaly',o2_stress:'Low-oxygen stress',ph_stress:'Acidity stress',thermal_stress:'Thermal stress',strat_stress:'Stratification stress'};
function pWhy(){
  const d=dep();
  if(S.sel<0){
    const w=prov.filter1.weights;
    return `<p class="muted">${JBI('map')} ${JB.t('pickcell')}</p><h3>${JB.t('f1')}</h3><p class="small">${cells.label_en}.<br><i>${cells.meaning}</i></p>
    <p class="small">PAI = ${Object.entries(w).map(([k,v])=>`${v.toFixed(3)}·${k==='VI'?'(1−VI)':k}`).join(' + ')}</p><p class="tiny muted">${prov.filter1.status}</p>
    <h3>${JB.t('f2')}</h3><p class="small">s<sub>k</sub> = clip((h<sub>stop</sub> − h)/(h<sub>stop</sub> − h<sub>safe</sub>), 0, 1) · s<sub>phys</sub> = min<sub>k</sub> s<sub>k</sub> · R<sub>T</sub> = d<sub>out</sub>/v + T<sub>fish</sub> + d<sub>ret</sub>/v · M = (W − R<sub>T</sub>)/R<sub>T</sub> · S = G<sub>BMD</sub> · min(s<sub>phys</sub>, clip(M/0.25, 0, 1))</p>
    <table><tr><th>${JB.t('vessel')}</th><th>${JB.t('wave')} m</th><th>${JB.t('wind')} m/s</th><th>${JB.t('gust')} m/s</th><th>${JB.t('vis')} km</th><th>kn · h · NM</th></tr>${Object.entries(M.vessels).map(([k,v])=>`<tr><td>${vname(k)}</td><td>${v.hazards.wave_height_m.safe}/${v.hazards.wave_height_m.stop}</td><td>${v.hazards.wind_speed_ms.safe}/${v.hazards.wind_speed_ms.stop}</td><td>${v.hazards.wind_gust_ms.safe}/${v.hazards.wind_gust_ms.stop}</td><td>${v.hazards.visibility_km.safe}/${v.hazards.visibility_km.stop}</td><td>${v.speed_kn} · ${v.fishing_hours} · ${v.max_range_nm}</td></tr>`).join('')}</table><p class="tiny muted">safe / stop — ${prov.filter2.vessel_status}</p>
    <h3>${JB.t('f3')}</h3><p class="small">U = G<sub>MPA</sub> · G<sub>season</sub> · G<sub>zone</sub> · (u<sub>buf</sub> · u<sub>crowd</sub> · u<sub>life</sub>)<sup>1/3</sup>; u<sub>crowd</sub>, u<sub>life</sub>: ${JB.t('notassessed')}.</p>
    <p class="small"><b>${JB.t('rule_order')}</b></p>`;
  }
  const i=S.sel,c=d.c[i],e=eff(c),bits=JB.maskBits(d.rb[i]);
  const f=k=>bits.filter(b=>RS.codes[b].filter===k);
  const grp=(k,t)=>{const r=f(k);return r.length?`<h3>${t}</h3><ul class="reasons">${reasonRows(r)}</ul>`:''};
  const drv=(arr,sg)=>[0,1,2].map(k=>arr[i*(sg>0?3:2)+k]).filter(v=>v>=0).map(v=>COMP_NAMES[cells.drv_comp[v]]||cells.drv_comp[v]);
  const pos=drv(cells.drv_pos,1),neg=drv(cells.drv_neg,-1).slice(0,2);
  const mg=d.m[i];
  return `<div class="verdict ${e}"><div class="glyph">${JBI(JB.GLYPH[e]||'q')}</div><div><div class="big">${JB.t(e)}</div><div class="small">${JB.t('cell')} #${stn.id[i]} · ${stn.lat[i].toFixed(3)}°N ${stn.lon[i].toFixed(3)}°E · ${JB.num(cells.depth[i])} m</div>${d.pre[i]!==d.c[i]?`<div class="tiny">pre-BMD class: ${d.pre[i]}</div>`:''}</div></div>
  ${grp('DATA','Data')}${grp('F3',JB.t('f3'))}${grp('F2',JB.t('f2'))}${grp('F1',JB.t('f1'))}
  <h3>${JB.t('f1')}</h3>${cells.pai[i]>=0?bar(cells.pai[i],100,'PAI '+JB.num(cells.pai[i]/100,2))+`<div class="tiny muted">${cells.mode==='frozen'?'frozen thesis':'experimental'} · class ${['low','medium','high'][cells.pcls[i]]||'?'} (p60 ${cells.p60.toFixed(3)}, p80 ${cells.p80.toFixed(3)})</div>`:'<p class="muted small">PAI —</p>'}
  <table><tr><th>PFZI</th><th>PPI</th><th>OHI</th><th>VI</th></tr><tr>${['pfzi','ppi','ohi','vi'].map(k=>`<td>${cells[k][i]>=0?JB.num(cells[k][i]/100,2):'–'}</td>`).join('')}</tr></table>
  <p class="small">SST ${cells.sst[i]>=0?JB.num(cells.sst[i]/10,1)+'°C':'–'} · Chl ${cells.chl[i]>=0?JB.num(cells.chl[i]/100,2):'–'} · SSS ${cells.sss[i]>=0?JB.num(cells.sss[i]/10,1):'–'} · cur ${cells.cur[i]>=0?JB.num(cells.cur[i]/100,2)+' m/s':'–'} · O₂ ${cells.o2[i]>=0?JB.num(cells.o2[i]):'–'} · pH ${cells.ph[i]>=0?JB.num(cells.ph[i]/100,2):'–'}</p>
  ${pos.length?`<p class="small"><b>↑</b> ${pos.join(', ')}</p>`:''}${neg.length?`<p class="small"><b>↓</b> ${neg.join(', ')}</p>`:''}
  ${cells.thesis_pai?`<p class="tiny muted">Thesis PAI 2025 (${cells.thesis_season}): ${cells.thesis_pai[i]>=0?JB.num(cells.thesis_pai[i]/1000,2):'–'}</p>`:''}
  <h3>${JB.t('f2')}</h3>${bar(d.s[i],100,'S '+JB.num(d.s[i]/100,2))}
  <p class="small">${JB.t('dist')}: ${JB.num(d.d[i])} · R<sub>T</sub> ${JB.num(d.rt[i])} ${JB.t('hrs')} · M ${mg>-100?(mg>=99?'>99':JB.num(mg,1))+' h':'–'}</p>
  <h3>${JB.t('f3')}</h3>${bar(d.u[i],100,'U '+JB.num(d.u[i]/100,2))}
  <p class="small">MPA: ${cells.mpa[i]>=0?warn.mpas[cells.mpa[i]].name+' ('+warn.mpas[cells.mpa[i]].legal_status+')':'–'} · ${JB.lang==='bn'?'সুরক্ষিত এলাকা থেকে দূরত্ব':'distance to MPA'} ${cells.dmpa[i]>=999?'>999':JB.num(cells.dmpa[i])} km · IFA ${cells.ifa[i]?JB.t('yes'):JB.t('no')}</p>
  <p class="small">${JB.lang==='bn'?'আস্থা':'Confidence'} ${JB.num(d.cf[i]/100,2)}</p>
  <button class="chip" id="bTrace">${JBI('dl')} ${JB.t('dl_trace')}</button>`;
}
function aWhy(){const b=$('#bTrace');if(b)b.onclick=trace}
function trace(){
  const i=S.sel,d=dep();if(i<0)return;
  const o={bundle_id:M.bundle_id,mode:M.mode,generated_at:M.generated_at,analysis_time:M.analysis_time,config_hash:M.config_hash,rules_version:M.rules_version,spatial_version:M.spatial_version,
    port:S.port,vessel:S.vessel,depart:{offset_h:d.offset_h,bdt:d.depart_bdt},station:{index:i,id:stn.id[i],lat:stn.lat[i],lon:stn.lon[i],depth_m:cells.depth[i]},
    class:d.c[i],class_before_bmd_gate:d.pre[i],reason_bits:JB.maskBits(d.rb[i]).map(b=>({bit:b,code:RS.codes[b].code,en:RS.codes[b].en})),
    filter1:{mode:cells.mode,PAI:cells.pai[i]/100,PFZI:cells.pfzi[i]/100,PPI:cells.ppi[i]/100,OHI:cells.ohi[i]/100,VI:cells.vi[i]/100,class:cells.pcls[i]},
    filter2:{S:d.s[i]/100,round_trip_h:d.rt[i],distance_nm:d.d[i],margin_h:d.m[i]>-100?d.m[i]:null},filter3:{U:d.u[i]/100,mpa_state:cells.mpa_state[i],dist_mpa_km:cells.dmpa[i],in_ifa:!!cells.ifa[i]},
    confidence:d.cf[i]/100,bmd_verified:M.bmd_verified,disclaimer:prov.disclaimer_en};
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(o,null,2)],{type:'application/json'}));a.download=`jelebondhu_trace_${stn.id[i]}_${S.port}_${S.vessel}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}

/* ---- weather chart */
function nearestRep(lat,lon){let b=0,bd=1e9;hazard.pts.forEach((p,k)=>{const d=JB.hav(lat,lon,p.lat,p.lon);if(d<bd){bd=d;b=k}});return b}
function pHaz(){
  if(!hazard)return `<p class="muted">${JB.t('err_load')}</p>`;
  const p=M.ports[S.port],k=nearestRep(S.sel>=0?stn.lat[S.sel]:p.entry.lat,S.sel>=0?stn.lon[S.sel]:p.entry.lon);S._rep=k;
  return `<p class="small"><b>${JB.t('hz_pt')}</b>: ${hazard.pts[k].lat.toFixed(2)}°N ${hazard.pts[k].lon.toFixed(2)}°E (${S.sel>=0?JB.t('cell')+' #'+stn.id[S.sel]:pname(S.port)})</p>
  <h3>${JBI('wave')} ${JB.t('wave')} (m)</h3><canvas class="chart" id="c1"></canvas><h3>${JBI('wind')} ${JB.t('wind')} / ${JB.t('gust')} (m/s)</h3><canvas class="chart" id="c2"></canvas><h3>${JBI('eye')} ${JB.t('vis')} (km) · ${JBI('bolt')} ${JB.t('thunder')}</h3><canvas class="chart" id="c3"></canvas><p class="tiny muted">${JB.t('hz_note')}</p>`;
}
function aHaz(){
  if(!hazard)return;const k=S._rep,V=M.vessels[S.vessel].hazards,H=hazard.sel_hours;
  const t0=Date.parse(hazard.t0_utc),get=a=>a[k].map(v=>v<0?NaN:v/10);
  const d=dep(),marks=[{h:d.offset_h,c:'#1f6feb'}];if(S.sel>=0&&d.rt[S.sel]>0)marks.push({h:d.offset_h+d.rt[S.sel],c:'#1f6feb'});
  const th=hazard.thunder[k].map(v=>v>0);
  draw($('#c1'),H,t0,[{d:get(hazard.wave_m10),c:'#0b6fa8'}],{safe:V.wave_height_m.safe,stop:V.wave_height_m.stop},marks);
  draw($('#c2'),H,t0,[{d:get(hazard.wind_ms10),c:'#0b6fa8'},{d:get(hazard.gust_ms10),c:'#7a4bd1'}],{safe:V.wind_speed_ms.safe,stop:V.wind_speed_ms.stop,safe2:V.wind_gust_ms.safe,stop2:V.wind_gust_ms.stop},marks);
  draw($('#c3'),H,t0,[{d:get(hazard.vis_km10),c:'#0b6fa8'}],{safe:V.visibility_km.safe,stop:V.visibility_km.stop,low:true},marks,th);
}
function draw(cv,H,t0,series,thr,marks,thunder){
  if(!cv)return;const dpr=Math.max(1,devicePixelRatio||1),w=cv.clientWidth,h=cv.clientHeight;cv.width=w*dpr;cv.height=h*dpr;const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);
  const L=34,R=6,T=6,Bt=18,xs=v=>L+(v/H[H.length-1])*(w-L-R);
  let ymax=Math.max(...series.flatMap(s=>s.d.filter(isFinite)),thr.stop*(thr.low?1.2:1.1),thr.stop2||0,1)*1.05;
  const ys=v=>h-Bt-(v/ymax)*(h-T-Bt);
  c.fillStyle='#f8fbfc';c.fillRect(0,0,w,h);c.font='10px system-ui';c.fillStyle='#5b6c7d';c.strokeStyle='#e0e8ee';
  for(let k=0;k<=4;k++){const v=ymax*k/4,y=ys(v);c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.fillText(v.toFixed(v<10?1:0),2,y+3)}
  // day boundaries (Dhaka midnight)
  for(let hh=0;hh<=H[H.length-1];hh++){const t=new Date(t0+hh*36e5),a=JB.dhaka(t);if(a.h===0&&a.mi===0){const x=xs(hh);c.strokeStyle='#c8d5de';c.beginPath();c.moveTo(x,T);c.lineTo(x,h-Bt);c.stroke();c.fillStyle='#5b6c7d';c.fillText(a.d+'/'+a.m,x+2,h-4)}}
  const line=(y,col,dash)=>{c.setLineDash(dash||[]);c.strokeStyle=col;c.lineWidth=1.3;c.beginPath();c.moveTo(L,ys(y));c.lineTo(w-R,ys(y));c.stroke();c.setLineDash([])};
  line(thr.safe,'#e8a200',[5,4]);line(thr.stop,'#d2352d',[5,4]);if(thr.safe2){line(thr.safe2,'rgba(232,162,0,.5)',[2,3]);line(thr.stop2,'rgba(210,53,45,.5)',[2,3])}
  (marks||[]).forEach(m=>{const x=xs(m.h);c.strokeStyle=m.c;c.lineWidth=2;c.beginPath();c.moveTo(x,T);c.lineTo(x,h-Bt);c.stroke()});
  series.forEach(s=>{c.strokeStyle=s.c;c.lineWidth=2;c.beginPath();let on=false;s.d.forEach((v,j)=>{if(!isFinite(v)){on=false;return}const x=xs(H[j]),y=ys(v);on?c.lineTo(x,y):c.moveTo(x,y);on=true});c.stroke()});
  if(thunder)thunder.forEach((v,j)=>{if(v){c.fillStyle='#d2352d';c.fillRect(xs(H[j])-1.5,h-Bt-8,3,8)}});
}

/* ---- rules */
const dayN=s=>Date.UTC(+s.slice(0,4),+s.slice(5,7)-1,+s.slice(8,10))/864e5;
function pRules(){
  const W=warn.rules,n=JB.dhaka(new Date()),today=Date.UTC(n.y,n.m-1,n.d)/864e5;
  const s0=Date.UTC(n.y,n.m-1,1)/864e5,s1=Date.UTC(n.y+1,n.m,1)/864e5,span=s1-s0,pos=d=>(d-s0)/span*100;
  const lanes=[];
  for(const [id,rg] of Object.entries(W.regimes)){
    const segs=[];
    for(const r of W.rules.filter(r=>r.regime===id&&r.approval_status==='approved')){const a=dayN(r.start_date),b=dayN(r.end_date)+1;if(b>s0&&a<s1)segs.push({a:Math.max(a,s0),b:Math.min(b,s1),c:rg.kind==='species_conservation'?'#e8a200':'#d2352d',t:`${r.start_date} → ${r.end_date}`})}
    if(rg.kind==='national_closure'){for(let y=n.y-1;y<=n.y+2;y++){if((rg.approved_years||[]).includes(y))continue;const a=dayN(`${y}-${rg.indicative_window.start}`),b=dayN(`${y}-${rg.indicative_window.end}`)+1;if(b>s0&&a<s1)segs.push({a:Math.max(a,s0),b:Math.min(b,s1),c:'#6a7786',t:JB.t('r_unconf'),dash:1})}}
    lanes.push({label:rg['label_'+JB.lang]||rg.label_en,segs});
  }
  const mons=[];for(let k=0;k<13;k++){const d=new Date(Date.UTC(n.y,n.m-1+k,1));mons.push({x:pos(d.getTime()/864e5),t:d.toLocaleString(JB.lang==='bn'?'bn-BD':'en-GB',{month:'short',timeZone:'UTC'})})}
  let h=`<p class="small">${JB.t('r_ver')}: <b>${W.rules_version}</b> · ${JB.t('r_due')}: <b>${W.review_due}</b> · <span class="badge ${W.status==='ok'?'S':'N'}">${W.status}</span>${W.problems&&W.problems.length?'<br>'+W.problems.join('<br>'):''}</p>`;
  h+=`<div class="tl">`+lanes.map(l=>`<div class="tiny"><b>${l.label}</b></div><div class="lane">`+l.segs.map(s=>`<div class="seg" title="${s.t}" style="left:${pos(s.a)}%;width:${pos(s.b)-pos(s.a)}%;background:${s.dash?'repeating-linear-gradient(45deg,#8a95a1,#8a95a1 4px,#a7b1bb 4px,#a7b1bb 8px)':s.c}">${s.t}</div>`).join('')+`</div>`).join('')
    +`<div class="now" style="left:${pos(today)}%" title="${JB.t('r_today')}"></div>`+mons.map(m=>`<span class="mon" style="left:${m.x}%">${m.t}</span>`).join('')+`</div>
  <p class="tiny muted">${JB.lang==='bn'?'ধূসর = এই বছরের সরকারি তারিখ এখনো নিশ্চিত নয়; ওই সময় পরামর্শ বন্ধ থাকে। নীল রেখা = আজ।':'Grey = this year\'s official dates not yet confirmed: advice is withheld in that window. Dark line = today.'}</p>`;
  h+=`<h3>${JB.t('r_closure')}</h3><table><tr><th>ID</th><th>${JB.lang==='bn'?'তারিখ':'Dates (inclusive)'}</th><th>Effect</th><th>Source</th></tr>${W.rules.map(r=>`<tr><td>${r.id}</td><td>${r.start_date} → ${r.end_date}</td><td>${r.effect}${r.applies_when_target?' ('+r.applies_when_target+')':''}</td><td>${r.source_url?`<a href="${r.source_url}" target="_blank" rel="noopener">${r.source_ref}</a>`:r.source_ref}</td></tr>`).join('')}</table>`;
  h+=`<h3>${JB.t('r_vz')}</h3>`+W.vessel_zone_rules.map(v=>`<p class="small"><b>${v.id}</b> · ${v.zone} · ${v.vessel_types.join(', ')} → ${v.effect} · <span class="badge ${v.approval_status==='approved'?'S':'U'}">${v.approval_status}</span><br><span class="muted">${v.note}</span></p>`).join('');
  h+=`<h3>${JB.t('r_mpa')}</h3><table><tr><th>MPA</th><th>Status</th><th>km² rep./calc.</th><th>Stations</th></tr>${warn.mpas.map(m=>`<tr><td>${m.name}</td><td>${m.legal_status}</td><td>${m.reported_km2}/${m.computed_km2}</td><td>${m.stations_inside}</td></tr><tr><td colspan="4" class="tiny muted">${m.note}</td></tr>`).join('')}</table>`;
  h+=`<h3>${JB.t('r_uneval')}</h3><ul class="small">${W.unevaluated.map(u=>`<li><b>${u.id}</b> ${u.label_en}<br><span class="muted">${u.reason_missing}</span></li>`).join('')}</ul>`;
  return h;
}
function aRules(){}

/* ---- evidence */
const CAVEATS=[
 'Observed catch data are CPUE context, not a catch forecast. 26 species rows share one event; validation is grouped by event (GroupKFold on DLC_ID) — never split rows randomly.',
 'Fisheries workbooks show uniform SST/catch values across rows and SST that varies within one event; CPUE is undefined for some records. Treat per-species skill claims as unsupported until the source is re-checked.',
 '67 of the 2,125 thesis stations are on land / too shallow and are excluded from advice.',
 'The SoNG MPA geometry is a bounding rectangle (≈5,645 km² vs 1,738 km² reported): advice inside it stays NO ADVICE until an authoritative polygon is loaded.',
 'Vessel safety thresholds and port sea-entry waypoints are PROVISIONAL and must be reviewed with fishers, BIWTA/BMD and port authorities.',
 'Filter 1 is an experimental reconstruction until the frozen thesis PAI functions are supplied; its output is relative suitability, not a probability of catch.'];
function pEvi(){
  let h='';
  if(valid&&valid.sections){h+=`<p class="tiny muted">${valid.generated_at||''} · ${valid.method||''}</p>`+valid.sections.map(s=>`<h3>${s.title}</h3>${s.rows?`<table>${s.rows.map(r=>`<tr><td>${r[0]}</td><td><b>${r[1]}</b></td></tr>`).join('')}</table>`:''}${(s.notes||[]).map(n=>`<p class="small muted">${n}</p>`).join('')}`).join('')}
  else h+=`<p class="muted">${JB.t('evi_none')}</p>`;
  if(species){h+=`<h3>${JB.lang==='bn'?'পর্যবেক্ষিত CPUE (প্রসঙ্গ)':'Observed CPUE (context only)'}</h3><p class="tiny muted">${species.note}</p><table><tr><th>Species</th><th>events</th><th>mean CPUE</th></tr>${species.species.slice(0,8).map(s=>`<tr><td><i>${s.scientific}</i></td><td>${s.n_events}</td><td>${s.mean_cpue}</td></tr>`).join('')}</table>`}
  if(climate){const o=climate.oni_last,i=climate.iod_last;h+=`<p class="small">ONI ${o.season} ${o.year}: <b>${o.value}</b> (${o.phase}) · IOD ${i.year}-${String(i.month).padStart(2,'0')}: <b>${i.value}</b> (${i.phase}) <span class="muted">— context only, not used in scores</span></p>`}
  h+=`<h3>${JB.t('caveats')}</h3><ul class="small">${CAVEATS.map(c=>`<li>${c}</li>`).join('')}</ul>`;
  return h;
}
function aEvi(){}

/* ---- data & provenance */
function pData(){
  const P=prov.sources,q=warn.bmd;
  const row=(k,v)=>`<dt>${k}</dt><dd>${v}</dd>`;
  const intg={ok:`<span class="badge S">SHA-256 ✓</span>`,failed:`<span class="badge N">FAILED</span>`,unavailable:`<span class="badge U">n/a (not HTTPS)</span>`}[B.verify];
  return `<dl class="kv">${row('Bundle',M.bundle_id)}${row('Mode',`<span class="badge ${M.mode==='live'?'S':'U'}">${M.mode}</span>`)}${row(JB.t('d_int'),intg)}${row('Analysis time',JB.fmtDT(new Date(M.analysis_time)))}${row('Valid until',JB.fmtDT(new Date(M.valid_until)))}${row('Freshness',fresh)}
  ${row('App / schema',`${M.app_release} / ${M.schema_version}`)}${row('Config hash',M.config_hash)}${row('Rules / spatial',`${M.rules_version} / ${M.spatial_version}`)}${row('Git',prov.git_sha||'–')}</dl>
  <h3>${JB.t('d_prov')}</h3><dl class="kv">
  ${row('CMEMS',P.cmems.used?`valid ${P.cmems.valid_time||'?'}`:'<span class="badge U">not used</span>')}${row('Open-Meteo',P.open_meteo.used?`${P.open_meteo.points} pts · horizon ${P.open_meteo.horizon_h} h · ${P.open_meteo.fetched_at}`:'<span class="badge U">not used</span>')}
  ${row('BMD record',P.bmd.verified?`<span class="badge S">verified</span> ${P.bmd.record_issued||''} (${P.bmd.verified_by||''})`:`<span class="badge N">not verified</span> ${P.bmd.reason}`)}${row('GEBCO','static bathymetry grid (0.0125°)')}</dl>
  <h3>${JB.t('d_conf')}</h3><p class="small">${Object.entries(prov.confidence_median_default_trip||{}).map(([k,v])=>`${k}: <b>${v==null?'–':(+v).toFixed?(+v).toFixed(2):v}</b>`).join(' · ')}</p>
  <p class="tiny muted">C = min(components); C&lt;0.3 withdraws advice; 0.3≤C&lt;0.5 caps at CAUTION. Experimental mode multiplies by a 0.7 calibration factor.</p>
  <h3>${JB.t('d_qc')}</h3><ul class="small">${prov.qc.checks.map(c=>`<li>${c.ok?'✓':'✗'} <b>${c.name}</b> — ${c.detail}</li>`).join('')}</ul>
  <h3>Files</h3><p class="small"><a href="${B.base}manifest.json" target="_blank">manifest.json</a> · <a href="${B.base}provenance.json" target="_blank">provenance.json</a> · <a href="${B.base}warnings.json" target="_blank">warnings.json</a> · <a href="${B.base}sms.json" target="_blank">sms.json</a></p>
  <p class="small muted">${JB.lang==='bn'?prov.disclaimer_bn:prov.disclaimer_en}</p>`;
}
function aData(){}

/* ------------------------------------------------------------- state changes */
async function loadAdv(){
  adv=await B.get(`advisory/${S.vessel}__${S.port}.json`);
  if(S.dep>=adv.departs.length)S.dep=0;fillDeps();
}
function pick(i,focus){
  S.sel=i;map.setSelected(i);
  if(i>=0){if(focus)map.focus(stn.lat[i],stn.lon[i],Math.max(map.view.s,260));if(S.tab!=='haz'&&focus!==true||(focus===true&&S.tab==='advice')){}}
  if(i>=0&&S.tab==='advice'&&focus!==true)S.tab='why';
  if(i>=0&&focus===true&&S.tab==='advice')S.tab='why';
  chrome();panel();
}
function focusPort(){const p=M.ports[S.port];map.fit();map.focus(p.entry.lat-.25,p.lon-.1,map.view.s*1.55)}
async function refresh(){await loadAdv();updateMap();focusPort();chrome();panel()}

/* ------------------------------------------------------------- boot */
async function boot(){
  JB.setLang(JB.lang);
  try{
    B=await JB.pickBase();M=B.m;fresh=B.freshness();
    const stat=u=>fetch(u).then(r=>r.ok?r.json():null).catch(()=>null);
    const [rs,cl,pv,wr,hz,st,eez,ifa,mpa,gr,val,sp,cm]=await Promise.all([B.get('reasons.json'),B.get('cells.json'),B.get('provenance.json'),B.get('warnings.json'),B.get('hazard.json',true).catch(()=>null),
      stat('static/stations.json'),stat('static/eez.geojson'),stat('static/ifa.geojson'),stat('static/bd_mpas.geojson'),stat('static/fishing_grounds.geojson'),stat('static/validation_summary.json'),stat('static/species_context.json'),stat('static/climate_context.json')]);
    RS=rs;cells=cl;prov=pv;warn=wr;hazard=hz;stn=st;geo={eez,ifa,mpas:mpa,grounds:gr};valid=val;species=sp;climate=cm;
    if(!stn)throw new Error('stations.json missing');
    if(stn.n!==M.n_cells)throw new Error('station count mismatch');
    const meta=await stat('assets/img/bathy_bg.json');const img=new Image();img.src='assets/img/bathy_bg.png';await new Promise(r=>{img.onload=img.onerror=r});
    map=new JBMap($('#map'),{bbox:{lon0:88.6,lon1:92.8,lat0:17.6,lat1:23.0},img,meta,geo,stations:stn,
      onSelect:i=>{if(i>=0)pick(i);else{S.sel=-1;map.setSelected(-1);panel()}},
      onHover:(i,x,y)=>{const t=$('#tip');if(i<0){t.style.display='none';return}const d=dep(),e=eff(d.c[i]);t.style.display='block';t.style.left=Math.min(x+12,map.W-200)+'px';t.style.top=(y+12)+'px';t.innerHTML=`#${stn.id[i]} · <b>${JB.t(e)}</b><br>PAI ${cells.pai[i]>=0?JB.num(cells.pai[i]/100,2):'–'} · ${JB.num(cells.depth[i])} m`}});
    $('#zin').onclick=()=>map.zoom(1.5);$('#zout').onclick=()=>map.zoom(1/1.5);$('#zfit').onclick=()=>map.fit();
    await loadAdv();
    $('#selPort').onchange=e=>{S.port=e.target.value;JB.store.set('jb_port',S.port);S.sel=-1;refresh()};
    $('#selVessel').onchange=e=>{S.vessel=e.target.value;JB.store.set('jb_vessel',S.vessel);S.sel=-1;refresh()};
    $('#selDep').onchange=e=>{S.dep=+e.target.value;updateMap();panel()};
    $('#selLayer').onchange=e=>{S.layer=e.target.value;updateMap()};
    $('#langbtn').onclick=async()=>{JB.setLang(JB.lang==='bn'?'en':'bn');fillDeps();chrome();updateMap();panel()};
    updateMap();chrome();panel();JB.warmCache(B);
    focusPort();
    setInterval(()=>{const f=B.freshness();if(f!==fresh){fresh=f;updateMap();chrome();panel()}},60000);
    if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
  }catch(e){console.error(e);$('#panel').innerHTML=`<div class="bn bad" style="border-radius:10px">${JBI('warn')}<span>${JB.t(B?'err_load':'no_bundle')}<br><span class="tiny">${e.message}</span></span></div>`}
}
await boot();
})();
