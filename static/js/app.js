const qs = (s, root=document) => root.querySelector(s);
const qsa = (s, root=document) => [...root.querySelectorAll(s)];
const fmt = n => Number(n || 0).toLocaleString();
const crowdClass = c => c === 'busy' ? 'crowd-busy' : (c === 'medium' ? 'crowd-medium' : 'crowd-easy');
async function getJSON(url){ const r = await fetch(url); if(!r.ok) throw new Error(url); return r.json(); }

function markerIcon(type, crowd='easy'){
  const cls = type === 'stadium' ? 'stadium-dot' : type === 'cab' ? 'cab-dot' : `map-marker marker-${crowd}`;
  return L.divIcon({className:'', html:`<div class="${cls}"></div>`, iconSize:[34,34], iconAnchor:[17,17]});
}

let liveMap, mapData, markerLayer, selectedZone;
function initLiveMap(){
  const el = qs('#liveMap');
  if(!el || !window.L) return;
  liveMap = L.map(el, { zoomControl:true, attributionControl:true }).setView([-27.4648,153.0095], 16);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'© OpenStreetMap'}).addTo(liveMap);
  markerLayer = L.layerGroup().addTo(liveMap);
  getJSON('/api/map-feed').then(data => { mapData = data; renderMapFeed('best'); }).catch(console.error);
  qs('#recenterMap')?.addEventListener('click',()=>fitMap());
  qsa('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>{
    qsa('.tab-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    renderRecommendations(btn.dataset.mode);
  }));
}
function fitMap(){
  if(!mapData || !liveMap) return;
  const pts = [[mapData.stadium.lat,mapData.stadium.lng], ...mapData.pickups.slice(0,10).map(p=>[p.lat,p.lng])];
  liveMap.fitBounds(pts, {padding:[90,520], maxZoom:16});
}
function renderMapFeed(mode='best'){
  if(!mapData) return;
  markerLayer.clearLayers();
  L.marker([mapData.stadium.lat,mapData.stadium.lng], {icon:markerIcon('stadium')}).addTo(markerLayer).bindPopup('Suncorp Stadium');
  mapData.pickups.forEach(p=>{
    L.marker([p.lat,p.lng], {icon:markerIcon('pickup', p.crowd)}).addTo(markerLayer)
      .bindPopup(`<b>${p.zone}</b><br>${p.walk_min} min walk • ${p.eta} min ETA`)
      .on('click',()=>selectPickup(p, true));
  });
  (mapData.cabs || []).slice(0,55).forEach(c=>{
    L.marker([c.lat,c.lng], {icon:markerIcon('cab')}).addTo(markerLayer)
      .bindPopup(`<b>${c.company}</b><br>${c.eta} min ETA`);
  });
  fitMap();
  selectPickup((mapData.best || mapData.pickups)[0]);
  renderRecommendations(mode);
}
function listForMode(mode){
  return mode === 'fastest' ? mapData.fastest : mode === 'safest' ? mapData.safest : mapData.best;
}
function renderRecommendations(mode='best'){
  const list = qs('#recommendationList');
  if(!list || !mapData) return;
  const title = mode === 'fastest' ? 'Fastest pickup' : mode === 'safest' ? 'Safer pickup' : 'Best pickup';
  const sub = mode === 'fastest' ? 'Lowest cab arrival time.' : mode === 'safest' ? 'Lower crowd pressure.' : 'Best balance right now.';
  qs('#bestHeadline').textContent = title;
  qs('#bestSubline').textContent = sub;
  const recs = (listForMode(mode) || []).slice(0,5);
  list.innerHTML = recs.map((p,i)=>`
    <button class="rec-card ${selectedZone && selectedZone.zone===p.zone?'selected':''}" data-zone="${p.zone}">
      <span class="rec-badge">${i===0?'★':'P'}</span>
      <span>
        <h3>${p.label}</h3>
        <p>${p.walk_min} min walk · ${p.eta} min cab ETA</p>
      </span>
      <span class="rec-meta">
        <strong>${fmt(p.bookings)}</strong><small>bookings</small>
        <em class="crowd-pill ${crowdClass(p.crowd)}">${p.crowd}</em>
      </span>
    </button>`).join('');
  qsa('.rec-card', list).forEach(btn=> btn.addEventListener('click',()=>{
    const p = mapData.pickups.find(x=>x.zone===btn.dataset.zone);
    selectPickup(p, true);
    renderRecommendations(mode);
  }));
}
function selectPickup(p, pan=false){
  if(!p) return;
  selectedZone = p;
  if(pan && liveMap) liveMap.setView([p.lat,p.lng], 17, {animate:true});
  const strip = qs('#selectedStrip');
  if(strip){
    strip.innerHTML = `<strong>Why this pickup?</strong><span>${p.label}: ${p.walk_min} min walk, ${p.eta} min ETA, ${p.crowd} crowd pressure.</span>`;
  }
}

function initHomePreview(){
  const el = qs('#homePreviewMap');
  if(!el || !window.L) return;
  const m = L.map(el, {zoomControl:false, attributionControl:false, dragging:false, scrollWheelZoom:false, doubleClickZoom:false}).setView([-27.4648,153.0095], 15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18}).addTo(m);
  getJSON('/api/map-feed').then(data=>{
    L.marker([data.stadium.lat,data.stadium.lng], {icon:markerIcon('stadium')}).addTo(m);
    data.pickups.slice(0,9).forEach(p=>L.marker([p.lat,p.lng], {icon:markerIcon('pickup', p.crowd)}).addTo(m));
    (data.cabs || []).slice(0,15).forEach(c=>L.marker([c.lat,c.lng], {icon:markerIcon('cab')}).addTo(m));
    const best = data.best[0];
    if(best){
      qs('#homeBestZone').textContent = best.label;
      qs('#homeBestWalk').textContent = best.walk_min + ' min';
      qs('#homeBestEta').textContent = best.eta + ' min';
      qs('#homeLiveStatus').textContent = best.crowd === 'busy' ? 'Busy exits' : best.crowd === 'medium' ? 'Balanced flow' : 'Smooth flow';
    }
    const pts = [[data.stadium.lat,data.stadium.lng], ...data.pickups.slice(0,9).map(p=>[p.lat,p.lng])];
    m.fitBounds(pts,{padding:[45,45],maxZoom:15});
  }).catch(console.error);
}

