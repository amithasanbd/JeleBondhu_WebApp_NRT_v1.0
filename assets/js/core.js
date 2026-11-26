/* Shared runtime: language, formatting, verified bundle loader, freshness logic. */
(function(){
const JB=window.JB={ic:window.JBI,T:window.JB_T};
JB.store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
JB.lang=JB.store.get('jb_lang')||'bn';
JB.setLang=function(l){JB.lang=l;JB.store.set('jb_lang',l);document.documentElement.lang=l==='bn'?'bn':'en'};
JB.t=function(k,v){const e=JB.T[k];if(!e)return k;let s=e[JB.lang];if(typeof s==='string'&&v)for(const x in v)s=s.replace('{'+x+'}',v[x]);return s};
const BN='০১২৩৪৫৬৭৮৯';
JB.num=function(x,d){if(x==null||x===''||(typeof x==='number'&&!isFinite(x)))return '–';let s=typeof x==='number'?(d!=null?x.toFixed(d):String(x)):String(x);if(JB.lang==='bn')s=s.replace(/\d/g,c=>BN[+c]);return s};
/* ---------- time (always Asia/Dhaka) ---------- */
const dtf=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dhaka',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
JB.dhaka=function(d){const p={};dtf.formatToParts(d).forEach(x=>p[x.type]=x.value);return{y:+p.year,m:+p.month,d:+p.day,h:+p.hour,mi:+p.minute}};
JB.dayWord=function(h){const w=JB.T.dayw[JB.lang];return h>=4&&h<6?w[1]:h>=6&&h<12?w[2]:h>=12&&h<15?w[3]:h>=15&&h<17?w[4]:h>=17&&h<19?w[5]:w[0]};
JB.fmtWhen=function(d){ // friendly: "Today morning 11:00"
  const a=JB.dhaka(d),n=JB.dhaka(new Date());const k=Date.UTC(a.y,a.m-1,a.d)-Date.UTC(n.y,n.m-1,n.d);const day=k===0?JB.t('today'):k===864e5?JB.t('tomorrow'):`${a.d}/${a.m}`;
  const h12=a.h%12===0?12:a.h%12;const hh=JB.lang==='bn'?JB.num(h12)+':'+JB.num(String(a.mi).padStart(2,'0')):String(a.h).padStart(2,'0')+':'+String(a.mi).padStart(2,'0');
  return JB.lang==='bn'?`${day} ${JB.dayWord(a.h)} ${hh}`:`${day} ${hh}`};
JB.fmtDT=function(d){const a=JB.dhaka(d);const p=x=>String(x).padStart(2,'0');return JB.num(`${a.y}-${p(a.m)}-${p(a.d)} ${p(a.h)}:${p(a.mi)}`)+' BDT'};
JB.fmtAge=function(ms){const h=ms/36e5;if(h<1)return JB.num(Math.max(1,Math.round(ms/6e4)))+(JB.lang==='bn'?' মিনিট':' min');return JB.num(h<10?h.toFixed(1):Math.round(h))+(JB.lang==='bn'?' ঘণ্টা':' h')};
JB.parseBDT=function(s){return new Date(s.replace(' ','T')+':00+06:00')};
/* ---------- geometry ---------- */
JB.bearing=function(la1,lo1,la2,lo2){const r=Math.PI/180,y=Math.sin((lo2-lo1)*r)*Math.cos(la2*r),x=Math.cos(la1*r)*Math.sin(la2*r)-Math.sin(la1*r)*Math.cos(la2*r)*Math.cos((lo2-lo1)*r);return(Math.atan2(y,x)/r+360)%360};
JB.dirWord=function(b){return JB.T.dirs[JB.lang][Math.round(b/45)%8]};
JB.hav=function(a,b,c,d){const r=Math.PI/180,x=Math.sin((c-a)*r/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2;return 12742*Math.asin(Math.sqrt(x))};
/* ---------- verified bundle loader ---------- */
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
JB.Bundle=class{
  constructor(base){this.base=base;this.m=null;this.cache={};this.verify='ok';this.errors=[];this.fromCache=false;this.used=new Set([base+'manifest.json'])}
  async init(){
    const r=await fetch(this.base+'manifest.json',{cache:'no-cache'});
    if(!r.ok)throw new Error('manifest '+r.status);
    this.m=await r.json();
    if(r.headers.get('x-jb-from-cache'))this.fromCache=true;
    if(!(window.crypto&&crypto.subtle))this.verify='unavailable';
    return this.m;
  }
  async get(rel,optional){
    if(this.cache[rel])return this.cache[rel];
    const meta=this.m.files[rel];
    if(!meta){if(optional)return null;throw new Error('not in manifest: '+rel)}
    for(let attempt=0;attempt<2;attempt++){
      const r=await fetch(this.base+rel,{cache:attempt?'reload':'no-cache'});
      if(!r.ok)throw new Error(rel+' '+r.status);
      const buf=await r.arrayBuffer();
      if(this.verify!=='unavailable'){
        const h=hex(await crypto.subtle.digest('SHA-256',buf));
        if(h!==meta.sha256){if(attempt)break;continue}
      }
      const obj=JSON.parse(new TextDecoder('utf-8').decode(buf));
      this.used.add(this.base+rel);
      return this.cache[rel]=obj;
    }
    this.verify='failed';this.errors.push(rel);
    throw new Error('integrity '+rel);
  }
  /* freshness relative to the browser clock */
  freshness(now){now=now||Date.now();const m=this.m;const v=Date.parse(m.valid_until),s=Date.parse(m.stale_after),e=Date.parse(m.expire_after);
    return now<=v?'fresh':now<=s?'aging':now<=e?'stale':'expired'}
  age(now){return(now||Date.now())-Date.parse(this.m.analysis_time)}
};
/* effective class after freshness downgrade */
JB.effClass=function(letter,fresh){
  if(fresh==='expired'&&'SCN'.includes(letter))return 'U';
  if(fresh==='stale'&&'SC'.includes(letter))return 'U';
  return letter};
JB.pickBase=async function(){
  /* Production only ever reads live/. The synthetic demo/ bundle is reachable ONLY with ?demo=1 so that the public
     can never be silently shown fake data. */
  const demo=new URLSearchParams(location.search).get('demo')==='1';
  const b=new JB.Bundle(demo?'demo/':'live/');await b.init();return b;
};
JB.reasonText=function(rs,bit){const c=rs.codes[bit];return c?c[JB.lang]:('#'+bit)};
JB.maskBits=function(m){const o=[];for(let b=0;b<31;b++)if((m>>>b)&1)o.push(b);return o};
JB.CLS='SCNURL';
/* ask the service worker to cache the files just used, so the first visit also works offline */
JB.warmCache=function(B){try{if(!('serviceWorker' in navigator))return;navigator.serviceWorker.ready.then(reg=>{if(reg.active)reg.active.postMessage({type:'warm',urls:[...B.used]})})}catch(e){}};
JB.GLYPH={S:'check',C:'warn',N:'stop',U:'q'};
JB.speak=function(text){
  if(!('speechSynthesis' in window))return false;
  const vs=speechSynthesis.getVoices();const v=vs.find(x=>/^bn/i.test(x.lang));
  const u=new SpeechSynthesisUtterance(text);if(v){u.voice=v;u.lang=v.lang}else u.lang='bn-BD';u.rate=.85;
  speechSynthesis.cancel();speechSynthesis.speak(u);return true};
JB.hasBnVoice=function(){return 'speechSynthesis' in window&&speechSynthesis.getVoices().some(x=>/^bn/i.test(x.lang))};
})();
