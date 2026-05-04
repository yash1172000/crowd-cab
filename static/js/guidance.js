/* CrowdCab guidance page logic.
   Keeps selected_pickup and recommended_pickup distinct, while the route always follows selected_pickup. */
(function(){
  const C = window.CrowdCab;
  if(!C) return;
  const {qs, qsa, getJSON, customerLabelCrowd} = C;

  const guidance = {
    map: null,
    userMarker: null,
    pickupMarker: null,
    routeLayers: [],
    routePts: [],
    steps: [],
    activeStep: 0,
    mapFeed: null,
    recommendations: null,
    selectedPickup: null,
    recommendedPickup: null,
    routeRequestId: 0
  };

  function gpsUserIcon(){
    return L.divIcon({className:'', html:`<div class="gps-user-person"><span>🚶</span></div>`, iconSize:[52,52], iconAnchor:[26,26]});
  }
  function gpsPickupIcon(){
    return L.divIcon({className:'', html:`<div class="gps-destination-pin"><span></span></div>`, iconSize:[44,44], iconAnchor:[22,38]});
  }
  function buildWalkingRoute(start, end){
    const mid1 = [start[0] + (end[0]-start[0])*.34, start[1] + (end[1]-start[1])*.18];
    const mid2 = [start[0] + (end[0]-start[0])*.62, start[1] + (end[1]-start[1])*.72];
    return [start, mid1, mid2, end];
  }
  async function fetchWalkingRoute(start, end){
    const url = `https://router.project-osrm.org/route/v1/foot/${start[1]},${start[0]};${end[1]},${end[0]}?overview=full&geometries=geojson&steps=true`;
    const response = await fetch(url, {cache:'no-store'});
    if(!response.ok) throw new Error(`OSRM ${response.status}`);
    const data = await response.json();
    const route = data.routes?.[0];
    const coords = route?.geometry?.coordinates?.map(([lng, lat]) => [lat, lng]);
    if(!coords?.length) throw new Error('No walking route geometry');
    return {coords, steps: route.legs?.[0]?.steps || []};
  }
  function osrmStepTitle(step){
    const maneuver = step?.maneuver || {};
    const type = String(maneuver.type || 'continue').replaceAll('_', ' ');
    const modifier = maneuver.modifier ? ` ${String(maneuver.modifier).replaceAll('_', ' ')}` : '';
    const road = step?.name ? ` onto ${step.name}` : '';
    if(type === 'depart') return step?.name ? `Start on ${step.name}` : 'Start walking';
    if(type === 'arrive') return 'Arrive at pickup';
    if(type === 'new name') return step?.name ? `Continue onto ${step.name}` : 'Continue straight';
    if(type === 'roundabout') return `Take the roundabout${road}`;
    if(type === 'turn') return `Turn${modifier}${road}`.trim();
    return `${type}${modifier}${road}`.trim();
  }
  function osrmStepDistance(step){
    return step?.distance ? `${Math.round(step.distance)} m` : '';
  }
  function normalizeLabel(value){
    return String(value || '').trim().toLowerCase();
  }
  function samePickup(a, b){
    if(!a || !b) return false;
    return normalizeLabel(a.pickup || a.label || a.zone) === normalizeLabel(b.pickup || b.label || b.zone);
  }
  function scoreBadge(label, value){
    const score = Math.round(Number(value || 0));
    const band = score >= 80 ? 'score-good' : score >= 50 ? 'score-mid' : 'score-low';
    return `<span class="${band}"><b>${score}</b>${label}</span>`;
  }
  function liveStatusBadge(){
    const realtime = guidance.recommendations?.realtime;
    if(!realtime) return '';
    const active = realtime.enabled && !realtime.fallback_used;
    const label = active && realtime.provider === 'open_data' ? 'Live Brisbane open traffic active' : active && realtime.provider === 'tomtom' ? 'Live TomTom Traffic API active' : active ? 'Live traffic active' : 'Using fallback traffic model';
    const isInternal = ['admin', 'developer'].includes(document.body?.dataset?.role || '');
    const authIssue = String(realtime.fallback_reason || '').includes('not_authorized');
    const devMessage = isInternal && authIssue ? `<p class="traffic-dev-note">TomTom key present but Traffic API access is not authorised.</p>` : '';
    return `<div class="live-traffic-badge ${active ? 'live-active' : 'live-fallback'}">${label}</div>${devMessage}`;
  }
  function liveNote(pickup){
    const source = pickup?.scores || pickup || {};
    const note = source.live_traffic_note || source.live_congestion_note || '';
    const current = Number(source.current_speed_kmph);
    const free = Number(source.free_flow_speed_kmph);
    const speed = Number.isFinite(current) && Number.isFinite(free) ? `<br>Current speed: ${Math.round(current)} km/h | Free-flow: ${Math.round(free)} km/h` : '';
    return note || speed ? `<p class="live-traffic-note">${note}${speed}</p>` : '';
  }
  function tripRouteSteps(pickup, routeSteps=null){
    if(routeSteps?.length){
      const usable = routeSteps.filter(step => step.distance > 5 || ['depart', 'arrive'].includes(step?.maneuver?.type));
      if(usable.length){
        return usable.map((step, index) => ({
          title: index === 0 ? 'Exit Suncorp Stadium' : osrmStepTitle(step),
          detail: step.name ? `Follow ${step.name}.` : 'Follow the highlighted walking route.',
          distance: osrmStepDistance(step),
          point: step?.maneuver?.location ? [step.maneuver.location[1], step.maneuver.location[0]] : null
        }));
      }
    }
    const name = pickup.pickup || pickup.label || 'your pickup';
    const walk = Number(pickup.walk_min || 3);
    const metres = Math.max(180, Math.round(walk * 85));
    return [
      {title:'Exit Suncorp Stadium', detail:'Use the closest open exit and head towards the stadium forecourt.', distance:'60 m', point:null},
      {title:`Continue towards ${name}`, detail:'Follow the highlighted walking path on the map.', distance:`${Math.max(90, metres-90)} m`, point:null},
      {title:'Arrive at the pickup marker', detail:'Look for the highlighted CrowdCab pickup sign.', distance:'20 m', point:null},
      {title:'Meet your cab', detail:`Your cab ETA is about ${pickup.eta || walk} min.`, distance:'arrival', point:null}
    ];
  }
  function pickupFromRecommendation(pickup){
    if(!pickup) return null;
    return {
      pickup: pickup.label,
      zone: pickup.label,
      lat: pickup.latitude,
      lng: pickup.longitude,
      walk_min: pickup.walk_min,
      eta: pickup.walk_min,
      crowd: `${Math.round(pickup.congestion_score)} congestion score`,
      destination: 'Recommended pickup',
      reason: pickup.reason,
      scores: pickup,
      confirmed_at: 'Recommended now'
    };
  }
  function comparisonInsight(selected, best){
    if(!selected?.scores || !best) return '';
    const insights = [];
    const congestionGain = Math.round(Number(best.congestion_score || 0) - Number(selected.scores.congestion_score || 0));
    const walkGain = Math.round(Number(selected.walk_min || 0) - Number(best.walk_min || 0));
    const driverGain = Math.round(Number(best.driver_access_score || 0) - Number(selected.scores.driver_access_score || 0));
    if(congestionGain > 0) insights.push(`${congestionGain} points better congestion score`);
    if(walkGain > 0) insights.push(`${walkGain} min shorter walk`);
    if(driverGain > 0) insights.push(`${driverGain} points higher driver access`);
    if(!insights.length) return '';
    return `<p class="comparison-insight">Better because: ${insights.slice(0,3).join(', ')}.</p>`;
  }
  function recommendationQueryForSelected(trip){
    const params = new URLSearchParams({priority:'balanced'});
    if(trip?.pickup || trip?.label) params.set('selected_label', trip.pickup || trip.label);
    if(trip?.zone) params.set('selected_zone', trip.zone);
    if(trip?.lat) params.set('selected_lat', trip.lat);
    if(trip?.lng) params.set('selected_lng', trip.lng);
    return `/api/recommend-pickups?${params.toString()}`;
  }
  function enrichSelectedPickup(trip){
    if(!trip) return null;
    const engineMatch = guidance.recommendations?.selected_pickup || (guidance.recommendations?.recommendations || []).find(p => (
      samePickup({pickup:p.label}, trip) || samePickup({pickup:p.pickup_point_id}, trip)
    ));
    const mapMatch = (guidance.mapFeed?.pickups || []).find(p => p.zone === trip.zone || p.label === trip.pickup);
    return {
      ...trip,
      lat: Number(trip.lat || mapMatch?.lat || engineMatch?.latitude),
      lng: Number(trip.lng || mapMatch?.lng || engineMatch?.longitude),
      walk_min: Number(trip.walk_min || mapMatch?.walk_min || engineMatch?.walk_min || 3),
      eta: Number(trip.eta || mapMatch?.eta || engineMatch?.walk_min || 8),
      reason: engineMatch?.reason || trip.reason || 'Selected pickup scored with current guidance data.',
      scores: engineMatch || trip.scores || null,
      crowd: trip.crowd || (mapMatch ? `${customerLabelCrowd(mapMatch.crowd)} crowd` : 'Selected pickup')
    };
  }
  function loadStoredTrip(){
    let trip = null;
    try{ trip = JSON.parse(localStorage.getItem('crowdcab_active_trip') || 'null'); }catch(e){}
    if(!trip){
      try{ const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]'); trip = trips[0]; }catch(e){}
    }
    return trip;
  }
  function saveSelectedPickup(pickup){
    try{ localStorage.setItem('crowdcab_active_trip', JSON.stringify(pickup)); }catch(e){}
  }

  function renderRouteSummary(){
    const selected = guidance.selectedPickup;
    if(!selected) return;
    const walk = Number(selected.walk_min || 3);
    const eta = Number(selected.eta || walk);
    const metres = Math.max(180, Math.round(walk * 85));
    qs('#gpsPickupTitle').textContent = selected.pickup;
    qs('#gpsTopEta').textContent = `${walk} min`;
    qs('#gpsWalkTime').textContent = `${walk} min`;
    qs('#gpsDistance').textContent = `${metres} m`;
    qs('#gpsCabEta').textContent = `${eta} min`;
    qs('#gpsPickupName').textContent = selected.pickup;
    qs('#gpsCrowdLevel').textContent = selected.crowd || 'Selected pickup';
  }

  function renderSteps(routeSteps=null){
    guidance.steps = tripRouteSteps(guidance.selectedPickup, routeSteps);
    guidance.activeStep = 0;
    qs('#gpsCurrentInstruction').textContent = guidance.steps[0].title;
    qs('#gpsCurrentDistance').textContent = guidance.steps[0].distance;
    qs('#gpsSteps').innerHTML = guidance.steps.map((s,i)=>`<li class="${i===0?'active':''}" data-step="${i}"><strong>${s.title}</strong><span>${s.detail}</span><em>${s.distance}</em></li>`).join('');
    qsa('#gpsSteps li').forEach(li=>li.addEventListener('click',()=>setStep(Number(li.dataset.step))));
    qs('#startGuidanceBtn').textContent = 'Start';
  }

  async function renderMapRoute(){
    const selected = guidance.selectedPickup;
    if(!guidance.map || !guidance.mapFeed || !selected) return;
    const requestId = ++guidance.routeRequestId;
    guidance.routeLayers.forEach(layer => guidance.map.removeLayer(layer));
    guidance.routeLayers = [];
    if(guidance.pickupMarker) guidance.map.removeLayer(guidance.pickupMarker);

    const start = [guidance.mapFeed.stadium.lat, guidance.mapFeed.stadium.lng];
    const end = [Number(selected.lat), Number(selected.lng)];
    guidance.routePts = buildWalkingRoute(start, end);
    guidance.routeLayers.push(L.polyline(guidance.routePts, {weight:14, opacity:.22, color:'#001523'}).addTo(guidance.map));
    guidance.routeLayers.push(L.polyline(guidance.routePts, {weight:8, opacity:1, color:'#25c9ff', lineCap:'round', lineJoin:'round'}).addTo(guidance.map));
    if(!guidance.userMarker){
      guidance.userMarker = L.marker(start, {icon:gpsUserIcon(), zIndexOffset:1000}).addTo(guidance.map).bindPopup('You are here');
    }else{
      guidance.userMarker.setLatLng(start);
    }
    guidance.pickupMarker = L.marker(end, {icon:gpsPickupIcon(), zIndexOffset:900}).addTo(guidance.map).bindPopup(`Pickup: ${selected.pickup}`).openPopup();
    guidance.map.fitBounds(guidance.routePts, {paddingTopLeft:[80,150], paddingBottomRight:[540,150], maxZoom:18});
    try{
      const route = await fetchWalkingRoute(start, end);
      if(requestId !== guidance.routeRequestId) return;
      guidance.routeLayers.forEach(layer => guidance.map.removeLayer(layer));
      guidance.routePts = route.coords;
      guidance.routeLayers = [
        L.polyline(guidance.routePts, {weight:14, opacity:.22, color:'#001523'}).addTo(guidance.map),
        L.polyline(guidance.routePts, {weight:8, opacity:1, color:'#25c9ff', lineCap:'round', lineJoin:'round'}).addTo(guidance.map)
      ];
      renderSteps(route.steps);
      guidance.map.fitBounds(guidance.routePts, {paddingTopLeft:[80,150], paddingBottomRight:[540,150], maxZoom:18});
    }catch(error){
      console.warn('Walking route unavailable, using approximate guidance route', error);
    }
  }

  function renderRecommendationPanel(){
    const panel = qs('#pickupRecommendationPanel');
    const best = guidance.recommendations?.recommended_pickup || guidance.recommendations?.best;
    if(!panel || !best || !guidance.selectedPickup) return;
    const selected = guidance.selectedPickup;
    const selectedScores = selected.scores || {};
    const mismatch = !samePickup(selected, {pickup:best.label});
    const selectedTotal = Number(selectedScores.total_score || 0);
    const bestTotal = Number(best.total_score || 0);
    const scoreGain = Math.max(0, Math.round(bestTotal - selectedTotal));
    const walkGain = Math.max(0, Math.round(Number(selected.walk_min || 0) - Number(best.walk_min || 0)));
    const switchText = walkGain > 0 ? `Save ${walkGain} min - switch` : scoreGain > 0 ? `Improve score +${scoreGain} - switch` : 'Switch to recommended';
    const updatedByRealtime = best.recommendation_updated_by_realtime || (guidance.recommendations?.recommendations || []).some(p => p.recommendation_updated_by_realtime);
    panel.innerHTML = `
      ${liveStatusBadge()}
      ${updatedByRealtime ? `<p class="realtime-decision-note">Recommendation updated due to live traffic conditions.</p>` : ''}
      ${mismatch ? `<div class="better-pickup-banner"><strong>Better pickup available: ${best.label}</strong><button data-switch-pickup="${best.pickup_point_id}">${switchText}</button></div>` : ''}
      <div class="recommendation-best selected-guidance-pickup">
        <small>Selected pickup</small>
        <strong>${selected.pickup}</strong>
        <p>${selected.reason || 'This is the pickup currently used for your walking route.'}</p>
        ${liveNote(selected)}
        <div class="recommendation-score-grid">
          ${scoreBadge('Walk', selectedScores.walking_score)}
          ${scoreBadge('Congestion', selectedScores.congestion_score)}
          ${scoreBadge('Safety', selectedScores.safety_score)}
          ${scoreBadge('Accessibility', selectedScores.accessibility_score)}
          ${scoreBadge('Driver access', selectedScores.driver_access_score)}
        </div>
      </div>
      <div class="recommendation-best">
        <small>Best recommended pickup</small>
        <strong>${best.label}</strong>
        <p>${best.reason}</p>
        ${liveNote(best)}
        ${comparisonInsight(selected, best)}
      </div>
      <div class="recommendation-alternatives">
        <small>Top alternatives</small>
        ${[best, ...(guidance.recommendations.alternatives || [])].map(p=>`
          <article class="guidance-alt-card">
            <div class="guidance-alt-main">
              <strong>${p.label}</strong>
              <span>${p.walk_min} min walk - score ${p.total_score}</span>
              ${liveNote(p)}
            </div>
            <div class="alternative-actions">
              <button data-view-pickup="${p.pickup_point_id}">View route</button>
              <button data-switch-pickup="${p.pickup_point_id}">${p.walk_min < selected.walk_min ? 'Take faster route' : 'Switch'}</button>
            </div>
          </article>`).join('')}
      </div>
    `;
    qsa('[data-view-pickup]', panel).forEach(btn => btn.addEventListener('click', () => viewPickup(btn.dataset.viewPickup)));
    qsa('[data-switch-pickup]', panel).forEach(btn => btn.addEventListener('click', () => switchPickup(btn.dataset.switchPickup)));
  }

  function applySelectedPickup(pickup, persist=false){
    guidance.selectedPickup = enrichSelectedPickup(pickup);
    if(!guidance.selectedPickup) return;
    renderRouteSummary();
    renderSteps();
    renderMapRoute();
    renderRecommendationPanel();
    if(persist) saveSelectedPickup(guidance.selectedPickup);
  }

  function recommendationById(id){
    return (guidance.recommendations?.recommendations || []).find(p => p.pickup_point_id === id || p.label === id);
  }
  function viewPickup(id){
    const pickup = pickupFromRecommendation(recommendationById(id));
    if(pickup) applySelectedPickup(pickup, false);
  }
  function switchPickup(id){
    const pickup = pickupFromRecommendation(recommendationById(id));
    if(pickup) applySelectedPickup(pickup, true);
  }

  function setStep(i){
    guidance.activeStep = Math.min(i, guidance.steps.length-1);
    qsa('#gpsSteps li').forEach((li,idx)=>li.classList.toggle('active', idx===guidance.activeStep));
    qs('#gpsCurrentInstruction').textContent = guidance.steps[guidance.activeStep].title;
    qs('#gpsCurrentDistance').textContent = guidance.steps[guidance.activeStep].distance;
    const step = guidance.steps[guidance.activeStep] || {};
    const target = step.point || guidance.routePts[Math.min(guidance.activeStep, guidance.routePts.length-1)] || guidance.routePts[guidance.routePts.length-1];
    if(target && guidance.userMarker && guidance.map){
      guidance.userMarker.setLatLng(target);
      guidance.map.flyTo(target, guidance.activeStep === guidance.steps.length-1 ? 18 : 17, {animate:true, duration:.7});
    }
    qs('#startGuidanceBtn').textContent = guidance.activeStep === guidance.steps.length-1 ? 'Arrived' : (guidance.activeStep === 0 ? 'Start' : 'Next step');
  }

  async function initGuidancePage(){
    const el = qs('#guidanceMap');
    if(!el || !window.L) return;
    const storedTrip = loadStoredTrip();
    guidance.recommendations = await getJSON(recommendationQueryForSelected(storedTrip));
    guidance.recommendedPickup = pickupFromRecommendation(guidance.recommendations.recommended_pickup || guidance.recommendations.best);
    guidance.mapFeed = await getJSON('/api/map-feed');

    guidance.map = L.map(el, {zoomControl:true, attributionControl:true}).setView([guidance.mapFeed.stadium.lat, guidance.mapFeed.stadium.lng], 17);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'OpenStreetMap'}).addTo(guidance.map);

    const selected = storedTrip || guidance.recommendedPickup;
    if(!selected){
      qs('#gpsPickupTitle').textContent = 'No pickup selected';
      qs('#gpsPickupName').textContent = 'Choose pickup first';
      qs('#gpsCurrentInstruction').textContent = 'Open Live Map and confirm a pickup.';
      qs('#gpsSteps').innerHTML = `<li><strong>Open Live Map</strong><span>Choose and confirm a pickup option.</span></li>`;
      return;
    }

    applySelectedPickup(selected, false);
    qs('#startGuidanceBtn')?.addEventListener('click',()=>setStep(guidance.activeStep+1));
  }

  window.CrowdCabGuidance = {initGuidancePage, switchPickup, viewPickup};
  C.onReady(initGuidancePage);
})();
