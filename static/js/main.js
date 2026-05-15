/* CrowdCab shared helpers and page boot utilities.
   Feature files safely exit when their DOM is not present. */
(function(){
  const CrowdCab = window.CrowdCab || {};
  const DESTINATION_STORAGE_KEY = 'crowdcab_destination';
  // Queensland-only fallback destination suggestions.
  // This keeps address help reliable without depending on a paid geocoding API.
  const DESTINATION_SUGGESTIONS = [
    'Brisbane CBD, QLD',
    'Brisbane City, QLD',
    'South Bank, QLD',
    'Fortitude Valley, QLD',
    'Roma Street Station, Brisbane QLD',
    'Brisbane Airport, QLD',
    'Suncorp Stadium, Milton QLD',
    'Queensland Tennis Centre, Tennyson QLD',
    'The Gabba, Woolloongabba QLD',
    'Milton Station, QLD',
    'South Brisbane Station, QLD',
    'Queen Street Mall, Brisbane QLD',
    'QUT Gardens Point, Brisbane QLD',
    'UQ St Lucia, QLD',
    'West End, QLD',
    'Kangaroo Point, QLD',
    'New Farm, QLD',
    'Toowong, QLD',
    'Auchenflower, QLD',
    'Paddington, QLD',
    'Red Hill, QLD',
    'Petrie Terrace, QLD',
    'Milton, QLD',
    'Tennyson, QLD',
    'Yeronga, QLD',
    'Fairfield, QLD',
    'Annerley, QLD',
    'Indooroopilly, QLD',
    'St Lucia, QLD',
    'Dutton Park, QLD',
    'Woolloongabba, QLD',
    'South Brisbane, QLD',
    'Spring Hill, QLD',
    'Newstead, QLD',
    'Bowen Hills, QLD',
    'Chermside, QLD',
    'Mount Gravatt, QLD',
    'Carindale, QLD',
    'Garden City, Upper Mount Gravatt QLD',
    'Eight Mile Plains, QLD',
    'Sunnybank, QLD',
    'Sunnybank Hills, QLD',
    'Macgregor, QLD',
    'Moorooka, QLD',
    'Rocklea, QLD',
    'Salisbury, QLD',
    'Coopers Plains, QLD',
    'Archerfield, QLD',
    'Acacia Ridge, QLD',
    'Morningside, QLD',
    'Coorparoo, QLD',
    'Camp Hill, QLD',
    'Carina, QLD',
    'Carina Heights, QLD',
    'Hawthorne, QLD',
    'Bulimba, QLD',
    'Norman Park, QLD',
    'Teneriffe, QLD',
    'Albion, QLD',
    'Windsor, QLD',
    'Lutwyche, QLD',
    'Nundah, QLD',
    'Toombul, QLD',
    'Hamilton, QLD',
    'Ascot, QLD',
    'Clayfield, QLD',
    'Eagle Farm, QLD',
    'Hendra, QLD',
    'Stafford, QLD',
    'Everton Park, QLD',
    'Mitchelton, QLD',
    'The Gap, QLD',
    'Ashgrove, QLD',
    'Bardon, QLD',
    'Kenmore, QLD',
    'Chapel Hill, QLD',
    'Fig Tree Pocket, QLD',
    'Jindalee, QLD',
    'Sherwood, QLD',
    'Graceville, QLD',
    'Corinda, QLD',
    'Oxley, QLD',
    'Moggill, QLD',
    'Capalaba, QLD',
    'Cleveland, QLD',
    'Wynnum, QLD',
    'Manly, QLD',
    'North Lakes, QLD',
    'Strathpine, QLD',
    'Carseldine, QLD',
    'Zillmere, QLD',
    'Aspley, QLD',
    'Bracken Ridge, QLD',
    'Sandgate, QLD',
    'Shorncliffe, QLD',
    'Logan Central, QLD',
    'Springwood, QLD',
    'Underwood, QLD',
    'Eight Mile Plains Busway Station, QLD',
    'Rochedale, QLD',
    'Rochedale South, QLD',
    'Daisy Hill, QLD',
    'Shailer Park, QLD',
    'Beenleigh, QLD',
    'Yatala, QLD',
    'Ormeau, QLD',
    'Coomera, QLD',
    'Upper Coomera, QLD',
    'Pimpama, QLD',
    'Helensvale, QLD',
    'Hope Island, QLD',
    'Ipswich Central, QLD',
    'Springfield Central, QLD',
    'Goodna, QLD',
    'Redbank Plains, QLD',
    'Forest Lake, QLD',
    'Redcliffe, QLD',
    'Gold Coast, QLD',
    'Surfers Paradise, QLD',
    'Southport, QLD',
    'Broadbeach, QLD',
    'Burleigh Heads, QLD',
    'Coolangatta, QLD',
    'Robina, QLD',
    'Sunshine Coast, QLD',
    'Maroochydore, QLD',
    'Mooloolaba, QLD',
    'Caloundra, QLD',
    'Kawana Waters, QLD',
    'Noosa Heads, QLD'
  ];

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
  CrowdCab.destinationStorageKey = DESTINATION_STORAGE_KEY;
  CrowdCab.destinationSuggestions = DESTINATION_SUGGESTIONS;
  CrowdCab.cleanDestination = value => String(value || '').trim().replace(/\s+/g, ' ');
  CrowdCab.isValidDestination = value => CrowdCab.cleanDestination(value).length >= 2;
  CrowdCab.saveDestination = value => {
    const cleaned = CrowdCab.cleanDestination(value);
    if(!cleaned) return '';
    try{
      localStorage.setItem(DESTINATION_STORAGE_KEY, cleaned);
      sessionStorage.setItem(DESTINATION_STORAGE_KEY, cleaned);
    }catch(e){}
    return cleaned;
  };
  CrowdCab.getStoredDestination = () => {
    try{
      return CrowdCab.cleanDestination(sessionStorage.getItem(DESTINATION_STORAGE_KEY) || localStorage.getItem(DESTINATION_STORAGE_KEY));
    }catch(e){
      return '';
    }
  };

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

  function normalizeSearchText(value){
    return CrowdCab.cleanDestination(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }

  function escapeHTML(value){
    return String(value || '').replace(/[&<>"']/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[char]);
  }

  function qldFallbackSuggestion(query){
    const cleaned = CrowdCab.cleanDestination(query).replace(/,\s*qld$/i, '');
    if(cleaned.length < 2) return '';
    return `${cleaned}, QLD`;
  }

  function destinationMatches(query){
    const cleaned = CrowdCab.cleanDestination(query);
    const normalizedQuery = normalizeSearchText(cleaned);
    if(normalizedQuery.length < 2) return [];

    const queryParts = normalizedQuery.split(' ').filter(Boolean);
    const scored = DESTINATION_SUGGESTIONS
      .map(item => {
        const normalizedItem = normalizeSearchText(item);
        const words = normalizedItem.split(' ');
        let score = -1;
        if(normalizedItem.startsWith(normalizedQuery)) score = 100;
        else if(words.some(word => word.startsWith(normalizedQuery))) score = 90;
        else if(normalizedItem.includes(normalizedQuery)) score = 75;
        else if(queryParts.every(part => normalizedItem.includes(part))) score = 60;
        return {item, score};
      })
      .filter(match => match.score >= 0)
      .sort((a, b) => b.score - a.score || a.item.localeCompare(b.item))
      .map(match => match.item);

    const fallback = qldFallbackSuggestion(cleaned);
    const unique = [...new Set(scored)];
    if(fallback && !unique.some(item => normalizeSearchText(item) === normalizeSearchText(fallback))){
      unique.push(fallback);
    }
    return unique.slice(0, 7);
  }

  function attachDestinationAutocomplete(input){
    if(!input || input.dataset.autocompleteReady === 'true') return;
    input.dataset.autocompleteReady = 'true';
    input.setAttribute('autocomplete', 'off');

    const field = input.closest('.route-input, .trip-field') || input.parentElement;
    if(!field) return;

    const list = document.createElement('div');
    list.className = 'destination-suggestions';
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    field.appendChild(list);

    const clearSuggestionSpace = () => {
      field.classList.remove('suggestions-open');
      field.style.marginBottom = '';
    };
    const reserveSuggestionSpace = matches => {
      const visibleRows = Math.min(matches.length, 4);
      field.classList.add('suggestions-open');
      field.style.marginBottom = `${visibleRows * 52 + 22}px`;
    };
    const hide = () => {
      list.hidden = true;
      list.innerHTML = '';
      clearSuggestionSpace();
    };
    const show = matches => {
      if(!matches.length){ hide(); return; }
      list.innerHTML = matches.map(item => `<button type="button" role="option">${escapeHTML(item)}</button>`).join('');
      list.hidden = false;
      reserveSuggestionSpace(matches);
      CrowdCab.qsa('button', list).forEach(button => {
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => {
          input.value = button.textContent.trim();
          CrowdCab.saveDestination(input.value);
          input.dispatchEvent(new Event('input', {bubbles:true}));
          hide();
        });
      });
    };

    input.addEventListener('input', () => {
      const query = CrowdCab.cleanDestination(input.value);
      if(query.length < 2){ hide(); return; }
      show(destinationMatches(query));
    });
    input.addEventListener('focus', () => {
      const query = CrowdCab.cleanDestination(input.value);
      if(query.length >= 2){
        show(destinationMatches(query));
      }
    });
    input.addEventListener('blur', () => setTimeout(hide, 120));
  }

  CrowdCab.onReady(() => {
    const form = CrowdCab.qs('#homePlanForm');
    const input = CrowdCab.qs('#homeDestinationInput', form || document);
    const submit = CrowdCab.qs('#homePlanSubmit', form || document);
    const feedback = CrowdCab.qs('#homePlanFeedback', form || document);
    if(!form || !input || !submit) return;

    const sync = () => {
      const destination = CrowdCab.cleanDestination(input.value);
      const valid = CrowdCab.isValidDestination(destination);
      submit.disabled = !valid;
      form.classList.toggle('has-destination', valid);
      if(feedback){
        feedback.textContent = valid
          ? `Plan preview: Suncorp Stadium to ${destination}.`
          : 'Enter a destination to see your best pickup.';
        feedback.classList.toggle('error', !!destination && !valid);
      }
    };

    input.addEventListener('input', sync);
    attachDestinationAutocomplete(input);
    form.addEventListener('submit', event => {
      const destination = CrowdCab.cleanDestination(input.value);
      if(!CrowdCab.isValidDestination(destination)){
        event.preventDefault();
        if(feedback){
          feedback.textContent = 'Please enter a destination before opening the Live Map.';
          feedback.classList.add('error');
        }
        input.focus();
        return;
      }
      CrowdCab.saveDestination(destination);
      form.action = `/map?destination=${encodeURIComponent(destination)}`;
    });
    sync();
  });

  CrowdCab.onReady(() => {
    attachDestinationAutocomplete(CrowdCab.qs('#destinationInput'));
  });
})();
