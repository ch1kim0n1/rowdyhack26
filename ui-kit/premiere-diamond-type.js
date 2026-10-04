/* The story's two headlines, set in stones like the title (premiere-title-particles.js):
   the same cut and the same light, with the accent word in rubies. The letters are read
   from the page's own type, so the words stay real text underneath; with motion paused or
   reduced, or with no WebGL, the type shows as type. The stones follow the scroll: each
   headline's gather as it arrives and blow away as it leaves. */
(() => {
  'use strict';
  const statement = document.querySelector('.case-statement');
  const stage = statement?.querySelector('.statement-stage');
  const types = [...(statement?.querySelectorAll('.statement-line') || [])];
  if (!stage || !types.length) return;

  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const DENSITY = .25;       /* stones per CSS px of lettering */
  const MOST = 26000;
  const WAIST = .64;         /* a stone's width, as a part of its height */
  const FIELDS = 14;         /* floats per stone: anchor 2, motion 4, look 4, gather 2, blow 2 */
  const DIAMOND = [[.12, .15, .22], [.85, .91, .99]];    /* a stone's dark facets, and its lit ones */
  const RUBY = [[.2, .02, .05], [.98, .4, .42]];
  const clamp = (n, min = 0, max = 1) => Math.min(max, Math.max(min, n));

  /* The title's stone: it idles on a small orbit, its facets take the light in turn,
     one in six flashes, and a bar of light crosses the lettering on a slant. */
  const VERTEX = `
    attribute vec2 anchor, gather, blow;
    attribute vec4 motion, look;
    uniform vec2 view;
    uniform vec3 sweep;
    uniform float ratio, time, formed, blown;
    uniform mediump float layer;
    varying float glow, flash, lit, spin, hue;
    void main() {
      float turn = time * motion.y + motion.x;
      vec2 at = anchor + vec2(sin(turn), cos(turn) * .8) * motion.z;
      float bar = sweep.z * smoothstep(0., 1., 1. - abs(anchor.x + anchor.y * .45 - sweep.x) / sweep.y);
      flash = max(step(look.w, .167) * pow(max(0., cos(turn * .61 + motion.x * 3.)), 80.), bar * smoothstep(.88, 1., motion.w));
      float arrived = clamp(formed - look.z, 0., 1.);
      at += gather * pow(1. - arrived, 3.);
      float gone = clamp(blown * 1.7 - motion.w * .7, 0., 1.);
      at += blow * gone * gone;
      glow = clamp(look.y * min(1., arrived * 3.) * (1. - gone), 0., 1.);
      lit = bar;
      spin = mod(turn * 1.9, 6.2832);
      hue = fract(look.w * 6.);
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
    uniform vec3 shade, shine;
    varying float glow, flash, lit, spin, hue;
    void main() {
      vec2 at = gl_PointCoord - .5;
      if (layer > .5) {
        float across = max(0., 1. - abs(at.x) * 2.), down = max(0., 1. - abs(at.y) * 2.);
        float rays = exp(-abs(at.y) * 30.) * across * across + exp(-abs(at.x) * 30.) * down * down;
        float star = clamp((rays * .85 + exp(-dot(at, at) * 90.) * .9) * flash * glow, 0., 1.);
        vec3 fire = .5 + .5 * cos(6.2832 * (hue + vec3(0., .33, .67)));
        gl_FragColor = vec4(mix(vec3(1.), fire, .28) * star, star);
        return;
      }
      float edge = abs(at.x) * ${(2 / WAIST).toFixed(3)} + abs(at.y) * 2.;
      float side = (at.x < 0. ? 0. : 1.) + (at.y < 0. ? 0. : 2.);
      float facet = side < .5 ? .96 : side < 1.5 ? .68 : side < 2.5 ? .42 : .2;
      float catching = pow(max(0., sin(spin + side * 1.5708)), 10.);
      float bright = mix(facet, 1.15, catching);
      float table = 1. - smoothstep(.34, .42, edge);
      bright = mix(bright, .7 + .35 * catching, table);
      bright -= .3 * smoothstep(.34, .42, edge) * (1. - smoothstep(.42, .52, edge));
      bright += lit * .2 + flash * .6;
      vec3 tone = mix(shade, shine, smoothstep(0., .8, bright));
      tone = mix(tone, vec3(1.), smoothstep(.72, 1.15, bright));
      float a = glow * (1. - smoothstep(.84, 1., edge));
      gl_FragColor = vec4(tone * a, a);
    }`;

  function program(gl) {
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
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    [['anchor', 2, 0], ['motion', 4, 2], ['look', 4, 6], ['gather', 2, 10], ['blow', 2, 12]].forEach(([name, size, offset]) => {
      const at = gl.getAttribLocation(linked, name);
      gl.enableVertexAttribArray(at);
      gl.vertexAttribPointer(at, size, gl.FLOAT, false, FIELDS * 4, offset * 4);
    });
    gl.enable(gl.BLEND);
    gl.clearColor(0, 0, 0, 0);
    const uniform = name => gl.getUniformLocation(linked, name);
    return { view: uniform('view'), sweep: uniform('sweep'), ratio: uniform('ratio'), time: uniform('time'),
      formed: uniform('formed'), blown: uniform('blown'), layer: uniform('layer'), shade: uniform('shade'), shine: uniform('shine') };
  }

  function randomGenerator(seed) {
    return () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    };
  }

  /* Where the letters are: each word is drawn again, where the page set it, onto a
     plate one CSS px to the pixel. Plain words in one channel, the accent in another. */
  function readType(type, W, H) {
    const plate = document.createElement('canvas');
    plate.width = W; plate.height = H;
    const ctx = plate.getContext('2d', { willReadFrequently: true });
    const box = type.getBoundingClientRect();
    const walker = document.createTreeWalker(type, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const style = getComputedStyle(node.parentElement);
      ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      if ('letterSpacing' in ctx) ctx.letterSpacing = style.letterSpacing;
      const accent = node.parentElement.closest('em');
      ctx.fillStyle = accent && type.contains(accent) ? '#00f' : '#f00';
      const metrics = ctx.measureText('H');
      const rise = metrics.fontBoundingBoxAscent / (metrics.fontBoundingBoxAscent + metrics.fontBoundingBoxDescent);
      for (const word of node.data.matchAll(/\S+/g)) {
        range.setStart(node, word.index);
        range.setEnd(node, word.index + word[0].length);
        const at = range.getBoundingClientRect();
        if (!at.width) continue;
        const text = style.textTransform === 'uppercase' ? word[0].toUpperCase() : word[0];
        ctx.fillText(text, at.left - box.left, at.top - box.top + at.height * rise);
      }
    }
    const data = ctx.getImageData(0, 0, W, H).data;
    const body = new Uint8Array(W * H), plain = [], accent = [];
    for (let i = 0, p = 0; i < W * H; i++, p += 4) {
      if (data[p + 3] < 150) continue;
      body[i] = 1;
      (data[p + 2] > data[p] ? accent : plain).push(i);
    }
    return { body, plain, accent };
  }

  /* Each stone is set inside its letter: tried in a few places, then cut smaller until
     it fits, so strokes keep their edges and the gaps between letters stay open. */
  function setStones(line, read, W, H, pad, grain) {
    const random = randomGenerator(1138 + line.index * 77);
    const ink = read.plain.length + read.accent.length;
    const n = Math.round(clamp(ink * DENSITY / Math.pow(Math.min(1, grain), 1.6), 600, MOST));
    const rubies = Math.round(n * read.accent.length / ink);
    const data = new Float32Array(n * FIELDS);
    const cx = pad + W * .5, cy = pad + H * .5;
    const inside = (x, y, tall) => {
      const up = Math.round(tall * .5), out = Math.round(tall * WAIST * .5);
      return x >= out && x + out < W && y >= up && y + up < H
        && read.body[y * W + x - out] && read.body[y * W + x + out] && read.body[(y - up) * W + x] && read.body[(y + up) * W + x];
    };
    for (let i = 0, k = 0; i < n; i++, k += FIELDS) {
      const from = i < n - rubies ? read.plain : read.accent;      /* diamonds first, then the rubies */
      const band = i < n - rubies ? i / (n - rubies) : (i - n + rubies) / rubies;
      let at = 0, tall = (band > .93 ? 6.2 + random() * 3.4 : 2.7 + random() * 2.9) * grain, set = false;
      for (let tries = 0; tries < 8 && !set; tries++) {
        at = from[Math.floor(random() * from.length)];
        set = inside(at % W, Math.floor(at / W), tall);
        if (!set && tries % 2) tall *= .8;
      }
      if (!set) continue;                                          /* an empty seat draws nothing */
      const x = pad + (at % W) + random(), y = pad + Math.floor(at / W) + random();
      data[k] = x; data[k + 1] = y;
      data[k + 2] = random() * Math.PI * 2;                        /* phase */
      data[k + 3] = .5 + random() * .95;                           /* pace */
      data[k + 4] = (.25 + random() * .9) * Math.min(1, grain);    /* orbit */
      data[k + 5] = random();                                      /* when it lets go; how readily it catches the bar */
      data[k + 6] = tall;
      data[k + 7] = .9 + random() * .1;                            /* how solid */
      data[k + 8] = random() * .35;                                /* when it gathers */
      data[k + 9] = random();                                      /* the colour of its fire */
      const origin = random() * Math.PI * 2, far = pad * (.3 + random() * .7);
      data[k + 10] = Math.cos(origin) * far; data[k + 11] = Math.sin(origin) * far;
      const away = Math.atan2(y - cy, x - cx) + (random() - .5) * 1.5, blown = pad * (.35 + random() * .6);
      data[k + 12] = Math.cos(away) * blown; data[k + 13] = Math.sin(away) * blown - pad * .12;
    }
    return { n, rubies, data };
  }

  const lines = types.map((type, index) => {
    const canvas = document.createElement('canvas');
    canvas.className = 'statement-stones';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.dataset.running = 'false';
    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false });
    if (!gl) return null;
    const line = { index, type, canvas, gl, G: null, n: 0, rubies: 0, width: 0, height: 0, ready: false, lit: false };
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); line.G = null; line.ready = false; schedule(); });
    canvas.addEventListener('webglcontextrestored', resize);
    type.after(canvas);
    return line;
  }).filter(Boolean);
  if (!lines.length) return;

  let raf = 0, last = 0, elapsed = 0, dirty = true, intersecting = false, stopped = false;

  function measure() {
    dirty = false;
    for (const line of lines) {
      const { type, canvas, gl } = line;
      line.ready = false;
      const W = Math.round(type.offsetWidth), H = Math.round(type.offsetHeight);
      if (!W || !H || gl.isContextLost()) continue;
      line.G ||= program(gl);
      if (!line.G) continue;
      const read = readType(type, W, H);
      if (read.plain.length + read.accent.length < 200) continue;      /* the type has not been set yet */
      /* Room around the words for stones still gathering, or already blown loose. */
      const pad = Math.round(clamp(W * .12, 30, 110));
      const width = W + pad * 2, height = H + pad * 2;
      const dpr = Math.min(devicePixelRatio || 1, width * height < 2e5 ? 3 : 2);
      /* Stones scale with the type, but never below about three device pixels: smaller
         than that a stone has no facets left to draw and the letters thin out. */
      const grain = Math.max(clamp(parseFloat(getComputedStyle(type).fontSize) / 150, .5, 1.3), 1.2 / dpr);
      const stones = setStones(line, read, W, H, pad, grain);
      Object.assign(canvas.style, { left: `${type.offsetLeft - pad}px`, top: `${type.offsetTop - pad}px`, width: `${width}px`, height: `${height}px` });
      canvas.width = Math.ceil(width * dpr);
      canvas.height = Math.ceil(height * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(line.G.view, width, height);
      gl.uniform1f(line.G.ratio, dpr);
      gl.bufferData(gl.ARRAY_BUFFER, stones.data, gl.STATIC_DRAW);
      Object.assign(line, { n: stones.n, rubies: stones.rubies, width, height, ready: true });
      canvas.dataset.particleCount = String(stones.n);
    }
  }

  function canAnimate() {
    return intersecting && !document.hidden && !reduced.matches
      && !document.body.classList.contains('motion-paused')
      && !document.body.classList.contains('film-static');
  }

  function draw(line, formed, blown) {
    const { gl, G, n, rubies, width, height } = line;
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (formed <= 0 || blown >= 1) return;
    /* Every few seconds a bar of light crosses the lettering, corner to corner. */
    const pass = ((elapsed + line.index * 1.9) % 4.8) / 1.5, bar = width * .13, span = width + height * .45;
    gl.uniform3f(G.sweep, pass * (span + bar * 2) - bar, bar, pass < 1 ? 1 : 0);
    gl.uniform1f(G.time, elapsed);
    gl.uniform1f(G.formed, formed);
    gl.uniform1f(G.blown, blown);
    for (const [layer, blend] of [[0, gl.ONE_MINUS_SRC_ALPHA], [1, gl.ONE]]) {     /* the stones, then their flares */
      gl.blendFunc(gl.ONE, blend);
      gl.uniform1f(G.layer, layer);
      for (const [[shade, shine], first, count] of [[DIAMOND, 0, n - rubies], [RUBY, n - rubies, rubies]]) {
        if (!count) continue;
        gl.uniform3fv(G.shade, shade);
        gl.uniform3fv(G.shine, shine);
        gl.drawArrays(gl.POINTS, first, count);
      }
    }
  }

  function frame(timestamp) {
    raf = 0;
    if (stopped) return;
    if (dirty) measure();
    const running = canAnimate();
    for (const line of lines) {
      const lit = running && line.ready;
      if (lit === line.lit) continue;
      line.lit = lit;
      line.canvas.dataset.running = String(lit);
      line.canvas.style.opacity = lit ? '1' : '0';
      line.type.classList.toggle('in-stones', lit);
    }
    if (!running) { last = 0; return; }
    elapsed += last ? Math.min((timestamp - last) / 1000, .05) : 0;
    last = timestamp;
    /* premiere.js writes the scene's progress here on every scroll frame. */
    const read = (name, otherwise) => parseFloat(statement.style.getPropertyValue(name) || otherwise);
    const arrive = [read('--story-enter', '1'), read('--story-second', '0')];
    const leave = [1 - read('--story-first', '1'), read('--story-exit', '0')];
    lines.forEach(line => { if (line.ready) draw(line, arrive[line.index] * 1.35, leave[line.index]); });
    raf = requestAnimationFrame(frame);
  }

  function schedule() { if (!raf && !stopped) raf = requestAnimationFrame(frame); }
  function resize() { dirty = true; schedule(); }

  new IntersectionObserver(entries => { intersecting = entries[0].isIntersecting; schedule(); }).observe(stage);
  const sizing = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
  types.forEach(type => sizing?.observe(type));
  document.fonts?.ready.then(resize);
  addEventListener('resize', resize, { passive: true });
  addEventListener('pageshow', resize);
  document.addEventListener('visibilitychange', schedule);
  /* The scroll clock runs once the other scripts have settled a motion change, so the
     stones come back even when this file hears about the change first. */
  window.PremiereScroll?.subscribe(schedule);
  document.addEventListener('vaultmotionchange', resize);
  if (reduced.addEventListener) reduced.addEventListener('change', resize);
  else reduced.addListener(resize);                        /* Safari 13 and older */
  addEventListener('pagehide', event => {
    cancelAnimationFrame(raf);
    raf = 0; last = 0;
    if (!event.persisted) stopped = true;
  });
  schedule();
})();
