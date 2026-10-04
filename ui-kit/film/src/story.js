/* The picture, beat by beat. Every moment is a pure function of t (seconds),
   so render.mjs can draw any frame in any order and get the same image.

   Reel 1: the leader, the walk (six exhibits found, typed, marked, counted),
   then the cap's footage lands in the dashboard. Reel 2: the cue mark, the
   freeze, the lineup, the total, the stamp. THE END. */

export const FPS = 24;

/* ---------- easing, the kit's curves (noir.css motion tokens) ---------- */
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = t => ((ax * t + bx) * t + cx) * t;
  const sy = t => ((ay * t + by) * t + cy) * t;
  const dx = t => (3 * ax * t + 2 * bx) * t + cx;
  return x => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) { const e = sx(t) - x, d = dx(t); if (Math.abs(e) < 1e-6 || !d) break; t -= e / d; }
    return sy(Math.min(1, Math.max(0, t)));
  };
}
export const ez = {
  settle: bezier(0.42, 0.02, 0.18, 1),
  odo: bezier(0.33, 0.02, 0.16, 1),
  film: bezier(0.45, 0.03, 0.2, 1),
  stamp: bezier(0.33, 0.02, 0.2, 1),
  outCubic: x => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3),
  inOutCubic: x => { x = Math.min(1, Math.max(0, x)); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
  smooth: x => { x = Math.min(1, Math.max(0, x)); return x * x * (3 - 2 * x); },
};
export const span = (t, a, d) => Math.min(1, Math.max(0, (t - a) / d));
const lerp = (a, b, k) => a + (b - a) * k;

/* ---------- the schedule ---------- */
const LEADER_FOOT = 8 / FPS;           /* half a foot per number: a trailer cut of the Academy leader */
export const T = {
  pictureStart: 0, countFrom: 0.5, countEnd: 0.5 + 6 * LEADER_FOOT,
  fadeUp: 2.7, fadeUpDur: 0.7,
  typeChar: 0.016, beatMark: 0.28, marker: 0.56, beatCount: 0.32, odo: 1.04, digitStagger: 0.072,
  toDash: 10.3, toDashDur: 1.05, stillEvery: 0.5,
  cue: 12.2, cueDur: 0.86, freeze: 12.45, judder: 0.38,
  curtain: 12.65, dissolve: 0.78, lineup: 13.45, fadeup: 0.7,
  suspectStagger: 0.42, drop: 0.7, count: 1.1, stamp: 0.82, shake: 0.52,
  end: 18.7, endFade: 0.68, endHold: 1.5,
};
T.suspects = T.lineup + T.fadeup * 0.2;
T.landed = T.suspects + 4 * T.suspectStagger + T.drop;
T.totalRoll = T.landed + 0.14;
T.stampAt = T.totalRoll + T.odo * 0.62;
T.duration = T.end + T.endFade + T.endHold;
export const FRAMES = Math.round(T.duration * FPS);

/* when each exhibit is found: the EXAMINING line types, then the result lands.
   The film cut holds each marker a little longer than the dashboard does. */
export const FINDS = Array.from({ length: 6 }, (_, i) => {
  const pend = 3.3 + i * 0.85, land = pend + 0.4;
  return { pend, land };
});
export function beats(find, name) {
  const typed = find.land + name.length * T.typeChar;
  const marker = typed + T.beatMark;
  const fly = marker + 0.24, landed = fly + 0.98;
  return { ...find, typed, marker, fly, landed, retire: landed + 0.45, count: landed + 0.22 };
}

/* ---------- the walk: a cap at head height, Hermite through keyframes ---------- */
const KEYS = [
  { t: 2.4, pos: [2.75, 1.66, 2.35], look: [-0.5, 1.15, -2.2] },
  { t: 4.32, pos: [1.45, 1.64, 0.75], look: [-1.0, 1.0, -2.0] },
  { t: 5.17, pos: [0.5, 1.56, -0.22], look: [-0.98, 0.88, -1.52] },
  { t: 6.02, pos: [0.0, 1.38, -0.72], look: [-0.3, 0.8, -1.62] },
  { t: 6.87, pos: [0.4, 1.38, -0.88], look: [0.07, 0.89, -1.97] },
  { t: 7.72, pos: [0.92, 1.4, -0.95], look: [0.42, 0.95, -2.04] },
  { t: 8.62, pos: [1.38, 1.6, -0.62], look: [1.55, 1.74, -2.96] },
  { t: 10.3, pos: [2.05, 1.66, 0.4], look: [0.15, 1.18, -2.3] },
  { t: 12.8, pos: [2.2, 1.66, 0.62], look: [0.1, 1.16, -2.3] },
];

