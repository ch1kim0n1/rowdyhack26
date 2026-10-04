/* WebGL scenes: where one picture becomes another instead of fading across it.
   The story's two photographs of the crew. As the scroll takes the scene from its
   first beat to its second, ink lands on the first photograph at the hat's lens and
   spreads across the print like a puddle: an uneven front, running further where the
   paper lets it, red and wet at its lip. Where it has passed, the second photograph
   is there. It is the kit's one ink (--stamp, --stamp-lit), and it moves only as the
   scroll does, so scrolling back draws it in again.
   Both photographs stay in the page as images, with their alt text; the canvas is
   only how they are shown. No WebGL, a lost context, a photograph that has not
   loaded, or motion reduced or paused: this file stands down and the page's own CSS
   crossfade (premiere-scroll.css) is what shows. It draws only when the scene is
   near the window and its progress has changed. */
(() => {
  'use strict';
  const cinema = window.ScrollCinema, capability = window.MotionPresets?.capability;
  const plate = document.querySelector('.statement-plate');
  const images = [...(plate?.querySelectorAll('.statement-image') || [])];
  if (!cinema || !capability?.webgl || images.length !== 2) return;

  const canvas = document.createElement('canvas');
  canvas.className = 'statement-morph';
  canvas.setAttribute('aria-hidden', 'true');
  canvas.dataset.running = 'false';
  const gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false });
  if (!gl) return;

  const VERTEX = `
    attribute vec2 corner;
    varying vec2 at;
    void main() {
      at = vec2(corner.x * .5 + .5, .5 - corner.y * .5);      /* the plate, 0..1, top left first */
      gl_Position = vec4(corner, 0., 1.);
    }`;
  /* Each photograph is placed as CSS places it (object-fit: cover, at its own
     object-position) and graded as CSS grades it, so the canvas and the images it
     stands in for agree. The grade is done here and not by a filter on the canvas,
     because a filter would take the red out of the ink as well. */
  const FRAGMENT = `
    precision mediump float;
    varying vec2 at;
    uniform sampler2D first, second;
    uniform vec4 fitFirst, fitSecond;
    uniform vec2 origin;
    uniform float progress, aspect;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    /* Gradient noise, not value noise: its contours are round, and a puddle's edge has no corners. */
    vec2 lean(vec2 i) { float a = 6.2831853 * hash(i); return vec2(cos(a), sin(a)); }
    float grain(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      vec2 u = f * f * f * (f * (f * 6. - 15.) + 10.);
      float a = dot(lean(i), f), b = dot(lean(i + vec2(1., 0.)), f - vec2(1., 0.));
      float c = dot(lean(i + vec2(0., 1.)), f - vec2(0., 1.)), d = dot(lean(i + vec2(1.)), f - vec2(1.));
      return mix(mix(a, b, u.x), mix(c, d, u.x), u.y) * .7 + .5;
    }
    /* Four turns of it, each at an angle to the last, so no edge of the grid shows through. */
    float haze(vec2 p) {
      float sum = 0., weight = .5;
      for (int turn = 0; turn < 4; turn++) {
        sum += grain(p) * weight;
        p = mat2(1.6, 1.2, -1.2, 1.6) * p + 7.3;
        weight *= .5;
      }
      return sum / .9375;
    }
    /* grayscale(1) contrast(1.08) brightness(.88), as premiere-scroll.css has it on the images */
    vec3 grade(vec3 c) { return vec3(((dot(c, vec3(.2126, .7152, .0722)) - .5) * 1.08 + .5) * .88); }
    void main() {
      vec2 p = vec2(at.x * aspect, at.y), o = vec2(origin.x * aspect, origin.y);
      /* how far the ink must run to reach the furthest corner of the print */
      float reach = max(max(distance(o, vec2(0.)), distance(o, vec2(aspect, 0.))), max(distance(o, vec2(0., 1.)), distance(o, vec2(aspect, 1.))));
      vec2 q = mat2(.8, .6, -.6, .8) * p;
      /* Distance from where it landed, made uneven: it runs further where the paper lets it. */
      float run = distance(p, o) / reach + (haze(q * 2.4) - .5) * .7 + (haze(q * 7. + 17.) - .5) * .14;
      /* The front starts behind every point of the print and ends beyond every point of it,
         so at 0 the first photograph is untouched and at 1 the second is. */
      float edge = run - mix(-.6, 1.7, progress);                 /* below zero: the ink has been here */
      float wet = smoothstep(.006, -.006, edge);
      /* The lip of a puddle stands proud and bends what is under it. */
      vec2 bend = normalize(p - o + 1e-4) * smoothstep(.07, 0., abs(edge)) * .012 * vec2(1. / aspect, 1.);
      vec3 a = grade(texture2D(first, (at + bend) * fitFirst.xy + fitFirst.zw).rgb);
      vec3 b = grade(texture2D(second, (at - bend) * fitSecond.xy + fitSecond.zw).rgb);
      vec3 picture = mix(a * (1. - .3 * smoothstep(.05, 0., edge)), b, wet);      /* and throws a little shadow ahead of itself */
      /* The ink is deep at the front and thins away behind it, and the new picture comes up through it. */
      vec3 ink = mix(vec3(.647, .176, .196), vec3(.898, .455, .463), smoothstep(-.035, 0., edge));
      picture = mix(picture, ink, wet * smoothstep(-.17, 0., edge) * .84);
      /* one line of light along the very lip, where it is wettest */
      picture += vec3(.95, .94, .91) * smoothstep(.011, 0., abs(edge + .005)) * .5;
      gl_FragColor = vec4(picture, 1.);
    }`;
  /* Where the ink lands: the hat's lens, as a part of the first photograph's width and height. */
  const LENS = [.375, .1];

  let G = null, lost = false, dirty = true, drawn = -1, running = false;
  const textures = [null, null];

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
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const corner = gl.getAttribLocation(linked, 'corner');
    gl.enableVertexAttribArray(corner);
    gl.vertexAttribPointer(corner, 2, gl.FLOAT, false, 0, 0);
    const uniform = name => gl.getUniformLocation(linked, name);
    gl.uniform1i(uniform('first'), 0);
    gl.uniform1i(uniform('second'), 1);
    return { fits: [uniform('fitFirst'), uniform('fitSecond')], progress: uniform('progress'), aspect: uniform('aspect'), origin: uniform('origin') };
  }

  function load(index) {
    const image = images[index];
    if (!G || !image.complete || !image.naturalWidth) return;
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + index);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    for (const side of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, side, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    try { gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, image); } catch { return; }
    textures[index] = texture;
    dirty = true;
  }

  function size() {
    dirty = false;
    const width = plate.clientWidth, height = plate.clientHeight;
    if (!width || !height) return false;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform1f(G.aspect, width / height);
    images.forEach((image, index) => {
      /* the image's own box on the plate, then the photograph covering that box */
      const boxWidth = image.offsetWidth, boxHeight = image.offsetHeight;
      const fit = Math.max(boxWidth / image.naturalWidth, boxHeight / image.naturalHeight);
      const shown = [image.naturalWidth * fit, image.naturalHeight * fit];
      const position = getComputedStyle(image).objectPosition.split(' ').map(value => (parseFloat(value) || 0) / 100);
      const left = image.offsetLeft + (boxWidth - shown[0]) * (position[0] ?? .5);
      const top = image.offsetTop + (boxHeight - shown[1]) * (position[1] ?? .5);
      gl.uniform4f(G.fits[index], width / shown[0], height / shown[1], -left / shown[0], -top / shown[1]);
      if (!index) gl.uniform2f(G.origin, (left + LENS[0] * shown[0]) / width, (top + LENS[1] * shown[1]) / height);
    });
    return true;
  }

  function draw(scene) {
    const ready = !lost && !!G && !!textures[0] && !!textures[1] && !capability.reduced
      && !document.body.classList.contains('film-static');
    if (ready !== running) {
      running = ready;
      canvas.dataset.running = String(running);
      plate.classList.toggle('is-morphing', running);
      dirty = true;
    }
    if (!running) return;
    const progress = parseFloat(scene.get('--story-crossfade')) || 0;
    if (!dirty && progress === drawn) return;
    if (dirty && !size()) { dirty = true; return; }
    drawn = progress;
    gl.uniform1f(G.progress, progress);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  function start() {
    G = program();
    textures.fill(null);
    images.forEach((image, index) => load(index));
    again();
  }
  function again() { dirty = true; window.PremiereScroll?.invalidate(); }

  plate.querySelector('.statement-shade')?.before(canvas);
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); lost = true; G = null; again(); });
  canvas.addEventListener('webglcontextrestored', () => { lost = false; start(); });
  images.forEach((image, index) => image.addEventListener('load', () => { load(index); again(); }));
  if (typeof ResizeObserver === 'function') new ResizeObserver(again).observe(plate);
  document.addEventListener('vaultmotionchange', again);
  start();
  cinema.scene('story', draw);
})();
