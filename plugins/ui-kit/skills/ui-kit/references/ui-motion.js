/*
 * ui-motion.js - UI transitions on spring.js (load spring.js first). No dependencies.
 *
 *   UIMotion.enter(el)                      fade + rise in on the 'ui' spring (~0.20 s, no bounce); returns a Promise
 *   UIMotion.exit(el)                       fade + sink out on 'uiExit' (~0.16 s); sets el.hidden at the end
 *   UIMotion.disclose(button, panel)        wire a menu / popover / accordion button: aria-expanded, Esc closes
 *   UIMotion.openDialog(dlg) / closeDialog(dlg, value)   native <dialog> with spring in / out
 *   UIMotion.toast(text, {title, tone, timeout})          a toast in the page's .ui-toasts live region
 *
 * Rules it keeps (from the engine's website kit): opacity is clamped to 0..1 so it never overshoots; motion is
 * time-based (any frame rate gives the same curve); a new move starts from wherever the element is, so a quick
 * open-close-open never jumps; prefers-reduced-motion makes every change instant.
 */
(function (root) {
  'use strict';
  const S = root.Spring;
  if (!S) throw new Error('ui-motion.js: load spring.js first');
  const reduced = () => root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DIST = 8;                     // px traveled while entering: matches --move-ui in tokens.css
  const runs = new WeakMap();         // el -> {p (0 hidden .. 1 shown), raf}

  function draw(el, p, dist) {
    el.style.opacity = String(S.clamp01(p));                              // opacity never overshoots
    el.style.transform = p >= 1 ? '' : `translateY(${((1 - p) * dist).toFixed(2)}px)`;
  }

  // move el's shown-ness from where it is now to `to` (0 or 1) on a spring preset
  function move(el, to, preset, dist) {
    const st = runs.get(el) || { p: to ? 0 : 1, raf: 0 };
    cancelAnimationFrame(st.raf);
    runs.set(el, st);
    const from = st.p;
    if (reduced() || from === to) { st.p = to; draw(el, to, dist); return Promise.resolve(); }
    const dur = S.settle({ preset }), t0 = performance.now();
    return new Promise((done) => {
      const step = (now) => {
        const t = (now - t0) / 1000;
        st.p = t >= dur ? to : from + (to - from) * S.progress(t, { preset });
        draw(el, st.p, dist);
        if (t >= dur) { st.raf = 0; done(); } else st.raf = requestAnimationFrame(step);
      };
      st.raf = requestAnimationFrame(step);
    });
  }

  function enter(el, o) {
    o = o || {};
    el.hidden = false;
    if (!runs.has(el)) draw(el, 0, o.distance != null ? o.distance : DIST);
    return move(el, 1, o.preset || 'ui', o.distance != null ? o.distance : DIST);
  }

  function exit(el, o) {
    o = o || {};
    return move(el, 0, o.preset || 'uiExit', o.distance != null ? o.distance : DIST).then(() => {
      if ((runs.get(el) || {}).p === 0 && o.hide !== false) el.hidden = true;
    });
  }

  // a button that shows / hides a panel (menu, popover, accordion section). The panel starts with `hidden`.
  function disclose(button, panel, o) {
    o = o || {};
    if (!panel.id) panel.id = 'ui-panel-' + Math.random().toString(36).slice(2, 8);
    button.setAttribute('aria-controls', panel.id);
    button.setAttribute('aria-expanded', String(!panel.hidden));
    const set = (open) => {
      button.setAttribute('aria-expanded', String(open));
      return open ? enter(panel) : exit(panel);
    };
    button.addEventListener('click', () => set(button.getAttribute('aria-expanded') !== 'true'));
    const onKey = (e) => {
      if (e.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') { set(false); button.focus(); }
    };
    button.addEventListener('keydown', onKey); panel.addEventListener('keydown', onKey);
    if (o.closeOnOutside !== false) {
      document.addEventListener('pointerdown', (e) => {
        if (button.getAttribute('aria-expanded') === 'true' && !panel.contains(e.target) && !button.contains(e.target)) set(false);
      });
    }
    return { open: () => set(true), close: () => set(false) };
  }

  function openDialog(dlg) {
    if (!dlg.open) dlg.showModal();
    return enter(dlg, { distance: 12 });
  }

  function closeDialog(dlg, value) {
    return exit(dlg, { hide: false, distance: 12 }).then(() => { dlg.close(value); runs.delete(dlg); dlg.style.opacity = ''; dlg.style.transform = ''; });
  }

  /*
   * Toasts are for confirmations that need no action ("Saved", "Copied"). A toast:
   *  - goes into the page's one live region (<div class="ui-toasts" role="status" aria-live="polite">)
   *  - stays at least 6 s (timeout: 0 keeps it until closed), and the timer pauses while hovered or focused
   *  - always has a Close button
   */
  function toast(text, o) {
    o = o || {};
    const region = o.region || document.querySelector('.ui-toasts');
    if (!region) throw new Error('ui-motion.js: add <div class="ui-toasts" role="status" aria-live="polite"></div> to the page');
    const el = document.createElement('div');
    el.className = 'ui-toast' + (o.tone ? ' ui-toast--' + o.tone : '');
    const msg = document.createElement('p'); msg.className = 'ui-toast__msg';
    if (o.title) { const b = document.createElement('strong'); b.textContent = o.title; msg.appendChild(b); }
    msg.appendChild(document.createTextNode(text));
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'ui-btn ui-btn--ghost ui-btn--sm'; close.textContent = 'Close';
    close.setAttribute('aria-label', 'Close notification');
    el.append(msg, close);
    region.appendChild(el);
    let timer = 0, left = o.timeout != null ? o.timeout : 6000, since = 0;
    const dismiss = () => { clearTimeout(timer); exit(el).then(() => el.remove()); };
    const start = () => { if (left > 0) { since = Date.now(); timer = setTimeout(dismiss, left); } };
    const pause = () => { if (timer) { clearTimeout(timer); timer = 0; left -= Date.now() - since; } };
    close.addEventListener('click', dismiss);
    el.addEventListener('pointerenter', pause); el.addEventListener('pointerleave', start);
    el.addEventListener('focusin', pause); el.addEventListener('focusout', start);
    enter(el); start();
    return { el, dismiss };
  }

  root.UIMotion = { enter, exit, disclose, openDialog, closeDialog, toast };
})(typeof self !== 'undefined' ? self : this);
