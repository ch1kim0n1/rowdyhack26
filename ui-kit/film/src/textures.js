/* Procedural textures for the film set. Everything is drawn on a canvas from
   a seeded generator, so the same frame renders the same way every time and
   the repo carries no image files for the set. */
import * as THREE from 'three';

/* mulberry32: small, fast, seeded */
export function rng(seed) {
  return () => {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash2(ix, iy, seed) {
  let h = Math.imul(ix, 374761393) ^ Math.imul(iy, 668265263) ^ Math.imul(seed + 1, 1442695041);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}

export function vnoise(x, y, seed = 0) {
  const ix = Math.floor(x), iy = Math.floor(y);
  const fx = x - ix, fy = y - iy;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const a = hash2(ix, iy, seed), b = hash2(ix + 1, iy, seed);
  const c = hash2(ix, iy + 1, seed), d = hash2(ix + 1, iy + 1, seed);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

export function fbm(x, y, oct = 5, seed = 0) {
  let v = 0, amp = 0.5, f = 1;
  for (let i = 0; i < oct; i++) { v += amp * vnoise(x * f, y * f, seed + i * 17); f *= 2; amp *= 0.5; }
  return v;
}

function canvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return [c, c.getContext('2d')];
}

function toTex(c, { repeat = [1, 1], srgb = true } = {}) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat[0], repeat[1]);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/* per-pixel painter: fn(u, v) -> [r, g, b] with u, v in 0..1 */
function paint(w, h, fn) {
  const [c, g] = canvas(w, h);
  const img = g.createImageData(w, h);
  const d = img.data;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, gg, b] = fn(x / w, y / h, x, y);
      const i = (y * w + x) * 4;
      d[i] = r; d[i + 1] = gg; d[i + 2] = b; d[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return [c, g];
}

const clamp255 = v => Math.max(0, Math.min(255, v));

/* old plaster: a mid grey with slow mottling, so stripes of light read on it */
export function plaster() {
  const [c] = paint(512, 512, (u, v) => {
    const m = fbm(u * 6, v * 6, 5, 3) - 0.5;
    const fine = vnoise(u * 180, v * 180, 9) - 0.5;
    const base = 150 + m * 34 + fine * 7;
    return [clamp255(base + 4), clamp255(base), clamp255(base - 8)];
  });
  return toTex(c, { repeat: [3, 2] });
}

/* walnut floorboards, 14cm wide, staggered joints. Covers 4m square per tile. */
export function planks() {
  const W = 1024, H = 1024, rows = 28, R = rng(7);
  const rowLen = [];
  for (let r = 0; r < rows; r++) {
    const cuts = [0]; let x = R() * 0.4;
    while (x < 1) { cuts.push(x); x += 0.28 + R() * 0.32; }
    cuts.push(1);
    rowLen.push(cuts.map((cut, i) => ({ cut, tint: 0.82 + R() * 0.36, seed: r * 31 + i })));
  }
  const [c] = paint(W, H, (u, v) => {
    const row = Math.min(rows - 1, Math.floor(v * rows));
    const fv = v * rows - row;
    const cuts = rowLen[row];
    let k = 0;
    while (k < cuts.length - 1 && cuts[k + 1].cut <= u) k++;
    const p = cuts[k];
    const grain = fbm(u * 3 + p.seed, fv * 0.6 + p.seed * 0.1, 4, p.seed) * 0.6
      + Math.sin((fv * 9 + fbm(u * 4, fv * 2, 3, p.seed) * 6) * 3.14) * 0.08;
    let l = (52 + grain * 46) * p.tint;
    const edge = Math.min(fv, 1 - fv);
    if (edge < 0.04) l *= 0.35;                                   /* the gap between boards */
    const joint = Math.abs(u - p.cut);
    if (joint < 0.0016 && k > 0) l *= 0.4;
    return [clamp255(l * 1.18), clamp255(l * 0.86), clamp255(l * 0.62)];
  });
  return toTex(c, { repeat: [2.5, 2.5] });
}

/* polished mahogany: long grain with soft figure */
export function mahogany(seed = 2) {
  const [c] = paint(512, 512, (u, v) => {
    const warp = fbm(u * 2, v * 8, 4, seed) * 3;
    const ring = Math.sin((v * 22 + warp) * Math.PI) * 0.5 + 0.5;
    const fleck = vnoise(u * 90, v * 400, seed + 5);
    const l = 34 + ring * 20 + fleck * 8;
    return [clamp255(l * 1.55), clamp255(l * 0.78), clamp255(l * 0.55)];
  });
  return toTex(c);
}

/* desk-top leather with a gilt tooling line round the edge */
export function leather() {
  const W = 1024, H = 512;
  const [c, g] = paint(W, H, (u, v) => {
    const n = vnoise(u * 300, v * 150, 4) * 0.5 + fbm(u * 8, v * 4, 4, 6) * 0.5;
    const l = 26 + n * 18;
    return [clamp255(l * 0.9), clamp255(l * 1.15), clamp255(l * 0.9)];
  });
  g.strokeStyle = 'rgba(196,160,92,.85)';
  g.lineWidth = 5; g.strokeRect(22, 22, W - 44, H - 44);
  g.lineWidth = 2; g.strokeRect(34, 34, W - 68, H - 68);
  return toTex(c);
}

/* a worn Persian rug: borders, a lozenge field, a medallion */
export function rug() {
  const W = 1024, H = 704;
  const [c, g] = canvas(W, H);
  g.fillStyle = '#5a1f1c'; g.fillRect(0, 0, W, H);
  const band = (inset, w, col) => { g.strokeStyle = col; g.lineWidth = w; g.strokeRect(inset, inset, W - inset * 2, H - inset * 2); };
  band(18, 22, '#1c2236'); band(46, 10, '#c9b78f'); band(70, 30, '#2a3150'); band(100, 6, '#c9b78f');
  g.save(); g.beginPath(); g.rect(110, 110, W - 220, H - 220); g.clip();
  for (let y = 110; y < H - 110; y += 60) {
    for (let x = 110; x < W - 110; x += 60) {
      const off = ((y - 110) / 60) % 2 ? 30 : 0;
      g.fillStyle = (x + y) % 120 ? '#7a2b25' : '#3a2a2e';
      g.beginPath(); g.moveTo(x + off, y - 18); g.lineTo(x + off + 18, y); g.lineTo(x + off, y + 18); g.lineTo(x + off - 18, y); g.closePath(); g.fill();
    }
  }
  g.restore();
  const cx = W / 2, cy = H / 2;
  [[190, '#1c2236'], [150, '#c9b78f'], [120, '#6b231f'], [80, '#1c2236'], [44, '#c9b78f'], [18, '#6b231f']].forEach(([r, col]) => {
    g.fillStyle = col; g.beginPath(); g.moveTo(cx, cy - r * 0.8); g.lineTo(cx + r, cy); g.lineTo(cx, cy + r * 0.8); g.lineTo(cx - r, cy); g.closePath(); g.fill();
  });
  /* wear: pile shading and bald patches */
  const img = g.getImageData(0, 0, W, H), d = img.data;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = (y * W + x) * 4;
    const k = 0.78 + fbm(x / 90, y / 90, 4, 12) * 0.3 + (vnoise(x * 0.9, y * 0.9, 3) - 0.5) * 0.16;
    d[i] = clamp255(d[i] * k); d[i + 1] = clamp255(d[i + 1] * k); d[i + 2] = clamp255(d[i + 2] * k);
  }
  g.putImageData(img, 0, 0);
  return toTex(c);
}