function plotConfig(){ return {displayModeBar:false, responsive:true}; }
function layout(title=''){
  return {title:{text:title,font:{color:'#f2f7ff',size:16}}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', font:{color:'#cbd7e7'}, margin:{l:45,r:20,t:45,b:45}, xaxis:{gridcolor:'rgba(255,255,255,.08)'}, yaxis:{gridcolor:'rgba(255,255,255,.08)'}};
}
function kpi(label,value){ return `<div class="kpi"><small>${label}</small><strong>${value}</strong></div>`; }
async function initDashboard(){
  const page = qs('.dash-page');
  if(!page) return;
  const kind = page.dataset.dashboard;
  const data = await getJSON(`/api/dashboard/${kind}`);
  const root = qs('#dashboardContent');
  if(kind==='bookings') return renderBookingsDash(root,data);
  if(kind==='pickups') return renderPickupDash(root,data);
  if(kind==='congestion') return renderCongestionDash(root,data);
  if(kind==='cabs') return renderCabDash(root,data);
  if(kind==='roads') return renderRoadDash(root,data);
}
function renderBookingsDash(root,d){
  root.innerHTML = `<div class="kpi-row">${kpi('Bookings',fmt(d.summary.total_bookings))}${kpi('Pickup zones',fmt(d.summary.pickup_zones))}${kpi('Avg ETA',d.summary.avg_eta+' min')}${kpi('Accessible',fmt(d.summary.accessible_requests))}</div><div class="dash-grid-2"><div class="plot-card"><div id="bookingTimeline" class="plot"></div></div><div class="plot-card"><div id="bookingChannels" class="plot"></div></div></div>`;
  Plotly.newPlot('bookingTimeline',[{x:Object.keys(d.timeline),y:Object.values(d.timeline),type:'bar'}],layout('Bookings by time'),plotConfig());
  Plotly.newPlot('bookingChannels',[{labels:Object.keys(d.channel),values:Object.values(d.channel),type:'pie',hole:.55}],layout('Booking channels'),plotConfig());
}
function renderPickupDash(root,d){
  const max = Math.max(...d.recommendations.map(x=>x.bookings),1);
  root.innerHTML = `<div class="dash-grid-2"><div class="list-card"><h2>Demand ranking</h2><div class="rank-list">${d.recommendations.map((p,i)=>`<div class="rank-item"><div><strong>${i+1}. ${p.label}</strong><div class="rank-bar"><div class="rank-fill" style="width:${(p.bookings/max)*100}%"></div></div></div><b>${p.bookings}</b></div>`).join('')}</div></div><div class="status-board"><h2>Best choices</h2>${d.recommendations.slice(0,4).map(p=>`<div class="rec-card"><span class="rec-badge">P</span><span><h3>${p.label}</h3><p>${p.walk_min} min walk · ${p.crowd}</p></span><span class="rec-meta"><strong>${p.eta}</strong><small>ETA</small></span></div>`).join('')}</div></div>`;
}
function renderCongestionDash(root,d){
  const types = d.type_counts || [];
  root.innerHTML = `<div class="status-grid"><div class="status-card red"><h2>High watch</h2><strong>${fmt(types[0]?.[1]||0)}</strong><p>Major signals nearby.</p></div><div class="status-card amber"><h2>Medium flow</h2><strong>${fmt(types[1]?.[1]||0)}</strong><p>Crossings and turns.</p></div><div class="status-card green"><h2>Clear support</h2><strong>${fmt(types[2]?.[1]||0)}</strong><p>Available road points.</p></div></div><div class="plot-card"><div id="congestionType" class="plot"></div></div>`;
  Plotly.newPlot('congestionType',[{x:types.map(x=>x[0]),y:types.map(x=>x[1]),type:'bar'}],layout('Congestion signals'),plotConfig());
}
function renderCabDash(root,d){
  root.innerHTML = `<div class="kpi-row">${kpi('Active cabs',fmt(d.summary.active_cabs))}${kpi('Avg ETA',d.summary.avg_eta+' min')}${kpi('Companies',fmt(d.companies.length))}${kpi('Top zone',d.summary.top_pickup.split(' ')[0])}</div><div class="fleet-grid">${d.companies.map(c=>`<div class="fleet-card"><strong>${c.cab_company_name || c.company || 'Cab company'}</strong><small>${fmt(c.total_allocations || c.allocations || 0)} allocations</small><span>${c.avg_eta_min || c.average_eta_min || '—'} min average ETA</span></div>`).join('')}</div>`;
}
function renderRoadDash(root,d){
  const rows = d.highway || [];
  root.innerHTML = `<div class="route-board"><h2>Road movement support</h2>${rows.map((r,i)=>`<div class="route-row"><strong>${r[0] || 'Road type'}</strong><span class="route-line" style="opacity:${1-(i*.07)}"></span><b>${fmt(r[1])}</b></div>`).join('')}</div>`;
}
async function initAllocations(){
  const root = qs('#allocationsContent') || qs('#allocationGrid');
  if(!root) return;
  const data = await getJSON('/api/allocations');
  const rows = (data.rows || []).slice(0,24);
  root.innerHTML = `<div class="allocation-grid">${rows.map(r=>`<article class="alloc-card"><strong>${r.cab_company_name || 'Cab'}</strong><span>${r.allocated_vehicle_make_model || 'Assigned vehicle'}</span><small>${r.estimated_arrival_to_pickup_min || '—'} min ETA · ${r.allocation_status || 'Assigned'}</small></article>`).join('')}</div>`;
}
async function initSystem(){
  const root = qs('#systemContent') || qs('#systemFiles');
  if(!root) return;
  const data = await getJSON('/api/system');
  root.innerHTML = `<div class="flow-line">${data.flow.map(x=>`<span>${x}</span>`).join('')}</div><div class="system-files">${data.files.map(f=>`<div class="file-card"><strong>${f.file}</strong><span>${fmt(f.rows)} rows</span><code>${f.columns.join(', ')}</code></div>`).join('')}</div>`;
}

document.addEventListener('DOMContentLoaded',()=>{
  initHomePreview();
  initLiveMap();
  initDashboard();
  initAllocations();
  initSystem();
});

/* FINAL MAP + INTERNAL OVERRIDES */
let pickupMarkerMap = {}, routeLine = null;
function customerLabelCrowd(c){ return c === 'busy' ? 'Busy' : c === 'medium' ? 'Moderate' : 'Less crowded'; }
function routeReason(p){
  const bits = [];
  bits.push(p.walk_min <= 3 ? 'short walk' : 'clear walk');
  bits.push(p.eta <= 7 ? 'fast cab arrival' : 'steady cab flow');
  bits.push(p.crowd === 'easy' ? 'low crowd' : p.crowd === 'medium' ? 'manageable crowd' : 'busy but available');
  if(p.accessible > 0) bits.push('accessible support');
  return bits.slice(0,3).join(' • ');
}
function initLiveMap(){
  const el = qs('#liveMap');
  if(!el || !window.L) return;
  liveMap = L.map(el, { zoomControl:true, attributionControl:true }).setView([-27.4648,153.0095], 16);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'© OpenStreetMap'}).addTo(liveMap);
  markerLayer = L.layerGroup().addTo(liveMap);
  getJSON('/api/map-feed').then(data => { mapData = data; renderMapFeed('best'); }).catch(console.error);
  qs('#recenterMap')?.addEventListener('click',()=>{ if(mapData){ selectPickup((mapData.best||mapData.pickups)[0], true); fitMap(); }});
  qsa('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>{
    qsa('.tab-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    renderRecommendations(btn.dataset.mode);
  }));
}
function fitMap(){
  if(!mapData || !liveMap) return;
  const pts = [[mapData.stadium.lat,mapData.stadium.lng], ...mapData.pickups.slice(0,10).map(p=>[p.lat,p.lng])];
  liveMap.fitBounds(pts, {paddingTopLeft:[380,80], paddingBottomRight:[520,80], maxZoom:16});
}
function renderMapFeed(mode='best'){
  if(!mapData) return;
  markerLayer.clearLayers(); pickupMarkerMap = {};
  L.marker([mapData.stadium.lat,mapData.stadium.lng], {icon:markerIcon('stadium')}).addTo(markerLayer).bindPopup('<b>Suncorp Stadium</b><br>Event pickup starts here');
  mapData.pickups.forEach((p,idx)=>{
    const m = L.marker([p.lat,p.lng], {icon:markerIcon('pickup', p.crowd)}).addTo(markerLayer)
      .bindPopup(`<b>${p.label}</b><br>${p.walk_min} min walk • ${p.eta} min cab ETA<br>${customerLabelCrowd(p.crowd)}`)
      .on('click',()=>{ selectPickup(p, true); renderRecommendations(qs('.tab-btn.active')?.dataset.mode || 'best'); });
    pickupMarkerMap[p.zone] = m;
  });
  (mapData.cabs || []).slice(0,45).forEach(c=>{
    L.marker([c.lat,c.lng], {icon:markerIcon('cab')}).addTo(markerLayer).bindPopup(`<b>${c.company}</b><br>${c.eta} min ETA`);
  });
  fitMap();
  selectPickup((mapData.best || mapData.pickups)[0], false);
  renderRecommendations(mode);
}
function listForMode(mode){
  if(!mapData) return [];
  if(mode === 'fastest') return mapData.fastest || [];
  if(mode === 'quiet') return mapData.quiet || [];
  if(mode === 'accessible') return mapData.accessible || [];
  return mapData.best || mapData.pickups || [];
}
function renderRecommendations(mode='best'){
  const list = qs('#recommendationList');
  if(!list || !mapData) return;
  const recs = (listForMode(mode) || []).slice(0,8);
  list.innerHTML = recs.map((p,i)=>`
    <button class="rec-card pickup-option-card ${selectedZone && selectedZone.zone===p.zone?'selected':''}" data-zone="${p.zone}">
      <span class="rec-badge">${i+1}</span>
      <span class="option-main">
        <h3>${p.label}</h3>
        <p>${p.walk_min} min walk · ${p.eta} min cab ETA</p>
        <small>${routeReason(p)}</small>
      </span>
      <span class="rec-meta">
        <em class="crowd-pill ${crowdClass(p.crowd)}">${customerLabelCrowd(p.crowd)}</em>
        <small>${p.accessible || 0} accessible</small>
      </span>
    </button>`).join('');
  qsa('.rec-card', list).forEach(btn=> btn.addEventListener('click',()=>{
    const p = mapData.pickups.find(x=>x.zone===btn.dataset.zone);
    selectPickup(p, true);
    renderRecommendations(mode);
  }));
}
function selectPickup(p, pan=false){
  if(!p || !liveMap) return;
  selectedZone = p;
  Object.entries(pickupMarkerMap).forEach(([zone,m]) => m.setIcon(markerIcon('pickup', zone===p.zone ? 'selected' : (mapData.pickups.find(x=>x.zone===zone)?.crowd || 'easy'))));
  if(routeLine) { liveMap.removeLayer(routeLine); routeLine = null; }
  routeLine = L.polyline([[mapData.stadium.lat,mapData.stadium.lng],[p.lat,p.lng]], {weight:6, opacity:.9, dashArray:'10 10'}).addTo(liveMap);
  pickupMarkerMap[p.zone]?.openPopup();
  if(pan) liveMap.flyTo([p.lat,p.lng], 17, {animate:true, duration:.6});
  const strip = qs('#selectedStrip');
  if(strip){
    strip.innerHTML = `<div><small>Selected pickup</small><strong>${p.label}</strong></div><div class="selected-stats"><span>${p.walk_min} min walk</span><span>${p.eta} min ETA</span><span>${customerLabelCrowd(p.crowd)}</span></div><p>${routeReason(p)}</p><button class="confirm-pickup-btn">Confirm pickup</button>`;
  }
}

