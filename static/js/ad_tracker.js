// Lightweight helper: renderAd(containerSelector, config) and trackAdClick(payload)
window.AdTracker = (function(){
  function _send(payload){
    try{
      const body = JSON.stringify(payload || {});
      if (navigator.sendBeacon){
        navigator.sendBeacon('/track-ad-click/', body);
      } else {
        fetch('/track-ad-click/', {method:'POST', body:body, headers:{'Content-Type':'application/json'}, keepalive:true}).catch(()=>{});
      }
    }catch(e){ console.warn(e); }
  }
  function renderAd(selector, cfg){
    const el = (typeof selector === 'string') ? document.querySelector(selector) : selector;
    if (!el) return;
    // minimal card to match server fragment shape (fallback)
    const html = `
      <div class="card ad-card mb-2" data-ad-id="${cfg.id}" data-ad-placement="${cfg.placement}" data-ad-target="${cfg.target}" data-ad-context="${cfg.context||''}" data-invoice-id="${cfg.invoice_id||''}">
        <div class="card-body d-flex gap-2 align-items-start">
          <div style="flex:0 0 54px;"><img src="${cfg.logo||'/static/img/ad-placeholder.png'}" alt="" style="width:48px;height:48px;border-radius:6px;object-fit:cover;" /></div>
          <div style="flex:1 1 auto;">
            <div style="font-weight:600;margin-top:2px;">${cfg.title||'Recommended for you'}</div>
            <div class="text-muted" style="font-size:0.85rem;margin-top:4px;">${cfg.description||''}</div>
            <div class="mt-2 d-flex gap-2">
              <a href="${cfg.target}" class="btn btn-sm btn-outline-primary ad-cta" target="_blank" rel="noopener noreferrer">Learn more</a>
              <a href="#" class="btn btn-sm btn-link text-muted ad-dismiss">Dismiss</a>
            </div>
          </div>
        </div>
      </div>`;
    el.insertAdjacentHTML('afterbegin', html);
    const root = el.querySelector('.ad-card');
    if (!root) return;
    root.querySelector('.ad-cta').addEventListener('click', function(){
      _send({ ad_id: cfg.id, placement: cfg.placement, url: cfg.target, user_context: cfg.context||'', invoice_id: cfg.invoice_id||null });
      // allow navigation
    });
    root.querySelector('.ad-dismiss').addEventListener('click', function(e){
      e.preventDefault();
      root.style.display = 'none';
      _send({ ad_id: cfg.id, placement: cfg.placement, url: '', user_context: cfg.context||'', invoice_id: cfg.invoice_id||null });
    });
  }
  function trackAdClick(payload){ _send(payload); }
  return { renderAd: renderAd, trackAdClick: trackAdClick };
})();

// Backwards-compatible global function used by older templates
window.trackAdClick = function(ad_id, placement, url, user_context, invoice_id){
  try{
    if (window.AdTracker && typeof window.AdTracker.trackAdClick === 'function'){
      window.AdTracker.trackAdClick({ ad_id: ad_id, placement: placement, url: url, user_context: user_context || '', invoice_id: invoice_id || null });
    } else {
      // fallback: send directly
      const payload = JSON.stringify({ ad_id: ad_id, placement: placement, url: url, user_context: user_context || '', invoice_id: invoice_id || null });
      if (navigator.sendBeacon){ navigator.sendBeacon('/track-ad-click/', payload); }
      else { fetch('/track-ad-click/', { method: 'POST', body: payload, headers: {'Content-Type':'application/json'}, keepalive:true }).catch(()=>{}); }
    }
  }catch(e){ console.warn('trackAdClick failed', e); }
};