/* the painting: a night sea, a lighthouse on the rocks, laid on with a brush */
export function seascape() {
  const W = 1024, H = 768, hz = 0.58;
  const [c, g] = paint(W, H, (u, v) => {
    let l;
    if (v < hz) {
      const cloud = fbm(u * 3 + fbm(u * 2, v * 3, 3, 4) * 1.4, v * 6, 6, 21);
      const glow = Math.exp(-((u - 0.74) ** 2 * 18 + (v - 0.3) ** 2 * 26));
      l = 40 + v * 70 + (cloud - 0.45) * 120 + glow * 70;
    } else {
      const w = fbm(u * 26, (v - hz) * 90, 4, 8);
      const shine = Math.exp(-((u - 0.74) ** 2) * 30) * (1 - (v - hz) * 1.6);
      l = 30 + w * 50 + shine * Math.max(0, w - 0.38) * 260;
    }
    const stroke = vnoise(u * 160 + v * 40, v * 30, 2) * 18 - 9;   /* brush direction */
    l += stroke;
    return [clamp255(l * 1.08), clamp255(l * 1.0), clamp255(l * 0.82)];
  });
  /* rocks and the lighthouse, a dark silhouette against the moonlit cloud */
  g.fillStyle = '#16140f';
  g.beginPath(); g.moveTo(560, 768); g.lineTo(600, 470); g.lineTo(650, 440); g.lineTo(705, 452); g.lineTo(790, 420); g.lineTo(860, 446); g.lineTo(930, 500); g.lineTo(1024, 520); g.lineTo(1024, 768); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(752, 432); g.lineTo(766, 250); g.lineTo(796, 250); g.lineTo(810, 432); g.closePath(); g.fill();
  g.fillRect(758, 226, 46, 26);
  g.beginPath(); g.moveTo(754, 228); g.lineTo(781, 206); g.lineTo(808, 228); g.closePath(); g.fill();
  const beam = g.createLinearGradient(781, 238, 340, 150);
  beam.addColorStop(0, 'rgba(245,232,190,.85)'); beam.addColorStop(1, 'rgba(245,232,190,0)');
  g.fillStyle = beam; g.beginPath(); g.moveTo(781, 232); g.lineTo(300, 120); g.lineTo(320, 196); g.closePath(); g.fill();
  g.fillStyle = '#f6eccd'; g.fillRect(768, 232, 26, 14);
  /* varnish: a warm, uneven film over everything */
  g.fillStyle = 'rgba(120,90,30,.12)'; g.fillRect(0, 0, W, H);
  return toTex(c);
}

