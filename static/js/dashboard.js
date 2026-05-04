/* CrowdCab internal dashboard logic.
   Renders dashboard, allocation, and system pages from existing Flask JSON endpoints. */
(function(){
  const C = window.CrowdCab;
  if(!C) return;
  const {qs, getJSON, fmt, safeText, safeNum} = C;

  function plotConfig(){ return {displayModeBar:false, responsive:true}; }
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
    if(!root) return;
    root.className = `dashboard-content dashboard-${kind}`;
    if(kind==='bookings') return renderBookingsDash(root,data);
    if(kind==='pickups') return renderPickupDash(root,data);
    if(kind==='congestion') return renderCongestionDash(root,data);
    if(kind==='cabs') return renderCabDash(root,data);
    if(kind==='roads') return renderRoadDash(root,data);
  }

  function renderBookingsDash(root,d){
    const channelRows = (d.bar?.x || []).map((x,i)=>({name:x,value:d.bar.y[i]})).sort((a,b)=>b.value-a.value);
    root.innerHTML = `${dashKpiPanel(d.kpis)}
      <section class="booking-control-layout">
        <article class="dashboard-hero-card booking-hero-card"><span class="panel-label">Booking control</span><h2>Where bookings are coming from</h2><p>Channel and payment behaviour for event-day riders.</p><div class="channel-stack">${channelRows.map(r=>`<div><span>${r.name}</span><b>${fmt(r.value)}</b></div>`).join('')}</div></article>
        <article class="dashboard-plot-card wide"><div id="bookingChannelBar" class="plot"></div></article>
        <article class="dashboard-plot-card"><div id="bookingPaymentDonut" class="plot"></div></article>
      </section>${dashboardTable(d.table,'Booking dataset')}`;
    drawPremiumBar('bookingChannelBar', d.bar, 'Bookings by channel');
    drawPremiumDonut('bookingPaymentDonut', d.donut, 'Payment mix');
  }

  function renderPickupDash(root,d){
    const rows = d.table?.rows || [];
    const max = Math.max(...rows.map(r=>safeNum(r.bookings)),1);
    const busiest = rows.slice().sort((a,b)=>safeNum(b.bookings)-safeNum(a.bookings)).slice(0,6);
    root.innerHTML = `${dashKpiPanel(d.kpis)}
      <section class="pickup-command-layout">
        <article class="pickup-leaderboard"><div class="table-title"><h2>Demand leaderboard</h2><span>ranked pickup pressure</span></div>${busiest.map((r,i)=>`<div class="leader-row"><b>${i+1}</b><div><strong>${safeText(r.zone)}</strong><span>${safeText(r.walk_min)} min walk - ${safeText(r.eta)} min ETA - ${safeText(r.accessible)} accessible</span><em style="width:${safeNum(r.bookings)/max*100}%"></em></div><strong>${safeText(r.bookings)}</strong></div>`).join('')}</article>
        <article class="zone-insight-card"><span class="panel-label">Decision support</span><h2>Choose zones by pressure, not just distance.</h2><div class="zone-badges">${rows.slice(0,5).map(r=>`<span>${safeText(r.crowd)} - ${safeText(r.zone).split(' ')[0]}</span>`).join('')}</div></article>
        <article class="dashboard-plot-card"><div id="pickupDemandBar" class="plot"></div></article>
        <article class="dashboard-plot-card"><div id="pickupAccessDonut" class="plot"></div></article>
      </section>${dashboardTable(d.table,'Pickup zone dataset')}`;
    drawPremiumBar('pickupDemandBar', d.bar, 'Demand by zone', 'h');
    drawPremiumDonut('pickupAccessDonut', d.donut, 'Accessibility share');
  }

  function renderCongestionDash(root,d){
    const rows = d.table?.rows || [];
    const signals = rows.filter(r=>String(r.traffic_signals).toLowerCase()==='true' || String(r.traffic_signals)==='1').length;
    const crossings = rows.filter(r=>safeText(r.crossing,'')).length;
    const other = Math.max(rows.length - signals - crossings, 0);
    root.innerHTML = `<section class="traffic-command-board"><article class="traffic-tile high"><span>High watch</span><strong>${fmt(signals)}</strong><small>signal-controlled pressure points</small></article><article class="traffic-tile medium"><span>Crossing flow</span><strong>${fmt(crossings)}</strong><small>pedestrian crossing points</small></article><article class="traffic-tile low"><span>Road context</span><strong>${fmt(other)}</strong><small>supporting network points</small></article></section>
      <section class="congestion-layout"><article class="dashboard-plot-card wide"><div id="congestionTypeBar" class="plot"></div></article><article class="signal-console"><span class="panel-label">Signal readout</span><h2>Congestion records are road context, not customer choices.</h2><p>Used internally to support safer pickup recommendations near stadium exits.</p><div class="console-metric"><span>Total records</span><b>${fmt(rows.length)}</b></div><div class="console-metric"><span>Dataset preview</span><b>${rowCount(d.table)}</b></div></article></section>${dashboardTable(d.table,'Congestion dataset')}`;
    drawPremiumBar('congestionTypeBar', d.bar, 'Congestion point types');
  }

  function renderCabDash(root,d){
    const companyEta = (d.bar?.x || []).map((x,i)=>({company:x, eta:safeNum(d.bar.y[i])})).sort((a,b)=>a.eta-b.eta);
    root.innerHTML = `${dashKpiPanel(d.kpis)}<section class="fleet-ops-layout"><article class="fleet-status-panel"><span class="panel-label">Dispatcher view</span><h2>Fleet readiness by ETA</h2>${companyEta.slice(0,6).map(c=>`<div class="fleet-eta-row"><span>${c.company}</span><em><i style="width:${Math.max(12,100-(c.eta*8))}%"></i></em><b>${c.eta.toFixed(1)} min</b></div>`).join('')}</article><article class="dashboard-plot-card"><div id="cabEtaBar" class="plot"></div></article><article class="dashboard-plot-card compact"><div id="cabStatusDonut" class="plot"></div></article></section>${dashboardTable(d.table,'Cab allocation dataset')}`;
    drawPremiumBar('cabEtaBar', d.bar, 'Average ETA by company', 'h');
    drawPremiumDonut('cabStatusDonut', d.donut, 'Allocation status');
  }

  function renderRoadDash(root,d){
    const rows = d.table?.rows || [];
    const named = rows.filter(r=>safeText(r.name,'') !== '-').slice(0,8);
    root.innerHTML = `${dashKpiPanel(d.kpis)}<section class="road-network-layout"><article class="road-map-console"><span class="panel-label">Road network</span><h2>Movement context around stadium exits.</h2><div class="road-lines">${named.map((r,i)=>`<div><strong>${safeText(r.name,'Unnamed road')}</strong><span>${safeText(r.highway)} - ${safeText(r.oneway,'two-way')}</span><em style="width:${90-i*7}%"></em></div>`).join('')}</div></article><article class="dashboard-plot-card wide"><div id="roadTypeBar" class="plot"></div></article><article class="dashboard-plot-card compact"><div id="roadDirectionDonut" class="plot"></div></article></section>${dashboardTable(d.table,'Road network dataset')}`;
    drawPremiumBar('roadTypeBar', d.bar, 'Road types', 'h');
    drawPremiumDonut('roadDirectionDonut', d.donut, 'Direction support');
  }

  async function initAllocations(){
    const root = qs('#allocationsContent') || qs('#allocationGrid');
    if(!root) return;
    const data = await getJSON('/api/allocations');
    const rows = (data.rows || []).slice(0,60);
    root.innerHTML = `<div class="allocation-grid">${rows.map(r=>`<article class="alloc-card"><strong>${safeText(r.driver_id,'Driver')}</strong><span>${safeText(r.cab_company_name,'Cab')} - ${safeText(r.allocated_vehicle_make_model,'Vehicle')}</span><small>${safeText(r.pickup_location_name)} - ${safeText(r.estimated_arrival_to_pickup_min)} min ETA - ${safeText(r.allocation_status,'Assigned')}</small></article>`).join('')}</div>`;
  }

  async function initSystem(){
    const root = qs('#systemContent') || qs('#systemFiles');
    if(!root) return;
    const data = await getJSON('/api/system');
    root.innerHTML = `<div class="system-overview-grid"><div class="system-flow-card"><h2>Data pipeline</h2><div class="flow-line">${data.flow.map(x=>`<span>${x}</span>`).join('')}</div></div><div class="system-role-card"><h2>Role access</h2>${data.roles.map(r=>`<span class="role-chip">${r}</span>`).join('')}</div></div><h2 class="console-heading">API endpoints</h2><div class="endpoint-grid">${data.endpoints.map(e=>`<div class="endpoint-card"><code>${e.path}</code><span>${e.purpose}</span></div>`).join('')}</div><h2 class="console-heading">Datasets</h2><div class="system-files dataset-grid">${data.files.map(f=>`<div class="file-card"><strong>${f.file}</strong><span>${fmt(f.rows)} rows</span><code>${(f.columns || []).join(', ')}</code></div>`).join('')}</div>`;
  }

  window.CrowdCabDashboard = {initDashboard, initAllocations, initSystem};
  C.onReady(()=>{ initDashboard(); initAllocations(); initSystem(); });
})();
