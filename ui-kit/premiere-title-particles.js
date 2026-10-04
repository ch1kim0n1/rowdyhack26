/* The title, in diamonds. "THE APPRAISAL JOB" is sampled from the supplied
   artwork and set again in thousands of small cut stones that hold the letters'
   shape, glint, part around the pointer and scatter as the camera leaves for the
   vault. Only the three title words are touched: there is no ambient field, and
   the lines above and below the title stay as painted. With motion paused or
   reduced, or with no WebGL, the original lettering shows instead. */
(() => {
  'use strict';
  const stage = document.querySelector('.hero .vault-stage');
  const scene = stage?.querySelector('.vault-scene');
  const art = scene?.querySelector('.vault-art');
  if (!stage || !scene || !art) return;

  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const precise = matchMedia('(hover: hover) and (pointer: fine)');
  const layer = name => {
    const el = document.createElement('canvas');
    el.className = name;
    el.setAttribute('aria-hidden', 'true');
    return el;
  };
  const cover = layer('title-cover');         /* paints the wall back in over the painted letters */
  const canvas = layer('title-particles');    /* the letters again, in stones */
  const coverContext = cover.getContext('2d', { willReadFrequently: true });
  const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false });
  if (!coverContext || !gl) return;
  canvas.dataset.running = 'false';

  // Tight, independent word bounds exclude ROWDYHACKS, the tagline, room and
  // diamond. Coordinates are in the original source images, not screen units.
  const sources = {
    wide: { width: 1916, height: 821, words: [[348, 134, 92, 94], [346, 229, 463, 192], [347, 424, 170, 160]] },
    portrait: { width: 1536, height: 1024, words: [[73, 72, 103, 113], [69, 190, 532, 235], [71, 432, 189, 195]] }
  };
  const MARGIN = 8;          /* source px around the words, for the cover's soft edge */
  const COVER = .96;         /* how completely the painted letters are put out under the stones */
  const DENSITY = .25;       /* stones per CSS px of lettering */
  const MOST = 30000;
  const WAIST = .64;         /* a stone's width, as a part of its height */
  const SPRING = .05, DRAG = .86;
  const FIELDS = 14;         /* floats per stone: anchor 2, motion 4, look 4, gather 2, blow 2 */
  const clamp = (n, min = 0, max = 1) => Math.min(max, Math.max(min, n));
  const smooth = v => v * v * (3 - 2 * v);

  /* Each stone idles on a small orbit around its place in a letter. As it turns,
     each of its facets takes the light in its turn, and now and then the whole
     stone flashes. A bar of light also crosses the lettering on a slant. The
     gathering and the scattering are worked out here too, on the card.
     Drawn in two layers: the stones, then only the flares of those flashing. */
  const VERTEX = `
    attribute vec2 anchor, nudge, gather, blow;
    attribute vec4 motion, look;
    uniform vec2 view;
    uniform vec3 sweep;
    uniform float ratio, time, formed, blown;
    uniform mediump float layer;      /* shared with the fragment shader, so the same precision */
    varying float glow, flash, lit, spin, hue;
    void main() {
      float turn = time * motion.y + motion.x;
      vec2 at = anchor + nudge + vec2(sin(turn), cos(turn) * .8) * motion.z;
      float bar = sweep.z * smoothstep(0., 1., 1. - abs(anchor.x + anchor.y * .45 - sweep.x) / sweep.y);
      // One stone in six is cut to flash as it turns; inside the bar, the readiest few do.
      flash = max(step(look.w, .167) * pow(max(0., cos(turn * .61 + motion.x * 3.)), 80.), bar * smoothstep(.88, 1., motion.w));
      float arrived = clamp(formed - look.z, 0., 1.);
      at += gather * pow(1. - arrived, 3.);
      float gone = clamp(blown * 1.7 - motion.w * .7, 0., 1.);
      at += blow * gone * gone;
      glow = clamp(look.y * min(1., arrived * 3.) * (1. - gone), 0., 1.);
      lit = bar;
      spin = mod(turn * 1.9, 6.2832);
      hue = fract(look.w * 6.);      /* the flashing sixth still span every colour */
      gl_Position = vec4(at.x / view.x * 2. - 1., 1. - at.y / view.y * 2., 0., 1.);
      float tall = look.x * ratio;
      if (layer < .5) {
        gl_PointSize = max(2., tall);
      } else {
        float flare = flash * glow;
        gl_PointSize = max(8. * ratio, tall * 2.2) * (1. + flare * 1.3);
        if (flare < .05) gl_Position = vec4(2., 2., 2., 1.);
      }
    }`;
  const FRAGMENT = `
    precision mediump float;
    uniform mediump float layer;
    varying float glow, flash, lit, spin, hue;
    void main() {
      vec2 at = gl_PointCoord - .5;
      if (layer > .5) {
        // A four-pointed flare with a hot centre, and a little of the stone's fire in it.
        float across = max(0., 1. - abs(at.x) * 2.), down = max(0., 1. - abs(at.y) * 2.);
        float rays = exp(-abs(at.y) * 30.) * across * across + exp(-abs(at.x) * 30.) * down * down;
        float star = clamp((rays * .85 + exp(-dot(at, at) * 90.) * .9) * flash * glow, 0., 1.);
        vec3 fire = .5 + .5 * cos(6.2832 * (hue + vec3(0., .33, .67)));
        gl_FragColor = vec4(mix(vec3(1.), fire, .28) * star, star);
        return;
      }
      // A cut stone, point up, taller than it is wide: a flat table in the middle
      // and four facets around it, lit from the upper left.
      float edge = abs(at.x) * ${(2 / WAIST).toFixed(3)} + abs(at.y) * 2.;
      float side = (at.x < 0. ? 0. : 1.) + (at.y < 0. ? 0. : 2.);
      float facet = side < .5 ? .96 : side < 1.5 ? .68 : side < 2.5 ? .42 : .2;
      float catching = pow(max(0., sin(spin + side * 1.5708)), 10.);
      float bright = mix(facet, 1.15, catching);
      float table = 1. - smoothstep(.34, .42, edge);
      bright = mix(bright, .7 + .35 * catching, table);
      bright -= .3 * smoothstep(.34, .42, edge) * (1. - smoothstep(.42, .52, edge));
      bright += lit * .2 + flash * .6;
      vec3 tone = mix(vec3(.12, .15, .22), vec3(.85, .91, .99), smoothstep(0., .8, bright));
      tone = mix(tone, vec3(1.), smoothstep(.72, 1.15, bright));
      float a = glow * (1. - smoothstep(.84, 1., edge));
      gl_FragColor = vec4(tone * a, a);
    }`;

  let raf = 0, last = 0, elapsed = 0, formed = 0, camera = 0;
  let dirty = true, ready = false, intersecting = true, stopped = false, lost = false;
  let running = false, replay = true, moving = false;
  let width = 0, height = 0, fit = 1, pad = 0, reach = 0, dpr = 1, hidden = 0;
  let sourceKey = '', sampled = null, P = null, G = null, built = 0, settle = 0, density = 0;
  const pointer = { x: 0, y: 0, on: false };

  function randomGenerator() {
    let seed = 1138;
    return () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    };
  }

  function program() {
    const build = (type, text) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, text);
      gl.compileShader(shader);
      return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
    };
    const vertex = build(gl.VERTEX_SHADER, VERTEX), fragment = build(gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vertex || !fragment) return null;
    const linked = gl.createProgram();
    gl.attachShader(linked, vertex);
    gl.attachShader(linked, fragment);
    gl.linkProgram(linked);
    if (!gl.getProgramParameter(linked, gl.LINK_STATUS)) return null;
    gl.useProgram(linked);
    const at = name => gl.getAttribLocation(linked, name);
    const uniform = name => gl.getUniformLocation(linked, name);
    const stones = gl.createBuffer(), nudges = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, stones);
    [['anchor', 2, 0], ['motion', 4, 2], ['look', 4, 6], ['gather', 2, 10], ['blow', 2, 12]].forEach(([name, size, offset]) => {
      gl.enableVertexAttribArray(at(name));
      gl.vertexAttribPointer(at(name), size, gl.FLOAT, false, FIELDS * 4, offset * 4);
    });
    gl.bindBuffer(gl.ARRAY_BUFFER, nudges);
    gl.enableVertexAttribArray(at('nudge'));
    gl.vertexAttribPointer(at('nudge'), 2, gl.FLOAT, false, 0, 0);
    gl.enable(gl.BLEND);
    gl.clearColor(0, 0, 0, 0);
    return { stones, nudges, view: uniform('view'), sweep: uniform('sweep'), ratio: uniform('ratio'),
      time: uniform('time'), formed: uniform('formed'), blown: uniform('blown'), layer: uniform('layer') };
  }

  /* Reads the lettering out of the artwork once per image: where the letters
     are (where stones may be set), and a cover that paints the wall back in over
     them, filled from the nearest wall on each side. */
  function sampleTitle(source) {
    const x0 = Math.max(0, Math.min(...source.words.map(w => w[0])) - MARGIN);
    const y0 = Math.max(0, Math.min(...source.words.map(w => w[1])) - MARGIN);
    const x1 = Math.min(source.width, Math.max(...source.words.map(w => w[0] + w[2])) + MARGIN);
    const y1 = Math.min(source.height, Math.max(...source.words.map(w => w[1] + w[3])) + MARGIN);
    const W = x1 - x0, H = y1 - y0;
    cover.width = W;
    cover.height = H;
    const sx = art.naturalWidth / source.width, sy = art.naturalHeight / source.height;
    coverContext.drawImage(art, x0 * sx, y0 * sy, W * sx, H * sy, 0, 0, W, H);
    const plate = coverContext.getImageData(0, 0, W, H);
    const data = plate.data;

    const lit = new Uint8Array(W * H), body = new Uint8Array(W * H);
    const ink = [];
    for (const [wx, wy, ww, wh] of source.words) {
      for (let y = wy - y0 - 3; y < wy - y0 + wh + 3; y++) {
        for (let x = wx - x0 - 3; x < wx - x0 + ww + 3; x++) {
          const i = y * W + x, p = i * 4;
          const lum = (data[p] * 299 + data[p + 1] * 587 + data[p + 2] * 114) / 1000;
          if (lum > 46) lit[i] = 1;
          if (lum > 120 && x >= wx - x0 && x < wx - x0 + ww && y >= wy - y0 && y < wy - y0 + wh) { ink.push(i); body[i] = 1; }
        }
      }
    }
    if (!ink.length) return null;

    // Grow the lit area past the letters' soft fringe.
    const grown = new Uint8Array(W * H), hide = new Uint8Array(W * H);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      for (let k = Math.max(0, x - 3); k <= Math.min(W - 1, x + 3); k++) if (lit[y * W + k]) { grown[y * W + x] = 1; break; }
    }
    for (let x = 0; x < W; x++) for (let y = 0; y < H; y++) {
      for (let k = Math.max(0, y - 3); k <= Math.min(H - 1, y + 3); k++) if (grown[k * W + x]) { hide[y * W + x] = 1; break; }
    }

    // Each hidden pixel takes the wall on either side of it, nearest first.
    const fill = new Float32Array(W * H * 3), weight = new Float32Array(W * H);
    const take = (i, from, distance) => {
      const k = 1 / (distance * distance), p = from * 4;
      fill[i * 3] += data[p] * k; fill[i * 3 + 1] += data[p + 1] * k; fill[i * 3 + 2] += data[p + 2] * k;
      weight[i] += k;
    };
    for (let y = 0; y < H; y++) {
      for (let x = 0, wall = -1; x < W; x++) { const i = y * W + x; if (!hide[i]) wall = x; else if (wall >= 0) take(i, y * W + wall, x - wall); }
      for (let x = W - 1, wall = -1; x >= 0; x--) { const i = y * W + x; if (!hide[i]) wall = x; else if (wall >= 0) take(i, y * W + wall, wall - x); }
    }
    for (let x = 0; x < W; x++) {
      for (let y = 0, wall = -1; y < H; y++) { const i = y * W + x; if (!hide[i]) wall = y; else if (wall >= 0) take(i, wall * W + x, y - wall); }
      for (let y = H - 1, wall = -1; y >= 0; y--) { const i = y * W + x; if (!hide[i]) wall = y; else if (wall >= 0) take(i, wall * W + x, wall - y); }
    }
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const i = y * W + x, p = i * 4;
      if (hide[i] && weight[i]) {
        data[p] = fill[i * 3] / weight[i]; data[p + 1] = fill[i * 3 + 1] / weight[i]; data[p + 2] = fill[i * 3 + 2] / weight[i];
      }
      // A soft edge, so the cover never shows as a cut-out.
      let sum = 0, count = 0;
      for (let v = Math.max(0, y - 2); v <= Math.min(H - 1, y + 2); v++) {
        for (let u = Math.max(0, x - 2); u <= Math.min(W - 1, x + 2); u++) { sum += hide[v * W + u]; count++; }
      }
      data[p + 3] = Math.round(255 * smooth(sum / count));
    }
    coverContext.putImageData(plate, 0, 0);
    return { x: x0, y: y0, w: W, h: H, ink, body };
  }

  function objectPosition(value, freeSpace) {
    if (value === 'left' || value === 'top') return 0;
    if (value === 'right' || value === 'bottom') return freeSpace;
    if (value?.endsWith('%')) return freeSpace * parseFloat(value) / 100;
    if (value?.endsWith('px')) return parseFloat(value);
    return freeSpace * .5;
  }

  function setStones() {
    const random = randomGenerator();
    const bell = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(random() * Math.PI * 2);
    const { ink, body, w: W, h: H } = sampled;
    // Where the title is drawn small the stones are finer and there are more of
    // them, so the letters still read.
    const small = clamp(fit / .85, .3, 1.1), grain = clamp(fit / .85, .45, 1.5);
    const n = Math.round(clamp(ink.length * fit * fit * DENSITY / Math.pow(Math.min(1, grain), 1.6), 900, MOST));
    const data = new Float32Array(n * FIELDS);
    const cx = pad + W * fit * .5, cy = pad + H * fit * .5;
    // Would a stone this tall, set here, lie wholly inside its letter?
    const inside = (x, y, tall) => {
      const up = Math.round(tall * .5 / fit), out = Math.round(tall * WAIST * .5 / fit);
      return x >= out && x + out < W && y >= up && y + up < H
        && body[y * W + x - out] && body[y * W + x + out] && body[(y - up) * W + x] && body[(y + up) * W + x];
    };
    for (let i = 0, k = 0; i < n; i++, k += FIELDS) {
      // Each stone is set inside its letter: tried in a few places, then cut
      // smaller until it fits. Strokes keep their edges and the gaps between
      // letters stay open, which is what keeps the title readable.
      // The last few are larger stones, drawn on top, where a stroke is wide enough to take one.
      let at = 0, tall = (i > n * .93 ? 6.2 + random() * 3.4 : 2.7 + random() * 2.9) * grain;
      let set = false;
      for (let tries = 0; tries < 8 && !set; tries++) {
        at = ink[Math.floor(random() * ink.length)];
        set = inside(at % W, Math.floor(at / W), tall);
        if (!set && tries % 2) tall *= .8;
      }
      // If nowhere was found whole, the seat is left empty (its fields stay
      // zeroed, so nothing draws there) rather than a stone overhanging its
      // letter and breaking the stroke's edge.
      if (!set) continue;
      let x = pad + ((at % W) + random()) * fit, y = pad + (Math.floor(at / W) + random()) * fit;
      const stray = random() < .03;    /* a few have come loose and lie just outside */
      if (stray) { x += bell() * 4 * small; y += bell() * 4 * small; }
      const depth = random();          /* when it lets go as the camera leaves; how readily it catches the bar of light */
      data[k] = x; data[k + 1] = y;
      data[k + 2] = random() * Math.PI * 2;                                                    /* phase */
      data[k + 3] = .5 + random() * .95;                                                       /* pace */
      data[k + 4] = (random() < .03 ? 2.2 + random() * 2 : .25 + random() * .9) * small;       /* orbit */
      data[k + 5] = depth;
      data[k + 6] = stray ? tall * .7 : tall;                                                  /* height */
      data[k + 7] = stray ? .5 : .9 + random() * .1;                                           /* how solid */
      data[k + 8] = random() * .35;                                                            /* when it gathers */
      data[k + 9] = random();                                                                  /* the colour of its fire */
      const from = random() * Math.PI * 2, far = pad * (.3 + random() * .7);
      data[k + 10] = Math.cos(from) * far; data[k + 11] = Math.sin(from) * far;
      const away = Math.atan2(y - cy, x - cx) + (random() - .5) * 1.5, blown = pad * (.35 + random() * .6);
      data[k + 12] = Math.cos(away) * blown; data[k + 13] = Math.sin(away) * blown - pad * .12;
    }
    return { n, data, nudge: new Float32Array(n * 2), speed: new Float32Array(n * 2) };
  }

  function measure() {
    dirty = false;
    const fail = () => { ready = false; };
    if (lost || !art.complete || !art.naturalWidth || !art.clientWidth || !art.clientHeight) return fail();
    const made = !G;
    G ||= program();
    if (!G) { stopped = true; return fail(); }
    /* The same rule premiere-portal.js uses: which artwork is showing is judged
       by its shape (wide ~2.3:1, portrait 1.5:1), not its name. */
    const key = art.naturalWidth / art.naturalHeight < 2 ? 'portrait' : 'wide';
    const source = sources[key];
    const swapped = sourceKey !== key;
    try {
      if (swapped || !sampled) sampled = sampleTitle(source);
      sourceKey = key;
    } catch {
      // A future cross-origin art source may prevent pixel reads. Leave the
      // original title untouched instead of drawing incorrectly placed stones.
      sampled = null;
    }
    if (!sampled) return fail();
    const css = getComputedStyle(art);
    const scaleX = art.clientWidth / source.width;
    const scaleY = art.clientHeight / source.height;
    const scale = css.objectFit === 'contain' ? Math.min(scaleX, scaleY) : Math.max(scaleX, scaleY);
    const position = css.objectPosition.split(/\s+/);
    const left = art.offsetLeft + objectPosition(position[0], art.clientWidth - source.width * scale) + sampled.x * scale;
    const top = art.offsetTop + objectPosition(position[1], art.clientHeight - source.height * scale) + sampled.y * scale;
    Object.assign(cover.style, { left: `${left}px`, top: `${top}px`, width: `${sampled.w * scale}px`, height: `${sampled.h * scale}px` });
    if (P && !made && !swapped) {
      // Nothing to remake if only the title's position moved. And while the
      // window is still being dragged, stretch the stones already drawn and
      // remake them at the new size once the resizing settles.
      const k = scale / fit, same = Math.abs(k - 1) < .002 && devicePixelRatio === density;
      if (same || performance.now() - built < 200) {
        Object.assign(canvas.style, { left: `${left - pad * k}px`, top: `${top - pad * k}px`, width: `${width * k}px`, height: `${height * k}px` });
        clearTimeout(settle);
        if (!same) settle = setTimeout(resize, 220);
        return;
      }
    }
    fit = scale;
    // Room around the words for stones the pointer or the camera has knocked loose.
    pad = Math.round(clamp(sampled.w * fit * .22, 30, 96));
    reach = clamp(sampled.w * fit * .19, 30, 84);
    width = sampled.w * fit + pad * 2;
    height = sampled.h * fit + pad * 2;
    Object.assign(canvas.style, { left: `${left - pad}px`, top: `${top - pad}px`, width: `${width}px`, height: `${height}px` });
    density = devicePixelRatio;
    dpr = Math.min(density || 1, width * height < 2e5 ? 3 : 2);
    // A phone's title is a few millimetres tall: there the painted letters stay
    // faintly under the stones, which alone could not hold their shape.
    hidden = COVER * (.5 + .5 * smooth(clamp((fit - .3) / .3)));
    canvas.width = Math.ceil(width * dpr);
    canvas.height = Math.ceil(height * dpr);
    P = setStones();
    moving = false;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(G.view, width, height);
    gl.uniform1f(G.ratio, dpr);
    gl.bindBuffer(gl.ARRAY_BUFFER, G.stones);
    gl.bufferData(gl.ARRAY_BUFFER, P.data, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, G.nudges);
    gl.bufferData(gl.ARRAY_BUFFER, P.nudge, gl.DYNAMIC_DRAW);
    canvas.dataset.source = key;
    canvas.dataset.particleCount = String(P.n);
    if (running) cover.style.opacity = hidden.toFixed(3);
    built = performance.now();
    ready = true;
  }

  function canAnimate() {
    return ready && intersecting && !document.hidden && !reduced.matches
      && !document.body.classList.contains('motion-paused')
      && !document.documentElement.classList.contains('intro-on');
  }

  /* The pointer pushes the stones aside; each springs back to its place in a letter. */
  function part(step) {
    const { n, data, nudge, speed } = P;
    const hot = precise.matches && pointer.on;
    if (!hot && !moving) return;
    const px = pointer.x, py = pointer.y, r2 = reach * reach, push = reach * .03 * step;
    const drag = Math.pow(DRAG, step), pull = SPRING * step;
    let stir = false;
    for (let i = 0, j = 0, k = 0; i < n; i++, j += 2, k += FIELDS) {
      if (hot) {
        const qx = data[k] + nudge[j] - px, qy = data[k + 1] + nudge[j + 1] - py, d2 = qx * qx + qy * qy;
        if (d2 < r2) {
          const d = Math.sqrt(d2) || 1, f = 1 - d / reach;
          speed[j] += qx / d * f * f * push; speed[j + 1] += qy / d * f * f * push;
        }
      }
      speed[j] = (speed[j] - nudge[j] * pull) * drag; speed[j + 1] = (speed[j + 1] - nudge[j + 1] * pull) * drag;
      nudge[j] += speed[j] * step; nudge[j + 1] += speed[j + 1] * step;
      if (!stir && Math.abs(nudge[j]) + Math.abs(nudge[j + 1]) + Math.abs(speed[j]) + Math.abs(speed[j + 1]) > .04) stir = true;
    }
    if (!stir) { nudge.fill(0); speed.fill(0); }
    moving = stir;
    gl.bindBuffer(gl.ARRAY_BUFFER, G.nudges);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, nudge);
  }

  /* One frame. Returns true when nothing is left to move, so the loop can rest. */
  function draw(dt) {
    // The title has left the frame by the time the camera is this far in.
    const blown = smooth(clamp((camera - .015) / .4));
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (blown >= 1) return true;
    part(dt * 60);
    // Every few seconds a bar of light crosses the lettering, corner to corner.
    const pass = (elapsed % 4.8) / 1.5, bar = width * .13, span = width + height * .45;
    gl.uniform3f(G.sweep, pass * (span + bar * 2) - bar, bar, pass < 1 ? 1 : 0);
    gl.uniform1f(G.time, elapsed);
    gl.uniform1f(G.formed, Math.min(formed, 4));
    gl.uniform1f(G.blown, blown);
    // The stones lie over one another, the later ones on top...
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.uniform1f(G.layer, 0);
    gl.drawArrays(gl.POINTS, 0, P.n);
    // ...and their flares are light, added over all of them.
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.uniform1f(G.layer, 1);
    gl.drawArrays(gl.POINTS, 0, P.n);
    return false;
  }

  function frame(timestamp) {
    raf = 0;
    if (stopped) return;
    if (dirty) measure();
    const next = canAnimate();
    if (next !== running) {
      running = next;
      canvas.dataset.running = String(running);
      canvas.style.opacity = running ? '1' : '0';
      cover.style.opacity = running ? hidden.toFixed(3) : '0';
      // The stones gather into the title when it first appears and when motion resumes.
      if (running && replay) { formed = 0; replay = false; }
      last = 0;
    }
    if (!running) return;
    const dt = last ? Math.min((timestamp - last) / 1000, .05) : 0;
    last = timestamp;
    elapsed += dt;
    formed += dt;
    if (draw(dt)) last = 0;
    else raf = requestAnimationFrame(frame);
  }

  function schedule() { if (!raf && !stopped) raf = requestAnimationFrame(frame); }
  function resize() { dirty = true; schedule(); }
  function rest() {
    if (document.body.classList.contains('motion-paused') || document.documentElement.classList.contains('intro-on')) replay = true;
    schedule();
  }
  function leave() { pointer.on = false; }
  function move(event) {
    if (!running || !precise.matches) return;
    const rect = canvas.getBoundingClientRect();
    // Undo the parent camera scale before applying the local response.
    pointer.x = (event.clientX - rect.left) * width / (rect.width || 1);
    pointer.y = (event.clientY - rect.top) * height / (rect.height || 1);
    pointer.on = pointer.x > -reach && pointer.y > -reach && pointer.x < width + reach && pointer.y < height + reach;
  }
  function follow(event) {
    const next = event.detail?.camera || 0;
    if (next === camera) return;
    camera = next;
    schedule();
  }

  scene.append(cover, canvas);
  // A lost graphics context hides the stones, which leaves the painted title.
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); lost = true; ready = false; G = null; schedule(); });
  canvas.addEventListener('webglcontextrestored', () => { lost = false; resize(); });
  const visibility = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
    intersecting = entries[0].isIntersecting;
    schedule();
  }, { threshold: 0 }) : null;
  visibility?.observe(canvas);
  const sizing = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
  sizing?.observe(stage);
  const intro = new MutationObserver(rest);
  intro.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  art.addEventListener('load', resize);
  addEventListener('resize', resize, { passive: true });
  document.addEventListener('visibilitychange', schedule);
  document.addEventListener('vaultmotionchange', rest);
  document.addEventListener('premiereportal', follow);
  if (reduced.addEventListener) reduced.addEventListener('change', rest);
  else reduced.addListener(rest);                        /* Safari 13 and older */
  stage.addEventListener('pointermove', move, { passive: true });
  stage.addEventListener('pointerleave', leave, { passive: true });
  addEventListener('pagehide', event => {
    cancelAnimationFrame(raf);
    clearTimeout(settle);
    raf = 0;
    last = 0;
    if (event.persisted) return;
    stopped = true;
    visibility?.disconnect();
    sizing?.disconnect();
    intro.disconnect();
    art.removeEventListener('load', resize);
    removeEventListener('resize', resize);
    document.removeEventListener('visibilitychange', schedule);
    document.removeEventListener('vaultmotionchange', rest);
    document.removeEventListener('premiereportal', follow);
    if (reduced.removeEventListener) reduced.removeEventListener('change', rest);
    else reduced.removeListener(rest);
    stage.removeEventListener('pointermove', move);
    stage.removeEventListener('pointerleave', leave);
  });
  addEventListener('pageshow', resize);
  schedule();
})();
