/* CrowdCab shared helpers and page boot utilities.
   Feature files safely exit when their DOM is not present. */
(function(){
  const CrowdCab = window.CrowdCab || {};

  CrowdCab.qs = (selector, root=document) => root.querySelector(selector);
  CrowdCab.qsa = (selector, root=document) => [...root.querySelectorAll(selector)];
  CrowdCab.fmt = value => Number(value || 0).toLocaleString();
  CrowdCab.crowdClass = crowd => crowd === 'busy' ? 'crowd-busy' : (crowd === 'medium' ? 'crowd-medium' : 'crowd-easy');
  CrowdCab.customerLabelCrowd = crowd => crowd === 'busy' ? 'Busy' : crowd === 'medium' ? 'Moderate' : 'Less crowded';
  CrowdCab.safeText = (value, fallback='-') => {
    if(value === undefined || value === null || value === '' || String(value).toLowerCase() === 'nan') return fallback;
    return value;
  };
  CrowdCab.safeNum = (value, fallback=0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  };
  CrowdCab.onReady = fn => document.addEventListener('DOMContentLoaded', fn);

  CrowdCab.getJSON = async url => {
    const response = await fetch(url);
    if(!response.ok) throw new Error(url);
    return response.json();
  };

  CrowdCab.postJSON = async (url, data) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const payload = await response.json().catch(() => ({}));
    if(!response.ok){
      const error = new Error(payload.error || url);
      error.status = response.status;
      throw error;
    }
    return payload;
  };

  window.CrowdCab = CrowdCab;
})();
