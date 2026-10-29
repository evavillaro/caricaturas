function feCart(){ try{ return JSON.parse(localStorage.getItem('fe_cart')||'[]'); }catch(e){ return []; } }
function feSave(c){ try{ localStorage.setItem('fe_cart', JSON.stringify(c)); }catch(e){} feCount(); }
function feCount(){ const n = feCart().reduce((s,i)=>s+i.qty,0); const el = document.getElementById('cartCount'); if (el) el.textContent = n || ''; }
function feCartAdd(it){ const c = feCart(); const same = c.find(x => x.slug===it.slug && x.size===it.size && x.frame===it.frame); if (same) same.qty = Math.min(10, same.qty + it.qty); else c.push(it); feSave(c); }
function feCartRemove(n){ const c = feCart(); c.splice(n,1); feSave(c); }
async function feCheckout(items){
  if (!items || !items.length) return;
  const value = items.reduce((s,i)=>s+i.price*i.qty,0);
  if (window.track) track('begin_checkout', {value});
  let email = null; try{ email = localStorage.getItem('fe_email'); }catch(e){}
  const r = await fetch('/api/checkout', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({items: items.map(i=>({slug:i.slug,size:i.size,frame:i.frame,qty:i.qty})), email})});
  const d = await r.json(); if (d.url) location.href = d.url; else alert('No se ha podido iniciar el pago. Inténtalo de nuevo.');
}
async function feSubscribe(e, source){
  e.preventDefault(); const f = e.target; const email = f.email.value.trim();
  const r = await fetch('/api/subscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, source})});
  if (r.ok){ try{ localStorage.setItem('fe_email', email); localStorage.setItem('fe_popup','done'); }catch(_){}
    if (window.track) track('sign_up', {});
    const ok = f.parentElement.querySelector('.popup-ok'); if (ok){ ok.hidden = false; f.hidden = true; } else { f.innerHTML = '<p>✦ ¡Gracias! Tu código es <b>BIENVENIDA15</b>.</p>'; } }
  return false;
}
function feClosePopup(){ document.getElementById('popup').hidden = true; try{ localStorage.setItem('fe_popup', String(Date.now())); }catch(e){} }
(function(){
  feCount();
  let seen = null; try{ seen = localStorage.getItem('fe_popup'); }catch(e){}
  const recently = seen && (seen === 'done' || Date.now() - Number(seen) < 7*864e5);
  if (!recently && !location.pathname.startsWith('/carrito') && !location.pathname.startsWith('/gracias')) setTimeout(()=>{ const p = document.getElementById('popup'); if (p) p.hidden = false; }, 12000);
})();
