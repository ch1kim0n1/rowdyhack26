/* One clock for scroll choreography. Native scrolling owns the document;
   only the pictures ease toward it. No wheel, touch, or keyboard interception. */
(() => {
  'use strict';
  const clients = new Set();
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let raf = 0, last = 0, dirty = true, y = scrollY;
  const state = { y, rawY: y, dt: 0, vh: innerHeight, width: innerWidth, reduced: false };
  const stopped = () => preference.matches || document.body.classList.contains('motion-paused');
  function wake() {
    if (!raf && !document.hidden) raf = requestAnimationFrame(frame);
  }
  function invalidate() { dirty = true; wake(); }
  function frame(now) {
    raf = 0;
    if (document.hidden) return;
    const dt = Math.min(64, last ? now - last : 16.667);
    last = now;
    const rawY = scrollY, reduced = stopped();
    // Large anchor/history jumps arrive immediately; ordinary input settles in ~350ms.
    y = reduced || Math.abs(rawY - y) > innerHeight * 1.5
      ? rawY : y + (rawY - y) * (1 - Math.exp(-dt / 85));
    if (Math.abs(rawY - y) < .15) y = rawY;
    Object.assign(state, { y, rawY, dt, vh: innerHeight, width: innerWidth, reduced });
    if (dirty) {
      dirty = false;
      // All geometry reads precede the animation writes.
      for (const client of clients) client.measure?.(state);
    }
    for (const client of clients) client.render(state);
    if (y !== rawY || dirty) wake();
    else last = 0;
  }
  window.PremiereScroll = {
    subscribe(render, measure) {
      const client = { render, measure }; clients.add(client); invalidate();
      return () => clients.delete(client);
    },
    wake, invalidate,
    top(el) { let top = 0; for (let n = el; n; n = n.offsetParent) top += n.offsetTop; return top; },
    get state() { return { ...state, pending: !!raf }; },
  };
  addEventListener('scroll', wake, { passive: true });
  addEventListener('resize', invalidate, { passive: true });
  addEventListener('pageshow', invalidate);
  addEventListener('pagehide', () => { cancelAnimationFrame(raf); raf = 0; last = 0; });
  document.addEventListener('visibilitychange', () => {
    cancelAnimationFrame(raf); raf = 0; last = 0;
    if (!document.hidden) { y = scrollY; invalidate(); }
  });
  document.addEventListener('vaultmotionchange', invalidate);
  preference.addEventListener('change', invalidate);
  document.fonts?.ready.then(invalidate);
  document.addEventListener('load', invalidate, true);
  new ResizeObserver(invalidate).observe(document.body);
})();
