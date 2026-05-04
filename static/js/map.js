/* CrowdCab live map and map preview logic.
   Owns Leaflet setup, pickup marker rendering, recommendation tabs, and selected pickup state. */
(function(){
  const C = window.CrowdCab;
  if(!C) return;
  const {qs, qsa, getJSON, crowdClass, customerLabelCrowd} = C;

  const state = { liveMap:null, mapData:null, recommendationData:null, markerLayer:null, trafficLayer:null, routeMarkerLayer:null, selectedZone:null, pickupMarkerMap:{}, routeLine:null, routeSteps:[], activeStep:'plan' };

  function markerIcon(type, crowd='easy'){
    const cls = type === 'stadium' ? 'stadium-dot' : type === 'cab' ? 'cab-dot' : `map-marker marker-${crowd}`;
    return L.divIcon({className:'', html:`<div class="${cls}"></div>`, iconSize:[34,34], iconAnchor:[17,17]});
  }
  function trafficIcon(eventType='info'){
    const severe = ['crash', 'closure'].includes(eventType);
    const busy = ['congestion', 'roadwork'].includes(eventType);
    const caution = ['hazard', 'flood', 'special_event'].includes(eventType);
    const cls = severe ? 'traffic-red' : busy ? 'traffic-orange' : caution ? 'traffic-yellow' : 'traffic-blue';
    return L.divIcon({className:'', html:`<div class="traffic-event-marker ${cls}"></div>`, iconSize:[22,22], iconAnchor:[11,11]});
  }

  function pickupCrowdFromScore(p){
    const score = Number(p.congestion_score ?? 70);
    return score >= 70 ? 'easy' : score >= 45 ? 'medium' : 'busy';
  }
  function cabEtaForPickup(p){
    return Math.max(4, Math.round(Number(p.walk_min || 5) + (Number(p.congestion_score || 60) < 50 ? 3 : 1)));
  }
  function routeReason(p){
    return p.live_traffic_note || p.reason || 'Live scoring is checking walk, traffic, safety and driver access.';
  }
  function toMapPickup(p){
    if(p.lat && p.lng) return p;
    return {
      ...p,
      zone: p.pickup_point_id || p.label,
      lat: p.latitude,
      lng: p.longitude,
      eta: cabEtaForPickup(p),
      crowd: pickupCrowdFromScore(p),
      accessible: Math.round(Number(p.accessibility_score || 0)),
      score: p.total_score
    };
  }
  function scoredPickups(){
    return (state.recommendationData?.recommendations || []).map(toMapPickup);
  }

  function listForMode(mode){
    const list = scoredPickups();
    if(mode === 'fastest') return [...list].sort((a,b) => a.walk_min - b.walk_min || b.total_score - a.total_score);
    if(mode === 'quiet') return [...list].sort((a,b) => b.congestion_score - a.congestion_score || b.total_score - a.total_score);
    if(mode === 'accessible') return [...list].sort((a,b) => b.accessibility_score - a.accessibility_score || a.walk_min - b.walk_min);
    return list;
  }

  function fitMap(){
    if(!state.mapData || !state.liveMap) return;
    const pickups = scoredPickups();
    const pts = [[state.mapData.stadium.lat,state.mapData.stadium.lng], ...pickups.slice(0,10).map(p=>[p.lat,p.lng])];
    state.liveMap.fitBounds(pts, {paddingTopLeft:[380,80], paddingBottomRight:[520,80], maxZoom:16});
  }
  function setPlannerStep(step){
    state.activeStep = step;
    qsa('.trip-flow-mini [data-step]').forEach(btn => btn.classList.toggle('active', btn.dataset.step === step));
  }

  function fallbackWalkingRoute(p){
    if(!state.mapData) return [];
    const start = [state.mapData.stadium.lat, state.mapData.stadium.lng];
    const end = [p.lat, p.lng];
    const midA = [start[0], end[1]];
    const midB = [start[0] + ((end[0] - start[0]) * 0.58), end[1]];
    return [start, midA, midB, end];
  }

  function directionFromStep(step){
    const maneuver = step?.maneuver || {};
    const type = String(maneuver.type || 'continue').replaceAll('_', ' ');
    const modifier = maneuver.modifier ? ` ${String(maneuver.modifier).replaceAll('_', ' ')}` : '';
    const road = step?.name ? ` onto ${step.name}` : '';
    const distance = step?.distance ? ` (${Math.round(step.distance)} m)` : '';
    return `${type}${modifier}${road}${distance}`;
  }

  function renderRouteDirections(p, routeSteps=[], fallback=false){
    const box = qs('#tripPlannerSummary');
    if(!box || !p) return;
    const dest = (qs('#destinationInput')?.value || '').trim() || 'your destination';
    const stepText = routeSteps.length
      ? routeSteps.slice(0,3).map(directionFromStep)
      : ['Exit Suncorp Stadium', `Walk toward ${p.label}`, 'Meet your cab at the selected pickup'];
    box.classList.remove('hidden');
    box.innerHTML = `
      <small>Your exit plan</small>
      <strong>${p.label}</strong>
      <span>${p.walk_min} min walk - live score ${Math.round(p.total_score || p.score || 0)}<br>Destination: ${dest}</span>
      <ol class="mini-route-steps">
        ${stepText.map((s,i)=>`<li><b>${i+1}</b><span>${s}</span></li>`).join('')}
      </ol>
      <em>${fallback ? 'Approximate walking line shown. Live street routing was unavailable.' : 'Walking route follows nearby streets where routing data is available.'}</em>`;
  }

  function drawRouteMarkers(coords){
    state.routeMarkerLayer?.clearLayers();
    if(!coords.length || !state.routeMarkerLayer) return;
    coords.slice(1, -1).slice(0, 4).forEach((point, index) => {
      L.circleMarker(point, {
        radius: 5,
        color: '#07111d',
        weight: 2,
        fillColor: '#71ffd3',
        fillOpacity: 1
      }).addTo(state.routeMarkerLayer).bindPopup(`Turn point ${index + 1}`);
    });
  }

  async function drawWalkingRoute(p){
    if(!state.liveMap || !state.mapData || !p) return;
    if(state.routeLine){ state.liveMap.removeLayer(state.routeLine); state.routeLine = null; }
    const start = state.mapData.stadium;
    const url = `https://router.project-osrm.org/route/v1/foot/${start.lng},${start.lat};${p.lng},${p.lat}?overview=full&geometries=geojson&steps=true`;
    try{
      const response = await fetch(url, {cache:'no-store'});
      if(!response.ok) throw new Error(`OSRM ${response.status}`);
      const data = await response.json();
      const route = data.routes?.[0];
      const coords = route?.geometry?.coordinates?.map(([lng,lat]) => [lat,lng]);
      if(!coords?.length) throw new Error('No route geometry');
      state.routeSteps = route.legs?.[0]?.steps || [];
      state.routeLine = L.polyline(coords, {className:'walking-route-line', weight:7, opacity:.95}).addTo(state.liveMap);
      drawRouteMarkers(coords);
      renderRouteDirections(p, state.routeSteps, false);
    }catch(error){
      const coords = fallbackWalkingRoute(p);
      state.routeSteps = [];
      state.routeLine = L.polyline(coords, {className:'walking-route-line fallback-route-line', weight:7, opacity:.9, dashArray:'12 10'}).addTo(state.liveMap);
      drawRouteMarkers(coords);
      renderRouteDirections(p, [], true);
    }
  }

  function updateTripPlannerSummary(p, confirmed=false){
    const box = qs('#tripPlannerSummary');
    if(!box || !p) return;
    const dest = (qs('#destinationInput')?.value || '').trim() || 'your destination';
    box.classList.remove('hidden');
    box.classList.toggle('confirmed', !!confirmed);
    box.innerHTML = `<small>${confirmed ? 'Pickup confirmed' : 'Your exit plan'}</small><strong>${p.label}</strong><span>${p.walk_min} min walk - live score ${Math.round(p.total_score || p.score || 0)}<br>Destination: ${dest}</span>`;
  }

  function selectPickup(p, pan=false){
    if(!p || !state.liveMap || !state.mapData) return;
    state.selectedZone = p;
    Object.entries(state.pickupMarkerMap).forEach(([zone, marker]) => {
      const pickup = scoredPickups().find(x=>x.zone===zone);
      marker.setIcon(markerIcon('pickup', zone === p.zone ? 'selected' : (pickup?.crowd || 'easy')));
    });
    drawWalkingRoute(p);
    state.pickupMarkerMap[p.zone]?.openPopup();
    if(pan) state.liveMap.flyTo([p.lat,p.lng], 17, {animate:true, duration:.6});
    const strip = qs('#selectedStrip');
    if(strip){
      strip.innerHTML = `<div><small>Selected pickup</small><strong>${p.label}</strong></div><div class="selected-stats"><span>${p.walk_min} min walk</span><span>${Math.round(p.total_score || 0)} live score</span><span>${p.nearby_qldtraffic_events_count || 0} events</span></div><p>${routeReason(p)}</p><button class="confirm-pickup-btn">Confirm pickup</button>`;
    }
    setPlannerStep('choose');
  }

  function renderRecommendations(mode='best'){
    const list = qs('#recommendationList');
    if(!list || !state.mapData) return;
    const recs = (listForMode(mode) || []).slice(0,8);
    list.innerHTML = recs.map((p,i)=>`
      <button class="rec-card pickup-option-card ${state.selectedZone && state.selectedZone.zone===p.zone?'selected':''}" data-zone="${p.zone}">
        <span class="rec-badge">${i+1}</span>
        <span class="option-main"><h3>${p.label}</h3><p>${p.walk_min} min walk - score ${Math.round(p.total_score || 0)}</p><small>${routeReason(p)}</small></span>
        <span class="rec-meta"><em class="crowd-pill ${crowdClass(p.crowd)}">${p.nearby_qldtraffic_events_count ? 'Live event' : customerLabelCrowd(p.crowd)}</em><small>${Math.round(p.driver_access_score || 0)} driver access</small></span>
      </button>`).join('');
    qsa('.rec-card', list).forEach(btn => btn.addEventListener('click', () => {
      const p = scoredPickups().find(x=>x.zone===btn.dataset.zone);
      selectPickup(p, true);
      renderRecommendations(mode);
    }));
  }

  function renderMapFeed(mode='best'){
    if(!state.mapData || !state.markerLayer) return;
    state.markerLayer.clearLayers();
    state.trafficLayer?.clearLayers();
    state.pickupMarkerMap = {};
    L.marker([state.mapData.stadium.lat,state.mapData.stadium.lng], {icon:markerIcon('stadium')}).addTo(state.markerLayer).bindPopup('<b>Suncorp Stadium</b><br>Event pickup starts here');
    const pickups = scoredPickups();
    pickups.forEach(p => {
      const marker = L.marker([p.lat,p.lng], {icon:markerIcon('pickup', p.crowd)}).addTo(state.markerLayer)
        .bindPopup(`<b>${p.label}</b><br>${p.walk_min} min walk - score ${Math.round(p.total_score || 0)}<br>${routeReason(p)}`)
        .on('click',()=>{ selectPickup(p, true); renderRecommendations(qs('.tab-btn.active')?.dataset.mode || 'best'); });
      state.pickupMarkerMap[p.zone] = marker;
    });
    (state.mapData.cabs || []).slice(0,45).forEach(c=>{
      L.marker([c.lat,c.lng], {icon:markerIcon('cab')}).addTo(state.markerLayer).bindPopup(`<b>${c.company}</b><br>${c.eta} min ETA`);
    });
    (state.mapData.traffic_events || []).forEach(event => {
      L.marker([event.latitude,event.longitude], {icon:trafficIcon(event.type), zIndexOffset:700}).addTo(state.trafficLayer)
        .bindPopup(`<b>${String(event.type || 'info').replace('_',' ')}</b><br>${event.description || 'Traffic event'}`);
    });
    fitMap();
    selectPickup(pickups[0], false);
    renderRecommendations(mode);
  }

  function initLiveMap(){
    const el = qs('#liveMap');
    if(!el || !window.L) return;
    state.liveMap = L.map(el, { zoomControl:true, attributionControl:true }).setView([-27.4648,153.0095], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'OpenStreetMap'}).addTo(state.liveMap);
    state.markerLayer = L.layerGroup().addTo(state.liveMap);
    state.trafficLayer = L.layerGroup().addTo(state.liveMap);
    state.routeMarkerLayer = L.layerGroup().addTo(state.liveMap);
    Promise.all([getJSON('/api/map-feed'), getJSON('/api/recommend-pickups')]).then(([mapData, recData]) => {
      state.mapData = mapData;
      state.recommendationData = recData;
      renderMapFeed('best');
    }).catch(console.error);
    qs('#recenterMap')?.addEventListener('click',()=>{ const first = scoredPickups()[0]; if(first){ setPlannerStep('choose'); selectPickup(first, true); fitMap(); }});
    qsa('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>{
      qsa('.tab-btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      renderRecommendations(btn.dataset.mode);
    }));
    qsa('.trip-flow-mini [data-step]').forEach(btn => btn.addEventListener('click', () => {
      setPlannerStep(btn.dataset.step);
      if(btn.dataset.step === 'choose') qs('#recommendationList')?.scrollIntoView({block:'nearest', behavior:'smooth'});
      if(btn.dataset.step === 'ride') qs('.confirm-pickup-btn')?.click();
    }));
  }

  function initHomePreview(){
    const el = qs('#homePreviewMap');
    if(!el || !window.L) return;
    const map = L.map(el, {zoomControl:false, attributionControl:false, dragging:false, scrollWheelZoom:false, doubleClickZoom:false}).setView([-27.4648,153.0095], 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18}).addTo(map);
    getJSON('/api/map-feed').then(data=>{
      L.marker([data.stadium.lat,data.stadium.lng], {icon:markerIcon('stadium')}).addTo(map);
      data.pickups.slice(0,9).forEach(p=>L.marker([p.lat,p.lng], {icon:markerIcon('pickup', p.crowd)}).addTo(map));
      (data.cabs || []).slice(0,15).forEach(c=>L.marker([c.lat,c.lng], {icon:markerIcon('cab')}).addTo(map));
      const best = data.best[0];
      if(best){
        qs('#homeBestZone').textContent = best.label;
        qs('#homeBestWalk').textContent = best.walk_min + ' min';
        qs('#homeBestEta').textContent = best.eta + ' min';
        qs('#homeLiveStatus').textContent = best.crowd === 'busy' ? 'Busy exits' : best.crowd === 'medium' ? 'Balanced flow' : 'Smooth flow';
      }
      const pts = [[data.stadium.lat,data.stadium.lng], ...data.pickups.slice(0,9).map(p=>[p.lat,p.lng])];
      map.fitBounds(pts,{padding:[45,45],maxZoom:15});
    }).catch(console.error);
  }

  C.onReady(()=>{
    initHomePreview();
    initLiveMap();
    qs('#destinationInput')?.addEventListener('input',()=>{ setPlannerStep('plan'); if(state.selectedZone) renderRouteDirections(state.selectedZone, state.routeSteps, false); });
  });

  window.CrowdCabMap = {
    state, selectPickup, setPlannerStep,
    getSelectedZone: () => state.selectedZone,
    getRouteLine: () => state.routeLine,
    getLiveMap: () => state.liveMap,
    updateTripPlannerSummary
  };
})();
