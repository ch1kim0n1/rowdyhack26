/* The title sequence: Bond's gun barrel, in the crew's colours. Dots roll
   across the dark and the last one opens into a spyglass. The spyglass tracks
   the emblem in from the wing to the centre, locks on and zooms in, then the
   dark closes around the emblem as it returns to its corner of the marquee
   and the premiere fades up from black.
   The head decides whether it plays (html.intro-on): once per session, never
   for reduced or paused motion or a deep link; ?intro replays it. Any key,
   click, wheel or touch skips it. */
(() => {
  const root = document.documentElement;
  const overlay = document.querySelector('.intro');
  if (!root.classList.contains('intro-on') || !overlay) {
    document.querySelector('.intro-skip')?.remove();   /* not playing: the hidden overlay stays, its button goes */
    return;
  }

  const canvas = overlay.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const skipButton = document.querySelector('.intro-skip');
  const mark = document.querySelector('.brand-mark');
  const emblem = new Image();
  emblem.src = mark.src;

  const NIGHT = '#050507', INK = '#0d0e12', PAPER = '242,240,233', RED = '220,40,40';
  const TAU = Math.PI * 2;

  /* the cue sheet, in seconds */
  const DOTS_STOP = 0.9;
  const BLOOM = [0.9, 1.3];      /* the last dot opens into the glass */
  const WALK = [1.05, 2.6];      /* the emblem walks in from the right */
  const TRACK = [1.4, 2.7];      /* the glass follows it to the centre */
  const LOCK = [2.7, 3.0];       /* crosshair, red dot */
  const ZOOM = [3.0, 3.35];      /* into the glass */
  const HOME = [3.35, 4.15];     /* back to the marquee as the dark closes in */

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  const logLerp = (a, b, k) => Math.exp(lerp(Math.log(a), Math.log(b), k));
  const span = (t, [a, b]) => clamp((t - a) / (b - a));
  const outQuad = k => 1 - (1 - k) ** 2;
  const outCubic = k => 1 - (1 - k) ** 3;
  const inOutCubic = k => k < .5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2;
  const outBack = k => 1 + 1.9 * (k - 1) ** 3 + .9 * (k - 1) ** 2;   /* a small overshoot, like a hand on the glass */

  let W = 0, H = 0;
  function size() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* where everything is at time t */
  function state(t) {
    const R = clamp(Math.min(W, H) * .22, 90, 230);   /* the glass */
    const L = R * .62;                                 /* the emblem inside it */
    const cy = H / 2, stopX = W * .7, rd = R * .3;

    /* the dots: one train at one speed; the last one brakes to a stop */
    const gap = rd * 3.4, x3 = -rd - 3 * gap;
    const v = 2 * (stopX - x3) / DOTS_STOP;
    const dots = [];
    if (t < BLOOM[1]) {
      for (let i = 0; i < 3; i++) dots.push(-rd - i * gap + v * t);
    }

    const bloom = outCubic(span(t, BLOOM));
    const s = {
      dots, rd, cy,
      hx: lerp(x3, stopX, outQuad(clamp(t / DOTS_STOP))), hy: cy,
      hr: lerp(rd, R, bloom), wall: bloom, cream: 1 - bloom, rim: bloom,
      lx: 0, ly: cy, lr: L, rot: 0, logo: t >= WALK[0],
      cross: 0, ping: 0, spin: t * .35,
    };

    /* the walk: a stride that settles as it arrives */
    const w = span(t, WALK);
    const step = w * Math.PI * 6, stride = 1 - outCubic(w);
    s.lx = lerp(W + L * 1.4, W / 2, outCubic(w));
    s.ly = cy - Math.abs(Math.sin(step)) * R * .04 * stride;
    s.rot = Math.sin(step) * .06 * stride;

    /* the glass tracks it, a beat behind, with a little handheld sway */
    const k = span(t, TRACK);
    if (t >= TRACK[0]) s.hx = lerp(stopX, W / 2, outBack(k));
    s.hy = cy + Math.sin(t * 3.1) * R * .025 * (1 - span(t, LOCK)) * bloom;

    /* lock on */
    s.cross = clamp(span(t, LOCK) * 2) * (1 - span(t, [ZOOM[1] - .1, HOME[0] + .15]));
    s.ping = t >= LOCK[0] ? span(t, [LOCK[0] + .08, LOCK[1] + .3]) : 0;

    /* zoom in through the glass */
    const z = outCubic(span(t, ZOOM));
    s.hr *= 1 + .55 * z;
    s.lr *= 1 + .3 * z;
    s.spin += z * .9;

    /* home: the emblem returns to the marquee and the dark closes around it */
    if (t >= HOME[0]) {
      const h = span(t, HOME), e = inOutCubic(h);
      const box = mark.getBoundingClientRect();
      const mx = box.left + box.width / 2, my = box.top + box.height / 2, mr = box.width / 2;
      s.lx = lerp(W / 2, mx, e);
      s.ly = lerp(cy, my, e ** 1.6);          /* y lags x, so it arcs up and over */
      s.lr = logLerp(L * 1.3, mr, e);
      s.hx = s.lx; s.hy = s.ly;
      s.hr = logLerp(R * 1.55, mr * 1.02, e);
      s.wall = s.rim = 1 - span(h, [0, .7]);
      s.rot = 0;
    }
    return s;
  }

  /* the barrel: a lit bore, with rifling spiralling out of it into the dark */
  function barrel(x, y, r, alpha, spin) {
    if (alpha <= 0) return;
    const outer = r * 3.4;
    ctx.save();
    ctx.globalAlpha = alpha;
    const wall = ctx.createRadialGradient(x, y, r, x, y, outer);
    wall.addColorStop(0, 'rgba(150,146,138,.5)');
    wall.addColorStop(.12, 'rgba(84,82,80,.36)');
    wall.addColorStop(.45, 'rgba(32,32,36,.2)');
    wall.addColorStop(1, 'rgba(5,5,7,0)');
    ctx.fillStyle = wall;
    ctx.beginPath(); ctx.arc(x, y, outer, 0, TAU); ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,.5)';
    const N = 14, S = 18, width = TAU / N * .46;
    for (let g = 0; g < N; g++) {
      const a0 = spin + g * TAU / N;
      ctx.beginPath();
      for (let j = 0; j <= S; j++) {
        const rr = r * (1 + 2.4 * j / S), a = a0 + .85 * Math.log(rr / r);
        ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      }
      for (let j = S; j >= 0; j--) {
        const rr = r * (1 + 2.4 * j / S), a = a0 + width + .85 * Math.log(rr / r);
        ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      }
      ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }

  function render(s) {
    ctx.fillStyle = NIGHT;
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    ctx.fillStyle = `rgb(${PAPER})`;
    ctx.shadowColor = `rgba(${PAPER},.35)`; ctx.shadowBlur = s.rd * .6;
    for (const x of s.dots) { ctx.beginPath(); ctx.arc(x, s.cy, s.rd, 0, TAU); ctx.fill(); }
    ctx.restore();

    const { hx, hy, hr } = s;
    barrel(hx, hy, hr, s.wall, s.spin);

    /* the view through the glass */
    ctx.save();
    ctx.beginPath(); ctx.arc(hx, hy, hr, 0, TAU); ctx.clip();
    ctx.fillStyle = INK;
    ctx.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);
    const glow = ctx.createRadialGradient(hx, hy + hr * .25, 0, hx, hy, hr);
    glow.addColorStop(0, `rgba(165,45,50,${.42 * s.wall})`);
    glow.addColorStop(1, 'rgba(165,45,50,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);

    if (s.logo && emblem.naturalWidth) {
      ctx.save();
      ctx.translate(s.lx, s.ly); ctx.rotate(s.rot);
      ctx.drawImage(emblem, -s.lr, -s.lr, s.lr * 2, s.lr * 2);
      ctx.restore();
    }

    if (s.cross > 0) {
      const gap = hr * .16;
      ctx.strokeStyle = `rgba(${PAPER},${.55 * s.cross})`; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hx - hr, hy); ctx.lineTo(hx - gap, hy); ctx.moveTo(hx + gap, hy); ctx.lineTo(hx + hr, hy);
      ctx.moveTo(hx, hy - hr); ctx.lineTo(hx, hy - gap); ctx.moveTo(hx, hy + gap); ctx.lineTo(hx, hy + hr);
      ctx.stroke();
      ctx.fillStyle = `rgba(${RED},${s.cross})`;
      ctx.shadowColor = `rgba(${RED},.8)`; ctx.shadowBlur = 8;
      ctx.beginPath(); ctx.arc(hx, hy, 4, 0, TAU); ctx.fill();
      ctx.shadowBlur = 0;
    }
    if (s.ping > 0 && s.ping < 1) {
      ctx.strokeStyle = `rgba(${RED},${.9 * (1 - s.ping)})`; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(hx, hy, lerp(6, hr * .8, outCubic(s.ping)), 0, TAU); ctx.stroke();
      ctx.fillStyle = `rgba(${RED},${.16 * (1 - s.ping)})`;
      ctx.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);
    }

    /* lens falloff toward the rim */
    const edge = ctx.createRadialGradient(hx, hy, hr * .7, hx, hy, hr);
    edge.addColorStop(0, 'rgba(0,0,0,0)');
    edge.addColorStop(1, `rgba(0,0,0,${.55 * s.wall})`);
    ctx.fillStyle = edge;
    ctx.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);

    if (s.cream > 0) {
      ctx.fillStyle = `rgba(${PAPER},${s.cream})`;
      ctx.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);
    }
    ctx.restore();

    if (s.rim > 0) {
      ctx.strokeStyle = `rgba(${PAPER},${.5 * s.rim})`; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(hx, hy, hr, 0, TAU); ctx.stroke();
    }
  }

  /* ---------- running it ---------- */
  let start = 0, raf = 0, fading = false, done = false;
  const SKIPS = ['keydown', 'wheel', 'touchstart'];

  function tick(now) {
    if (done) return;
    start ||= now;
    const t = (now - start) / 1000;
    try { render(state(t)); } catch (err) { console.warn('intro: skipped,', err); fadeOut(true); return; }
    if (t >= HOME[1]) fadeOut(false);
    raf = requestAnimationFrame(tick);
  }

  function fadeOut(quick) {
    if (done || (fading && !quick)) return;
    fading = true;
    overlay.classList.add('out');
    overlay.classList.toggle('quick', quick);
    skipButton?.remove();
    clearTimeout(fadeOut.timer);
    fadeOut.timer = setTimeout(finish, quick ? 400 : 760);
  }

  function finish() {
    done = true;
    cancelAnimationFrame(raf);
    overlay.remove();
    root.classList.remove('intro-on');
    removeEventListener('resize', size);
    SKIPS.forEach(type => removeEventListener(type, skip));
  }

  const skip = () => fadeOut(true);
  SKIPS.forEach(type => addEventListener(type, skip, { passive: true }));
  overlay.addEventListener('pointerdown', skip);
  skipButton?.addEventListener('click', skip);
  addEventListener('resize', size);

  overlay.classList.add('running');                   /* the CSS failsafe stands down */
  try { sessionStorage.setItem('appraisal-intro', 'seen'); } catch { /* replays next load; harmless */ }
  size();
  ctx.fillStyle = NIGHT;
  ctx.fillRect(0, 0, W, H);

  /* the emblem has to be ready before it can walk on; give it a moment, then go without the show */
  const late = new Promise(resolve => setTimeout(resolve, 1500, 'late'));
  /* the load event, not decode(): some embedded Chromium views never settle decode() */
  const loaded = new Promise((resolve, reject) => {
    if (emblem.complete && emblem.naturalWidth) return resolve();
    emblem.addEventListener('load', resolve, { once: true });
    emblem.addEventListener('error', reject, { once: true });
  });
  Promise.race([loaded, late])
    .then(result => { if (result === 'late') throw result; raf = requestAnimationFrame(tick); })
    .catch(err => { console.warn('intro: skipped,', err); fadeOut(true); });
})();
