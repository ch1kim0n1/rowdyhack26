/* The flock. Between the paperwork and the credits the room fades to black, and a
   flock crosses the dark: in from the left, out to the right. Half way over, for one
   beat, it is the diamond.
   Where each bird is comes from the scroll, so scrolling back turns the flock round
   and sends it home. Its wingbeats, and the small circles it flies while it waits,
   are its own. Drawn in the kit's paper, bone and ash; nothing in the page moves for
   it, and with motion paused or reduced it never takes off. */
(() => {
  'use strict';
  const cinema = window.ScrollCinema, capability = window.MotionPresets?.capability;
  if (!cinema || !capability) return;
  const canvas = Object.assign(document.createElement('canvas'), { className: 'flock' });
  canvas.setAttribute('aria-hidden', 'true');
  canvas.dataset.running = 'false';
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const { lerp, range, smooth } = cinema;

  /* The stone, as a cutter draws it: x across and y down, in units of half its width. */
  const GEM = [
    [-.52, -.62, .52, -.62],                            /* the table */
    [-.52, -.62, -1, -.2], [.52, -.62, 1, -.2],         /* the crown */
    [-1, -.2, 1, -.2],                                  /* the girdle */
    [-1, -.2, 0, 1], [1, -.2, 0, 1],                    /* the pavilion, down to the culet */
    [-.52, -.62, -.38, -.2], [.52, -.62, .38, -.2],     /* the crown's facets */
    [-.38, -.2, 0, 1], [.38, -.2, 0, 1],                /* and the pavilion's */
  ];
  const IN = [.04, .44], OUT = [.58, .92];      /* of the crossing: gathering, then leaving */
  const DEPTHS = [                              /* far to near: token, opacity, size */
    ['--ash', .5, .55, .75], ['--bone', .8, .75, 1], ['--paper', .95, 1, 1.3],
  ];

  let birds = [], tones = [], hatched = '', p = 0, raf = 0, last = 0, clock = 0, dirty = true, aloft = false;
  let width = 0, height = 0, cx = 0, cy = 0, radius = 0, unit = 0;

  function random(seed) {
    return () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    };
  }

  /* Every bird has a place on the stone, a way in from the left and a way out to the right. */
  function hatch() {
    const next = random(1138);
    const count = capability.compact ? 70 : capability.lowPower ? 100 : 150;
    const lengths = GEM.map(([x0, y0, x1, y1]) => Math.hypot(x1 - x0, y1 - y0));
    const whole = lengths.reduce((sum, length) => sum + length, 0);
    birds = [];
    GEM.forEach(([x0, y0, x1, y1], line) => {
      const seats = Math.max(2, Math.round(count * lengths[line] / whole));
      for (let i = 0; i < seats; i++) {
        const along = (i + .5 + (next() - .5) * .4) / seats;
        const depth = next() < .35 ? 0 : next() < .6 ? 1 : 2;
        birds.push({
          sx: lerp(x0, x1, along), sy: lerp(y0, y1, along), depth,
          z: lerp(DEPTHS[depth][2], DEPTHS[depth][3], next()),
          ax: -.08 - next() * .5, ay: .15 + next() * .95,       /* where it comes from */
          bx: 1.08 + next() * .5, by: -.25 + next() * .85,      /* and where it goes */
          lag: next() * .1, lead: next() * .07,
          bend: (next() - .35) * .22, rise: (next() - .3) * .2,
          pace: 1.4 + next() * 1.8, phase: next() * Math.PI * 2,
          beat: 9 + next() * 5, flap: next() * Math.PI * 2,
          x: NaN, y: NaN, hx: 1, hy: 0,
        });
      }
    });
    tones = DEPTHS.map(([token]) => getComputedStyle(document.body).getPropertyValue(token).trim() || '#d9d7d0');
  }

  function size() {
    dirty = false;
    width = innerWidth; height = innerHeight;
    const ratio = Math.min(devicePixelRatio || 1, width * height > 2.2e6 ? 1.5 : 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    cx = width * .5; cy = height * .47;
    radius = capability.compact ? Math.min(width * .34, height * .2) : Math.min(width * .16, height * .26);
    unit = Math.min(13, Math.max(7, radius * .055));
    const kind = capability.compact ? 'phone' : 'wide';        /* a phone gets a smaller flock */
    if (kind !== hatched) { hatched = kind; hatch(); }
  }

  const flying = () => p > 0 && p < 1 && !capability.reduced && !document.hidden;

  function land() {
    if (!aloft) return;
    aloft = false; last = 0;
    canvas.dataset.running = 'false';
    ctx.clearRect(0, 0, width, height);
    for (const bird of birds) bird.x = NaN;
  }

  function frame(now) {
    raf = 0;
    if (!flying()) { land(); return; }
    if (dirty) size();
    const dt = last ? Math.min((now - last) / 1000, .05) : 0;
    last = now; clock += dt;
    ctx.clearRect(0, 0, width, height);
    /* The stone is not held still: it sways a little and breathes. */
    const sway = Math.sin(clock * .5) * .035, swell = radius * (1 + Math.sin(clock * .8) * .02);
    const cos = Math.cos(sway) * swell, sin = Math.sin(sway) * swell;
    let shown = 0, formed = 0;
    DEPTHS.forEach(([, opacity], depth) => {
      ctx.beginPath();
      for (const bird of birds) {
        if (bird.depth !== depth) continue;
        const gathered = smooth(range(p, IN[0] + bird.lag, IN[1] + bird.lag));
        const left = smooth(range(p, OUT[0] + bird.lead, OUT[1] + bird.lead));
        const seatX = cx + bird.sx * cos - bird.sy * sin, seatY = cy + bird.sx * sin + bird.sy * cos;
        let x, y;
        if (left <= 0) {
          const k = 1 - (1 - gathered) * (1 - gathered);       /* fast across the dark, gently into its place */
          x = lerp(bird.ax * width, seatX, k);
          y = lerp(bird.ay * height, seatY, k) - Math.sin(gathered * Math.PI) * bird.bend * height;
        } else {
          const k = left * left;
          x = lerp(seatX, bird.bx * width, k);
          y = lerp(seatY, bird.by * height, k) - Math.sin(left * Math.PI) * bird.rise * height;
        }
        const seated = gathered * (1 - left);
        formed += seated;
        const loose = lerp(14, 2.2, seated) * bird.z;           /* it circles while it waits, tighter in its place */
        x += Math.cos(clock * bird.pace + bird.phase) * loose;
        y += Math.sin(clock * bird.pace * 1.3 + bird.phase) * loose * .7;
        /* It faces the way it is going, so a scroll back turns it round. */
        if (bird.x === bird.x) {
          const dx = x - bird.x, dy = y - bird.y;
          if (dx * dx + dy * dy > .04) { bird.hx += (dx - bird.hx) * .25; bird.hy += (dy - bird.hy) * .25; }
        }
        bird.x = x; bird.y = y;
        if (x < -40 || x > width + 40 || y < -40 || y > height + 40) continue;
        const speed = Math.hypot(bird.hx, bird.hy) || 1, ux = bird.hx / speed, uy = bird.hy / speed;
        bird.flap += dt * bird.beat * (1 + Math.min(speed / 12, 1.5));
        const span = .3 + .7 * Math.abs(Math.sin(bird.flap)), scale = unit * bird.z * lerp(1, .82, seated);
        /* A bird from below: nose, shoulder, the bend of the wing, its tip swept back behind
           the body, the trailing edge, a forked tail, and back up the other side. (fx, fy) is
           one length forward and (wx, wy) one across; the wing is drawn in as it beats. */
        const fx = ux * scale, fy = uy * scale, wx = -uy * scale, wy = ux * scale;
        const reach = span + .1, back = -.42 - .2 * (1 - span);
        ctx.moveTo(x + .5 * fx, y + .5 * fy);
        for (const side of [-1, 1]) {
          const sx = wx * side, sy = wy * side;
          const wing = [[.2, .08], [.16, reach * .5], [back, reach], [-.1, reach * .42], [-.2, .08], [-.66, .1], [-.5, 0]];
          if (side > 0) wing.reverse();
          for (const [u, v] of wing) ctx.lineTo(x + u * fx + v * sx, y + u * fy + v * sy);
        }
        ctx.closePath();
        shown++;
      }
      ctx.globalAlpha = opacity;
      ctx.fillStyle = tones[depth];
      ctx.fill();
    });
    const state = [String(shown), (formed / birds.length).toFixed(2)];
    if (canvas.dataset.shown !== state[0]) canvas.dataset.shown = state[0];
    if (canvas.dataset.formed !== state[1]) canvas.dataset.formed = state[1];
    if (!aloft) { aloft = true; canvas.dataset.running = 'true'; }
    raf = requestAnimationFrame(frame);
  }
  function wake() { if (!raf) raf = requestAnimationFrame(frame); }

  document.body.append(canvas);
  /* The crossing is the paperwork leaving: the same stretch of scroll that fades the room to black. */
  cinema.scene('paperwork', (scene, { vh, reduced }) => {
    const reach = Math.min(1, (document.documentElement.scrollHeight - scene.top - scene.height) / vh);
    p = reduced ? 0 : range(scene.exit, .05, .95 * reach);
    if (aloft || flying()) wake();
    /* Far from the window the picture's memory is given back until the flock is wanted again. */
    else if (!scene.active && canvas.width > 1) { canvas.width = canvas.height = 1; dirty = true; }
  });
  addEventListener('resize', () => { dirty = true; }, { passive: true });
  document.addEventListener('visibilitychange', wake);
  document.addEventListener('vaultmotionchange', wake);
  addEventListener('pagehide', () => { cancelAnimationFrame(raf); raf = 0; });
})();
