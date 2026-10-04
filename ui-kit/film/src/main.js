/* Film entry point. Builds the set, then exposes window.FILM for render.mjs:
   FILM.seek(t) draws the frame at t seconds, FILM.still() photographs the set
   from anywhere, FILM.mugshot(n) takes an exhibit's booking photo. */
import * as THREE from 'three';
import { build, screenBox } from './scene.js';
import { T, FPS, FRAMES, FINDS, beats, cameraAt, feedTime } from './story.js';
import { makeOverlay } from './overlay.js';
/* global Noir: noir.js is a classic script, its const lives in the global scope */

const W = 1600, H = 900;

async function fonts() {
  await Promise.all([
    '400 40px "League Gothic"', '400 20px "Special Elite"', '400 14px "Courier Prime"',
    '700 14px "Courier Prime"', '500 20px "Caveat"',
  ].map(f => document.fonts.load(f)));
  await document.fonts.ready;
}

const frame = document.getElementById('frame');
const shot = Object.assign(document.createElement('div'), { className: 'shot' });
frame.append(shot);

await fonts();

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
/* nothing that casts a shadow ever moves: draw the shadow maps once */
renderer.shadowMap.autoUpdate = false;
renderer.shadowMap.needsUpdate = true;
shot.append(renderer.domElement);
for (const cls of ['markers', 'wash', 'lens-fall']) shot.append(Object.assign(document.createElement('div'), { className: cls }));

const set = build(renderer);
const { scene, camera } = set;
set.setDustScale(H);

function aim(pos, look, fov = 46, aspect = W / H) {
  camera.fov = fov; camera.aspect = aspect;
  camera.position.set(...pos);
  camera.lookAt(...look);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
}

const nextFrame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

/* render one picture of the set into a data URL, any size, any camera */
function photograph({ pos, look, fov = 46, w = W, h = H, t = 4, exposure = 1, flash = 0, quality = 0.9 }) {
  const rt = new THREE.WebGLRenderTarget(w, h, { samples: 4, colorSpace: THREE.SRGBColorSpace });
  aim(pos, look, fov, w / h);
  set.setDustScale(h);
  set.update(t);
  let bulb = null;
  if (flash) {
    bulb = new THREE.PointLight(0xffffff, flash, 3, 2);
    bulb.position.set(...pos);
    scene.add(bulb);
  }
  const keep = renderer.toneMappingExposure;
  renderer.toneMappingExposure = exposure;
  renderer.setRenderTarget(rt);
  renderer.render(scene, camera);
  const px = new Uint8Array(w * h * 4);
  renderer.readRenderTargetPixels(rt, 0, 0, w, h, px);
  renderer.setRenderTarget(null);
  renderer.toneMappingExposure = keep;
  if (bulb) scene.remove(bulb);
  rt.dispose();
  set.setDustScale(H);
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'), img = g.createImageData(w, h);
  for (let y = 0; y < h; y++) img.data.set(px.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
  g.putImageData(img, 0, 0);
  return c.toDataURL('image/jpeg', quality);
}

/* a booking photo: the exhibit from where the cap first saw it, with a flash */
function mugshot(ex, i) {
  const box = new THREE.Box3().setFromObject(ex.target);
  const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  const seen = cameraAt(beats(FINDS[i], ex.item).marker).pos;
  const dir = new THREE.Vector3(...seen).sub(c).normalize();
  const fov = 30, r = Math.max(size.x, size.y, size.z) * 0.55;
  const dist = Math.max(0.28, r / Math.tan(THREE.MathUtils.degToRad(fov / 2)) * 1.25);
  const pos = c.clone().addScaledVector(dir, dist);
  return photograph({ pos: pos.toArray(), look: c.toArray(), fov, w: 360, h: 480, t: 4, flash: 7 * dist * dist, quality: 0.88 });
}
const mugs = {};
set.exhibits.forEach((ex, i) => { mugs[ex.n] = mugshot(ex, i); });

/* markers: where an exhibit sits in the frame, now or at another moment */
const scratch = camera.clone();
function boxAt(target, at) {
  if (at === undefined) return screenBox(target, camera);
  const c = cameraAt(feedTime(at));
  scratch.position.set(...c.pos); scratch.lookAt(...c.look); scratch.rotateZ(c.roll);
  scratch.updateMatrixWorld(true); scratch.updateProjectionMatrix();
  return screenBox(target, scratch);
}

const overlay = makeOverlay(frame, { exhibits: set.exhibits, mugs, qr: 'src/qr.png', Noir, shot, boxAt });

async function seek(i) {
  frame.classList.remove('bare');
  renderer.toneMappingExposure = 1;
  const t = i / FPS, ft = feedTime(t);
  const c = cameraAt(ft);
  aim(c.pos, c.look);
  camera.rotateZ(c.roll);
  camera.updateMatrixWorld(true);
  if (t >= T.fadeUp && t < T.lineup) {
    set.update(ft);
    renderer.render(scene, camera);
  }
  overlay.update(t, camera);
  await nextFrame();
}

window.FILM = {
  W, H, set, renderer, camera, scene, THREE, T, FPS, frames: FRAMES, mugs, seek,
  /* debug and stills: point the camera anywhere and draw */
  async view({ pos, look, fov = 46, t = 4, exposure = 1 }) {
    frame.classList.add('bare');
    shot.style.display = ''; shot.style.transform = '';
    renderer.toneMappingExposure = exposure;
    aim(pos, look, fov);
    set.update(t);
    renderer.render(scene, camera);
    await nextFrame();
  },
  photograph,
  /* the stills the premiere page uses: hero, the rover's view, the desk, and the booking photos */
  stills() {
    frame.classList.add('bare');
    const out = {
      'still-hero': photograph({ pos: [2.5, 1.44, 0.62], look: [-0.15, 1.24, -2.6], fov: 40, w: 2400, h: 1350, quality: 0.9 }),
      'still-rover': photograph({ pos: [1.25, 0.21, 0.05], look: [-0.45, 0.46, -2.25], fov: 56, w: 1200, h: 900, flash: 1.4 }),
      'still-desk': photograph({ pos: [0.7, 1.36, -0.42], look: [-0.38, 0.84, -1.76], fov: 42, w: 1600, h: 1000 }),
      'still-painting': photograph({ pos: [1.42, 1.62, -0.85], look: [1.55, 1.72, -2.98], fov: 40, w: 1200, h: 900 }),
    };
    for (const [n, url] of Object.entries(mugs)) out[`mug-${n}`] = url;
    frame.classList.remove('bare');
    return out;
  },
  ready: true,
};
document.documentElement.dataset.ready = '1';