function renderBookingsDash(root,d){
  root.innerHTML = `<div class="dash-insight-banner"><strong>How busy is the system?</strong><span>${fmt(d.summary.total_bookings)} bookings across ${fmt(d.summary.pickup_zones)} pickup zones.</span></div><div class="kpi-row compact-kpis">${kpi('Bookings',fmt(d.summary.total_bookings))}${kpi('Active cabs',fmt(d.summary.active_cabs))}${kpi('Avg ETA',d.summary.avg_eta+' min')}${kpi('Accessible',fmt(d.summary.accessible_requests))}</div><div class="dash-grid-2"><div class="plot-card"><div id="bookingTimeline" class="plot"></div></div><div class="plot-card"><div id="bookingChannels" class="plot"></div></div></div>`;
  Plotly.newPlot('bookingTimeline',[{x:Object.keys(d.timeline),y:Object.values(d.timeline),type:'bar'}],layout('Bookings by pickup time'),plotConfig());
  Plotly.newPlot('bookingChannels',[{labels:Object.keys(d.channel),values:Object.values(d.channel),type:'pie',hole:.58}],layout('Booking channels'),plotConfig());
}
function renderPickupDash(root,d){
  const max = Math.max(...d.recommendations.map(x=>x.bookings),1);
  root.innerHTML = `<div class="dash-insight-banner"><strong>Where is demand highest?</strong><span>Ranked pickup pressure with accessibility demand.</span></div><div class="dash-grid-2 pickup-dashboard-layout"><div class="list-card"><h2>Demand ranking</h2><div class="rank-list">${d.recommendations.slice(0,10).map((p,i)=>`<div class="rank-item"><div><strong>${i+1}. ${p.label}</strong><span>${p.walk_min} min walk · ${p.eta} min ETA</span><div class="rank-bar"><div class="rank-fill" style="width:${(p.bookings/max)*100}%"></div></div></div><b>${p.bookings}</b></div>`).join('')}</div></div><div class="status-board pickup-best-board"><h2>Best operational choices</h2>${d.recommendations.slice(0,5).map(p=>`<div class="mini-decision"><strong>${p.label}</strong><span>${customerLabelCrowd(p.crowd)} · ${p.accessible} accessible requests</span></div>`).join('')}</div></div>`;
}
function renderCongestionDash(root,d){
  const types = d.type_counts || [];
  root.innerHTML = `<div class="dash-insight-banner"><strong>Where is it crowded?</strong><span>Signals grouped by road/crossing type for event control.</span></div><div class="status-grid congestion-status"><div class="status-card red"><h2>High watch</h2><strong>${fmt(types[0]?.[1]||0)}</strong><p>Major signals nearby.</p></div><div class="status-card amber"><h2>Medium flow</h2><strong>${fmt(types[1]?.[1]||0)}</strong><p>Crossings and turns.</p></div><div class="status-card green"><h2>Clear support</h2><strong>${fmt(types[2]?.[1]||0)}</strong><p>Available road points.</p></div></div><div class="plot-card"><div id="congestionType" class="plot"></div></div>`;
  Plotly.newPlot('congestionType',[{x:types.map(x=>x[0]),y:types.map(x=>x[1]),type:'bar'}],layout('Congestion signals'),plotConfig());
}
function renderCabDash(root,d){
  root.innerHTML = `<div class="dash-insight-banner"><strong>Are enough cabs available?</strong><span>${fmt(d.summary.active_cabs)} assigned vehicles with ${d.summary.avg_eta} min average ETA.</span></div><div class="kpi-row compact-kpis">${kpi('Active cabs',fmt(d.summary.active_cabs))}${kpi('Avg ETA',d.summary.avg_eta+' min')}${kpi('Companies',fmt(d.companies.length))}${kpi('Top zone',d.summary.top_pickup.split(' ')[0])}</div><div class="fleet-grid company-grid">${d.companies.map(c=>`<div class="fleet-card"><strong>${c.cab_company_name || c.company || 'Cab company'}</strong><small>${fmt(c.total_allocations || c.allocations || 0)} allocations</small><span>${c.avg_eta_min || c.average_eta_min || '—'} min average ETA</span></div>`).join('')}</div>`;
}
function renderRoadDash(root,d){
  const rows = d.highway || [];
  root.innerHTML = `<div class="dash-insight-banner"><strong>Which routes are usable?</strong><span>Road network points grouped for routing context.</span></div><div class="route-board route-console"><h2>Road movement support</h2>${rows.map((r,i)=>`<div class="route-row"><strong>${r[0] || 'Road type'}</strong><span class="route-line" style="opacity:${1-(i*.07)}"></span><b>${fmt(r[1])}</b></div>`).join('')}</div>`;
}
async function initAllocations(){
  const root = qs('#allocationsContent') || qs('#allocationGrid');
  if(!root) return;
  const data = await getJSON('/api/allocations');
  const rows = (data.rows || []).slice(0,60);
  root.innerHTML = `<div class="dispatcher-toolbar"><input id="allocSearch" placeholder="Search cab, company, pickup or status"><select id="allocStatus"><option value="">All statuses</option><option>Assigned</option><option>Active</option><option>Idle</option></select></div><div class="dispatcher-table-wrap"><table class="dispatcher-table"><thead><tr><th>Cab / Driver</th><th>Company</th><th>Pickup</th><th>ETA</th><th>Status</th><th>Vehicle</th></tr></thead><tbody id="allocRows"></tbody></table></div>`;
  const tbody = qs('#allocRows');
  const draw = () => {
    const q = (qs('#allocSearch')?.value || '').toLowerCase();
    const st = qs('#allocStatus')?.value || '';
    const filtered = rows.filter(r => (!st || (r.allocation_status||'').includes(st)) && JSON.stringify(r).toLowerCase().includes(q)).sort((a,b)=>Number(a.estimated_arrival_to_pickup_min||99)-Number(b.estimated_arrival_to_pickup_min||99));
    tbody.innerHTML = filtered.map(r=>`<tr><td><strong>${r.driver_id || r.booking_id || 'Cab'}</strong><small>${r.booking_id || ''}</small></td><td>${r.cab_company_name || 'Cab'}</td><td>${r.pickup_location_name || 'Pickup zone'}</td><td><b>${r.estimated_arrival_to_pickup_min || '—'} min</b></td><td><span class="status-badge">${r.allocation_status || 'Assigned'}</span></td><td>${r.allocated_vehicle_make_model || 'Vehicle'}</td></tr>`).join('');
  };
  qs('#allocSearch')?.addEventListener('input', draw); qs('#allocStatus')?.addEventListener('change', draw); draw();
}
async function initSystem(){
  const root = qs('#systemContent') || qs('#systemFiles');
  if(!root) return;
  const data = await getJSON('/api/system');
  root.innerHTML = `<div class="system-overview-grid"><div class="system-flow-card"><h2>Data pipeline</h2><div class="flow-line">${data.flow.map(x=>`<span>${x}</span>`).join('')}</div></div><div class="system-role-card"><h2>Role access</h2>${data.roles.map(r=>`<span class="role-chip">${r}</span>`).join('')}</div></div><h2 class="console-heading">API endpoints</h2><div class="endpoint-grid">${data.endpoints.map(e=>`<div class="endpoint-card"><code>${e.path}</code><span>${e.purpose}</span></div>`).join('')}</div><h2 class="console-heading">Datasets</h2><div class="system-files">${data.files.map(f=>`<div class="file-card"><strong>${f.file}</strong><span>${fmt(f.rows)} rows</span><code>${f.columns.join(', ')}</code></div>`).join('')}</div>`;
}