/* gilt lettering for a book lying flat: the spine reads left to right.
   Transparent, laid over the cloth. Fonts must already be loaded. */
export function spine({ title, author, gilt = '#d2b26e' }) {
  const W = 1024, H = 180;
  const [c, g] = canvas(W, H);
  g.fillStyle = gilt;
  g.fillRect(40, 30, 10, H - 60); g.fillRect(58, 30, 4, H - 60);
  g.fillRect(W - 50, 30, 10, H - 60); g.fillRect(W - 62, 30, 4, H - 60);
  g.font = '400 112px "League Gothic"'; g.textBaseline = 'middle';
  g.fillText(title, 96, H / 2 + 4);
  g.font = '400 64px "League Gothic"'; g.textAlign = 'right';
  g.fillText(author, W - 92, H / 2 + 6);
  return toTex(c);
}

/* a typed sheet: the loot manifest, half out of the folder */
export function typedPage() {
  const W = 700, H = 900;
  const [c, g] = paint(W, H, (u, v) => {
    const n = fbm(u * 6, v * 6, 3, 51) * 10 + vnoise(u * 400, v * 400, 7) * 6;
    const l = 204 + n;
    return [clamp255(l + 4), clamp255(l), clamp255(l - 14)];
  });
  g.fillStyle = 'rgba(26,25,22,.88)';
  g.font = '400 34px "Special Elite"'; g.textAlign = 'center';
  g.fillText('LOOT MANIFEST', W / 2, 96);
  g.font = '400 19px "Special Elite"';
  g.fillText('JOB NO. 1138 · WHAT THE CAMERA PRICED', W / 2, 136);
  g.fillRect(60, 160, W - 120, 2);
  g.textAlign = 'left';
  const rows = [['"VINTAGE ROLEX"', '$4,200.00'], ['"OIL ON CANVAS"', '$2,400.00'], ['"LEICA M3"', '$1,850.00'], ['"FIRST-ED. HEMINGWAY"', '$950.00'], ['"CRYSTAL DECANTER"', '$340.00'], ['"BRASS DESK LAMP"', '$180.00']];
  g.font = '400 22px "Special Elite"';
  rows.forEach(([a, b], i) => {
    const y = 214 + i * 46;
    g.fillText(a, 64, y);
    g.textAlign = 'right'; g.fillText(b, W - 64, y); g.textAlign = 'left';
    g.fillStyle = 'rgba(26,25,22,.35)';
    for (let x = 64 + g.measureText(a).width + 12; x < W - 180; x += 10) g.fillRect(x, y - 2, 3, 3);
    g.fillStyle = 'rgba(26,25,22,.88)';
  });
  g.fillRect(60, 500, W - 120, 2); g.fillRect(60, 506, W - 120, 2);
  g.font = '400 26px "Special Elite"'; g.fillText('TOTAL TAKE', 64, 548);
  g.textAlign = 'right'; g.fillText('$9,920.00', W - 64, 548);
  g.save(); g.translate(W / 2, 700); g.rotate(-0.22);
  g.strokeStyle = 'rgba(165,56,47,.8)'; g.lineWidth = 8; g.strokeRect(-170, -54, 340, 108);
  g.fillStyle = 'rgba(165,56,47,.8)'; g.font = '400 92px "League Gothic"'; g.textAlign = 'center'; g.fillText('EVIDENCE', 0, 34);
  g.restore();
  return toTex(c);
}

