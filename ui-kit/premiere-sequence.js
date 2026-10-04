/* Bounded decoded-image cache. Scroll selects pictures, never queues video seeks.
   Six requests, coarse coverage first, then a window around the current frame. */
(() => {
  'use strict';
  window.createPremiereSequence = (canvas, { onReady, onFailure }) => {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) { onFailure(); return null; }
    // The budget follows the viewport, so a rotated phone or a narrowed window gives memory back.
    const compact = matchMedia('(max-width: 720px)');
    const COUNT = 501, CONCURRENCY = 6;
    const limit = () => compact.matches ? 32 : 56, radius = () => compact.matches ? 10 : 18;
    const cache = new Map(), pending = new Set(), failed = new Set();
    const anchors = [0, 500, 250, 125, 375, 62, 187, 312, 437];
    let target = 0, shown = -1, active = false, announced = false, errors = 0;
    canvas.width = 960; canvas.height = 540;
    function evict() {
      while (cache.size > limit()) {
        const candidates = [...cache.keys()].filter(n => !anchors.includes(n) && n !== shown);
        candidates.sort((a, b) => Math.abs(b - target) - Math.abs(a - target));
        cache.delete(candidates[0]);
      }
    }
    function draw() {
      if (!active || !cache.size) return;
      let best = -1, distance = Infinity;
      for (const n of cache.keys()) {
        const d = Math.abs(target - n);
        if (d < distance) { best = n; distance = d; }
      }
      if (best === shown) return;
      ctx.drawImage(cache.get(best), 0, 0, 960, 540);
      shown = best; canvas.dataset.frame = String(best);
      if (!announced) { announced = true; onReady(); }
    }
    function pump() {
      if (!active || document.hidden) return;
      // Target wins even on a deep jump. Coarse anchors make the first scrub usable.
      const queue = [target, ...anchors];
      for (let d = 1; d <= radius(); d++) queue.push(target + d, target - d);
      for (const n of queue) {
        if (pending.size >= CONCURRENCY) break;
        if (n < 0 || n >= COUNT || cache.has(n) || pending.has(n) || failed.has(n)) continue;
        pending.add(n);
        const img = new Image();
        img.decoding = 'async';
        const timeout = setTimeout(() => img.onerror?.(), 8000);
        img.onload = async () => {
          clearTimeout(timeout);
          try { await img.decode(); } catch { /* onload already supplied usable pixels */ }
          pending.delete(n); cache.set(n, img); evict(); draw(); pump();
        };
        img.onerror = () => {
          clearTimeout(timeout); img.onload = img.onerror = null;
          pending.delete(n); failed.add(n); errors++;
          if (!announced && errors >= CONCURRENCY) { active = false; onFailure(); }
          else pump();
        };
        img.src = `media/scroll-frames/frame-${String(n).padStart(3, '0')}.webp`;
      }
    }
    compact.addEventListener('change', evict);
    return {
      render(frame) { target = Math.max(0, Math.min(COUNT - 1, frame)); draw(); pump(); },
      setActive(value) { active = value; if (active) { draw(); pump(); } },
      get stats() { return { cached: cache.size, limit: limit(), pending: pending.size, target, shown, errors }; },
    };
  };
})();
