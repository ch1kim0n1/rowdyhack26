/* Motion presets: the premiere's vocabulary of entrances and exits. The markup names
   them (data-motion="rise" data-motion-out="lift") and this file builds each as an
   Anime.js animation that never plays by itself: scroll-cinema.js seeks it to
   wherever the scroll has it, so an entrance runs backwards when the page does.
   The numbers here are distance, scale and blur only. The curves are the kit's own
   (--ez-settle, --ez-film) and nothing sets a colour. */
(root => {
  'use strict';
  const doc = root.document, anime = root.anime;
  const narrow = root.matchMedia('(max-width: 720px)');
  const system = root.matchMedia('(prefers-reduced-motion: reduce)');

  /* Where each preset starts; every one ends at rest. As an exit it runs the other
     way, from rest to here. x and y in px, s is scale, o is opacity, b is blur in px,
     w is a wipe (1: wholly masked from the right, 0: open). */
  const REST = { x: 0, y: 0, s: 1, o: 1, b: 0, w: 0 };
  const PRESETS = {
    rise: { y: 70, o: 0 },                      /* display type rises behind a mask instead: see mask() */
    'slide-left': { x: -60, o: 0 },
    'slide-right': { x: 60, o: 0 },
    scan: { x: -28, o: 0, w: 1 },               /* a typed line, read off from its left end */
    signal: { x: -68, o: 0 },
    focus: { y: 20, s: 1.05, o: 0, b: 8 },
    relief: { y: 24, s: .94, o: 0, b: 8 },      /* comes forward, where focus settles back */
    settle: { y: 12, s: 1.03, o: .8 },
    dialogue: { y: 12, o: 0 },
    lift: { y: -34, o: 0 },                     /* the way out: up and gone */
    'depth-in': { s: 1.08, o: 0, b: 5 },
    mist: { x: -2, y: 8, s: .9, o: 0, b: 7 },   /* letter by letter: see letters() */
    crossfade: { o: 0 },
    drift: {},                                  /* a layer at its own speed: see drift() */
  };
  const MASKED = 125;      /* a masked glyph starts this far below its line, in % of its own height */
  const LARGE = 120000;    /* px²: past this an element is too big to blur as it moves */
  const MOVES = ['translate', 'scale', 'opacity', 'filter', 'clip-path'];

  /* Hints, not rules: they only ever take an effect away. */
  const capability = {
    get reduced() { return system.matches || doc.body.classList.contains('motion-paused'); },
    get compact() { return narrow.matches; },
    lowPower: !!navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4,
    webgl: 'WebGLRenderingContext' in root,
  };

  /* noir.css's curve, as Anime.js spells it */
  const curve = (token, otherwise) => {
    const bezier = /cubic-bezier\(([^)]+)\)/.exec(getComputedStyle(doc.documentElement).getPropertyValue(token));
    return bezier ? `cubicBezier(${bezier[1]})` : otherwise;
  };
  const plain = el => ![...el.childNodes].some(node => node.nodeType === 1 && node.nodeName !== 'BR');
  const strip = el => MOVES.forEach(property => el.style.removeProperty(property));

  /* What rises behind a mask: the glyphs noir.js cut a .cut title into, or each line of
     plain display type (wrapped once, here, as .motion-mask > .motion-rise). Anything
     with elements of its own inside is not type: it rises whole, with no mask. */
  function mask(el) {
    const glyphs = [...el.querySelectorAll('.ch')];
    if (glyphs.length) return glyphs;
    const wrapped = [...el.querySelectorAll(':scope > .motion-mask > .motion-rise')];
    if (wrapped.length) return wrapped;
    if (!plain(el)) return null;
    const lines = [[]];
    for (const node of [...el.childNodes]) {
      if (node.nodeName === 'BR') { lines.push([]); node.remove(); }
      else lines.at(-1).push(node);
    }
    return lines.filter(line => line.some(node => node.textContent.trim())).map(line => {
      const outer = doc.createElement('span'), inner = doc.createElement('span');
      outer.className = 'motion-mask'; inner.className = 'motion-rise';
      inner.append(...line); outer.append(inner); el.append(outer);
      return inner;
    });
  }

  /* What comes out of the mist: a line of plain type, letter by letter. The line is
     still read as its words (they stay in the page, unseen); the letters are for show. */
  function letters(el) {
    const set = [...el.querySelectorAll(':scope > .motion-mist .motion-char')];
    if (set.length) return set;
    if (!plain(el) || !el.textContent.trim()) return null;
    const text = el.textContent.replace(/\s+/g, ' ').trim();
    const read = doc.createElement('span'), shown = doc.createElement('span');
    read.className = 'sr-only'; read.textContent = text;
    shown.className = 'motion-mist'; shown.setAttribute('aria-hidden', 'true');
    text.split(' ').forEach((word, i) => {
      const group = doc.createElement('span');
      group.className = 'motion-word';                 /* a word never breaks between its letters */
      for (const letter of word) {
        const char = doc.createElement('span');
        char.className = 'motion-char'; char.textContent = letter;
        group.append(char);
      }
      if (i) shown.append(' ');
      shown.append(group);
    });
    el.replaceChildren(read, shown);
    return [...shown.querySelectorAll('.motion-char')];
  }

  /* A layer that keeps its own pace: it lags the scroll by `depth` of the distance
     it travels through the window, and is level with the page at mid-screen. */
  function drift(el) {
    const depth = parseFloat(el.dataset.motionDepth) || .15;
    let at = -1;
    return {
      el, drift: true,
      seek(p, travel) {
        if (p === at) return;
        at = p;
        el.style.translate = `0 ${((p - .5) * travel * depth).toFixed(1)}px`;
      },
      clear() { at = -1; el.style.removeProperty('translate'); },
    };
  }

  /* A preset's numbers, cut down to what this element and this machine can carry. */
  function fitted(preset, el) {
    const from = { ...preset };
    const travel = capability.compact ? .6 : 1;        /* a phone has less room to move in */
    if (from.x) from.x *= travel;
    if (from.y) from.y *= travel;
    /* Blur is for small things, and never on a phone or a slow machine. */
    if (capability.compact || capability.lowPower || el.offsetWidth * el.offsetHeight > LARGE) delete from.b;
    /* Something as wide as the window has nowhere to grow: it would push the page wider. */
    if (from.s > 1 && el.offsetWidth * from.s > root.innerWidth) delete from.s;
    return from;
  }

  function write(style, v, percent) {
    if (percent) style.translate = `0 ${v.y.toFixed(1)}%`;
    else if ('x' in v || 'y' in v) style.translate = `${(v.x || 0).toFixed(1)}px ${(v.y || 0).toFixed(1)}px`;
    if ('s' in v) style.scale = v.s.toFixed(4);
    if ('o' in v) style.opacity = v.o.toFixed(3);
    if ('b' in v) style.filter = v.b > .05 ? `blur(${v.b.toFixed(1)}px)` : '';
    if ('w' in v) style.clipPath = v.w > .001 ? `inset(-30% ${(v.w * 100).toFixed(1)}% -30% -10%)` : '';
  }

  /* One element's presets, ready to be sought. seek(p, gone): p runs its entrance from
     0 to 1, gone runs its exit from 0 to 1. At rest (1, 0) nothing of ours is left on it. */
  function build(el, name = el.dataset.motion, out = el.dataset.motionOut) {
    const preset = PRESETS[name];
    if (!preset) return null;
    if (name === 'drift') return capability.compact ? null : drift(el);
    if (!anime) return null;
    const pieces = name === 'rise' ? mask(el) : name === 'mist' ? letters(el) : null;
    const parts = pieces?.length ? pieces : null;
    const masked = !!parts && name === 'rise';
    const targets = parts || [el];
    const from = masked ? { y: MASKED } : fitted(preset, targets[0]);
    const settle = curve('--ez-settle', 'easeOutCubic'), film = curve('--ez-film', 'easeInOutSine');
    const eased = key => key === 'o' || key === 'b' ? film : settle;

    const state = targets.map(() => ({ ...from }));
    const several = targets.length > 1;
    const entrance = {
      targets: state, autoplay: false, easing: 'linear',
      duration: several ? 600 : 1000,                  /* glyphs, lines and letters follow one another */
      delay: several ? anime.stagger(400 / (targets.length - 1)) : 0,
    };
    for (const key of Object.keys(from)) entrance[key] = { value: [from[key], REST[key]], easing: eased(key) };
    const arriving = anime(entrance);

    /* The exit is the whole element's, even where the entrance was its letters'. */
    const to = PRESETS[out] && out !== 'drift' ? fitted(PRESETS[out], el) : null;
    const leaving = to && Object.fromEntries(Object.keys(to).map(key => [key, REST[key]]));
    const exit = to && { targets: leaving, autoplay: false, easing: 'linear', duration: 1000 };
    if (to) for (const key of Object.keys(to)) exit[key] = { value: [REST[key], to[key]], easing: eased(key) };
    const departing = to && anime(exit);

    let at = -1, away = -1, dressed = false, lifted = false, arrived = true, left = false;
    function undress() {
      if (!dressed) return;
      dressed = lifted = left = false; arrived = true;
      el.classList.remove('is-rising');
      for (const target of new Set([...targets, el])) strip(target);
      el.style.removeProperty('will-change');
    }
    return {
      el, out: !!to,
      seek(p, gone = 0) {
        if (!to) gone = 0;
        if (p === at && gone === away) return;
        at = p; away = gone;
        if (p >= 1 && gone <= 0) { undress(); return; }
        dressed = true;
        /* Its own layer only while it is actually moving: waiting below the window it holds none. */
        const moving = gone > 0 || (!parts && p > 0);
        if (lifted !== moving) { lifted = moving; el.style.willChange = moving ? 'translate, scale, opacity' : ''; }
        if (left && gone <= 0) { left = false; strip(el); }
        if (p < 1) {
          arrived = false;
          if (masked) el.classList.add('is-rising');
          arriving.seek(arriving.duration * p);
          targets.forEach((target, i) => write(target.style, state[i], masked));
        } else if (!arrived) {
          arrived = true;
          el.classList.remove('is-rising');
          targets.forEach(strip);
        }
        if (gone > 0) {
          left = true;
          departing.seek(departing.duration * Math.min(gone, .9999));
          write(el.style, leaving, false);
        }
      },
      clear() { at = away = -1; undress(); },
    };
  }

  root.MotionPresets = { names: Object.keys(PRESETS), capability, build };
})(window);
