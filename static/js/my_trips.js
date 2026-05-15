/* CrowdCab pickup plans.
   Shows one active guidance plan plus recent pickup plans; this is not a cab booking history. */
(function(){
  const C = window.CrowdCab;
  if(!C) return;
  const {qs, qsa, getJSON} = C;

  function activeTripStore(trip){
    if(window.CrowdCabBooking?.activeTripStore) return window.CrowdCabBooking.activeTripStore(trip);
    try{ localStorage.setItem('crowdcab_active_trip', JSON.stringify(trip)); }catch(e){}
  }

  async function initMyTripsPage(){
    const root = qs('#savedTripsList');
    if(!root) return;
    let trips = [];

    try{
      const data = await getJSON('/api/my-trips');
      trips = data.trips || [];
    }catch(e){ console.warn('Could not load database trips', e); }

    if(!trips.length){
      try{ trips = JSON.parse(localStorage.getItem('crowdcab_trips') || '[]'); }catch(e){}
    }

    if(!trips.length){
      root.innerHTML = `<div class="empty-state improved-empty"><strong>No pickup plan yet.</strong><span>Choose a pickup from the Live Map to start walking guidance.</span></div>`;
      return;
    }

    const active = trips[0];
    const recent = trips.slice(1, 4);
    const destinationText = trip => trip.destination && trip.destination !== 'Destination not set' ? trip.destination : 'Destination not set';
    const planCard = (t, i, featured=false) => `
      <article class="trip-card gps-trip-card pickup-plan-card ${featured ? 'active-pickup-plan' : ''}">
        <div class="pickup-plan-head">
          <small>${featured ? 'Active pickup plan' : 'Recent pickup plan'}</small>
          <strong>${t.pickup || 'Selected pickup'}</strong>
          <span>${destinationText(t)}</span>
        </div>
        <div class="trip-pill-row">
          <span>${t.walk_min || '--'} min walk</span>
          <span>${t.eta || '--'} min guidance ETA</span>
          <span>${t.crowd || 'Saved plan'}</span>
        </div>
        ${t.reason ? `<p>${t.reason}</p>` : ''}
        <em>${t.confirmed_at || ''}</em>
        <div class="trip-actions">
          <button class="start-guidance-link" data-trip-index="${i}">${featured ? 'Continue walking guidance' : 'Open guidance'}</button>
        </div>
      </article>`;

    root.innerHTML = `
      <div class="pickup-plans-layout">
        <div class="pickup-plans-main">
          <section class="active-plan-section">
            ${planCard(active, 0, true)}
          </section>
          ${recent.length ? `<section class="recent-plan-section"><div class="section-mini-title"><small>Recent plans</small><span>Last ${recent.length} saved pickup choices</span></div><div class="recent-plan-grid">${recent.map((trip, idx)=>planCard(trip, idx + 1)).join('')}</div></section>` : ''}
        </div>
        <aside class="pickup-plan-aside">
          <small>Next step</small>
          <strong>Walk to ${active.pickup || 'your selected pickup'}</strong>
          <p>${destinationText(active)}${active.destination && active.destination !== 'Destination not set' ? ' is saved as your destination.' : ' can be added from the Live Map before you start walking.'}</p>
          <div class="plan-aside-metrics">
            <span><b>${active.walk_min || '--'}</b> min walk</span>
            <span><b>${active.crowd || 'Ready'}</b> crowd status</span>
          </div>
        </aside>
      </div>
    `;

    qsa('.start-guidance-link', root).forEach(btn=>btn.addEventListener('click',()=>{
      const trip = trips[Number(btn.dataset.tripIndex)] || trips[0];
      activeTripStore(trip);
      window.location.href = '/guidance';
    }));
  }

  window.CrowdCabTrips = {initMyTripsPage};
  C.onReady(initMyTripsPage);
})();
