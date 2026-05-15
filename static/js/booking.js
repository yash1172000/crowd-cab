/* CrowdCab booking creation logic.
   Persists the selected pickup through POST /api/bookings and stores the active trip for guidance. */
(function(){
  const C = window.CrowdCab;
  if(!C) return;
  const {qs, postJSON, customerLabelCrowd} = C;

  function activeTripStore(trip){
    try{ localStorage.setItem('crowdcab_active_trip', JSON.stringify(trip)); }catch(e){}
  }

  function finalDestinationValue(){
    return (qs('#destinationInput')?.value || '').trim() || C.getStoredDestination?.() || 'Destination not set';
  }

  function finalTripFromSelected(){
    const selectedZone = window.CrowdCabMap?.getSelectedZone();
    const selectedVenue = window.CrowdCabMap?.getSelectedVenue?.();
    const userLocation = window.CrowdCabMap?.getUserLocation?.();
    if(!selectedZone) return null;
    return {
      venue_id: selectedVenue?.venue_id || window.CrowdCabMap?.getSelectedVenueId?.() || 'suncorp_stadium',
      venue_name: selectedVenue?.name || 'Suncorp Stadium',
      pickup: selectedZone.label || selectedZone.zone,
      zone: selectedZone.zone,
      lat: selectedZone.lat,
      lng: selectedZone.lng,
      walk_min: selectedZone.walk_min,
      eta: selectedZone.eta || selectedZone.walk_min,
      crowd: customerLabelCrowd(selectedZone.crowd),
      reason: selectedZone.reason || selectedZone.live_traffic_note,
      scores: selectedZone,
      destination: finalDestinationValue(),
      origin_lat: userLocation?.lat || null,
      origin_lng: userLocation?.lng || null,
      origin_label: userLocation ? 'My location' : selectedVenue?.name || 'Event venue',
      confirmed_at: new Date().toLocaleString()
    };
  }

  async function confirmSelectedPickup(){
    const trip = finalTripFromSelected();
    if(!trip) return;
    const btn = qs('.confirm-pickup-btn');
    if(btn){ btn.textContent = 'Confirming...'; btn.disabled = true; }

    let savedTrip = trip;
    try{
      const saved = await postJSON('/api/bookings', trip);
      savedTrip = {...trip, ...(saved.booking || {})};
      const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]');
      trips.unshift(savedTrip);
      localStorage.setItem('crowdcab_trips', JSON.stringify(trips.slice(0,12)));
      activeTripStore(savedTrip);
    }catch(e){
      console.warn('Could not save trip', e);
      if(e.status === 401){
        if(btn){ btn.textContent = 'Login to confirm'; btn.disabled = false; }
        window.location.href = '/login?next=/map';
        return;
      }
      try{
        const trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]');
        trips.unshift(trip);
        localStorage.setItem('crowdcab_trips', JSON.stringify(trips.slice(0,12)));
        activeTripStore(trip);
      }catch(localErr){ console.warn('Could not save local trip', localErr); }
    }

    if(btn){ btn.textContent = 'Pickup confirmed'; btn.classList.add('confirmed'); btn.disabled = true; }
    window.CrowdCabMap?.setPlannerStep?.('ride');
    window.CrowdCabMap?.updateTripPlannerSummary(window.CrowdCabMap.getSelectedZone(), true);

    const routeLine = window.CrowdCabMap?.getRouteLine();
    if(routeLine) routeLine.setStyle({weight:8, opacity:1, dashArray:null});
    const liveMap = window.CrowdCabMap?.getLiveMap();
    const selectedZone = window.CrowdCabMap?.getSelectedZone();
    if(liveMap && selectedZone) liveMap.flyTo([selectedZone.lat, selectedZone.lng], 17, {animate:true, duration:.7});

    let toast = qs('#pickupConfirmToast');
    if(!toast){
      toast = document.createElement('div');
      toast.id = 'pickupConfirmToast';
      toast.className = 'pickup-confirm-toast';
      document.body.appendChild(toast);
    }
    toast.innerHTML = `<strong>Pickup confirmed</strong><span>${savedTrip.pickup} - ${savedTrip.walk_min} min walk</span><div class="toast-actions"><a href="/guidance">Start GPS guidance</a><a href="/my-trips">View trip</a></div>`;
    toast.classList.add('show');
    setTimeout(()=>toast.classList.remove('show'), 7000);
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('.confirm-pickup-btn');
    if(!button) return;
    event.preventDefault();
    confirmSelectedPickup();
  });

  window.CrowdCabBooking = {confirmSelectedPickup, activeTripStore};
})();