/* DASHBOARD TABLE + CHART UPGRADE */
function dashKpis(items){
  return `<div class="kpi-row premium-kpis">${(items||[]).map(i=>`<div class="kpi"><small>${i.label}</small><strong>${fmt(i.value)}</strong></div>`).join('')}</div>`;
}
function renderDataTable(table, title='Key records'){
  if(!table || !table.columns || !table.rows) return '';
  return `<section class="data-table-card">
    <div class="table-title"><h2>${title}</h2><span>Dataset preview</span></div>
    <div class="data-table-wrap"><table class="data-table">
      <thead><tr>${table.columns.map(c=>`<th>${String(c).replaceAll('_',' ')}</th>`).join('')}</tr></thead>
      <tbody>${table.rows.map(r=>`<tr>${table.columns.map(c=>`<td>${r[c] ?? ''}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div>
  </section>`;
}
function drawBar(id, data){
  Plotly.newPlot(id,[{x:data.x||[], y:data.y||[], type:'bar', marker:{color:'#2b8bd2'}}], {
    ...layout(data.title||''),
    margin:{l:50,r:22,t:48,b:70},
    xaxis:{gridcolor:'rgba(255,255,255,.05)', tickangle:-12},
    yaxis:{gridcolor:'rgba(255,255,255,.14)'}
  }, plotConfig());
}
function drawDonut(id, data){
  Plotly.newPlot(id,[{labels:data.labels||[], values:data.values||[], type:'pie', hole:.58, textinfo:'percent', marker:{line:{color:'rgba(2,6,14,.9)',width:3}}}], {
    ...layout(data.title||''),
    showlegend:true,
    legend:{font:{color:'#cbd7e7'}, x:1, y:1},
    margin:{l:25,r:120,t:48,b:25}
  }, plotConfig());
}
function dashboardShell(root,d,tableTitle){
  root.innerHTML = `
    ${dashKpis(d.kpis)}
    <div class="dash-grid-2 analytics-grid">
      <div class="plot-card large-plot"><div id="dashBar" class="plot"></div></div>
      <div class="plot-card large-plot"><div id="dashDonut" class="plot"></div></div>
    </div>
    ${renderDataTable(d.table, tableTitle)}
  `;
  if(d.bar) drawBar('dashBar', d.bar);
  if(d.donut) drawDonut('dashDonut', d.donut);
}
function renderBookingsDash(root,d){ dashboardShell(root,d,'Booking records'); }
function renderPickupDash(root,d){ dashboardShell(root,d,'Pickup zone records'); }
function renderCongestionDash(root,d){ dashboardShell(root,d,'Congestion records'); }
function renderCabDash(root,d){ dashboardShell(root,d,'Cab allocation records'); }
function renderRoadDash(root,d){ dashboardShell(root,d,'Road network records'); }

async function initAllocations(){
  const root = qs('#allocationsContent') || qs('#allocationGrid');
  if(!root) return;
  const data = await getJSON('/api/allocations');
  const rows = (data.rows || []).slice(0,120);
  root.innerHTML = `
    <div class="dispatcher-toolbar premium-toolbar">
      <input id="allocSearch" placeholder="Search driver, company, pickup, vehicle...">
      <select id="allocStatus"><option value="">All statuses</option><option>Assigned</option><option>Active</option><option>Idle</option></select>
      <span id="allocCount" class="table-count"></span>
    </div>
    <div class="dispatcher-table-wrap premium-table-wrap">
      <table class="dispatcher-table data-table"><thead><tr>
        <th>Driver / booking</th><th>Company</th><th>Pickup</th><th>ETA</th><th>Status</th><th>Vehicle</th>
      </tr></thead><tbody id="allocRows"></tbody></table>
    </div>`;
  const tbody = qs('#allocRows');
  const draw = () => {
    const q = (qs('#allocSearch')?.value || '').toLowerCase();
    const st = qs('#allocStatus')?.value || '';
    const filtered = rows.filter(r => (!st || (r.allocation_status||'').includes(st)) && JSON.stringify(r).toLowerCase().includes(q))
      .sort((a,b)=>Number(a.estimated_arrival_to_pickup_min||99)-Number(b.estimated_arrival_to_pickup_min||99));
    qs('#allocCount').textContent = `${filtered.length} records shown`;
    tbody.innerHTML = filtered.map(r=>`<tr>
      <td><strong>${r.driver_id || 'Driver'}</strong><small>${r.booking_id || ''}</small></td>
      <td>${r.cab_company_name || 'Cab company'}</td>
      <td>${r.pickup_location_name || 'Pickup zone'}</td>
      <td><b>${r.estimated_arrival_to_pickup_min || '—'} min</b></td>
      <td><span class="status-badge">${r.allocation_status || 'Assigned'}</span></td>
      <td>${r.allocated_vehicle_make_model || 'Vehicle'}</td>
    </tr>`).join('');
  };
  qs('#allocSearch')?.addEventListener('input', draw);
  qs('#allocStatus')?.addEventListener('change', draw);
  draw();
}

async function initSystem(){
  const root = qs('#systemContent') || qs('#systemFiles');
  if(!root) return;
  const data = await getJSON('/api/system');
  root.innerHTML = `
    <div class="system-overview-grid">
      <div class="system-flow-card"><h2>Data pipeline</h2><div class="flow-line">${data.flow.map(x=>`<span>${x}</span>`).join('')}</div></div>
      <div class="system-role-card"><h2>Role access</h2>${data.roles.map(r=>`<span class="role-chip">${r}</span>`).join('')}</div>
    </div>
    <h2 class="console-heading">API endpoints</h2>
    <div class="endpoint-grid">${data.endpoints.map(e=>`<div class="endpoint-card"><code>${e.path}</code><span>${e.purpose}</span></div>`).join('')}</div>
    <h2 class="console-heading">Datasets</h2>
    <div class="system-files dataset-grid">${data.files.map(f=>`<div class="file-card"><strong>${f.file}</strong><span>${fmt(f.rows)} rows</span><code>${f.columns.join(', ')}</code></div>`).join('')}</div>
  `;
}

/* =========================================================
   Final dashboard redesign: each dashboard has a different
   purpose-led layout instead of repeating the same template.
   ========================================================= */
function safeText(v, fallback='—'){
  if(v === undefined || v === null || v === '' || String(v).toLowerCase() === 'nan') return fallback;
  return v;
}
function safeNum(v, fallback=0){
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function premiumLayout(title='', extra={}){
  return Object.assign({
    title:{text:title,font:{color:'#f2f7ff',size:16,family:'Inter, system-ui'}},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{color:'#cbd7e7',family:'Inter, system-ui'},
    margin:{l:56,r:24,t:52,b:58},
    xaxis:{gridcolor:'rgba(255,255,255,.075)', zerolinecolor:'rgba(255,255,255,.12)'},
    yaxis:{gridcolor:'rgba(255,255,255,.075)', zerolinecolor:'rgba(255,255,255,.12)'}
  }, extra);
}
function dashKpiPanel(kpis=[]){
  return `<div class="dashboard-kpi-strip">${kpis.map(k=>`<article><span>${safeText(k.label)}</span><strong>${safeText(k.value)}</strong></article>`).join('')}</div>`;
}
function dashboardTable(table, title='Dataset records'){
  if(!table || !table.columns || !table.rows) return '';
  return `<section class="dashboard-table-card">
    <div class="table-title"><h2>${title}</h2><span>${table.rows.length} preview records</span></div>
    <div class="dashboard-table-scroll"><table class="data-table"><thead><tr>${table.columns.map(c=>`<th>${c.replaceAll('_',' ')}</th>`).join('')}</tr></thead><tbody>
      ${table.rows.map(row=>`<tr>${table.columns.map(c=>`<td>${safeText(row[c])}</td>`).join('')}</tr>`).join('')}
    </tbody></table></div>
  </section>`;
}
function drawPremiumBar(id, data, title='', orientation='v'){
  if(!data || !qs('#'+id) || !window.Plotly) return;
  const trace = orientation === 'h'
    ? {y:data.x, x:data.y, type:'bar', orientation:'h', marker:{color:'rgba(72,215,255,.86)'}, hovertemplate:'%{y}: %{x}<extra></extra>'}
    : {x:data.x, y:data.y, type:'bar', marker:{color:'rgba(72,215,255,.86)'}, hovertemplate:'%{x}: %{y}<extra></extra>'};
  Plotly.newPlot(id,[trace],premiumLayout(title, orientation==='h'?{margin:{l:150,r:20,t:50,b:40}}:{}),plotConfig());
}
function drawPremiumDonut(id, data, title=''){
  if(!data || !qs('#'+id) || !window.Plotly) return;
  Plotly.newPlot(id,[{labels:data.labels, values:data.values, type:'pie', hole:.62, textinfo:'percent', marker:{line:{color:'#0b1523',width:3}}}],premiumLayout(title,{showlegend:true,margin:{l:20,r:20,t:50,b:20}}),plotConfig());
}
function rowCount(table){ return table && table.rows ? table.rows.length : 0; }

async function initDashboard(){
  const page = qs('.dash-page');
  if(!page) return;
  const kind = page.dataset.dashboard;
  const data = await getJSON(`/api/dashboard/${kind}`);
  const root = qs('#dashboardContent');
  root.className = `dashboard-content dashboard-${kind}`;
  if(kind==='bookings') return renderBookingsDash(root,data);
  if(kind==='pickups') return renderPickupDash(root,data);
  if(kind==='congestion') return renderCongestionDash(root,data);
  if(kind==='cabs') return renderCabDash(root,data);
  if(kind==='roads') return renderRoadDash(root,data);
}

function renderBookingsDash(root,d){
  const channelRows = (d.bar?.x || []).map((x,i)=>({name:x,value:d.bar.y[i]})).sort((a,b)=>b.value-a.value);
  root.innerHTML = `
    ${dashKpiPanel(d.kpis)}
    <section class="booking-control-layout">
      <article class="dashboard-hero-card booking-hero-card">
        <span class="panel-label">Booking control</span>
        <h2>Where bookings are coming from</h2>
        <p>Channel and payment behaviour for event-day riders.</p>
        <div class="channel-stack">${channelRows.map(r=>`<div><span>${r.name}</span><b>${fmt(r.value)}</b></div>`).join('')}</div>
      </article>
      <article class="dashboard-plot-card wide"><div id="bookingChannelBar" class="plot"></div></article>
      <article class="dashboard-plot-card"><div id="bookingPaymentDonut" class="plot"></div></article>
    </section>
    ${dashboardTable(d.table,'Booking dataset')}
  `;
  drawPremiumBar('bookingChannelBar', d.bar, 'Bookings by channel');
  drawPremiumDonut('bookingPaymentDonut', d.donut, 'Payment mix');
}

function renderPickupDash(root,d){
  const rows = d.table?.rows || [];
  const max = Math.max(...rows.map(r=>safeNum(r.bookings)),1);
  const busiest = rows.slice().sort((a,b)=>safeNum(b.bookings)-safeNum(a.bookings)).slice(0,6);
  root.innerHTML = `
    ${dashKpiPanel(d.kpis)}
    <section class="pickup-command-layout">
      <article class="pickup-leaderboard">
        <div class="table-title"><h2>Demand leaderboard</h2><span>ranked pickup pressure</span></div>
        ${busiest.map((r,i)=>`<div class="leader-row">
          <b>${i+1}</b><div><strong>${safeText(r.zone)}</strong><span>${safeText(r.walk_min)} min walk · ${safeText(r.eta)} min ETA · ${safeText(r.accessible)} accessible</span><em style="width:${safeNum(r.bookings)/max*100}%"></em></div><strong>${safeText(r.bookings)}</strong>
        </div>`).join('')}
      </article>
      <article class="zone-insight-card">
        <span class="panel-label">Decision support</span>
        <h2>Choose zones by pressure, not just distance.</h2>
        <div class="zone-badges">${rows.slice(0,5).map(r=>`<span>${safeText(r.crowd)} · ${safeText(r.zone).split(' ')[0]}</span>`).join('')}</div>
      </article>
      <article class="dashboard-plot-card"><div id="pickupDemandBar" class="plot"></div></article>
      <article class="dashboard-plot-card"><div id="pickupAccessDonut" class="plot"></div></article>
    </section>
    ${dashboardTable(d.table,'Pickup zone dataset')}
  `;
  drawPremiumBar('pickupDemandBar', d.bar, 'Demand by zone', 'h');
  drawPremiumDonut('pickupAccessDonut', d.donut, 'Accessibility share');
}

function renderCongestionDash(root,d){
  const rows = d.table?.rows || [];
  const signals = rows.filter(r=>String(r.traffic_signals).toLowerCase()==='true' || String(r.traffic_signals)==='1').length;
  const crossings = rows.filter(r=>safeText(r.crossing,'')).length;
  const other = Math.max(rows.length - signals - crossings, 0);
  root.innerHTML = `
    <section class="traffic-command-board">
      <article class="traffic-tile high"><span>High watch</span><strong>${fmt(signals)}</strong><small>signal-controlled pressure points</small></article>
      <article class="traffic-tile medium"><span>Crossing flow</span><strong>${fmt(crossings)}</strong><small>pedestrian crossing points</small></article>
      <article class="traffic-tile low"><span>Road context</span><strong>${fmt(other)}</strong><small>supporting network points</small></article>
    </section>
    <section class="congestion-layout">
      <article class="dashboard-plot-card wide"><div id="congestionTypeBar" class="plot"></div></article>
      <article class="signal-console">
        <span class="panel-label">Signal readout</span><h2>Congestion records are road context, not customer choices.</h2>
        <p>Used internally to support safer pickup recommendations near stadium exits.</p>
        <div class="console-metric"><span>Total records</span><b>${fmt(rows.length)}</b></div>
        <div class="console-metric"><span>Dataset preview</span><b>${rowCount(d.table)}</b></div>
      </article>
    </section>
    ${dashboardTable(d.table,'Congestion dataset')}
  `;
  drawPremiumBar('congestionTypeBar', d.bar, 'Congestion point types');
}

function renderCabDash(root,d){
  const rows = d.table?.rows || [];
  const companyEta = (d.bar?.x || []).map((x,i)=>({company:x, eta:safeNum(d.bar.y[i])})).sort((a,b)=>a.eta-b.eta);
  root.innerHTML = `
    ${dashKpiPanel(d.kpis)}
    <section class="fleet-ops-layout">
      <article class="fleet-status-panel">
        <span class="panel-label">Dispatcher view</span><h2>Fleet readiness by ETA</h2>
        ${companyEta.slice(0,6).map(c=>`<div class="fleet-eta-row"><span>${c.company}</span><em><i style="width:${Math.max(12,100-(c.eta*8))}%"></i></em><b>${c.eta.toFixed(1)} min</b></div>`).join('')}
      </article>
      <article class="dashboard-plot-card"><div id="cabEtaBar" class="plot"></div></article>
      <article class="dashboard-plot-card compact"><div id="cabStatusDonut" class="plot"></div></article>
    </section>
    ${dashboardTable(d.table,'Cab allocation dataset')}
  `;
  drawPremiumBar('cabEtaBar', d.bar, 'Average ETA by company', 'h');
  drawPremiumDonut('cabStatusDonut', d.donut, 'Allocation status');
}

function renderRoadDash(root,d){
  const rows = d.table?.rows || [];
  const named = rows.filter(r=>safeText(r.name,'') !== '—').slice(0,8);
  root.innerHTML = `
    ${dashKpiPanel(d.kpis)}
    <section class="road-network-layout">
      <article class="road-map-console">
        <span class="panel-label">Road network</span><h2>Movement context around stadium exits.</h2>
        <div class="road-lines">${named.map((r,i)=>`<div><strong>${safeText(r.name,'Unnamed road')}</strong><span>${safeText(r.highway)} · ${safeText(r.oneway,'two-way')}</span><em style="width:${90-i*7}%"></em></div>`).join('')}</div>
      </article>
      <article class="dashboard-plot-card wide"><div id="roadTypeBar" class="plot"></div></article>
      <article class="dashboard-plot-card compact"><div id="roadDirectionDonut" class="plot"></div></article>
    </section>
    ${dashboardTable(d.table,'Road network dataset')}
  `;
  drawPremiumBar('roadTypeBar', d.bar, 'Road types', 'h');
  drawPremiumDonut('roadDirectionDonut', d.donut, 'Direction support');
}

/* CONFIRM PICKUP INTERACTION FIX */
function confirmSelectedPickup(){
  if(!selectedZone) return;
  const trip = {
    pickup: selectedZone.label || selectedZone.zone,
    zone: selectedZone.zone,
    walk_min: selectedZone.walk_min,
    eta: selectedZone.eta,
    crowd: customerLabelCrowd(selectedZone.crowd),
    confirmed_at: new Date().toLocaleString()
  };
  try{
    const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]');
    trips.unshift(trip);
    localStorage.setItem('crowdcab_trips', JSON.stringify(trips.slice(0,10)));
  }catch(e){ console.warn('Could not save trip', e); }

  const btn = qs('.confirm-pickup-btn');
  if(btn){
    btn.textContent = 'Pickup confirmed ✓';
    btn.classList.add('confirmed');
    btn.disabled = true;
  }

  if(routeLine){ routeLine.setStyle({weight:8, opacity:1}); }
  if(liveMap && selectedZone){
    liveMap.flyTo([selectedZone.lat, selectedZone.lng], 17, {animate:true, duration:.7});
  }

  let toast = qs('#pickupConfirmToast');
  if(!toast){
    toast = document.createElement('div');
    toast.id = 'pickupConfirmToast';
    toast.className = 'pickup-confirm-toast';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<strong>Pickup confirmed</strong><span>${trip.pickup} · ${trip.walk_min} min walk · ${trip.eta} min cab ETA</span><a href="/my-trips">View trip</a>`;
  toast.classList.add('show');
  setTimeout(()=>toast.classList.remove('show'), 5200);
}

document.addEventListener('click', (e)=>{
  const button = e.target.closest('.confirm-pickup-btn');
  if(button){
    e.preventDefault();
    confirmSelectedPickup();
  }
});

function initMyTripsPage(){
  const root = qs('#savedTripsList');
  if(!root) return;
  let trips = [];
  try{ trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]'); }catch(e){}
  if(!trips.length){
    root.innerHTML = `<div class="empty-state"><strong>No saved trips yet.</strong><span>Use the Live Map to choose a pickup zone.</span><a class="primary-btn" href="/map">Open Live Map</a></div>`;
    return;
  }
  root.innerHTML = trips.map(t=>`<article class="trip-card"><small>Confirmed pickup</small><strong>${t.pickup}</strong><span>${t.walk_min} min walk · ${t.eta} min cab ETA · ${t.crowd}</span><em>${t.confirmed_at}</em></article>`).join('');
}

document.addEventListener('DOMContentLoaded', initMyTripsPage);

/* MAP LEFT PANEL UPGRADE: trip planner has a clear role */
function destinationValue(){
  return (qs('#destinationInput')?.value || '').trim();
}
function updateTripPlannerSummary(p, confirmed=false){
  const box = qs('#tripPlannerSummary');
  if(!box || !p) return;
  const dest = destinationValue() || 'your destination';
  box.classList.remove('hidden');
  box.classList.toggle('confirmed', !!confirmed);
  box.innerHTML = `<small>${confirmed ? 'Pickup confirmed' : 'Your exit plan'}</small><strong>${p.label}</strong><span>${p.walk_min} min walk · ${p.eta} min cab ETA · ${customerLabelCrowd(p.crowd)} crowd<br>Destination: ${dest}</span>`;
}
function selectPickup(p, pan=false){
  if(!p || !liveMap) return;
  selectedZone = p;
  Object.entries(pickupMarkerMap).forEach(([zone,m]) => m.setIcon(markerIcon('pickup', zone===p.zone ? 'selected' : (mapData.pickups.find(x=>x.zone===zone)?.crowd || 'easy'))));
  if(routeLine) { liveMap.removeLayer(routeLine); routeLine = null; }
  routeLine = L.polyline([[mapData.stadium.lat,mapData.stadium.lng],[p.lat,p.lng]], {weight:6, opacity:.9, dashArray:'10 10'}).addTo(liveMap);
  pickupMarkerMap[p.zone]?.openPopup();
  if(pan) liveMap.flyTo([p.lat,p.lng], 17, {animate:true, duration:.6});
  const strip = qs('#selectedStrip');
  if(strip){
    strip.innerHTML = `<div><small>Selected pickup</small><strong>${p.label}</strong></div><div class="selected-stats"><span>${p.walk_min} min walk</span><span>${p.eta} min ETA</span><span>${customerLabelCrowd(p.crowd)}</span></div><p>${routeReason(p)}</p><button class="confirm-pickup-btn">Confirm pickup</button>`;
  }
  updateTripPlannerSummary(p, false);
}
function confirmSelectedPickup(){
  if(!selectedZone) return;
  const dest = destinationValue() || 'Not specified';
  const trip = {
    pickup: selectedZone.label || selectedZone.zone,
    zone: selectedZone.zone,
    walk_min: selectedZone.walk_min,
    eta: selectedZone.eta,
    crowd: customerLabelCrowd(selectedZone.crowd),
    destination: dest,
    confirmed_at: new Date().toLocaleString()
  };
  try{
    const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]');
    trips.unshift(trip);
    localStorage.setItem('crowdcab_trips', JSON.stringify(trips.slice(0,10)));
  }catch(e){ console.warn('Could not save trip', e); }
  const btn = qs('.confirm-pickup-btn');
  if(btn){
    btn.textContent = 'Pickup confirmed ✓';
    btn.classList.add('confirmed');
    btn.disabled = true;
  }
  updateTripPlannerSummary(selectedZone, true);
  if(routeLine){ routeLine.setStyle({weight:8, opacity:1}); }
  if(liveMap && selectedZone){ liveMap.flyTo([selectedZone.lat, selectedZone.lng], 17, {animate:true, duration:.7}); }
  let toast = qs('#pickupConfirmToast');
  if(!toast){
    toast = document.createElement('div');
    toast.id = 'pickupConfirmToast';
    toast.className = 'pickup-confirm-toast';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<strong>Pickup confirmed</strong><span>${trip.pickup} · ${trip.walk_min} min walk · ${trip.eta} min cab ETA<br>${trip.destination}</span><a href="/my-trips">View trip</a>`;
  toast.classList.add('show');
  setTimeout(()=>toast.classList.remove('show'), 5200);
}
document.addEventListener('DOMContentLoaded',()=>{
  qs('#destinationInput')?.addEventListener('input',()=>{ if(selectedZone) updateTripPlannerSummary(selectedZone, false); });
});

/* FINAL GPS-STYLE TRIP FLOW FIX */
function activeTripStore(trip){
  try{ localStorage.setItem('crowdcab_active_trip', JSON.stringify(trip)); }catch(e){}
}
function finalDestinationValue(){ return (qs('#destinationInput')?.value || '').trim() || 'Destination not set'; }
function finalTripFromSelected(){
  if(!selectedZone) return null;
  return {
    pickup: selectedZone.label || selectedZone.zone,
    zone: selectedZone.zone,
    lat: selectedZone.lat,
    lng: selectedZone.lng,
    walk_min: selectedZone.walk_min,
    eta: selectedZone.eta,
    crowd: customerLabelCrowd(selectedZone.crowd),
    destination: finalDestinationValue(),
    confirmed_at: new Date().toLocaleString()
  };
}
confirmSelectedPickup = function(){
  const trip = finalTripFromSelected();
  if(!trip) return;
  try{
    const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]');
    trips.unshift(trip);
    localStorage.setItem('crowdcab_trips', JSON.stringify(trips.slice(0,12)));
    activeTripStore(trip);
  }catch(e){ console.warn('Could not save trip', e); }
  const btn = qs('.confirm-pickup-btn');
  if(btn){ btn.textContent = 'Pickup confirmed ✓'; btn.classList.add('confirmed'); btn.disabled = true; }
  if(typeof updateTripPlannerSummary === 'function') updateTripPlannerSummary(selectedZone, true);
  if(routeLine){ routeLine.setStyle({weight:8, opacity:1, dashArray:null}); }
  if(liveMap && selectedZone){ liveMap.flyTo([selectedZone.lat, selectedZone.lng], 17, {animate:true, duration:.7}); }
  let toast = qs('#pickupConfirmToast');
  if(!toast){ toast = document.createElement('div'); toast.id = 'pickupConfirmToast'; toast.className = 'pickup-confirm-toast'; document.body.appendChild(toast); }
  toast.innerHTML = `<strong>Pickup confirmed</strong><span>${trip.pickup} · ${trip.walk_min} min walk · ${trip.eta} min cab ETA</span><div class="toast-actions"><a href="/guidance">Start GPS guidance</a><a href="/my-trips">View trip</a></div>`;
  toast.classList.add('show');
  setTimeout(()=>toast.classList.remove('show'), 7000);
};
function tripRouteSteps(trip){
  const pickup = trip.pickup || 'your pickup';
  const walk = Number(trip.walk_min || 3);
  const metres = Math.max(180, Math.round(walk * 85));
  return [
    {title:'Exit Suncorp Stadium', detail:'Use the closest open exit and head towards the stadium forecourt.', distance:'60 m'},
    {title:`Continue towards ${pickup}`, detail:'Follow the highlighted walking path on the map.', distance:`${Math.max(90, metres-90)} m`},
    {title:'Arrive at the pickup marker', detail:'Look for the highlighted CrowdCab pickup sign.', distance:'20 m'},
    {title:'Meet your cab', detail:`Your cab ETA is about ${trip.eta || '—'} min.`, distance:'arrival'}
  ];
}
initMyTripsPage = function(){
  const root = qs('#savedTripsList');
  if(!root) return;
  let trips = [];
  try{ trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]'); }catch(e){}
  if(!trips.length){
    root.innerHTML = `<div class="empty-state improved-empty"><strong>No saved trips yet.</strong><span>Confirm a pickup from the Live Map to start GPS-style guidance.</span><a class="primary-btn" href="/map">Open Live Map</a></div>`;
    return;
  }
  root.innerHTML = trips.map((t,i)=>`
    <article class="trip-card gps-trip-card">
      <div><small>Confirmed pickup</small><strong>${t.pickup}</strong><span>${t.destination || 'Destination not set'}</span></div>
      <div class="trip-pill-row"><span>${t.walk_min} min walk</span><span>${t.eta} min cab ETA</span><span>${t.crowd}</span></div>
      <em>${t.confirmed_at || ''}</em>
      <div class="trip-actions"><button class="start-guidance-link" data-trip-index="${i}">Start GPS guidance</button><a href="/map">Change pickup</a></div>
    </article>`).join('');
  qsa('.start-guidance-link', root).forEach(btn=>btn.addEventListener('click',()=>{
    const trip = trips[Number(btn.dataset.tripIndex)] || trips[0];
    activeTripStore(trip);
    window.location.href = '/guidance';
  }));
};
function gpsUserIcon(){
  return L.divIcon({className:'', html:`<div class="gps-user-dot"><span></span></div>`, iconSize:[42,42], iconAnchor:[21,21]});
}
function gpsPickupIcon(){
  return L.divIcon({className:'', html:`<div class="gps-destination-pin"><span></span></div>`, iconSize:[44,44], iconAnchor:[22,38]});
}
function buildWalkingRoute(start, end){
  const mid1 = [start[0] + (end[0]-start[0])*.34, start[1] + (end[1]-start[1])*.18];
  const mid2 = [start[0] + (end[0]-start[0])*.62, start[1] + (end[1]-start[1])*.72];
  return [start, mid1, mid2, end];
}
async function initGuidancePage(){
  const el = qs('#guidanceMap');
  if(!el || !window.L) return;
  let trip = null;
  try{ trip = JSON.parse(localStorage.getItem('crowdcab_active_trip') || 'null'); }catch(e){}
  if(!trip){ try{ const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]'); trip = trips[0]; }catch(e){} }
  if(!trip){
    qs('#gpsPickupTitle').textContent = 'No pickup selected';
    qs('#gpsPickupName').textContent = 'Choose pickup first';
    qs('#gpsCurrentInstruction').textContent = 'Open Live Map and confirm a pickup.';
    qs('#gpsSteps').innerHTML = `<li><strong>Open Live Map</strong><span>Choose and confirm a pickup option.</span></li>`;
    return;
  }
  const data = await getJSON('/api/map-feed');
  const pickup = (data.pickups || []).find(p => p.zone === trip.zone || p.label === trip.pickup) || trip;
  trip.lat = Number(trip.lat || pickup.lat);
  trip.lng = Number(trip.lng || pickup.lng);
  const walk = Number(trip.walk_min || pickup.walk_min || 3);
  const eta = Number(trip.eta || pickup.eta || 8);
  const crowd = trip.crowd || customerLabelCrowd(pickup.crowd);
  const metres = Math.max(180, Math.round(walk * 85));

  qs('#gpsPickupTitle').textContent = trip.pickup;
  qs('#gpsTopEta').textContent = `${walk} min`;
  qs('#gpsWalkTime').textContent = `${walk} min`;
  qs('#gpsDistance').textContent = `${metres} m`;
  qs('#gpsCabEta').textContent = `${eta} min`;
  qs('#gpsPickupName').textContent = trip.pickup;
  qs('#gpsCrowdLevel').textContent = `${crowd} crowd`;

  const steps = tripRouteSteps({...trip, walk_min:walk, eta});
  qs('#gpsCurrentInstruction').textContent = steps[0].title;
  qs('#gpsCurrentDistance').textContent = steps[0].distance;
  qs('#gpsSteps').innerHTML = steps.map((s,i)=>`<li class="${i===0?'active':''}" data-step="${i}"><strong>${s.title}</strong><span>${s.detail}</span><em>${s.distance}</em></li>`).join('');

  const start = [data.stadium.lat, data.stadium.lng];
  const end = [trip.lat, trip.lng];
  const routePts = buildWalkingRoute(start, end);
  const m = L.map(el, {zoomControl:true, attributionControl:true}).setView(start, 17);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'© OpenStreetMap'}).addTo(m);
  L.polyline(routePts, {weight:14, opacity:.22, color:'#001523'}).addTo(m);
  L.polyline(routePts, {weight:8, opacity:1, color:'#25c9ff', lineCap:'round', lineJoin:'round'}).addTo(m);
  const userMarker = L.marker(start, {icon:gpsUserIcon(), zIndexOffset:1000}).addTo(m).bindPopup('You are here');
  L.marker(end, {icon:gpsPickupIcon(), zIndexOffset:900}).addTo(m).bindPopup(`Pickup: ${trip.pickup}`).openPopup();
  m.fitBounds(routePts, {paddingTopLeft:[80,150], paddingBottomRight:[540,150], maxZoom:18});

  let activeStep = 0;
  function setStep(i){
    activeStep = Math.min(i, steps.length-1);
    qsa('#gpsSteps li').forEach((li,idx)=>li.classList.toggle('active', idx===activeStep));
    qs('#gpsCurrentInstruction').textContent = steps[activeStep].title;
    qs('#gpsCurrentDistance').textContent = steps[activeStep].distance;
    const target = routePts[Math.min(activeStep, routePts.length-1)] || end;
    userMarker.setLatLng(target);
    m.flyTo(target, activeStep === steps.length-1 ? 18 : 17, {animate:true, duration:.7});
    qs('#startGuidanceBtn').textContent = activeStep === steps.length-1 ? 'Arrived ✓' : (activeStep === 0 ? 'Start' : 'Next step');
  }
  qs('#startGuidanceBtn')?.addEventListener('click',()=>setStep(activeStep+1));
  qsa('#gpsSteps li').forEach(li=>li.addEventListener('click',()=>setStep(Number(li.dataset.step))));
}
document.addEventListener('DOMContentLoaded',()=>{ initMyTripsPage(); initGuidancePage(); });
