// website kit: UI motion on spring.js ('ui' in, never bounces; opacity clamped), count-ups, consent-gated scripts, forms.
(function () {
  const S = window.Spring, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  // reveal: each element springs in (ui preset) when it enters the viewport; time-based, so frame rate doesn't matter
  const anim = (el, dur, fn) => { const t0 = performance.now(); const step = (now) => { const t = (now - t0) / 1000; fn(t); if (t < dur) requestAnimationFrame(step); }; requestAnimationFrame(step); };
  const show = (el, delay) => {
    if (reduce) { el.style.opacity = 1; el.style.transform = 'none'; return; }
    anim(el, 0.6 + delay, (t) => { const p = S.progress(t, { start: delay, preset: 'ui' }); el.style.opacity = S.clamp01(p); el.style.transform = `translateY(${(1 - p) * 24}px)`; });
  };
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target);
    const sib = [...e.target.parentElement.children].filter((x) => x.classList.contains('reveal')); show(e.target, Math.max(0, sib.indexOf(e.target)) * 0.06); } }), { threshold: 0.15 });
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
  // count-ups: the number counts on a critically damped spring and never passes its value; the last frame writes the
  // authored text exactly ("1,998", "99.5%"). Values with more than one number ("12x40", "7-5") are not animated.
  const cio = new IntersectionObserver((es) => es.forEach((e) => { if (!e.isIntersecting) return; cio.unobserve(e.target);
    const raw = e.target.dataset.count, m = raw.match(/^([^\d]*)([\d,]+(?:\.\d+)?)(.*)$/); if (!m || reduce || /\d/.test(m[1] + m[3])) return;
    const v = parseFloat(m[2].replace(/,/g, '')), dec = (m[2].split('.')[1] || '').length, comma = m[2].includes(','), T = 1.4;
    anim(e.target, T, (t) => { if (t >= T) { e.target.textContent = raw; return; }
      const x = v * S.clamp01(S.progress(t, { zeta: 1, omega: 6 }));
      e.target.textContent = m[1] + (comma ? x.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : x.toFixed(dec)) + m[3]; }); }), { threshold: 0.4 });
  document.querySelectorAll('[data-count]').forEach((el) => cio.observe(el));
  // cookie consent: nothing non-essential loads until Accept; Reject is the same size and weight; the choice is remembered
  const ck = document.querySelector('.cookie');
  const load = () => document.querySelectorAll('script[data-consent]').forEach((s) => { const n = document.createElement('script'); n.src = s.getAttribute('src'); document.body.appendChild(n); });
  let choice = null; try { choice = localStorage.getItem('cookie-choice'); } catch (e) {}
  if (ck) { if (!choice) ck.hidden = false; else if (choice === 'accept') load();
    ck.querySelectorAll('[data-cookie]').forEach((b) => b.addEventListener('click', () => { const c = b.dataset.cookie; try { localStorage.setItem('cookie-choice', c); } catch (e) {} ck.hidden = true; if (c === 'accept') load(); })); }
  document.querySelectorAll('[data-cookie-reset]').forEach((b) => b.addEventListener('click', () => { try { localStorage.removeItem('cookie-choice'); } catch (e) {} location.reload(); }));
  // forms: native validation with readable messages; nothing sends without the consent box ticked
  document.querySelectorAll('form.form').forEach((f) => f.addEventListener('submit', (ev) => {
    const msg = f.querySelector('.form-msg');
    if (!f.checkValidity()) { ev.preventDefault(); const bad = f.querySelector(':invalid'); bad && bad.focus(); msg.textContent = 'Please fill in the highlighted field' + (bad && bad.type === 'checkbox' ? ' (the consent box).' : '.'); return; }
    if (!f.getAttribute('action')) { ev.preventDefault(); msg.textContent = 'This form is not connected yet.'; }
  }));
})();