function hermite(keys, field, t) {
  if (t <= keys[0].t) return keys[0][field];
  const last = keys[keys.length - 1];
  if (t >= last.t) return last[field];
  let i = 0;
  while (keys[i + 1].t < t) i++;
  const k0 = keys[i], k1 = keys[i + 1], h = k1.t - k0.t, s = (t - k0.t) / h;
  const tan = j => {
    if (j === 0 || j === keys.length - 1) return [0, 0, 0];
    const a = keys[j - 1], b = keys[j + 1];
    return a[field].map((v, c) => (b[field][c] - v) / (b.t - a.t));
  };
  const m0 = tan(i), m1 = tan(i + 1);
  const h00 = 2 * s ** 3 - 3 * s ** 2 + 1, h10 = s ** 3 - 2 * s ** 2 + s, h01 = -2 * s ** 3 + 3 * s ** 2, h11 = s ** 3 - s ** 2;
  return k0[field].map((v, c) => h00 * v + h10 * h * m0[c] + h01 * k1[field][c] + h11 * h * m1[c]);
}

/* distance walked, for the head bob: integrate the path once */
const STRIDE = (() => {
  const dt = 1 / 240, table = [0];
  let prev = hermite(KEYS, 'pos', 0), acc = 0;
  for (let t = dt; t <= T.duration + dt; t += dt) {
    const p = hermite(KEYS, 'pos', t);
    acc += Math.hypot(p[0] - prev[0], p[2] - prev[2]);
    table.push(acc); prev = p;
  }
  return t => table[Math.min(table.length - 1, Math.max(0, Math.round(t * 240)))];
})();

const wobble = (t, f, seed) => Math.sin(t * f + seed) * 0.6 + Math.sin(t * f * 2.37 + seed * 3.1) * 0.3 + Math.sin(t * f * 5.13 + seed * 7.7) * 0.1;

export function cameraAt(t) {
  const pos = hermite(KEYS, 'pos', t), look = hermite(KEYS, 'look', t);
  const d = STRIDE(t), phase = d / 0.72 * Math.PI * 2;
  const p0 = hermite(KEYS, 'pos', t - 0.05), speed = Math.hypot(pos[0] - p0[0], pos[2] - p0[2]) / 0.05;
  const walk = Math.min(1, speed / 0.9);
  pos[1] += Math.abs(Math.sin(phase / 2)) * 0.018 * walk - 0.009 * walk;
  pos[0] += Math.sin(phase / 2) * 0.006 * walk;
  look[0] += wobble(t, 0.9, 1) * 0.006; look[1] += wobble(t, 1.1, 2) * 0.005;
  const roll = Math.sin(phase / 2) * 0.004 * walk + wobble(t, 0.7, 3) * 0.002;
  return { pos, look, roll };
}

/* the scene's own clock: during the dashboard the feed is CCTV stills, not video */
export function feedTime(t) {
  if (t < T.toDash + T.toDashDur * 0.5) return t;
  const base = T.toDash + T.toDashDur * 0.5;
  return Math.min(T.freeze, base + Math.floor((t - base) / T.stillEvery) * T.stillEvery);
}

/* the odometer: wheels left to right, rolls start right to left, each roll
   picks up from wherever the wheel is, the way a CSS transition would */
export function odometer(events, t) {
  const live = events.filter(e => e.t <= t);
  const now = live.length ? live[live.length - 1].value : 0;
  const text = Math.round(now).toLocaleString('en-US');
  const D = text.replace(/\D/g, '').length;
  const cols = [];
  for (let i = 0; i < D; i++) {
    let pos = 0;
    const starts = events.map(e => {
      const digits = Math.round(e.value).toLocaleString('en-US').replace(/\D/g, '');
      return { s: e.t + (digits.length - 1 - i) * T.digitStagger, to: i < digits.length ? Number(digits[i]) : 0 };
    });
    for (let k = 0; k < starts.length; k++) {
      const { s, to } = starts[k];
      if (s > t) break;
      const until = Math.min(t, k + 1 < starts.length ? Math.max(s, starts[k + 1].s) : Infinity);
      pos = lerp(pos, to, ez.odo(span(until, s, T.odo)));
    }
    cols.push(pos);
  }
  return { text, cols, k: Math.min(1, 7 / (text.length + 1)) };
}

export { lerp };
