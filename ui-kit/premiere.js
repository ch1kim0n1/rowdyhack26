/* The premiere page. One shared scroll clock runs pictures through the gate,
   with complete captions and a reversible editorial interlude. The scenes after
   the film are drawn here too, each from its own progress (scroll-cinema.js).
   Everything else is small: the marquee, the wrist screen, and the kit's sound. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const clock = window.PremiereScroll, cinema = window.ScrollCinema;
  let reduced = preference.matches || document.body.classList.contains('motion-paused');
  let layout = {};
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
  const navLinks = $$('.marquee-nav a');
  function chrome(y) {
    marquee.classList.toggle('solid', y > layout.heroHeight * 0.6);
    document.body.classList.toggle('in-reel', !reduced && y >= layout.filmTop && y <= layout.filmEnd);
    const here = layout.sections.findLast(s => s.top < y + innerHeight * .4)?.id;
    navLinks.forEach(a => a.classList.toggle('here', a.hash === '#' + here));
  }

  /* ---------- the wrist, showing this film's case ---------- */
  const WRIST = { case_no: 1138, take: 9920, count: 6, pending: false, revealed: false, top: [
    { item: 'Vintage Rolex', value_usd: 4200 }, { item: 'Oil on canvas, unsigned', value_usd: 2400 },
    { item: 'Leica M3 rangefinder', value_usd: 1850 }, { item: 'First-ed. Hemingway', value_usd: 950 },
    { item: 'Crystal decanter', value_usd: 340 },
  ] };
  if (typeof WristOLED !== 'undefined') $$('canvas.wrist-oled').forEach(c => WristOLED.draw(c, WRIST));

  /* ---------- the method: the board shows the step you're reading ---------- */
  const steps = $$('.step'), prints = $$('.board-print');
  let stepShown = -1;
  const pickStep = y => {
    let best = 0;
    layout.steps.forEach((top, i) => { if (top < y + innerHeight * .5) best = i; });
    if (best === stepShown) return;
    stepShown = best;
    steps.forEach((s, i) => s.classList.toggle('here', i === best));
    prints.forEach(p => p.classList.toggle('on', Number(p.dataset.step) === best));
  };

  /* ---------- the reel ---------- */
  const video = $('.reel-video');
  const chapterEl = $('.reel-chapter'), counter = $('.reel-counter'), sub = $('.reel-sub');
  /* The caption is a line of its own inside its row, so it can come and go by the film's
     time while the row keeps its place (and its fade with the rest of the projector). */
  const said = sub.appendChild(Object.assign(document.createElement('span'), { className: 'reel-line' }));
  const saying = window.MotionPresets?.build(said, 'dialogue', 'lift');
  const SAID_IN = .45, SAID_OUT = .35;      /* seconds of film a caption takes to arrive, and to go */
  const loading = $('.gate-loading'), meter = $('.gate-meter');
  const strip = $('.reel-strip'), stripItems = $$('.reel-strip li');
  let ready = false, frameShown = -1, lastLine = -1, lastT = 0;
  let sequenceReady = false, sequenceFailed = false, videoStarted = false;
  const canvas = $('.reel-canvas');
  const sequence = window.createPremiereSequence?.(canvas, {
    onReady() { sequenceReady = true; loading.classList.add('done'); loading.setAttribute('aria-hidden', 'true'); clock.wake(); },
    onFailure() { sequenceFailed = true; clock.wake(); },
  });
  if (!sequence) sequenceFailed = true;
  // A bounded diagnostic surface is useful for regression and memory-budget checks.
  window.PremiereFilm = { get stats() { return sequence?.stats || null; } };

  /* H.264 where the browser has it (Safari, Chrome), VP9 where it doesn't (Chromium builds) */
  const source = () => {
    const w = Math.min(innerWidth, 1920) * Math.min(devicePixelRatio || 1, 2);
    const ext = video.canPlayType('video/mp4; codecs="avc1.640028"') ? 'mp4' : 'webm';
    return `media/film-${w >= 1300 ? 1600 : 960}.${ext}`;
  };

  // Video is the fallback and the accessible manual player, not a second eager download.
  function thread() {
    if (videoStarted) return;
    videoStarted = true;
    video.addEventListener('loadeddata', () => {
      ready = true; loading.classList.add('done'); frameShown = -1; clock.wake();
    });
    video.addEventListener('seeked', () => clock.wake());
    video.addEventListener('error', () => {
      loading.classList.remove('done');
      loading.querySelector('.label').textContent = 'Film unavailable. Continue to the crew below.';
      meter.hidden = true;
    });
    video.src = source(); video.preload = 'auto'; video.load();
  }
  function syncMotion() {
    reduced = preference.matches || document.body.classList.contains('motion-paused');
    document.body.classList.toggle('film-static', reduced);
    video.controls = reduced;
    video.setAttribute('aria-hidden', String(!reduced));
    if (reduced) {
      sequence?.setActive(false); video.pause(); thread();
      loading.classList.add('done');
      said.textContent = LINES.map(l => l.text).join(' ');
      saying?.clear();
      chapterEl.textContent = 'The film';
    } else video.pause();
    lastLine = -1; frameShown = -1;
    clock.invalidate();
  }
  document.addEventListener('vaultmotionchange', syncMotion);
  preference.addEventListener('change', syncMotion);
  syncMotion();

  function paintReel(t) {
    const f = Math.min(FRAMES - 1, Math.max(0, Math.round(t * FPS)));
    counter.textContent = `FR 00:00:${pad(Math.floor(f / FPS))}:${pad(f % FPS)} · ${pad(Math.floor(f / 16), 4)} FT`;
    const ch = CHAPTERS.findLast(c => t >= c.from - 1e-3) || CHAPTERS[0];
    if (chapterEl.textContent !== ch.label) chapterEl.textContent = ch.label;
    stripItems.forEach(li => li.classList.toggle('here', li.querySelector('a').dataset.t <= t + 1e-3 && (li.nextElementSibling?.querySelector?.('a')?.dataset.t ?? 99) > t));
    strip.style.setProperty('--p', (t / DURATION).toFixed(4));

    // Complete captions remain readable while scrubbing, with no per-character live-region chatter.
    const i = Math.max(0, LINES.findLastIndex(l => t >= l.t - 1e-3));
    if (i !== lastLine) { said.textContent = LINES[i].text; lastLine = i; }
    /* The first is already there when the film opens, and the last stays to the end. */
    saying?.seek(i ? clamp((t - LINES[i].t) / SAID_IN) : 1, i < LINES.length - 1 ? clamp((t - LINES[i].until + SAID_OUT) / SAID_OUT) : 0);
    if (sfx?.on) {
      if (lastT < BEEP_AT && t >= BEEP_AT) sfx.beep();
      if (lastT < THUD_AT && t >= THUD_AT) sfx.thud();
    }
    lastT = t;

    sequence?.render(f);
    canvas.classList.toggle('is-ready', sequenceReady && !sequenceFailed);
    if (sequenceFailed && ready && f !== frameShown && !video.seeking) {
      video.currentTime = (f + 0.5) / FPS;    /* the middle of the frame, never the edge */
      frameShown = f;
    }
  }

  /* the perforations roll with the scroll, like film through a projector */
  const perfs = $$('.perfs');

  const statement = $('.case-statement');
  const invitation = $('.scroll-invitation');
  /* the crew's files and the paperwork's prints: each arrives in turn, dealt a little crooked */
  const deal = (el, i, turns) => ({el, top: 0, offset: (i % 3) * 32, turn: turns[i % turns.length]});
  const files = $$('.dossier').map((el, i) => deal(el, i, [-3, 1.5, 3]));
  const sheets = $$('.paperwork .print').map((el, i) => deal(el, i, [-5, 5]));
  function measure() {
    const filmTop = clock.top(reel);
    layout = {
      heroHeight: hero.offsetHeight, filmTop,
      filmEnd: filmTop + reel.offsetHeight - innerHeight,
      filmLength: Math.max(1, reel.offsetHeight - innerHeight),
      sections: ['film', 'crew', 'method', 'paperwork'].map(id => ({id, top: clock.top(document.getElementById(id))})),
      steps: steps.map(el => clock.top(el)), lastStep: steps.at(-1)?.offsetHeight || 1,
      statementTop: clock.top(statement), statementHeight: statement.offsetHeight,
    };
    for (const sheet of [...files, ...sheets]) sheet.top = clock.top(sheet.el);
  }
  clock.subscribe(({y, rawY, vh}) => {
    chrome(rawY); pickStep(rawY);
    invitation.style.opacity = reduced ? '1' : String(1 - clamp(y / (vh * .35)));
    const near = !reduced && !document.hidden && y > layout.filmTop - vh * 2 && y < layout.filmEnd + vh;
    sequence?.setActive(near && !sequenceFailed);
    if (near) {
      if (sequenceFailed) thread();
      paintReel(clamp((y - layout.filmTop) / layout.filmLength) * DURATION);
      perfs.forEach(p => p.style.setProperty('--roll', `${(-y * .3).toFixed(1)}px`));
    }
  }, measure);

  /* ---------- the scenes after the film (scroll-cinema.js gives each its progress) ---------- */
  const ease = v => 1 - Math.pow(1 - v, 3);
  /* The story has no edges: it comes up out of the film's black as it scrolls into place
     (enter), and before it lets go everything on it has left (exit), so what scrolls away
     is only its ground, dissolving into the crew's. */
  function story(scene) {
    const p = scene.progress, enter = scene.enter;
    const exit = reduced ? 0 : clamp((p - .8) / .18);
    scene.set('--story-enter', enter.toFixed(4));
    scene.set('--story-exit', exit.toFixed(4));
    scene.set('--story-scale', (1.03 + p * .09).toFixed(4));
    scene.set('--story-crossfade', clamp((p - .26) / .24).toFixed(4));
    scene.set('--story-first', (1 - clamp((p - .16) / .2)).toFixed(4));
    scene.set('--story-second', clamp((p - .38) / .18).toFixed(4));
    scene.set('--story-first-y', `${(-p * 60).toFixed(2)}px`);
    scene.set('--story-second-y', `${((1 - clamp((p - .34) / .24)) * 48 - exit * 36).toFixed(2)}px`);
  }
  function arrivals(list, {y, vh, width}) {
    const room = width > 720 ? 1 : 0;      /* on a phone a file fills the column: turned, its corners would leave the page */
    for (const {el, top, offset, turn} of list) {
      const eased = reduced ? 1 : ease(clamp((y + vh * .94 - top - offset) / (vh * .48)));
      el.style.setProperty('--arrival-y', `${((1 - eased) * 90).toFixed(2)}px`);
      el.style.setProperty('--arrival-turn', `${((1 - eased) * turn * room).toFixed(2)}deg`);
      el.style.setProperty('--arrival-opacity', (.15 + eased * .85).toFixed(4));
    }
  }
  /* A scene on its way out sinks back and dims while the next one comes up over it:
     one scene is never finished before the next has begun. It only starts once the
     scene is in the top half of the window, so what is being read stays at full
     strength, and once the scene has left the window it is put back as it was. */
  function recede(el, exit, from = .45, to = 1, floor = .45) {
    const gone = reduced || exit >= 1 ? 0 : cinema.smooth(cinema.range(exit, from, to));
    el.style.opacity = gone ? (1 - gone * (1 - floor)).toFixed(3) : '';
    el.style.translate = gone ? `0 ${(gone * Math.min(innerHeight * .07, 60)).toFixed(1)}px` : '';
  }
  /* The method's board: each print is laid over the last one as its step comes up, by
     the scroll and not by a timer, so a step half read shows its print half laid. */
  function board({y, vh}) {
    const tops = layout.steps, mid = y + vh * .5;
    let i = 0;
    while (i < tops.length - 1 && tops[i + 1] <= mid) i++;
    const length = i < tops.length - 1 ? tops[i + 1] - tops[i] : layout.lastStep;
    const laid = cinema.smooth(cinema.range((mid - tops[i]) / Math.max(1, length), .6, 1));
    prints.forEach(print => {
      const n = Number(print.dataset.step);
      const on = reduced ? null : n === i ? 1 : n === i + 1 ? laid : 0;
      print.style.opacity = on === null ? '' : on.toFixed(3);
      print.style.rotate = on === null ? '' : `${cinema.lerp(-1.2, .6, on).toFixed(2)}deg`;
      print.style.scale = on === null ? '' : cinema.lerp(.985, 1, on).toFixed(4);
    });
  }
  const wallpaper = $('.vault-wallpaper'), dossiers = $('.dossiers'), grid = $('.method-grid'), papers = $('.paperwork > .wrap');
  if (cinema) {
    cinema.scene('story', story);
    cinema.scene('crew', (scene, state) => { arrivals(files, state); recede(dossiers, scene.exit); });
    cinema.scene('method', (scene, state) => { board(state); recede(grid, scene.exit); });
    /* paperwork into credits: fade to black, and the credits come up out of it */
    cinema.scene('paperwork', (scene, state) => { arrivals(sheets, state); recede(papers, scene.exit, .1, .8, .15); });
    /* The wall behind the page is one still photograph. Over the length of the page the
       camera closes on it a little, so it is never quite the same frame twice. */
    cinema.scene('premiere', scene => {
      const push = reduced ? 0 : scene.progress;
      wallpaper.style.transform = push ? `translate3d(0, ${(-push * 2).toFixed(3)}vh, 0) scale(${(1 + push * .05).toFixed(4)})` : '';
    });
  } else {
    /* An older hub that does not serve scroll-cinema.js: the story and the arrivals still run. */
    clock.subscribe(state => {
      const {y, vh} = state;
      story({
        progress: reduced ? 1 : clamp((y - layout.statementTop) / Math.max(1, layout.statementHeight - vh)),
        enter: reduced ? 1 : clamp((y + vh - layout.statementTop) / vh),
        set: (name, value) => statement.style.setProperty(name, value),
      });
      arrivals([...files, ...sheets], state);
    });
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { sequence?.setActive(false); video.pause(); }
  });

  /* chapter ticks jump the scroll to that moment */
  $$('.reel-strip a').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    if (reduced) { thread(); video.currentTime = Number(a.dataset.t); return; }
    const len = layout.filmLength;
    const top = layout.filmTop;
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
