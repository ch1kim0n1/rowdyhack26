/* WebGL scenes: where one picture becomes another instead of fading across it.
   The story's two photographs of the crew: as the scroll takes the scene from its
   first beat to its second, the first photograph gives way through a displaced
   dissolve, the picture swimming a little where the two meet, like a dissolve cut on
   an optical printer. Both photographs stay in the page as images, with their alt
   text; the canvas is only how they are shown.
   No WebGL, a lost context, a photograph that has not loaded, or motion reduced or
   paused: this file stands down and the page's own CSS crossfade
   (premiere-scroll.css) is what shows. It draws only when the scene is near the
   window and its progress has changed. */
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
     object-position), so the canvas and the images it stands in for agree. */
  const FRAGMENT = `
    precision mediump float;
    varying vec2 at;
    uniform sampler2D first, second;
    uniform vec4 fitFirst, fitSecond;
    uniform float progress, aspect;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float grain(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      f = f * f * f * (f * (f * 6. - 15.) + 10.);
      return mix(mix(hash(i), hash(i + vec2(1., 0.)), f.x), mix(hash(i + vec2(0., 1.)), hash(i + vec2(1., 1.)), f.x), f.y);
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
    void main() {
      vec2 p = mat2(.8, .6, -.6, .8) * vec2(at.x * aspect, at.y) * 2.2;
      float n = haze(p);
      /* The picture swims most at the middle of the dissolve and not at all at either end. */
      float middle = sin(progress * 3.14159);
      vec2 swim = (vec2(n, haze(p + 31.)) - .5) * .09 * middle;
      vec4 a = texture2D(first, (at + swim * progress) * fitFirst.xy + fitFirst.zw);
      vec4 b = texture2D(second, (at - swim * (1. - progress)) * fitSecond.xy + fitSecond.zw);
      /* The second photograph comes through the haze unevenly: nowhere at 0, everywhere at 1. */
      vec3 both = mix(a.rgb, b.rgb, smoothstep(0., .35, progress * 1.35 - n));
      /* Two negatives printed together take a little more light where they overlap. */
      gl_FragColor = vec4(both * (1. + .16 * middle), 1.);
    }`;

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
    return { fits: [uniform('fitFirst'), uniform('fitSecond')], progress: uniform('progress'), aspect: uniform('aspect') };
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
