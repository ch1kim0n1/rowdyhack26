/* A single camera move into the diamond, starting with the first scroll. Native
   scroll and UI-dev's film remain authoritative: no wheel/touch interception.
   Where the title card is taller than the window, its mission band waits until
   the film has run, so the artwork alone fills the screen and the camera can
   leave at once. */
(() => {
  'use strict';
  const body = document.body;
  const hero = document.querySelector('.hero');
  const pin = hero?.querySelector('.hero-portal-pin');
  const vault = hero?.querySelector('.vault-stage');
  const scene = vault?.querySelector('.vault-scene');
  const art = scene?.querySelector('.vault-art');
  const reel = document.querySelector('.reel');
  const marquee = document.querySelector('.marquee');
  const projector = reel?.querySelector('.reel-stage');
  if (!pin || !art || !projector) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const sections = [...document.querySelectorAll('main > section, footer.credits')];
  const clamp = v => Math.max(0, Math.min(1, v));
  const range = (v, a, b) => clamp((v - a) / Math.max(.0001, b - a));
  const smooth = v => v * v * (3 - 2 * v);
  const mix = (a, b, v) => a + (b - a) * v;
  const topOf = el => { let top = 0; for (let n = el; n; n = n.offsetParent) top += n.offsetTop; return top; };
  const band = [...pin.children].filter(el => el !== vault);    /* the brief and the mission strip */
  const later = document.createElement('div');                   /* where they wait, after the film */
  later.className = 'mission-later';
  const clock = window.PremiereScroll;
  if (!clock) return;
  let active = false, mode = 'off', geometry;
  let reading = {el: hero, offset: 0};
  let told = -1;

  // The title's dust (premiere-title-particles.js) blows away as the camera leaves.
  function tell(camera) {
    const value = +camera.toFixed(4);
    if (value === told) return;
    told = value;
    document.dispatchEvent(new CustomEvent('premiereportal', {detail: {camera: value}}));
  }

  function measure() {
    const vh = innerHeight, height = pin.offsetHeight;
    const pinTop = Math.min(0, vh - height);
    hero.style.setProperty('--portal-pin-height', `${height}px`);
    hero.style.setProperty('--portal-pin-top', `${pinTop}px`);
    const w = scene.clientWidth, h = scene.clientHeight;
    /* Which artwork is showing is judged by its shape, not its name: the wide
       art is about 2.3:1, the portrait 1.5:1. Before the image loads the
       source name is the only hint. */
    const portrait = art.naturalWidth ? art.naturalWidth / art.naturalHeight < 2
                                      : !art.currentSrc.includes('hero-wide');
    const iw = art.naturalWidth || (portrait ? 1536 : 1916);
    const ih = art.naturalHeight || (portrait ? 1024 : 821);
    const css = getComputedStyle(art);
    const fit = css.objectFit === 'contain' ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
    const pos = css.objectPosition.split(' ').map(parseFloat);
    const ox = (w - iw * fit) * ((pos[0] ?? 50) / 100);
    const oy = (h - ih * fit) * ((pos[1] ?? 50) / 100);
    // Pixel coordinates in the existing wide and portrait artwork, respectively.
    const dx = ox + (portrait ? 1034 / 1536 : 1267 / 1916) * iw * fit;
    const dy = oy + (portrait ? 434 / 1024 : 342 / 821) * ih * fit;
    const heroTop = topOf(hero), filmTop = topOf(reel);
    // A link to #film stops short by the page's scroll padding: finish the move there.
    const arrive = filmTop - (parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0);
    geometry = {vh, w, h, height, pinTop, dx, dy, heroTop, filmTop, arrive,
      vaultTop: vault.offsetTop, start: heroTop - pinTop,
      sections: sections.map(el => ({el, top: topOf(el)}))};
  }

  function paint(y) {
    const g = geometry;
    const camera = smooth(range(y, g.start, g.arrive));
    const zoom = mix(1, innerWidth <= 980 ? 3.1 : 4.1, camera);
    // Center the diamond in the visible portion of its artwork.
    const pinY = Math.max(g.pinTop, g.heroTop - y);
    const targetY = Math.max(g.h * .2, Math.min(g.h * .8, g.vh * .46 - g.vaultTop - g.pinTop));
    const x = (g.w * .5 - g.dx) * camera - (zoom - 1) * g.dx;
    const dy = (targetY - g.dy) * camera - (zoom - 1) * g.dy;
    scene.style.transform = `translate3d(${x.toFixed(2)}px,${dy.toFixed(2)}px,0) scale(${zoom.toFixed(4)})`;
    scene.style.setProperty('--camera', camera.toFixed(4));   /* the light and the dust move at their own depth */
    tell(camera);
    const portal = smooth(range(y, g.filmTop - g.vh, g.arrive));
    const cx = x + g.dx * zoom;
    const cy = pinY + g.vaultTop + dy + g.dy * zoom;
    // Radius reaches the farthest corner at every viewport aspect ratio.
    const radius = Math.hypot(Math.max(cx, g.w - cx), Math.max(cy, g.vh - cy)) + 2;
    projector.style.setProperty('--portal-x', `${cx.toFixed(2)}px`);
    projector.style.setProperty('--portal-y', `${cy.toFixed(2)}px`);
    projector.style.setProperty('--portal-radius', `${(radius * portal).toFixed(2)}px`);
    reel.style.setProperty('--portal-gate-scale', mix(1.16, 1, portal).toFixed(4));
    reel.style.setProperty('--portal-ui', smooth(range(portal, .68, 1)).toFixed(3));
    // Native position is used for this switch so there is never a layout gap.
    projector.classList.toggle('is-entering', scrollY < g.filmTop);
    reel.classList.toggle('is-open', portal > .9);
    // Past the film's first frame premiere.js decides when the marquee shows.
    body.classList.toggle('portal-open', portal > .9 && scrollY < g.filmTop);
    const shut = portal < .9;
    reel.inert = shut;                                   /* inert where supported... */
    reel.setAttribute('aria-hidden', String(shut));      /* ...and hidden from readers either way */
  }

  /* 'whole': art and mission band fit the window together (a phone), so the band
     stays under the art. 'split': the art fills the window by itself, and the band
     moves to after the film. Either way the title card is pinned from scroll zero. */
  function plan() {
    if (reduced.matches || body.classList.contains('motion-paused')) return 'off';
    const card = (marquee?.offsetHeight || 0) + vault.offsetHeight + band.reduce((sum, el) => sum + el.offsetHeight, 0);
    return card <= innerHeight + 1 ? 'whole' : 'split';
  }

  function refresh() { if (plan() !== mode) sync(); else clock.invalidate(); }
  function trackReading() {
    const candidates = active && geometry ? geometry.sections : sections.map(el => ({el, top: topOf(el)}));
    let section = candidates[0];
    for (let i = candidates.length - 1; i >= 0; i--) {
      if (candidates[i].top <= scrollY + 1) { section = candidates[i]; break; }
    }
    reading = {el: section.el, offset: section.el === hero ? 0 : scrollY - section.top};
    // Someone reading the mission band follows it to wherever it goes.
    if (band.length) {
      const last = band[band.length - 1];
      const lead = topOf(band[0]) - scrollY, foot = topOf(last) + last.offsetHeight - scrollY;
      if (lead < innerHeight * .5 && foot > innerHeight * .25) reading = {el: band[0], offset: -lead};
    }
  }
  function sync() {
    if (geometry) trackReading();
    const next = plan();
    const restore = next !== mode && geometry ? reading : null;
    mode = next;
    active = mode !== 'off';
    body.classList.toggle('portal-ready', active);
    if (mode === 'split') { reel.after(later); later.append(...band); }
    else if (later.isConnected) { pin.append(...band); later.remove(); }
    if (!active) {
      scene.style.removeProperty('transform');
      scene.style.removeProperty('--camera');
      reel.inert = false;
      reel.removeAttribute('aria-hidden');
      reel.classList.remove('is-open');
      body.classList.remove('portal-open');
      projector.classList.remove('is-entering');
      tell(0);
    }
    if (active) measure();
    if (restore) requestAnimationFrame(() => {
      // Other preference listeners also change reel/story heights. Restore after all of them.
      const offset = Math.min(restore.offset, Math.max(0, restore.el.offsetHeight - innerHeight * .4));
      scrollTo({top: Math.max(0, topOf(restore.el) + offset), behavior: 'instant'});
      clock.invalidate();
    });
    clock.invalidate();
  }
  // vault.js changes its class before emitting the event; retain old geometry.
  document.addEventListener('click', event => {
    if (event.target.closest('[data-vault-motion]')) trackReading();
  }, true);
  document.addEventListener('vaultmotionchange', sync);
  if (reduced.addEventListener) reduced.addEventListener('change', sync);
  else reduced.addListener(sync);                        /* Safari 13 and older */
  addEventListener('resize', () => { trackReading(); refresh(); }, {passive: true});
  addEventListener('pageshow', refresh);
  art.addEventListener('load', refresh);
  document.fonts?.ready.then(refresh);
  const observer = new ResizeObserver(refresh);
  observer.observe(pin); observer.observe(vault);
  sync();
  clock.subscribe(({y}) => { if (active && geometry) paint(y); }, () => { if (active) measure(); });
})();
