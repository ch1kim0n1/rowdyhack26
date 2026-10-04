/* Scroll cinema: the page's scenes, and where the scroll has each of them.
   premiere-scroll.js keeps the one clock (native scroll; only the pictures ease).
   This file gives that clock a script to follow. Every [data-cinematic-scene] gets
   a progress, the handlers registered for it by name draw it from that, and every
   [data-motion] element stands wherever the scroll has put it in its preset
   (motion-presets.js). Nothing here plays by itself, so scrolling back runs it all
   backwards.
   Animation state only. Nothing in this file reads, holds or waits on the rig's data. */
(() => {
  'use strict';
  const clock = window.PremiereScroll, presets = window.MotionPresets;
  if (!clock) return;
  const root = document.documentElement;
  const clamp = (v, min = 0, max = 1) => Math.min(max, Math.max(min, v));
  const lerp = (from, to, p) => from + (to - from) * p;
  const range = (p, from, to) => clamp((p - from) / Math.max(1e-4, to - from));
  const smooth = p => p * p * (3 - 2 * p);

  /* An element starts its preset as its top comes in at the foot of the window and is at
     rest half a window later. data-motion-start and data-motion-span move those two;
     data-motion-order holds a neighbour back by a step, so a row arrives in turn. */
  const START = .96, SPAN = .5, ORDER = 32;
  const LEAST = .2;         /* the end of the page still gets this much of a window to arrive in */
  /* An element with a way out (data-motion-out) leaves as its foot nears the top of the
     window, and has gone by the time it is under the marquee. Once it is above the
     window altogether it is put back as it was, so nothing off-screen is left hidden. */
  const OUT = [.085, .2];

  const handlers = new Map();
  const motion = { activeScene: '', progress: 0 };      /* animation state, and only that */
  let scenes = [], elements = [], found = false, live = null, compact = null;

  const watch = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      const scene = scenes.find(s => s.el === entry.target);
      if (!scene) continue;
      scene.active = entry.isIntersecting;
      scene.flush = true;                               /* one last draw as it leaves, at its final value */
      entry.target.dataset.active = String(entry.isIntersecting);
    }
    clock.wake();
  }, { rootMargin: '100% 0px' }) : null;

  function find() {
    found = true;
    scenes = [...document.querySelectorAll('[data-cinematic-scene]')].map(el => {
      const written = new Map();
      return {
        el, name: el.dataset.cinematicScene, top: 0, height: 0, progress: 0, enter: 0, exit: 0,
        active: true, flush: true,
        /* a custom property for the scene's own CSS, written only when it changes */
        set(name, value) {
          if (written.get(name) === value) return;
          written.set(name, value);
          el.style.setProperty(name, value);
        },
        get(name) { return written.get(name); },
      };
    });
    scenes.forEach(scene => watch?.observe(scene.el));
  }

  function cast() {
    elements.forEach(element => element.clear());
    elements = presets ? [...document.body.querySelectorAll('[data-motion]')]
      .map(el => presets.build(el)).filter(Boolean) : [];
  }

  function measure({ vh, reduced }) {
    if (!found) find();
    /* Built when motion is first allowed, and again if the window becomes a phone's: it moves less. */
    if (presets && !reduced && presets.capability.compact !== compact) {
      compact = presets.capability.compact;
      cast();
    }
    const end = Math.max(0, root.scrollHeight - vh);
    for (const scene of scenes) {
      scene.top = clock.top(scene.el);
      scene.height = scene.el.offsetHeight;
      scene.flush = true;
    }
    for (const element of elements) {
      const { el } = element;
      element.top = clock.top(el);
      element.height = el.offsetHeight;
      const start = parseFloat(el.dataset.motionStart) || START, span = parseFloat(el.dataset.motionSpan) || SPAN;
      let from = element.top - vh * start + (Number(el.dataset.motionOrder) || 0) * ORDER;
      const to = Math.min(from + vh * span, end);
      if (to === end) from = Math.min(from, to - vh * LEAST);      /* the page ends first: start sooner */
      /* Already in the window when the page opens, or held where it is: at rest. */
      element.rest = !element.drift && (from < 0 || !!el.closest('[data-motion-rest]'));
      element.from = from; element.to = to;
    }
  }

  function render(state) {
    const { y, vh, reduced } = state;
    if (live !== !reduced) {                            /* motion was switched on or off */
      live = !reduced;
      root.classList.toggle('cine-on', live);
      scenes.forEach(scene => { scene.flush = true; });
      if (!live) elements.forEach(element => element.clear());
    }
    let current = null;
    for (const scene of scenes) {
      const travel = Math.max(1, scene.height - vh);
      scene.progress = reduced ? 1 : clamp((y - scene.top) / travel);                          /* through its pinned length */
      scene.enter = reduced ? 1 : clamp((y + vh - scene.top) / vh);                            /* coming up into the window */
      scene.exit = reduced ? 0 : clamp((y + vh - scene.top - scene.height) / vh);              /* leaving by the top of it */
      if (scene.top <= y + vh * .5 && scene.top + scene.height > y + vh * .5) current = scene;
      if (!scene.active && !scene.flush) continue;      /* far from the window: nothing to draw */
      scene.flush = false;
      for (const draw of handlers.get(scene.name) || []) draw(scene, state);
    }
    motion.activeScene = current?.name || '';
    motion.progress = current ? current.progress : 0;
    if (!live) return;
    for (const element of elements) {
      if (element.drift) { element.seek(clamp((y + vh - element.top) / (vh + element.height)), vh + element.height); continue; }
      const foot = element.top + element.height - y;      /* its foot, from the top of the window */
      const gone = element.out && !element.rest && foot > 0 ? 1 - range(foot, vh * OUT[0], vh * OUT[1]) : 0;
      element.seek(element.rest ? 1 : range(y, element.from, element.to), gone);
    }
  }

  window.ScrollCinema = {
    clamp, lerp, range, smooth,
    /* draw(scene, clock state) runs on every frame the scene is near the window */
    scene(name, draw) {
      if (!handlers.has(name)) handlers.set(name, []);
      handlers.get(name).push(draw);
      scenes.forEach(scene => { scene.flush = true; });
      clock.invalidate();
    },
    get scenes() { return scenes.map(({ name, active, progress, enter, exit }) => ({ name, active, progress, enter, exit })); },
    get motion() { return { ...motion, live: !!live, elements: elements.length }; },
  };
  clock.subscribe(render, measure);
})();
