/* Offline canvas map: GEBCO bathymetry PNG + vector overlays + station cells. No tile server, no external requests. */
(function(){
const COS=Math.cos(20.3*Math.PI/180);
class JBMap{
  constructor(canvas,opt){
    this.cv=canvas;this.ctx=canvas.getContext('2d');this.opt=opt;this.bbox=opt.bbox;this.img=opt.img;this.meta=opt.meta;
    this.geo=opt.geo||{};this.st=opt.stations;this.colors=null;this.glyphs=null;this.sel=-1;this.zones=[];this.port=null;this.hover=-1;
    this.cellDeg=0.075;this.view={clat:(this.bbox.lat0+this.bbox.lat1)/2,clon:(this.bbox.lon0+this.bbox.lon1)/2,s:100};
    this.ptr=new Map();this.moved=false;this.dpr=Math.max(1,window.devicePixelRatio||1);this.raf=0;
    this._pat=null;this.bind();new ResizeObserver(()=>this.resize()).observe(canvas.parentElement);this.resize();this.fit();
  }
  resize(){const r=this.cv.parentElement.getBoundingClientRect();this.W=Math.max(200,r.width);this.H=Math.max(200,r.height);
    this.cv.width=this.W*this.dpr;this.cv.height=this.H*this.dpr;this.ctx.setTransform(this.dpr,0,0,this.dpr,0,0);this.draw()}
  fit(){const b=this.bbox;const sx=this.W/((b.lon1-b.lon0)*COS),sy=this.H/(b.lat1-b.lat0);this.view={clat:(b.lat0+b.lat1)/2,clon:(b.lon0+b.lon1)/2,s:Math.min(sx,sy)*.97};this.draw()}
  X(lon){return this.W/2+(lon-this.view.clon)*this.view.s*COS} Y(lat){return this.H/2-(lat-this.view.clat)*this.view.s}
  lon(x){return this.view.clon+(x-this.W/2)/(this.view.s*COS)} lat(y){return this.view.clat-(y-this.H/2)/this.view.s}
  zoom(f,px,py){px=px??this.W/2;py=py??this.H/2;const lo=this.lon(px),la=this.lat(py);this.view.s=Math.min(4000,Math.max(40,this.view.s*f));
    this.view.clon=lo-(px-this.W/2)/(this.view.s*COS);this.view.clat=la+(py-this.H/2)/this.view.s;this.draw()}
  focus(lat,lon,s){this.view.clat=lat;this.view.clon=lon;if(s)this.view.s=s;this.draw()}
  setCells(colors,glyphs){this.colors=colors;this.glyphs=glyphs;this.draw()}
  setZones(z){this.zones=z||[];this.draw()} setPort(p){this.port=p;this.draw()} setSelected(i){this.sel=i;this.draw()}
  bind(){
    const c=this.cv;
    c.addEventListener('wheel',e=>{e.preventDefault();const r=c.getBoundingClientRect();this.zoom(e.deltaY<0?1.2:1/1.2,e.clientX-r.left,e.clientY-r.top)},{passive:false});
    c.addEventListener('pointerdown',e=>{c.setPointerCapture(e.pointerId);this.ptr.set(e.pointerId,{x:e.clientX,y:e.clientY});this.moved=false;this.down={x:e.clientX,y:e.clientY}});
    c.addEventListener('pointermove',e=>{
      const r=c.getBoundingClientRect();
      if(!this.ptr.has(e.pointerId)){this.hoverAt(e.clientX-r.left,e.clientY-r.top,e);return}
      const p=this.ptr.get(e.pointerId);
      if(this.ptr.size===1){const dx=e.clientX-p.x,dy=e.clientY-p.y;if(Math.abs(e.clientX-this.down.x)+Math.abs(e.clientY-this.down.y)>6)this.moved=true;
        this.view.clon-=dx/(this.view.s*COS);this.view.clat+=dy/this.view.s;this.draw()}
      else if(this.ptr.size===2){const o=[...this.ptr.entries()].find(([k])=>k!==e.pointerId)[1];const d0=Math.hypot(p.x-o.x,p.y-o.y),d1=Math.hypot(e.clientX-o.x,e.clientY-o.y);
        if(d0>0)this.zoom(d1/d0,(e.clientX+o.x)/2-r.left,(e.clientY+o.y)/2-r.top);this.moved=true}
      p.x=e.clientX;p.y=e.clientY});
    const up=e=>{if(this.ptr.has(e.pointerId)){this.ptr.delete(e.pointerId);if(!this.moved&&this.ptr.size===0){const r=c.getBoundingClientRect();const i=this.nearest(e.clientX-r.left,e.clientY-r.top,18);this.opt.onSelect&&this.opt.onSelect(i)}}};
    c.addEventListener('pointerup',up);c.addEventListener('pointercancel',e=>this.ptr.delete(e.pointerId));
    c.addEventListener('pointerleave',()=>{this.hover=-1;this.opt.onHover&&this.opt.onHover(-1)});
    c.addEventListener('keydown',e=>{if(e.key==='+')this.zoom(1.3);if(e.key==='-')this.zoom(1/1.3)});
  }
  hoverAt(x,y,e){const i=this.nearest(x,y,12);if(i!==this.hover){this.hover=i;this.opt.onHover&&this.opt.onHover(i,x,y)}else if(i>=0)this.opt.onHover&&this.opt.onHover(i,x,y)}
  nearest(x,y,tol){let best=-1,bd=tol*tol;const st=this.st;for(let i=0;i<st.n;i++){if(this.colors&&!this.colors[i])continue;const dx=this.X(st.lon[i])-x,dy=this.Y(st.lat[i])-y;const d=dx*dx+dy*dy;if(d<bd){bd=d;best=i}}return best}
  draw(){if(this.raf)return;this.raf=requestAnimationFrame(()=>{this.raf=0;this._draw()})}
  ring(r){const c=this.ctx;r.forEach((p,k)=>{const x=this.X(p[0]),y=this.Y(p[1]);k?c.lineTo(x,y):c.moveTo(x,y)});c.closePath()}
  poly(g){const c=this.ctx;c.beginPath();const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;polys.forEach(pg=>pg.forEach(r=>this.ring(r)))}
  hatch(){if(this._pat)return this._pat;const p=document.createElement('canvas');p.width=p.height=10;const x=p.getContext('2d');x.strokeStyle='rgba(16,100,140,.55)';x.lineWidth=1.4;x.beginPath();x.moveTo(0,10);x.lineTo(10,0);x.stroke();return this._pat=this.ctx.createPattern(p,'repeat')}
  _draw(){
    const c=this.ctx,W=this.W,H=this.H,b=this.meta;c.setTransform(this.dpr,0,0,this.dpr,0,0);c.fillStyle='#cfe4ee';c.fillRect(0,0,W,H);
    if(this.img&&this.img.complete){c.imageSmoothingEnabled=true;c.globalAlpha=.95;
      c.drawImage(this.img,this.X(b.lon0),this.Y(b.lat1),(b.lon1-b.lon0)*this.view.s*COS,(b.lat1-b.lat0)*this.view.s);c.globalAlpha=1}
    // graticule
    c.strokeStyle='rgba(11,42,74,.12)';c.fillStyle='rgba(11,42,74,.55)';c.font='10px system-ui';c.lineWidth=1;
    for(let la=18;la<=23;la++){const y=this.Y(la);c.beginPath();c.moveTo(0,y);c.lineTo(W,y);c.stroke();c.fillText(la+'°N',3,y-2)}
    for(let lo=89;lo<=92;lo++){const x=this.X(lo);c.beginPath();c.moveTo(x,0);c.lineTo(x,H);c.stroke();c.fillText(lo+'°E',x+2,H-3)}
    const G=this.geo;
    if(G.ifa){c.fillStyle=this.hatch();for(const f of G.ifa.features){this.poly(f.geometry);c.fill('evenodd');c.strokeStyle='rgba(16,100,140,.7)';c.lineWidth=1;c.stroke()}}
    if(G.eez){c.setLineDash([6,4]);c.strokeStyle='#0b2a4a';c.lineWidth=1.6;for(const f of G.eez.features){this.poly(f.geometry);c.stroke()}c.setLineDash([])}
    if(G.grounds){c.strokeStyle='rgba(120,70,0,.8)';c.lineWidth=1;c.setLineDash([3,3]);c.fillStyle='rgba(120,70,0,.9)';c.font='10px system-ui';
      for(const f of G.grounds.features){this.poly(f.geometry);c.stroke();const p=f.geometry.coordinates[0][0];c.fillText(f.properties.name,this.X(p[0])+3,this.Y(p[1])-3)}c.setLineDash([])}
    if(G.mpas){for(const f of G.mpas.features){const v=/verified/.test(f.properties.legal_status)&&!/provisional|candidate/.test(f.properties.legal_status);
      this.poly(f.geometry);c.fillStyle=v?'rgba(210,53,45,.28)':'rgba(240,140,0,.28)';c.fill('evenodd');c.strokeStyle=v?'#a1241d':'#c06a00';c.lineWidth=1.4;c.setLineDash(v?[]:[4,3]);c.stroke();c.setLineDash([])}}
    // cells
    const st=this.st,sz=Math.min(34,Math.max(3,this.cellDeg*this.view.s*COS*1.02));
    if(this.colors){for(let i=0;i<st.n;i++){const col=this.colors[i];if(!col)continue;const x=this.X(st.lon[i]),y=this.Y(st.lat[i]);if(x<-20||y<-20||x>W+20||y>H+20)continue;
      c.fillStyle=col;if(sz>=10){c.beginPath();c.roundRect(x-sz/2,y-sz/2,sz,sz,Math.min(5,sz/4));c.fill()}else c.fillRect(x-sz/2,y-sz/2,sz,sz)}
      if(sz>=14&&this.glyphs){c.fillStyle='#fff';c.font=`bold ${Math.round(sz*.62)}px system-ui`;c.textAlign='center';c.textBaseline='middle';
        for(let i=0;i<st.n;i++){const g=this.glyphs[i];if(!g)continue;const x=this.X(st.lon[i]),y=this.Y(st.lat[i]);if(x<-20||y<-20||x>W+20||y>H+20)continue;c.fillText(g,x,y+.5)}c.textAlign='start';c.textBaseline='alphabetic'}}
    // route + port
    const P=this.port;
    if(P){const px=this.X(P.lon),py=this.Y(P.lat),ex=this.X(P.entry.lon),ey=this.Y(P.entry.lat);
      c.setLineDash([2,4]);c.strokeStyle='#0b2a4a';c.lineWidth=2;c.beginPath();c.moveTo(px,py);c.lineTo(ex,ey);c.stroke();c.setLineDash([]);
      const zi=this.zones.find(z=>z.i===this.sel)||(this.sel>=0?{i:this.sel}:null);
      if(zi&&zi.i>=0){c.strokeStyle='#0b2a4a';c.lineWidth=2.5;c.beginPath();c.moveTo(ex,ey);c.lineTo(this.X(st.lon[zi.i]),this.Y(st.lat[zi.i]));c.stroke()}
      c.fillStyle='#0b2a4a';c.beginPath();c.arc(px,py,6,0,7);c.fill();c.strokeStyle='#fff';c.lineWidth=2;c.stroke();
      c.fillStyle='#0b2a4a';c.font='bold 12px system-ui';c.fillText(P.label,px+9,py+4)}
    // zones
    this.zones.forEach((z,k)=>{const x=this.X(st.lon[z.i]),y=this.Y(st.lat[z.i]);c.fillStyle='#0b2a4a';c.beginPath();c.arc(x,y,11,0,7);c.fill();c.strokeStyle='#fff';c.lineWidth=2.5;c.stroke();
      c.fillStyle='#fff';c.font='bold 12px system-ui';c.textAlign='center';c.textBaseline='middle';c.fillText(String(k+1),x,y+.5);c.textAlign='start';c.textBaseline='alphabetic'});
    if(this.sel>=0){const x=this.X(st.lon[this.sel]),y=this.Y(st.lat[this.sel]);c.strokeStyle='#fff';c.lineWidth=4;c.beginPath();c.arc(x,y,Math.max(9,sz*.8),0,7);c.stroke();c.strokeStyle='#0b2a4a';c.lineWidth=2;c.stroke()}
    if(this.hover>=0&&this.hover!==this.sel){const x=this.X(st.lon[this.hover]),y=this.Y(st.lat[this.hover]);c.strokeStyle='#0b2a4a';c.lineWidth=1.5;c.strokeRect(x-sz/2-1,y-sz/2-1,sz+2,sz+2)}
  }
}
window.JBMap=JBMap;
})();
