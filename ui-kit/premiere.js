/* The premiere page. The scroll wheel runs the film through the gate:
   one frame per notch of scroll, captions typed as the picture plays.
   Everything else is small: the marquee, cuts on arrival, the method's
   evidence board, the wrist screen, and the kit's sound. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const pad = (n, w = 2) => String(n).padStart(w, '0');

  /* ---------- the film: its length and its chapters (ui-kit/film/src/story.js) ---------- */
  const FPS = 24, FRAMES = 501, DURATION = FRAMES / FPS;
  const BEEP_AT = 0.5 + 5 * (8 / 24), THUD_AT = 17.09;
  const CHAPTERS = [
    { from: 0, label: 'Reel 1 · Picture Start', lines: [[0, 'Lights down. The leader counts the picture in.']] },
    { from: 2.7, label: 'Reel 1 · The Walk', lines: [
      [2.7, 'An authorized red-team walkthrough. The assessor wears a camera clipped to the brim of a cap.'],
      [4.6, 'When the scene changes, the cap takes a look. A model names what it sees.'],
      [6.5, 'Then the rig prices it: sold comps first, a model\'s quote second, the camera\'s own guess last.'],
      [8.4, 'Each observed asset enters the evidence ledger. The take is estimated asset value; guesses say est.'],
    ] },
    { from: 10.3, label: 'Reel 1 · The Screen', lines: [[10.3, 'Dispatch sees the shared asset ledger and value total. Stills, not video. Each one cuts in.']] },
    { from: 12.2, label: 'Changeover', lines: [[12.2, 'Press the button on the cap. The cue mark flashes and the frame freezes.']] },
    { from: 13.45, label: 'Reel 2 · The Lineup', lines: [
      [13.45, 'The debrief: five assets ranked by estimated value, not by security risk.'],
      [16.1, 'The QR opens the evidence case file. Observation alone does not prove a vulnerability.'],
    ] },
    { from: 18.7, label: 'The End', lines: [[18.7, 'Press the button again and the next case opens.']] },
  ];
  const LINES = CHAPTERS.flatMap(c => c.lines.map(([t, text]) => ({ t, text })));
  LINES.forEach((l, i) => { l.until = LINES[i + 1]?.t ?? DURATION; });

  const sfx = typeof Noir !== 'undefined' ? Noir.sfx : null;   /* noir.js: a global const, not a window property */
  const marquee = $('#marquee'), hero = $('.hero');

  /* ---------- marquee: solid once past the title, gone while the film runs ---------- */
  const reel = $('.reel');
  function chrome() {
    marquee.classList.toggle('solid', scrollY > hero.offsetHeight * 0.6);
    const r = reel.getBoundingClientRect();
    document.body.classList.toggle('in-reel', !reduced && r.top <= 1 && r.bottom >= innerHeight - 1);
    const here = ['film', 'crew', 'method', 'paperwork'].findLast(id => document.getElementById(id).getBoundingClientRect().top < innerHeight * 0.4);
    $$('.marquee-nav a').forEach(a => a.classList.toggle('here', a.hash === '#' + here));
  }

  /* ---------- cuts on arrival ---------- */
  const cueables = $$('.section-head, .dossier, .paperwork .print, .priors, .credits-roll > *');
  cueables.forEach(el => el.classList.add('on-cue'));
  const arrive = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); arrive.unobserve(e.target); }
  }), { rootMargin: '0px 0px -12% 0px' });
  cueables.forEach(el => arrive.observe(el));

  /* ---------- the wrist, showing this film's case ---------- */
  const WRIST = { case_no: 1138, take: 9920, count: 6, pending: false, revealed: false, top: [
    { item: 'Vintage Rolex', value_usd: 4200 }, { item: 'Oil on canvas, unsigned', value_usd: 2400 },
    { item: 'Leica M3 rangefinder', value_usd: 1850 }, { item: 'First-ed. Hemingway', value_usd: 950 },
    { item: 'Crystal decanter', value_usd: 340 },
  ] };
  if (typeof WristOLED !== 'undefined') $$('canvas.wrist-oled').forEach(c => WristOLED.draw(c, WRIST));

  /* ---------- the method: the board shows the step you're reading ---------- */
  const steps = $$('.step'), prints = $$('.board-print');
  const pickStep = () => {
    const mid = innerHeight * 0.5;
    let best = 0;
    steps.forEach((s, i) => { if (s.getBoundingClientRect().top < mid) best = i; });
    steps.forEach((s, i) => s.classList.toggle('here', i === best));
    prints.forEach(p => p.classList.toggle('on', Number(p.dataset.step) === best));
  };

  /* ---------- the reel ---------- */
  const video = $('.reel-video');
  const chapterEl = $('.reel-chapter'), counter = $('.reel-counter'), sub = $('.reel-sub');
  const loading = $('.gate-loading'), meter = $('.gate-meter');
  const strip = $('.reel-strip'), stripItems = $$('.reel-strip li');
  let ready = false, target = 0, shown = 0, frameShown = -1, lastChars = -1, lastLine = -1, lastT = 0;

  /* H.264 where the browser has it (Safari, Chrome), VP9 where it doesn't (Chromium builds) */
  const source = () => {
    const w = Math.min(innerWidth, 1920) * Math.min(devicePixelRatio || 1, 2);
    const ext = video.canPlayType('video/mp4; codecs="avc1.640028"') ? 'mp4' : 'webm';
    return `media/film-${w >= 1300 ? 1600 : 960}.${ext}`;
  };

  /* pull the whole reel into memory first, so every seek is local and instant */
  async function thread() {
    const url = source();
    try {
      const res = await fetch(url);
      if (!res.ok || !res.body) throw new Error(res.status);
      const total = Number(res.headers.get('content-length')) || 0;
      const reader = res.body.getReader(), parts = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value); got += value.length;
        if (total) meter.style.setProperty('--p', (got / total).toFixed(3));
      }
      video.src = URL.createObjectURL(new Blob(parts, { type: url.endsWith('.webm') ? 'video/webm' : 'video/mp4' }));
      video.preload = 'auto';
    } catch {
      video.src = url;                    /* opened from disk, or no streams: let the browser fetch it */
      video.preload = 'auto';
    }
    video.addEventListener('loadeddata', () => {
      ready = true;
      loading.classList.add('done');
      frameShown = -1;
    }, { once: true });
    video.load();
  }

  if (reduced) {
    /* no scrubbing: a plain player, and the captions as a list */
    video.controls = true; video.preload = 'metadata';
    video.src = source();
    loading.classList.add('done');
    sub.textContent = LINES.map(l => l.text).join(' ');
    chapterEl.textContent = 'The film';
  } else {
    const near = new IntersectionObserver(es => {
      if (es.some(e => e.isIntersecting)) { near.disconnect(); thread(); }
    }, { rootMargin: '150% 0px' });
    near.observe(reel);
  }

  function progress() {
    const len = reel.offsetHeight - innerHeight;
    return clamp(-reel.getBoundingClientRect().top / len);
  }

  function paintReel(t) {
    const f = Math.min(FRAMES - 1, Math.max(0, Math.round(t * FPS)));
    counter.textContent = `FR 00:00:${pad(Math.floor(f / FPS))}:${pad(f % FPS)} · ${pad(Math.floor(f / 16), 4)} FT`;
    const ch = CHAPTERS.findLast(c => t >= c.from - 1e-3) || CHAPTERS[0];
    if (chapterEl.textContent !== ch.label) chapterEl.textContent = ch.label;
    stripItems.forEach(li => li.classList.toggle('here', li.querySelector('a').dataset.t <= t + 1e-3 && (li.nextElementSibling?.querySelector?.('a')?.dataset.t ?? 99) > t));
    strip.style.setProperty('--p', (t / DURATION).toFixed(4));

    /* the caption types over the first half of its stretch of film, then holds */
    const i = LINES.findLastIndex(l => t >= l.t - 1e-3);
    const line = LINES[Math.max(0, i)];
    const k = clamp((t - line.t) / Math.max(0.6, (line.until - line.t) * 0.5));
    const chars = Math.round(line.text.length * k);
    if (chars !== lastChars || i !== lastLine) {
      if (sfx?.on && i === lastLine && chars > lastChars && chars % 3 === 0) sfx.key();
      sub.innerHTML = '';
      sub.append(line.text.slice(0, chars));
      if (chars < line.text.length) sub.insertAdjacentHTML('beforeend', '<span class="caret" aria-hidden="true">▌</span>');
      lastChars = chars; lastLine = i;
    }
    if (sfx?.on) {
      if (lastT < BEEP_AT && t >= BEEP_AT) sfx.beep();
      if (lastT < THUD_AT && t >= THUD_AT) sfx.thud();
    }
    lastT = t;

    if (ready && f !== frameShown && !video.seeking) {
      video.currentTime = (f + 0.5) / FPS;    /* the middle of the frame, never the edge */
      frameShown = f;
    }
  }

  /* the perforations roll with the scroll, like film through a projector */
  const perfs = $$('.perfs');

  function loop() {
    chrome();
    pickStep();
    if (!reduced) {
      const r = reel.getBoundingClientRect();
      if (r.bottom > 0 && r.top < innerHeight) {
        target = progress() * DURATION;
        shown += (target - shown) * 0.22;
        if (Math.abs(target - shown) < 0.004) shown = target;
        paintReel(shown);
        perfs.forEach(p => p.style.setProperty('--roll', `${(-shown * 96).toFixed(1)}px`));
      }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  /* chapter ticks jump the scroll to that moment */
  $$('.reel-strip a').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    const len = reel.offsetHeight - innerHeight;
    const top = reel.getBoundingClientRect().top + scrollY;
    scrollTo({ top: top + (Number(a.dataset.t) / DURATION) * len + 2, behavior: reduced ? 'auto' : 'smooth' });
  }));

  /* ---------- THE END, shot up ----------
     When the credits' title card comes into view a volley hits it, one round per
     letter. Each round is aimed at a stroke of its letter and the hole is placed
     inside that letter, so it covers the glyph and moves with it when the letter is
     knocked crooked. Every shot: a muzzle flash at the impact, a shockwave and
     smoke there, a hard jolt, chips, and the letter recoiling. The flash is local
     to the hit and clears on its own, so rapid fire never leaves the screen washed
     out. The holes stay while it's on screen and the volley replays when it comes
     back. Reduced or paused motion: the holes, without the show. Sound only if the
     viewer turned it on. */
  const endTitle = $('.credits-end');
  if (endTitle) {
    /* where a stroke is in each condensed capital, as fractions of the glyph's box */
    /* the strokes of each condensed capital, as [x, yFrom, yTo] in fractions of the
       glyph's box: stems, bars and arms, so a random round still lands on ink */
    const STROKES = {
      T: [[.5, .3, .9], [.2, .06, .13], [.8, .06, .13]],
      H: [[.2, .15, .85], [.8, .15, .85], [.5, .45, .55]],
      E: [[.22, .15, .85], [.62, .06, .13], [.55, .46, .54], [.62, .87, .94]],
      N: [[.2, .2, .85], [.8, .15, .8], [.5, .38, .62]],
      D: [[.24, .15, .85], [.78, .3, .7], [.55, .07, .13], [.55, .87, .93]],
    };
    let timers = [];
    const still = () => reduced || document.body.classList.contains('motion-paused');
    const jitter = n => (Math.random() - .5) * n;

    function clear() {
      timers.forEach(clearTimeout); timers = [];
      $$('.shot-fx', endTitle).forEach(n => n.remove());
      $$('.ch', endTitle).forEach(c => {
        c._holes = [];
        c.classList.remove('shot', 'fresh');
        for (const v of ['--hit', '--drop', '--hole-bg', '--hole-mask']) c.style.removeProperty(v);
      });
    }
    /* A letter's holes are painted into its own fill: each hole's art (tinted to the
       paper) and a powder burn are background layers, clipped to the glyph, and each
       core is cut through with a mask layer (intersected), so the page shows through. */
    function paint(letter) {
      const bg = [], mask = [];
      for (const h of letter._holes) {
        const x = (h.cx - h.size / 2).toFixed(1), y = (h.cy - h.size / 2).toFixed(1), at = `${h.cx.toFixed(1)}px ${h.cy.toFixed(1)}px`;
        bg.push(`url("brand/bullet-hole-paper-${h.k}.png") ${x}px ${y}px / ${h.size.toFixed(1)}px ${h.size.toFixed(1)}px no-repeat`);
        bg.push(`radial-gradient(circle ${(h.size * .62).toFixed(1)}px at ${at}, rgba(66,44,24,.5), rgba(66,44,24,.16) 55%, rgba(66,44,24,0) 100%)`);
        mask.push(`radial-gradient(circle ${(h.size * .17).toFixed(1)}px at ${at}, transparent 88%, #000 100%)`);
      }
      bg.push('linear-gradient(var(--paper), var(--paper))');
      letter.style.setProperty('--hole-bg', bg.join(', '));
      letter.style.setProperty('--hole-mask', mask.join(', '));
      letter.classList.add('shot');
    }
    function hit(letter, stroke) {
      const w = letter.offsetWidth, h = letter.offsetHeight;
      const size = parseFloat(getComputedStyle(letter).fontSize) * (.15 + Math.random() * .04);
      const [sx, y0, y1] = stroke;
      const cx = w * (sx + jitter(.06)), cy = h * (y0 + Math.random() * (y1 - y0));
      (letter._holes ||= []).push({ cx, cy, size, k: Math.floor(Math.random() * 4) });
      paint(letter);
      letter.style.setProperty('--hit', jitter(16).toFixed(1) + 'deg');
      letter.style.setProperty('--drop', (Math.random() * .05).toFixed(3) + 'em');
      if (still()) return;
      letter.classList.remove('fresh'); void letter.offsetWidth; letter.classList.add('fresh');
      /* the burst, smoke and chips on their own layer over the title */
      const tb = endTitle.getBoundingClientRect(), lb = letter.getBoundingClientRect();
      const fx = Object.assign(document.createElement('span'), { className: 'shot-fx' });
      fx.setAttribute('aria-hidden', 'true');
      fx.style.left = (lb.left + lb.width * (cx / w) - tb.left).toFixed(0) + 'px';
      fx.style.top = (lb.top + lb.height * (cy / h) - tb.top).toFixed(0) + 'px';
      fx.style.setProperty('--s', size.toFixed(0) + 'px');
      /* the muzzle burst: a jagged star, a new shape every shot (no circles) */
      const spark = Object.assign(document.createElement('i'), { className: 'shot-spark' });
      const spikes = 9 + Math.floor(Math.random() * 5), turn = Math.random() * 360, pts = [];
      for (let k = 0; k < spikes * 2; k++) {
        const a = (turn + k * 180 / spikes) * Math.PI / 180, r = k % 2 ? 6 + Math.random() * 10 : 28 + Math.random() * 22;
        pts.push(`${(50 + Math.cos(a) * r).toFixed(1)}% ${(50 + Math.sin(a) * r).toFixed(1)}%`);
      }
      spark.style.clipPath = `polygon(${pts.join(',')})`;
      const smoke = Object.assign(document.createElement('i'), { className: 'shot-smoke' });
      smoke.style.setProperty('--tilt', Math.round(jitter(70)) + 'deg');
      /* the muzzle flash: a soft bloom that lights only around the hole, then clears */
      const glow = Object.assign(document.createElement('i'), { className: 'shot-glow' });
      fx.append(glow, spark, smoke);
      for (let i = 0; i < 8; i++) {                    /* chips off the letter */
        const chip = Object.assign(document.createElement('i'), { className: 'shot-chip' });
        const a = Math.random() * Math.PI * 2, d = 50 + Math.random() * 90;
        chip.style.setProperty('--dx', (Math.cos(a) * d).toFixed(0) + 'px');
        chip.style.setProperty('--dy', (Math.sin(a) * d - 24).toFixed(0) + 'px');
        fx.append(chip);
      }
      endTitle.append(fx);
      setTimeout(() => fx.remove(), 900);
      letter.animate([{ scale: 1 }, { scale: .86 }, { scale: 1.04 }, { scale: 1 }], { duration: 260, easing: 'cubic-bezier(.2,.7,.3,1)' });
      const kick = () => `${jitter(26).toFixed(0)}px ${jitter(14).toFixed(0)}px`;
      endTitle.animate([{ translate: '0 0' }, { translate: kick() }, { translate: kick() }, { translate: kick() }, { translate: '0 0' }],
                       { duration: 300, easing: 'cubic-bezier(.2,.7,.3,1)' });
      $('.credits-roll')?.animate([{ rotate: '0deg' }, { rotate: `${jitter(1.2).toFixed(2)}deg` }, { rotate: '0deg' }], { duration: 260 });
      sfx?.shot?.();
    }
    /* a random volley: 5 to 8 rounds, each at a random letter and a random stroke of it.
       Some letters take two, some none; a stroke is never hit twice. Uneven timing, like
       someone actually firing. */
    function volley() {
      clear();
      const letters = $$('.ch', endTitle);
      const open = letters.flatMap(l => (STROKES[l.textContent.toUpperCase()] || [[.5, .3, .7]]).map(st => [l, st]));
      const rounds = Math.min(open.length, 5 + Math.floor(Math.random() * 4));
      let at = 150;
      for (let i = 0; i < rounds; i++) {
        const [letter, stroke] = open.splice(Math.floor(Math.random() * open.length), 1)[0];
        timers.push(setTimeout(() => hit(letter, stroke), still() ? 0 : at));
        at += 55 + Math.random() * 75 + (Math.random() < .15 ? 120 : 0);    /* rapid fire, the odd beat between bursts */
      }
    }
    new IntersectionObserver(es => es.forEach(e => (e.isIntersecting ? volley() : clear())), { threshold: .6 })
      .observe(endTitle);
  }

  /* ---------- sound: off until asked, synthesized by the kit ---------- */
  const toggle = $('.sound-toggle');
  toggle?.addEventListener('click', () => {
    if (!sfx) return;
    const on = sfx.toggle();
    toggle.setAttribute('aria-pressed', String(on));
    toggle.textContent = on ? 'Sound on' : 'Sound off';
  });

})();