/* the fore-edge of a stack of pages */
export function pageEdge() {
  const [c] = paint(256, 64, (u, v) => {
    const line = vnoise(1, v * 260, 5) * 22 + vnoise(u * 8, v * 40, 2) * 10;
    const l = 196 - line;
    return [clamp255(l + 8), clamp255(l), clamp255(l - 18)];
  });
  return toTex(c);
}

/* black watch dial, baton markers, hands at ten past ten */
export function watchDial() {
  const S = 512, [c, g] = canvas(S, S);
  const r = S / 2;
  const grad = g.createRadialGradient(r * 0.8, r * 0.7, 10, r, r, r);
  grad.addColorStop(0, '#2a2a2a'); grad.addColorStop(1, '#070707');
  g.fillStyle = grad; g.fillRect(0, 0, S, S);
  g.translate(r, r);
  for (let i = 0; i < 60; i++) {
    g.save(); g.rotate(i * Math.PI / 30);
    g.fillStyle = '#d8d4c7';
    if (i % 5 === 0) {
      if (i === 0) { g.beginPath(); g.moveTo(-18, -r * 0.9); g.lineTo(18, -r * 0.9); g.lineTo(0, -r * 0.7); g.closePath(); g.fill(); }
      else g.fillRect(-9, -r * 0.9, 18, 54);
    } else g.fillRect(-1.5, -r * 0.92, 3, 12);
    g.restore();
  }
  const hand = (a, len, w) => { g.save(); g.rotate(a); g.fillStyle = '#efe9db'; g.fillRect(-w / 2, -len, w, len + 20); g.restore(); };
  hand(-Math.PI / 3 + Math.PI / 30 * 1, r * 0.5, 16);     /* hour, near ten */
  hand(Math.PI / 3, r * 0.78, 11);                        /* minute, on two */
  g.save(); g.rotate(Math.PI * 0.82); g.fillStyle = '#c8c4b8'; g.fillRect(-2, -r * 0.82, 4, r * 1.02); g.restore();
  g.fillStyle = '#999'; g.beginPath(); g.arc(0, 0, 10, 0, Math.PI * 2); g.fill();
  return toTex(c);
}

/* a manila case folder with a typed label */
export function folder() {
  const W = 768, H = 560;
  const [c, g] = paint(W, H, (u, v) => {
    const n = fbm(u * 10, v * 10, 4, 33) * 0.6 + vnoise(u * 300, v * 300, 2) * 0.4;
    const l = 168 + n * 30;
    return [clamp255(l + 22), clamp255(l + 2), clamp255(l - 44)];
  });
  g.fillStyle = '#efe9db'; g.fillRect(70, 60, 360, 70);
  g.strokeStyle = 'rgba(15,14,12,.35)'; g.lineWidth = 2; g.strokeRect(70, 60, 360, 70);
  g.fillStyle = '#1a1916'; g.font = '400 38px "Special Elite"'; g.fillText('CASE NO. 1138', 92, 108);
  g.save(); g.translate(560, 380); g.rotate(-0.18);
  g.strokeStyle = 'rgba(165,56,47,.85)'; g.lineWidth = 7; g.strokeRect(-150, -46, 300, 92);
  g.fillStyle = 'rgba(165,56,47,.85)'; g.font = '400 70px "League Gothic"'; g.textAlign = 'center'; g.fillText('CONFIDENTIAL', 0, 24);
  g.restore();
  return toTex(c);
}

/* the street outside the blinds: out-of-focus lamps and a sign */
export function nightStreet() {
  const W = 1024, H = 512, R = rng(19);
  const [c, g] = canvas(W, H);
  const sky = g.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, '#05070c'); sky.addColorStop(1, '#141826');
  g.fillStyle = sky; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 70; i++) {
    const x = R() * W, y = H * (0.25 + R() * 0.7), rad = 6 + R() * 26, a = 0.12 + R() * 0.4;
    const b = g.createRadialGradient(x, y, 0, x, y, rad);
    b.addColorStop(0, `rgba(255,236,190,${a})`); b.addColorStop(0.7, `rgba(255,236,190,${a * 0.6})`); b.addColorStop(1, 'rgba(255,236,190,0)');
    g.fillStyle = b; g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
  }
  g.fillStyle = 'rgba(255,240,215,.75)'; g.font = '400 120px "League Gothic"'; g.fillText('HOTEL', 610, 220);
  return toTex(c);
}
