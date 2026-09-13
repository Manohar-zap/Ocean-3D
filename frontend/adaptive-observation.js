/* OCEAN 3D — Adaptive Observation MVP
 * Client-side decision layer: estimates observation-gap risk from the existing
 * observation API and recommends a glider/AUV waypoint. Replace the heuristic
 * with a trained uncertainty model when the ML service is available.
 */
(function () {
  'use strict';

  const ID = 'adaptiveObservationPanel';
  let targetEntity = null;
  const BOUNDS = { minLat: 0, maxLat: 25, minLon: 60, maxLon: 100 };

  function css() {
    if (document.getElementById('adaptiveObservationStyles')) return;
    const s = document.createElement('style');
    s.id = 'adaptiveObservationStyles';
    s.textContent = `
      #${ID}{position:absolute;right:16px;top:16px;width:330px;max-height:calc(100% - 32px);overflow:auto;background:rgba(13,26,36,.96);border:1px solid #1a2f3c;border-radius:4px;z-index:8;box-shadow:0 16px 50px rgba(0,0,0,.35);display:none;color:#dceaf0;font:12px 'IBM Plex Sans',system-ui,sans-serif}
      #${ID}.open{display:block}
      #${ID} .ao-head{padding:12px 14px;border-bottom:1px solid #1a2f3c;display:flex;align-items:center;justify-content:space-between}
      #${ID} .ao-title{font-size:13px;font-weight:600}.ao-kicker{font:10px 'IBM Plex Mono',monospace;color:#7c93a0;text-transform:uppercase;letter-spacing:.08em}
      #${ID} .ao-close{border:0;background:transparent;color:#7c93a0;cursor:pointer;font-size:16px}
      #${ID} .ao-body{padding:12px 14px;display:flex;flex-direction:column;gap:10px}
      #${ID} .ao-btn{width:100%;padding:9px 10px;border:1px solid #1f6e63;background:#1f6e63;color:#dceaf0;border-radius:3px;cursor:pointer;font:12px 'IBM Plex Sans'}
      #${ID} .ao-btn:hover{background:#3fe0c5;color:#04201b}
      #${ID} .ao-status{font:11px 'IBM Plex Mono',monospace;color:#7c93a0;min-height:15px}
      #${ID} .ao-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
      #${ID} .ao-card{background:#10212e;border:1px solid #1a2f3c;border-radius:3px;padding:8px}
      #${ID} .ao-label{font-size:10px;color:#7c93a0;margin-bottom:3px}.ao-value{font:12px 'IBM Plex Mono',monospace;color:#dceaf0}
      #${ID} .ao-reason{padding:9px;background:#10212e;border-left:3px solid #e8654f;line-height:1.45}
      #${ID} .ao-route{height:100px;background:#071019;border:1px solid #1a2f3c;border-radius:3px;position:relative;overflow:hidden}
      #${ID} .ao-route:before{content:'INDIAN OCEAN · SIMULATED MISSION';position:absolute;top:7px;left:8px;color:#7c93a0;font:9px 'IBM Plex Mono'}
      #${ID} .ao-route .start,#${ID} .ao-route .target{position:absolute;width:9px;height:9px;border-radius:50%;transform:translate(-50%,-50%)}
      #${ID} .ao-route .start{left:18%;top:72%;background:#8ec9e0}.ao-route .target{left:76%;top:34%;background:#e8654f;box-shadow:0 0 0 5px rgba(232,101,79,.12)}
      #${ID} .ao-route .line{position:absolute;left:19%;top:36%;width:62%;height:2px;background:#8ec9e0;transform:rotate(28deg);transform-origin:left center;opacity:.8}
      #${ID} .ao-foot{font-size:10px;color:#7c93a0;line-height:1.4}
    `;
    document.head.appendChild(s);
  }

  function panel() {
    css();
    const main = document.querySelector('main');
    if (!main || document.getElementById(ID)) return;
    const el = document.createElement('section');
    el.id = ID;
    el.innerHTML = `
      <div class="ao-head"><div><div class="ao-kicker">Decision layer</div><div class="ao-title">Adaptive Ocean Observation</div></div><button class="ao-close" aria-label="Close">×</button></div>
      <div class="ao-body">
        <button class="ao-btn" id="aoAnalyze">Analyze observation gaps</button>
        <div class="ao-status" id="aoStatus">Ready — Indian Ocean window 0–25°N, 60–100°E.</div>
        <div class="ao-grid">
          <div class="ao-card"><div class="ao-label">Priority</div><div class="ao-value" id="aoPriority">—</div></div>
          <div class="ao-card"><div class="ao-label">Confidence risk</div><div class="ao-value" id="aoRisk">—</div></div>
          <div class="ao-card"><div class="ao-label">Target latitude</div><div class="ao-value" id="aoLat">—</div></div>
          <div class="ao-card"><div class="ao-label">Target longitude</div><div class="ao-value" id="aoLon">—</div></div>
          <div class="ao-card"><div class="ao-label">Suggested depth</div><div class="ao-value" id="aoDepth">—</div></div>
          <div class="ao-card"><div class="ao-label">Nearest platform</div><div class="ao-value" id="aoNearest">—</div></div>
        </div>
        <div class="ao-reason" id="aoReason">The system will rank regions using observation age and spatial coverage. This MVP is a transparent decision heuristic, not a trained ML forecast.</div>
        <div class="ao-route"><span class="start"></span><span class="line"></span><span class="target"></span></div>
        <button class="ao-btn" id="aoSimulate" style="background:#10212e;border-color:#1a2f3c;display:none">Simulate glider observation</button>
        <div class="ao-foot">Recommended waypoint only. It does not command a real glider/AUV.</div>
      </div>`;
    main.appendChild(el);
    el.querySelector('.ao-close').onclick = () => el.classList.remove('open');
    el.querySelector('#aoAnalyze').onclick = analyze;
    el.querySelector('#aoSimulate').onclick = simulate;
  }

  function addButton() {
    const aside = document.querySelector('aside');
    if (!aside || document.getElementById('btnAdaptiveObservation')) return;
    const btn = document.createElement('button');
    btn.id = 'btnAdaptiveObservation'; btn.className = 'action primary';
    btn.textContent = 'Adaptive Observation Planner';
    const anchor = document.getElementById('btnFlyIndia');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(btn, anchor.nextSibling); else aside.prepend(btn);
    btn.onclick = () => { const p=document.getElementById(ID); p.classList.add('open'); analyze(); };
  }

  function haversine(aLat,aLon,bLat,bLon){const r=Math.PI/180,x=(bLon-aLon)*r*Math.cos(((aLat+bLat)/2)*r),y=(bLat-aLat)*r;return 6371*Math.sqrt(x*x+y*y);}
  function parseTime(v){const t=Date.parse(v||'');return Number.isFinite(t)?t:null;}
  function ageDays(t){return t?Math.max(0,(Date.now()-t)/86400000):30;}
  function set(id,value){const e=document.getElementById(id);if(e)e.textContent=value;}

  async function getObservations(){
    const base=(document.getElementById('apiBase')?.value||'http://localhost:8000').replace(/\/$/,'');
    const qs=new URLSearchParams({min_lat:BOUNDS.minLat,max_lat:BOUNDS.maxLat,min_lon:BOUNDS.minLon,max_lon:BOUNDS.maxLon});
    const r=await fetch(`${base}/api/observations?${qs}`); if(!r.ok) throw new Error(`Observation API returned ${r.status}`);
    return (await r.json()).markers||[];
  }

  function chooseTarget(markers){
    const candidates=[];
    for(let lat=2;lat<=24;lat+=2){for(let lon=62;lon<=98;lon+=2){
      let nearest=Infinity,weightedAge=0,weight=0;
      for(const m of markers){const d=haversine(lat,lon,Number(m.lat),Number(m.lon));nearest=Math.min(nearest,d);const w=1/Math.max(d,25);weightedAge+=ageDays(parseTime(m.time))*w;weight+=w;}
      const age=weight?weightedAge/weight:30,gap=Math.min(nearest,1200)/1200,stale=Math.min(age,15)/15,edge=(lat<5||lat>22)?.04:0;
      candidates.push({lat,lon,nearest,age,score:.62*gap+.34*stale+edge});
    }}
    candidates.sort((a,b)=>b.score-a.score);return candidates[0]||{lat:12,lon:76,nearest:Infinity,age:30,score:1};
  }

  async function analyze(){
    panel(); const p=document.getElementById(ID);p.classList.add('open');set('aoStatus','Loading observations from the existing Ocean 3D API…');
    try{const markers=await getObservations(),target=chooseTarget(markers),risk=Math.round(Math.min(99,target.score*100)),priority=risk>=75?'HIGH':risk>=50?'MEDIUM':'LOW',depth=risk>=75?1000:risk>=50?750:500;
      set('aoPriority',priority);set('aoRisk',`${risk}%`);set('aoLat',`${target.lat.toFixed(1)}°N`);set('aoLon',`${target.lon.toFixed(1)}°E`);set('aoDepth',`${depth} m`);set('aoNearest',markers.length?`${Math.round(target.nearest)} km`:'No nearby data');set('aoStatus',`${markers.length} observation platforms evaluated.`);
      set('aoReason',`Highest-priority gap: the candidate region is ${markers.length?Math.round(target.nearest):'unknown'} km from the nearest current marker and has an estimated nearby observation age of ${target.age.toFixed(1)} days. A ${depth} m profile is recommended for the simulation.`);
      document.getElementById('aoSimulate').style.display='block';showTarget(target.lat,target.lon,depth,priority);
    }catch(err){set('aoStatus',`Could not analyze: ${err.message}`);set('aoReason','Start the FastAPI backend at the configured API base, then run the planner again.');}
  }

  function showTarget(lat,lon,depth,priority){
    const v=window.oceanViewer;if(!v||!window.Cesium)return;if(targetEntity)v.entities.remove(targetEntity);
    targetEntity=v.entities.add({name:'Adaptive observation target',position:Cesium.Cartesian3.fromDegrees(lon,lat,0),point:{pixelSize:14,color:priority==='HIGH'?Cesium.Color.RED:Cesium.Color.YELLOW,outlineColor:Cesium.Color.WHITE,outlineWidth:2},label:{text:`RECOMMENDED\n${lat.toFixed(1)}°N ${lon.toFixed(1)}°E\nProfile ${depth} m`,font:'11px IBM Plex Mono',fillColor:Cesium.Color.WHITE,showBackground:true,backgroundColor:Cesium.Color.fromCssColorString('#071019').withAlpha(.9),verticalOrigin:Cesium.VerticalOrigin.BOTTOM,pixelOffset:new Cesium.Cartesian2(0,-18)},userData:{adaptiveTarget:true,lat,lon,depth}});
    v.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(lon,lat,2200000),duration:1.6});
  }

  function simulate(){
    const lat=parseFloat(document.getElementById('aoLat').textContent),lon=parseFloat(document.getElementById('aoLon').textContent),depth=parseInt(document.getElementById('aoDepth').textContent,10);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    const status=document.getElementById('aoStatus');status.textContent='Simulating glider mission → waypoint → profile → model update…';const start={lat:Math.max(1,lat-5),lon:Math.max(60,lon-10)},v=window.oceanViewer;
    if(v&&window.Cesium){let e=v.entities.getById('adaptive-sim-glider');if(e)v.entities.remove(e);e=v.entities.add({id:'adaptive-sim-glider',name:'Simulated glider',position:Cesium.Cartesian3.fromDegrees(start.lon,start.lat,0),point:{pixelSize:11,color:Cesium.Color.fromCssColorString('#8ec9e0')},label:{text:'SIM GLIDER',font:'10px IBM Plex Mono',fillColor:Cesium.Color.WHITE,showBackground:true,backgroundColor:Cesium.Color.fromCssColorString('#071019').withAlpha(.85),pixelOffset:new Cesium.Cartesian2(0,-14)}});const steps=50;let i=0;const timer=setInterval(()=>{i++;const t=i/steps,clat=start.lat+(lat-start.lat)*t,clon=start.lon+(lon-start.lon)*t;e.position=Cesium.Cartesian3.fromDegrees(clon,clat,0);if(i>=steps){clearInterval(timer);status.textContent=`Simulation complete: ${depth} m profile collected. Uncertainty reduced in the target region.`;set('aoRisk','LOWERED');}},40);
    }else status.textContent=`Simulation complete: virtual ${depth} m profile collected at ${lat.toFixed(1)}°N, ${lon.toFixed(1)}°E.`;
  }

  function boot(){panel();addButton();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
