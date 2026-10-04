/* The set: a private office after hours. Streetlight through venetian blinds,
   a banker's lamp on the desk, six things worth stealing. Units are metres.
   build() returns the scene, the camera and the exhibits the overlay marks. */
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import * as TX from './textures.js';

const V3 = (x, y, z) => new THREE.Vector3(x, y, z);

/* ---------- materials ---------- */
function materials(env) {
  const std = (o) => new THREE.MeshStandardMaterial(o);
  const phys = (o) => new THREE.MeshPhysicalMaterial(o);
  const plaster = TX.plaster();
  return {
    plaster: std({ map: plaster, roughness: 0.92 }),
    ceiling: std({ color: 0x3a3833, roughness: 1 }),
    floor: std({ map: TX.planks(), roughness: 0.42, metalness: 0 }),
    panel: std({ map: TX.mahogany(9), color: 0x8a6a5a, roughness: 0.5 }),
    trim: std({ map: TX.mahogany(4), color: 0x7a5a4a, roughness: 0.45 }),
    desk: phys({ map: TX.mahogany(2), roughness: 0.32, clearcoat: 0.8, clearcoatRoughness: 0.18 }),
    leather: std({ map: TX.leather(), roughness: 0.62 }),
    rug: std({ map: TX.rug(), roughness: 1 }),
    brass: std({ color: 0xc9a253, metalness: 1, roughness: 0.28 }),
    gilt: std({ color: 0xc19a55, metalness: 1, roughness: 0.4, envMap: env, envMapIntensity: 0.22 }),
    giltDark: std({ color: 0x8a6a35, metalness: 1, roughness: 0.5, envMap: env, envMapIntensity: 0.16 }),
    silver: std({ color: 0xbfc2c4, metalness: 1, roughness: 0.3, envMap: env, envMapIntensity: 0.22 }),
    chrome: std({ color: 0xe6e6e6, metalness: 1, roughness: 0.14, envMap: env, envMapIntensity: 0.9 }),
    steel: std({ color: 0xcfd2d4, metalness: 1, roughness: 0.22, envMap: env, envMapIntensity: 1.1 }),
    blackPaint: phys({ color: 0x0b0b0b, roughness: 0.32, clearcoat: 0.6 }),
    leatherette: std({ color: 0x151515, roughness: 0.82 }),
    bakelite: phys({ color: 0x0c0b0a, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08 }),
    shadeGlass: phys({ color: 0x0f4a2a, roughness: 0.1, clearcoat: 1, clearcoatRoughness: 0.05, side: THREE.FrontSide }),
    shadeOpal: std({ color: 0xf2ecd8, roughness: 0.6, emissive: 0xffe2b0, emissiveIntensity: 0.35, side: THREE.BackSide }),
    bulb: std({ color: 0xfff3d6, emissive: 0xfff0d0, emissiveIntensity: 6 }),
    glass: phys({ color: 0xffffff, transmission: 1, thickness: 0.012, ior: 1.52, roughness: 0.03, metalness: 0, flatShading: true, envMap: env, envMapIntensity: 1.6 }),
    whisky: phys({ color: 0xb8762e, transmission: 0.82, thickness: 0.09, ior: 1.36, roughness: 0.08, attenuationColor: new THREE.Color(0x7a3a0c), attenuationDistance: 0.06 }),
    paper: std({ color: 0xefe9db, roughness: 0.9 }),
    felt: phys({ color: 0x1d1c1a, roughness: 0.95, sheen: 0.6, sheenRoughness: 0.6, sheenColor: new THREE.Color(0x5a5650) }),
    band: std({ color: 0x0a0a0a, roughness: 0.6 }),
    cabinet: std({ color: 0x6e716c, metalness: 0.35, roughness: 0.48 }),
    chair: phys({ color: 0x2c1912, roughness: 0.48, clearcoat: 0.25 }),
    slat: std({ color: 0xd8d4c7, roughness: 0.55 }),
    lens: phys({ color: 0x050608, roughness: 0, metalness: 0.2, clearcoat: 1, iridescence: 0.8, iridescenceIOR: 1.6 }),
    std, phys,
  };
}

/* ---------- small geometry helpers ---------- */
function mesh(geo, mat, { pos = [0, 0, 0], rot = [0, 0, 0], cast = true, receive = true } = {}) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(...pos); m.rotation.set(...rot);
  m.castShadow = cast; m.receiveShadow = receive;
  return m;
}
const rbox = (w, h, d, r = 0.01, seg = 3) => new RoundedBoxGeometry(w, h, d, seg, Math.min(r, w / 2, h / 2, d / 2));
const lathe = (pts, seg = 64) => new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(r, y)), seg);

/* ridges round a cylinder: a fluted bezel, a knurled focus ring */
function fluted(geo, count, depth) {
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i), r = Math.hypot(x, z);
    if (r < 1e-5) continue;
    const a = Math.atan2(x, z), k = 1 + depth * Math.sign(Math.sin(a * count));
    p.setX(i, x * k); p.setZ(i, z * k);
  }
  geo.computeVertexNormals();
  return geo;
}

/* ---------- the room ---------- */
const ROOM = { x0: -4, x1: 4, z0: -3, z1: 3.5, h: 3.2 };
const WIN = { z0: -2.3, z1: -0.6, y0: 0.95, y1: 2.6 };

function room(M) {
  const g = new THREE.Group();
  const W = ROOM.x1 - ROOM.x0, D = ROOM.z1 - ROOM.z0;
  const floor = mesh(new THREE.PlaneGeometry(W, D), M.floor, { rot: [-Math.PI / 2, 0, 0], pos: [0, 0, (ROOM.z0 + ROOM.z1) / 2], cast: false });
  g.add(floor);
  g.add(mesh(new THREE.PlaneGeometry(W, D), M.ceiling, { rot: [Math.PI / 2, 0, 0], pos: [0, ROOM.h, (ROOM.z0 + ROOM.z1) / 2], cast: false }));
  /* back wall, right wall, front wall: plaster */
  g.add(mesh(new THREE.BoxGeometry(W, ROOM.h, 0.15), M.plaster, { pos: [0, ROOM.h / 2, ROOM.z0 - 0.075] }));
  g.add(mesh(new THREE.BoxGeometry(0.15, ROOM.h, D), M.plaster, { pos: [ROOM.x1 + 0.075, ROOM.h / 2, (ROOM.z0 + ROOM.z1) / 2] }));
  g.add(mesh(new THREE.BoxGeometry(W, ROOM.h, 0.15), M.plaster, { pos: [0, ROOM.h / 2, ROOM.z1 + 0.075] }));
  /* left wall in four pieces round the window opening */
  const lx = ROOM.x0 - 0.075, t = 0.15;
  g.add(mesh(new THREE.BoxGeometry(t, WIN.y0, D), M.plaster, { pos: [lx, WIN.y0 / 2, (ROOM.z0 + ROOM.z1) / 2] }));
  g.add(mesh(new THREE.BoxGeometry(t, ROOM.h - WIN.y1, D), M.plaster, { pos: [lx, (ROOM.h + WIN.y1) / 2, (ROOM.z0 + ROOM.z1) / 2] }));
  g.add(mesh(new THREE.BoxGeometry(t, WIN.y1 - WIN.y0, WIN.z0 - ROOM.z0), M.plaster, { pos: [lx, (WIN.y0 + WIN.y1) / 2, (ROOM.z0 + WIN.z0) / 2] }));
  g.add(mesh(new THREE.BoxGeometry(t, WIN.y1 - WIN.y0, ROOM.z1 - WIN.z1), M.plaster, { pos: [lx, (WIN.y0 + WIN.y1) / 2, (WIN.z1 + ROOM.z1) / 2] }));

  /* wainscot: dark panelling to the chair rail, on the back and left walls */
  const rail = 0.95;
  const wain = (len, place) => {
    const w = new THREE.Group();
    w.add(mesh(new THREE.BoxGeometry(len, rail, 0.02), M.panel, { pos: [0, rail / 2, 0.01] }));
    w.add(mesh(new THREE.BoxGeometry(len, 0.05, 0.05), M.trim, { pos: [0, rail, 0.025] }));
    w.add(mesh(new THREE.BoxGeometry(len, 0.15, 0.035), M.trim, { pos: [0, 0.075, 0.018] }));
    const n = Math.floor(len / 0.82);
    for (let i = 0; i < n; i++) {
      const x = -len / 2 + (len - n * 0.82) / 2 + 0.41 + i * 0.82;
      w.add(mesh(rbox(0.66, 0.5, 0.024, 0.008), M.trim, { pos: [x, 0.5, 0.028] }));
    }
    place(w); g.add(w);
  };
  wain(W, w => w.position.set(0, 0, ROOM.z0));
  wain(D, w => { w.rotation.y = Math.PI / 2; w.position.set(ROOM.x0, 0, (ROOM.z0 + ROOM.z1) / 2); });
  return g;
}

/* window, sash, blinds and the street beyond */
function windowSet(M) {
  const g = new THREE.Group();
  const cz = (WIN.z0 + WIN.z1) / 2, cy = (WIN.y0 + WIN.y1) / 2;
  const wz = WIN.z1 - WIN.z0, wy = WIN.y1 - WIN.y0;
  const x = ROOM.x0 + 0.01;
  g.add(mesh(new THREE.BoxGeometry(0.06, 0.07, wz + 0.2), M.trim, { pos: [x + 0.02, WIN.y1 + 0.035, cz] }));
  g.add(mesh(new THREE.BoxGeometry(0.16, 0.04, wz + 0.24), M.trim, { pos: [x + 0.05, WIN.y0 - 0.005, cz] }));
  g.add(mesh(new THREE.BoxGeometry(0.06, wy, 0.07), M.trim, { pos: [x + 0.02, cy, WIN.z0 - 0.035] }));
  g.add(mesh(new THREE.BoxGeometry(0.06, wy, 0.07), M.trim, { pos: [x + 0.02, cy, WIN.z1 + 0.035] }));
  /* sash bars, set back in the wall */
  g.add(mesh(new THREE.BoxGeometry(0.04, 0.04, wz), M.trim, { pos: [ROOM.x0 - 0.1, cy, cz] }));
  g.add(mesh(new THREE.BoxGeometry(0.04, wy, 0.04), M.trim, { pos: [ROOM.x0 - 0.1, cy, cz] }));
  const pane = new THREE.MeshPhysicalMaterial({ color: 0x9aa3b0, roughness: 0.04, transparent: true, opacity: 0.16, metalness: 0 });
  g.add(mesh(new THREE.PlaneGeometry(wz, wy), pane, { rot: [0, Math.PI / 2, 0], pos: [ROOM.x0 - 0.11, cy, cz], cast: false }));

  /* venetian blinds: real slats, so the shadows are real */
  const slats = new THREE.Group();
  const spacing = 0.056, tilt = 0.62;
  for (let y = WIN.y1 - 0.08; y > WIN.y0 + 0.03; y -= spacing) {
    slats.add(mesh(new THREE.BoxGeometry(0.052, 0.0026, wz - 0.04), M.slat, { pos: [x + 0.075, y, cz], rot: [0, 0, tilt] }));
  }
  slats.add(mesh(new THREE.BoxGeometry(0.06, 0.05, wz), M.slat, { pos: [x + 0.075, WIN.y1 - 0.03, cz] }));
  slats.add(mesh(new THREE.BoxGeometry(0.06, 0.012, wz - 0.04), M.slat, { pos: [x + 0.075, WIN.y0 + 0.012, cz] }));
  for (const z of [WIN.z0 + 0.3, WIN.z1 - 0.3]) {
    slats.add(mesh(new THREE.BoxGeometry(0.003, wy - 0.06, 0.003), M.slat, { pos: [x + 0.05, cy, z] }));
    slats.add(mesh(new THREE.BoxGeometry(0.003, wy - 0.06, 0.003), M.slat, { pos: [x + 0.1, cy, z] }));
  }
  slats.add(mesh(new THREE.CylinderGeometry(0.0018, 0.0018, 1.1, 6), M.slat, { pos: [x + 0.11, WIN.y1 - 0.6, WIN.z1 - 0.08] }));
  g.add(slats);

  /* the street: unlit, never casts */
  const street = new THREE.Mesh(new THREE.PlaneGeometry(9, 4.5), new THREE.MeshBasicMaterial({ map: TX.nightStreet(), toneMapped: false }));
  street.position.set(-8, 1.8, -1.2); street.rotation.y = Math.PI / 2;
  street.material.color.setScalar(0.55);
  g.add(street);
  return { group: g, slatSpacing: spacing };
}

/* ---------- furniture ---------- */
function desk(M) {
  const g = new THREE.Group();
  const W = 2.1, D = 0.96, H = 0.78;
  g.add(mesh(rbox(W, 0.05, D, 0.012), M.desk, { pos: [0, H - 0.025, 0] }));
  g.add(mesh(new THREE.BoxGeometry(W - 0.22, 0.004, D - 0.2), M.leather, { pos: [0, H + 0.001, 0] }));
  for (const sx of [-1, 1]) {
    const px = sx * (W / 2 - 0.29);
    g.add(mesh(rbox(0.52, H - 0.06, D - 0.06, 0.01), M.desk, { pos: [px, (H - 0.05) / 2, 0] }));
    for (let i = 0; i < 3; i++) {
      const y = 0.15 + i * 0.22;
      g.add(mesh(rbox(0.46, 0.19, 0.02, 0.006), M.desk, { pos: [px, y, D / 2 - 0.02] }));
      g.add(mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.09, 12), M.brass, { pos: [px, y, D / 2 + 0.006], rot: [0, 0, Math.PI / 2] }));
    }
  }
  g.add(mesh(new THREE.BoxGeometry(W - 1.1, 0.12, 0.03), M.desk, { pos: [0, H - 0.11, D / 2 - 0.04] }));
  g.add(mesh(new THREE.BoxGeometry(W - 1.12, H - 0.2, 0.02), M.desk, { pos: [0, (H - 0.2) / 2 + 0.04, -D / 2 + 0.06] }));
  return g;
}

function chair(M) {
  const g = new THREE.Group();
  g.add(mesh(rbox(0.6, 0.12, 0.56, 0.05), M.chair, { pos: [0, 0.5, 0] }));
  /* a curved back, so the blinds' stripes bend round it */
  const back = new THREE.Group(); back.position.set(0, 0.56, 0.12); back.rotation.x = -0.1;
  const arc = 1.5, r = 0.46, h = 0.56;
  back.add(mesh(new THREE.CylinderGeometry(r, r, h, 40, 1, true, Math.PI - arc / 2, arc), M.chair, { pos: [0, h / 2, 0] }));
  back.add(mesh(new THREE.CylinderGeometry(r + 0.05, r + 0.05, h, 40, 1, true, Math.PI - arc / 2, arc), M.chair, { pos: [0, h / 2, 0] }));
  back.add(mesh(new THREE.TorusGeometry(r + 0.025, 0.035, 12, 40, arc), M.chair, { pos: [0, h, 0], rot: [Math.PI / 2, 0, Math.PI / 2 + arc / 2] }));
  for (let row = 0; row < 3; row++) for (let k = 0; k < 5; k++) {
    const a = Math.PI - arc / 2 + arc * (k + 0.5) / 5 + (row % 2) * 0.1 - 0.05;
    back.add(mesh(new THREE.SphereGeometry(0.009, 8, 6), M.chair, { pos: [Math.sin(a) * (r - 0.004), 0.14 + row * 0.15, Math.cos(a) * (r - 0.004)] }));
  }
  g.add(back);
  for (const sx of [-1, 1]) g.add(mesh(rbox(0.07, 0.07, 0.46, 0.03), M.chair, { pos: [sx * 0.32, 0.7, -0.02] }));
  g.add(mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.36, 16), M.chrome, { pos: [0, 0.27, 0] }));
  for (let i = 0; i < 5; i++) {
    const a = i * Math.PI * 2 / 5;
    g.add(mesh(new THREE.BoxGeometry(0.035, 0.03, 0.32), M.chrome, { pos: [Math.sin(a) * 0.16, 0.07, Math.cos(a) * 0.16], rot: [0, a, 0] }));
    g.add(mesh(new THREE.SphereGeometry(0.028, 12, 8), M.blackPaint, { pos: [Math.sin(a) * 0.31, 0.03, Math.cos(a) * 0.31] }));
  }
  return g;
}

function cabinet(M) {
  const g = new THREE.Group();
  g.add(mesh(new THREE.BoxGeometry(0.46, 1.32, 0.62), M.cabinet, { pos: [0, 0.66, 0] }));
  const label = new THREE.MeshStandardMaterial({ color: 0xefe9db, roughness: 0.9 });
  for (let i = 0; i < 4; i++) {
    const y = 0.2 + i * 0.315;
    g.add(mesh(rbox(0.42, 0.29, 0.02, 0.006), M.cabinet, { pos: [0, y, 0.315] }));
    g.add(mesh(rbox(0.12, 0.022, 0.03, 0.008), M.chrome, { pos: [0, y - 0.03, 0.335] }));
    g.add(mesh(new THREE.BoxGeometry(0.09, 0.04, 0.004), label, { pos: [0, y + 0.07, 0.327] }));
    g.add(mesh(new THREE.BoxGeometry(0.1, 0.05, 0.003), M.chrome, { pos: [0, y + 0.07, 0.3255] }));
  }
  return g;
}

/* ---------- the exhibits and the props round them ---------- */
function bankersLamp(M) {
  const g = new THREE.Group();
  g.add(mesh(new THREE.CylinderGeometry(0.085, 0.096, 0.022, 48), M.brass, { pos: [0, 0.011, 0] }));
  g.add(mesh(new THREE.CylinderGeometry(0.058, 0.074, 0.022, 48), M.brass, { pos: [0, 0.033, 0] }));
  g.add(mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.29, 24), M.brass, { pos: [0, 0.19, 0] }));
  g.add(mesh(new THREE.SphereGeometry(0.017, 20, 14), M.brass, { pos: [0, 0.33, 0] }));
  g.add(mesh(new THREE.BoxGeometry(0.012, 0.03, 0.05), M.brass, { pos: [0, 0.35, 0.02] }));
  const shade = new THREE.Group();
  shade.position.set(0, 0.375, 0.035);
  const len = 0.34, r = 0.075;
  shade.add(mesh(new THREE.CylinderGeometry(r, r, len, 48, 1, true, 0, Math.PI), M.shadeGlass, { rot: [0, 0, Math.PI / 2] }));
  shade.add(mesh(new THREE.CylinderGeometry(r - 0.003, r - 0.003, len - 0.004, 48, 1, true, 0, Math.PI), M.shadeOpal, { rot: [0, 0, Math.PI / 2], cast: false }));
  for (const sx of [-1, 1]) {
    shade.add(mesh(new THREE.CircleGeometry(r, 32, 0, Math.PI), M.shadeGlass, { pos: [sx * len / 2, 0, 0], rot: [0, Math.PI / 2, 0] }));
    shade.add(mesh(new THREE.CylinderGeometry(0.0035, 0.0035, len, 8), M.brass, { pos: [0, 0, sx * r], rot: [0, 0, Math.PI / 2] }));
  }
  shade.add(mesh(new THREE.TorusGeometry(r, 0.004, 8, 32, Math.PI), M.brass, { pos: [len / 2, 0, 0], rot: [0, Math.PI / 2, 0] }));
  shade.add(mesh(new THREE.TorusGeometry(r, 0.004, 8, 32, Math.PI), M.brass, { pos: [-len / 2, 0, 0], rot: [0, Math.PI / 2, 0] }));
  const bulb = mesh(new THREE.SphereGeometry(0.022, 20, 14), M.bulb, { pos: [0, 0.006, 0], cast: false });
  shade.add(bulb);
  for (let i = 0; i < 9; i++) shade.add(mesh(new THREE.SphereGeometry(0.0032, 8, 6), M.brass, { pos: [0.06, -0.012 - i * 0.0075, 0.02], cast: false }));
  g.add(shade);
  return { group: g, bulb, shade };
}

function leica(M) {
  const g = new THREE.Group();
  g.add(mesh(rbox(0.138, 0.062, 0.034, 0.009), M.leatherette, { pos: [0, 0.031, 0] }));
  g.add(mesh(rbox(0.139, 0.017, 0.036, 0.005), M.chrome, { pos: [0, 0.07, 0] }));
  const dark = new THREE.MeshPhysicalMaterial({ color: 0x0a0b0d, roughness: 0.02, clearcoat: 1 });
  const frost = new THREE.MeshStandardMaterial({ color: 0xe8e4da, roughness: 0.4, emissive: 0x777777 });
  g.add(mesh(new THREE.BoxGeometry(0.02, 0.011, 0.002), dark, { pos: [-0.046, 0.07, 0.0181] }));
  g.add(mesh(new THREE.BoxGeometry(0.01, 0.011, 0.002), frost, { pos: [-0.012, 0.07, 0.0181] }));
  g.add(mesh(new THREE.BoxGeometry(0.022, 0.011, 0.002), dark, { pos: [0.04, 0.07, 0.0181] }));
  g.add(mesh(fluted(new THREE.CylinderGeometry(0.0095, 0.0095, 0.007, 48), 24, 0.04), M.chrome, { pos: [0.032, 0.0815, -0.002] }));
  g.add(mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.011, 24), M.chrome, { pos: [-0.052, 0.083, 0] }));
  g.add(mesh(rbox(0.032, 0.003, 0.008, 0.0015), M.chrome, { pos: [0.05, 0.08, 0.005], rot: [0, 0.4, 0] }));
  const L = new THREE.Group(); L.position.set(0.004, 0.034, 0.017); L.rotation.x = Math.PI / 2;
  L.add(mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.006, 48), M.chrome, { pos: [0, 0.003, 0] }));
  L.add(mesh(new THREE.CylinderGeometry(0.0195, 0.0195, 0.03, 48), M.blackPaint, { pos: [0, 0.021, 0] }));
  L.add(mesh(fluted(new THREE.CylinderGeometry(0.0205, 0.0205, 0.009, 96), 48, 0.035), M.chrome, { pos: [0, 0.014, 0] }));
  L.add(mesh(new THREE.CylinderGeometry(0.0185, 0.0185, 0.004, 48), M.chrome, { pos: [0, 0.037, 0] }));
  L.add(mesh(new THREE.CircleGeometry(0.0155, 48), M.lens, { pos: [0, 0.0392, 0], rot: [-Math.PI / 2, 0, 0], cast: false }));
  g.add(L);
  for (const sx of [-1, 1]) g.add(mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.006, 12), M.chrome, { pos: [sx * 0.071, 0.058, 0], rot: [0, 0, Math.PI / 2] }));
  return g;
}

function watchOnTray(M) {
  const g = new THREE.Group();
  const oxblood = new THREE.MeshStandardMaterial({ color: 0x3a1310, roughness: 0.55 });
  g.add(mesh(rbox(0.22, 0.012, 0.15, 0.006), oxblood, { pos: [0, 0.006, 0] }));
  for (const [w, d, x, z] of [[0.22, 0.012, 0, 0.069], [0.22, 0.012, 0, -0.069], [0.012, 0.15, 0.104, 0], [0.012, 0.15, -0.104, 0]]) {
    g.add(mesh(rbox(w, 0.02, d, 0.005), oxblood, { pos: [x, 0.016, z] }));
  }
  const w = new THREE.Group(); w.position.set(0, 0.018, 0); w.rotation.y = Math.PI / 2 + 0.25; w.scale.setScalar(1.12);
  w.add(mesh(new THREE.CylinderGeometry(0.0195, 0.0195, 0.009, 64), M.steel, { pos: [0, 0.0045, 0] }));
  w.add(mesh(fluted(lathe([[0.0166, 0.0089], [0.0204, 0.0089], [0.0207, 0.0104], [0.0197, 0.0118], [0.017, 0.0116]], 120), 60, 0.022), M.gilt));
  const dial = new THREE.MeshStandardMaterial({ map: TX.watchDial(), roughness: 0.35, metalness: 0.2 });
  w.add(mesh(new THREE.CircleGeometry(0.0168, 64), dial, { pos: [0, 0.0094, 0], rot: [-Math.PI / 2, 0, 0], cast: false }));
  const crystal = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0, transparent: true, opacity: 0.12, clearcoat: 1, envMapIntensity: 0.6 });
  w.add(mesh(new THREE.SphereGeometry(0.06, 48, 12, 0, Math.PI * 2, 0, 0.29), crystal, { pos: [0, 0.0115 - 0.0575, 0], cast: false }));
  w.add(mesh(new THREE.CylinderGeometry(0.0028, 0.0028, 0.005, 16), M.steel, { pos: [0.0215, 0.0045, 0], rot: [0, 0, Math.PI / 2] }));
  for (const sz of [-1, 1]) {
    for (const sx of [-1, 1]) w.add(mesh(rbox(0.004, 0.006, 0.01, 0.0015), M.steel, { pos: [sx * 0.0095, 0.004, sz * 0.021] }));
    for (let i = 0; i < 9; i++) {
      const z = sz * (0.028 + i * 0.0068);
      const y = 0.0025 + Math.max(0, i - 5) * 0.0004;
      w.add(mesh(rbox(0.0178, 0.0042, 0.0062, 0.0016, 2), i % 2 ? M.gilt : M.steel, { pos: [0, y, z] }));
    }
  }
  g.add(w);
  return { group: g, watch: w };
}

function books(M) {
  const g = new THREE.Group();
  const pageMat = new THREE.MeshStandardMaterial({ map: TX.pageEdge(), roughness: 0.9 });
  const specs = [
    { w: 0.19, h: 0.044, d: 0.255, cloth: '#3a2a20', title: 'MOBY DICK', author: 'MELVILLE', rot: 0.07 },
    { w: 0.17, h: 0.034, d: 0.24, cloth: '#1f2a3a', title: 'THE GREAT GATSBY', author: 'FITZGERALD', rot: -0.09 },
    { w: 0.165, h: 0.038, d: 0.228, cloth: '#2b3b2a', title: 'THE SUN ALSO RISES', author: 'HEMINGWAY', rot: 0.14 },
  ];
  let y = 0;
  const made = specs.map((s, i) => {
    const b = new THREE.Group();
    b.position.set(0.004 * i, y, 0); b.rotation.y = s.rot;
    const cloth = new THREE.MeshStandardMaterial({ color: s.cloth, roughness: 0.78 });
    const board = 0.0035, r = s.h / 2;
    b.add(mesh(new THREE.BoxGeometry(s.w, board, s.d - r), cloth, { pos: [0, board / 2, -r / 2] }));
    b.add(mesh(new THREE.BoxGeometry(s.w, board, s.d - r), cloth, { pos: [0, s.h - board / 2, -r / 2] }));
    b.add(mesh(new THREE.BoxGeometry(s.w - 0.008, s.h - board * 2, s.d - r - 0.006), pageMat, { pos: [0, s.h / 2, -r / 2 - 0.003] }));
    b.add(mesh(new THREE.CylinderGeometry(r, r, s.w, 24, 1, false, 0, Math.PI), cloth, { pos: [0, r, s.d / 2 - r], rot: [0, 0, Math.PI / 2] }));
    const label = new THREE.MeshStandardMaterial({ map: TX.spine({ ...s, seed: i + 3 }), transparent: true, roughness: 0.4, metalness: 0.6 });
    b.add(mesh(new THREE.PlaneGeometry(s.w * 0.92, s.h * 0.82), label, { pos: [0, r, s.d / 2 + 0.0005], cast: false }));
    g.add(b);
    y += s.h;
    return b;
  });
  return { group: g, top: made[2] };
}

function decanterSet(M) {
  const g = new THREE.Group();
  g.add(mesh(new THREE.CylinderGeometry(0.165, 0.16, 0.008, 64), M.silver, { pos: [0, 0.004, 0] }));
  g.add(mesh(new THREE.TorusGeometry(0.163, 0.0045, 8, 64), M.silver, { pos: [0, 0.009, 0], rot: [Math.PI / 2, 0, 0] }));
  const d = new THREE.Group(); d.position.set(-0.04, 0.008, 0);
  const body = [[0.0, 0], [0.06, 0], [0.068, 0.004], [0.072, 0.02], [0.077, 0.06], [0.079, 0.1], [0.072, 0.13], [0.052, 0.155], [0.026, 0.176], [0.018, 0.19], [0.017, 0.232], [0.023, 0.24], [0.022, 0.246], [0.016, 0.248]];
  d.add(mesh(lathe(body, 14), M.glass));
  d.add(mesh(lathe([[0, 0.006], [0.064, 0.006], [0.069, 0.03], [0.073, 0.07], [0.074, 0.092], [0, 0.092]], 14), M.whisky, { cast: false }));
  d.add(mesh(lathe([[0, 0.24], [0.012, 0.242], [0.013, 0.256], [0.03, 0.272], [0.026, 0.292], [0.0, 0.3]], 12), M.glass));
  g.add(d);
  const tumbler = [[0, 0], [0.033, 0], [0.035, 0.014], [0.037, 0.085], [0.034, 0.085], [0.032, 0.016], [0, 0.016]];
  g.add(mesh(lathe(tumbler, 12), M.glass, { pos: [0.085, 0.008, 0.06] }));
  g.add(mesh(lathe(tumbler, 12), M.glass, { pos: [0.095, 0.008, -0.065] }));
  g.add(mesh(lathe([[0, 0.016], [0.031, 0.016], [0.0325, 0.04], [0, 0.04]], 12), M.whisky, { pos: [0.085, 0.008, 0.06], cast: false }));
  return { group: g, decanter: d };
}

function ashtray(M) {
  const g = new THREE.Group();
  g.add(mesh(lathe([[0, 0], [0.06, 0], [0.064, 0.012], [0.062, 0.024], [0.05, 0.026], [0.045, 0.012], [0, 0.012]], 10), M.glass));
  const cig = new THREE.Group(); cig.position.set(0.04, 0.03, 0.005); cig.rotation.set(0, 0.3, -0.12);
  cig.add(mesh(new THREE.CylinderGeometry(0.0042, 0.0042, 0.05, 16), M.paper, { pos: [0.025, 0, 0], rot: [0, 0, Math.PI / 2] }));
  cig.add(mesh(new THREE.CylinderGeometry(0.0043, 0.0043, 0.02, 16), new THREE.MeshStandardMaterial({ color: 0xc7a06a, roughness: 0.8 }), { pos: [-0.01, 0, 0], rot: [0, 0, Math.PI / 2] }));
  const ember = mesh(new THREE.SphereGeometry(0.0043, 12, 8), new THREE.MeshStandardMaterial({ color: 0x331100, emissive: 0xff7a2a, emissiveIntensity: 3 }), { pos: [0.051, 0, 0], cast: false });
  cig.add(ember);
  g.add(cig);
  return { group: g, ember, tip: () => ember.getWorldPosition(new THREE.Vector3()) };
}

function telephone(M) {
  const g = new THREE.Group();
  g.add(mesh(rbox(0.17, 0.075, 0.21, 0.032, 5), M.bakelite, { pos: [0, 0.0375, 0] }));
  const dialTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const x = c.getContext('2d');
    x.fillStyle = '#0c0b0a'; x.beginPath(); x.arc(128, 128, 126, 0, 7); x.fill();
    x.fillStyle = '#e9e3d3';
    for (let i = 0; i < 10; i++) { const a = -2.2 + i * 0.47; x.beginPath(); x.arc(128 + Math.cos(a) * 90, 128 + Math.sin(a) * 90, 20, 0, 7); x.fill(); }
    x.fillStyle = '#efe9db'; x.beginPath(); x.arc(128, 128, 46, 0, 7); x.fill();
    x.fillStyle = '#1a1916'; x.font = '400 22px "Special Elite"'; x.textAlign = 'center'; x.fillText('1138', 128, 136);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const dial = mesh(new THREE.CylinderGeometry(0.046, 0.046, 0.006, 48), [M.bakelite, new THREE.MeshPhysicalMaterial({ map: dialTex, roughness: 0.25, clearcoat: 1 }), M.bakelite], { pos: [0, 0.07, 0.055], rot: [0.55, 0, 0] });
  g.add(dial);
  for (const sx of [-1, 1]) g.add(mesh(rbox(0.02, 0.04, 0.03, 0.008), M.bakelite, { pos: [sx * 0.07, 0.09, -0.04] }));
  const hs = new THREE.Group(); hs.position.set(0, 0.112, -0.045);
  hs.add(mesh(new THREE.CapsuleGeometry(0.014, 0.16, 6, 16), M.bakelite, { rot: [0, 0, Math.PI / 2] }));
  for (const sx of [-1, 1]) hs.add(mesh(new THREE.CylinderGeometry(0.027, 0.022, 0.034, 32), M.bakelite, { pos: [sx * 0.092, -0.012, 0] }));
  g.add(hs);
  const cord = new THREE.CatmullRomCurve3([V3(-0.085, 0.02, -0.08), V3(-0.13, 0.006, -0.04), V3(-0.16, 0.004, 0.06), V3(-0.12, 0.004, 0.14), V3(-0.05, 0.004, 0.16)]);
  g.add(mesh(new THREE.TubeGeometry(cord, 60, 0.005, 8, false), M.bakelite));
  return g;
}

function fedora(M) {
  const g = new THREE.Group();
  const crown = lathe([[0, 0.112], [0.03, 0.111], [0.055, 0.106], [0.074, 0.092], [0.084, 0.066], [0.089, 0.034], [0.091, 0.004]], 64);
  const p = crown.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i), r = Math.hypot(x, z);
    if (y > 0.07) {
      const a = Math.atan2(x, z);
      const pinch = 1 - 0.16 * (Math.exp(-((a - 0.55) ** 2) / 0.06) + Math.exp(-((a + 0.55) ** 2) / 0.06)) * (y - 0.07) / 0.042;
      p.setX(i, x * pinch); p.setZ(i, z * pinch);
    }
    if (r < 0.06 && y > 0.09) p.setY(i, y - 0.03 * (1 - r / 0.06));    /* the centre dent */
  }
  crown.scale(0.95, 1, 1.1); crown.computeVertexNormals();
  g.add(mesh(crown, M.felt));
  g.add(mesh(lathe([[0.085, 0.002], [0.12, 0.0], [0.15, -0.002], [0.164, 0.004], [0.168, 0.012], [0.166, 0.014], [0.15, 0.006], [0.12, 0.004], [0.085, 0.006]], 64).scale(0.95, 1, 1.1), M.felt));
  g.add(mesh(new THREE.CylinderGeometry(0.0905, 0.0915, 0.024, 64, 1, true).scale(0.95, 1, 1.1), M.band, { pos: [0, 0.016, 0] }));
  return g;
}

function folder(M) {
  const mat = new THREE.MeshStandardMaterial({ map: TX.folder(), roughness: 0.85 });
  const sheet = new THREE.MeshStandardMaterial({ map: TX.typedPage(), roughness: 0.92 });
  const g = new THREE.Group();
  g.add(mesh(new THREE.BoxGeometry(0.31, 0.004, 0.235), [M.paper, M.paper, mat, M.paper, M.paper, M.paper], { pos: [0, 0.002, 0] }));
  g.add(mesh(new THREE.PlaneGeometry(0.2, 0.258), sheet, { pos: [0.09, 0.0046, 0.05], rot: [-Math.PI / 2, 0, 0.32], cast: false }));
  return g;
}

/* a rectangular ring, extruded and bevelled: mitred corners for free */
function frameRing(outerW, outerH, innerW, innerH, depth, bevel) {
  const sh = new THREE.Shape();
  sh.moveTo(-outerW / 2, -outerH / 2); sh.lineTo(outerW / 2, -outerH / 2); sh.lineTo(outerW / 2, outerH / 2); sh.lineTo(-outerW / 2, outerH / 2); sh.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-innerW / 2, -innerH / 2); hole.lineTo(-innerW / 2, innerH / 2); hole.lineTo(innerW / 2, innerH / 2); hole.lineTo(innerW / 2, -innerH / 2); hole.closePath();
  sh.holes.push(hole);
  return new THREE.ExtrudeGeometry(sh, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 4, curveSegments: 1 });
}

function painting(M) {
  const g = new THREE.Group();
  const W = 1.0, H = 0.75;
  const canvasMat = new THREE.MeshStandardMaterial({ map: TX.seascape(), roughness: 0.55 });
  g.add(mesh(new THREE.PlaneGeometry(W, H), canvasMat, { pos: [0, 0, 0.03], cast: false }));
  const linen = new THREE.MeshStandardMaterial({ color: 0xe8dfc8, roughness: 0.95 });
  g.add(mesh(frameRing(W + 0.1, H + 0.1, W, H, 0.012, 0.004), linen, { pos: [0, 0, 0.026] }));
  /* a stepped gilt molding: back slab, a cove, a raised lip */
  const slab = mesh(frameRing(W + 0.36, H + 0.36, W + 0.12, H + 0.12, 0.03, 0.012), M.gilt, { pos: [0, 0, 0.012] });
  g.add(slab);
  g.userData.frame = slab;
  g.add(mesh(frameRing(W + 0.27, H + 0.27, W + 0.15, H + 0.15, 0.03, 0.018), M.giltDark, { pos: [0, 0, 0.04] }));
  g.add(mesh(frameRing(W + 0.17, H + 0.17, W + 0.1, H + 0.1, 0.022, 0.01), M.gilt, { pos: [0, 0, 0.046] }));
  /* the picture light */
  g.add(mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.48, 24), M.brass, { pos: [0, H / 2 + 0.24, 0.17], rot: [0, 0, Math.PI / 2] }));
  g.add(mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.17, 12), M.brass, { pos: [0, H / 2 + 0.21, 0.09], rot: [1.2, 0, 0] }));
  return g;
}

/* ---------- light, haze, smoke, dust ---------- */
const NOISE_GLSL = `
  float h21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
  float vn(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(h21(i), h21(i + vec2(1, 0)), u.x), mix(h21(i + vec2(0, 1)), h21(i + vec2(1, 1)), u.x), u.y); }
  float fbm2(vec2 p){ float v = 0.0, a = 0.5; for(int i = 0; i < 5; i++){ v += a * vn(p); p *= 2.03; a *= 0.5; } return v; }
`;

/* the blinds' stripes, as seen in the haze: each fragment traces back to the window */
function beamVolume(lightPos, spacing) {
  const pts = [];
  const corners = [[WIN.z0, WIN.y0], [WIN.z1, WIN.y0], [WIN.z1, WIN.y1], [WIN.z0, WIN.y1]].map(([z, y]) => V3(ROOM.x0 + 0.05, y, z));
  const far = corners.map(c => c.clone().add(c.clone().sub(lightPos).normalize().multiplyScalar(6.5)));
  const v = [...corners, ...far];
  const quads = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
  for (const [a, b, c, d] of quads) pts.push(v[a], v[b], v[c], v[a], v[c], v[d]);
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = new THREE.ShaderMaterial({
    uniforms: { lightPos: { value: lightPos }, spacing: { value: spacing }, time: { value: 0 }, strength: { value: 0.42 } },
    vertexShader: `varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `${NOISE_GLSL}
      uniform vec3 lightPos; uniform float spacing; uniform float time; uniform float strength; varying vec3 vW;
      void main(){
        vec3 d = vW - lightPos;
        float s = (${(ROOM.x0 + 0.075).toFixed(3)} - lightPos.x) / d.x;
        vec3 q = lightPos + d * s;
        float inside = step(${WIN.z0.toFixed(3)}, q.z) * step(q.z, ${WIN.z1.toFixed(3)}) * step(${(WIN.y0 + 0.03).toFixed(3)}, q.y) * step(q.y, ${(WIN.y1 - 0.08).toFixed(3)});
        float f = fract((q.y - ${(WIN.y1 - 0.08).toFixed(3)}) / spacing);
        float lit = smoothstep(0.08, 0.2, f) * (1.0 - smoothstep(0.62, 0.76, f));
        float dist = length(vW - q);
        float fall = exp(-dist * 0.32) * smoothstep(0.0, 0.4, dist);
        float n = 0.65 + 0.35 * fbm2(vW.xz * 2.2 + vec2(time * 0.05, vW.y * 1.7));
        gl_FragColor = vec4(vec3(1.0, 0.97, 0.9) * inside * lit * fall * n * strength, 1.0);
      }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  });
  const m = new THREE.Mesh(geo, mat);
  m.frustumCulled = false; m.renderOrder = 5;
  return m;
}

function dust(lightPos, spacing, count = 420) {
  const R = TX.rng(41), pos = new Float32Array(count * 3), seed = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = ROOM.x0 + 0.3 + R() * 4.2;
    pos[i * 3 + 1] = 0.5 + R() * 2.2;
    pos[i * 3 + 2] = -2.9 + R() * 2.9;
    seed[i] = R();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: { lightPos: { value: lightPos }, spacing: { value: spacing }, time: { value: 0 }, px: { value: 900 } },
    vertexShader: `
      attribute float seed; uniform float time; uniform float px; varying vec3 vW; varying float vS;
      void main(){
        vec3 p = position;
        p.x += sin(time * 0.31 + seed * 40.0) * 0.05;
        p.y += sin(time * 0.17 + seed * 23.0) * 0.04 - mod(time * 0.012 + seed, 1.0) * 0.1;
        p.z += cos(time * 0.23 + seed * 31.0) * 0.05;
        vec4 w = modelMatrix * vec4(p, 1.0); vW = w.xyz; vS = seed;
        vec4 mv = viewMatrix * w;
        gl_PointSize = px * (0.0035 + seed * 0.004) / -mv.z;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform vec3 lightPos; uniform float spacing; uniform float time; varying vec3 vW; varying float vS;
      void main(){
        vec2 c = gl_PointCoord - 0.5; float r = length(c); if(r > 0.5) discard;
        vec3 d = vW - lightPos; float s = (${(ROOM.x0 + 0.075).toFixed(3)} - lightPos.x) / d.x; vec3 q = lightPos + d * s;
        float inside = step(${WIN.z0.toFixed(3)}, q.z) * step(q.z, ${WIN.z1.toFixed(3)}) * step(${WIN.y0.toFixed(3)}, q.y) * step(q.y, ${WIN.y1.toFixed(3)});
        float f = fract((q.y - ${(WIN.y1 - 0.08).toFixed(3)}) / spacing);
        float lit = smoothstep(0.08, 0.2, f) * (1.0 - smoothstep(0.62, 0.76, f));
        float tw = 0.55 + 0.45 * sin(time * 2.0 + vS * 60.0);
        float a = inside * lit * tw * (1.0 - r * 2.0) * 0.9;
        gl_FragColor = vec4(vec3(1.0, 0.97, 0.9) * a, 1.0);
      }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const p = new THREE.Points(geo, mat);
  p.frustumCulled = false; p.renderOrder = 6;
  return p;
}

/* cigarette smoke: a camera-facing card with a curling plume */
function smoke() {
  const mat = new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `${NOISE_GLSL}
      uniform float time; varying vec2 vUv;
      void main(){
        float h = vUv.y, x = vUv.x - 0.5;
        float wander = (fbm2(vec2(h * 2.2 - time * 0.35, time * 0.11)) - 0.5) * 0.55 * h;
        float width = 0.016 + h * h * 0.24;
        float core = exp(-pow((x - wander) / width, 2.0));
        float wisp = fbm2(vec2((x - wander) * 7.0, h * 5.0 - time * 0.9) + fbm2(vec2(h * 3.0, time * 0.25)) * 2.0);
        float a = core * smoothstep(0.0, 0.05, h) * (1.0 - smoothstep(0.5, 1.0, h)) * (0.25 + wisp * 1.1);
        gl_FragColor = vec4(vec3(0.9, 0.88, 0.84), clamp(a, 0.0, 1.0) * 0.62);
      }`,
    transparent: true, depthWrite: false,
  });
  const m = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.75), mat);
  m.geometry.translate(0, 0.375, 0);
  m.renderOrder = 7;
  return m;
}

function glowSprite(size) {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  r.addColorStop(0, 'rgba(255,240,210,.9)'); r.addColorStop(0.25, 'rgba(255,230,190,.28)'); r.addColorStop(1, 'rgba(255,230,190,0)');
  g.fillStyle = r; g.fillRect(0, 0, 128, 128);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  s.scale.setScalar(size);
  return s;
}

/* ---------- build ---------- */
export function build(renderer) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050505);
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.12;
  scene.fog = new THREE.FogExp2(0x0a0908, 0.05);
  const M = materials(scene.environment);

  scene.add(room(M));
  const win = windowSet(M);
  scene.add(win.group);

  const rugMesh = mesh(new THREE.PlaneGeometry(3.4, 2.34), M.rug, { rot: [-Math.PI / 2, 0, 0], pos: [-0.3, 0.004, -1.55], cast: false });
  scene.add(rugMesh);

  const D = desk(M); D.position.set(-0.35, 0, -1.75); scene.add(D);
  const C = chair(M); C.position.set(-0.4, 0, -2.5); C.rotation.y = 0.18; scene.add(C);
  const F = cabinet(M); F.position.set(2.75, 0, -2.66); scene.add(F);
  const hat = fedora(M); hat.position.set(2.72, 1.322, -2.62); hat.rotation.y = 0.9; scene.add(hat);

  const top = 0.78;
  const lamp = bankersLamp(M); lamp.group.position.set(-1.1, top, -2.0); lamp.group.rotation.y = 0.12; scene.add(lamp.group);
  const ash = ashtray(M); ash.group.position.set(-0.7, top, -2.08); scene.add(ash.group);
  const cam35 = leica(M); cam35.position.set(-1.06, top, -1.44); cam35.rotation.y = 0.5; scene.add(cam35);
  const fold = folder(M); fold.position.set(-0.66, top, -1.52); fold.rotation.y = -0.1; scene.add(fold);
  const watch = watchOnTray(M); watch.group.position.set(-0.3, top, -1.62); watch.group.rotation.y = -0.22; scene.add(watch.group);
  const stack = books(M); stack.group.position.set(0.08, top, -1.98); stack.group.rotation.y = -0.18; scene.add(stack.group);
  const dec = decanterSet(M); dec.group.position.set(0.44, top, -2.04); scene.add(dec.group);
  const phone = telephone(M); phone.position.set(0.47, top, -1.52); phone.rotation.y = -0.45; scene.add(phone);
  const art = painting(M); art.position.set(1.55, 1.78, ROOM.z0); scene.add(art);

  /* light: the street through the blinds */
  const streetPos = V3(-10.6, 2.75, 1.05);
  const street = new THREE.SpotLight(0xdfe5ff, 1350, 0, 0.21, 0.25, 2);
  street.position.copy(streetPos); street.target.position.set(0.6, 1.3, -3.0);
  street.castShadow = true; street.shadow.mapSize.set(2048, 2048);
  street.shadow.bias = -0.0002; street.shadow.normalBias = 0.01;
  street.shadow.camera.near = 4; street.shadow.camera.far = 22;
  scene.add(street, street.target);

  /* the banker's lamp */
  const lampLight = new THREE.SpotLight(0xffd9a0, 8.5, 5, 1.2, 0.8, 2);
  const lampPos = lamp.shade.localToWorld(V3(0, -0.02, 0));
  lamp.group.updateMatrixWorld(true);
  lampLight.position.copy(lamp.shade.localToWorld(V3(0, -0.02, 0)));
  lampLight.target.position.set(-0.62, top, -1.58);
  lampLight.castShadow = true; lampLight.shadow.mapSize.set(2048, 2048);
  lampLight.shadow.bias = -0.0004; lampLight.shadow.normalBias = 0.004;
  lampLight.shadow.camera.near = 0.02; lampLight.shadow.camera.far = 4;
  scene.add(lampLight, lampLight.target);
  const inner = new THREE.PointLight(0xffe2b0, 0.5, 0.35, 2);
  inner.position.copy(lampLight.position).add(V3(0, 0.03, 0));
  scene.add(inner);
  const glow = glowSprite(0.32); glow.position.copy(lampLight.position); scene.add(glow);
  void lampPos;

  /* the picture light over the painting */
  const pic = new THREE.SpotLight(0xffe4b8, 3.2, 3, 0.75, 0.85, 2);
  pic.position.set(1.55, 2.38, ROOM.z0 + 0.2); pic.target.position.set(1.55, 1.62, ROOM.z0);
  pic.castShadow = true; pic.shadow.mapSize.set(1024, 1024); pic.shadow.bias = -0.0005;
  scene.add(pic, pic.target);

  /* a little bounce so the blacks are film blacks, not holes */
  scene.add(new THREE.HemisphereLight(0x8a90a0, 0x1a140f, 0.42));

  /* a high raking light from the outer office, for the right half of the desk */
  const rake = new THREE.SpotLight(0xd6dcf0, 7, 7, 0.42, 0.9, 2);
  rake.position.set(2.6, 2.9, 0.5); rake.target.position.set(0.3, 0.82, -1.95);
  rake.castShadow = true; rake.shadow.mapSize.set(1024, 1024); rake.shadow.bias = -0.0005;
  scene.add(rake, rake.target);

  const beams = beamVolume(streetPos, win.slatSpacing); scene.add(beams);
  const motes = dust(streetPos, win.slatSpacing); scene.add(motes);
  const plume = smoke(); scene.add(plume);

  const camera = new THREE.PerspectiveCamera(46, 16 / 9, 0.03, 40);
  scene.updateMatrixWorld(true);

  /* the six exhibits, in the order the cap finds them. target is what the marker frames */
  const exhibits = [
    { n: 1, item: 'Brass desk lamp', value: 180, estimated: false, why: 'sold comps', target: lamp.group },
    { n: 2, item: 'Leica M3 rangefinder', value: 1850, estimated: false, why: 'sold comps', target: cam35 },
    { n: 3, item: 'Vintage Rolex', value: 4200, estimated: false, why: 'sold comps', target: watch.watch },
    { n: 4, item: 'First-ed. Hemingway', value: 950, estimated: false, why: 'sold comps', target: stack.top },
    { n: 5, item: 'Crystal decanter', value: 340, estimated: true, why: 'model quote', target: dec.decanter },
    { n: 6, item: 'Oil on canvas, unsigned', value: 2400, estimated: true, why: 'model quote', target: art.userData.frame },
  ];

  function update(t) {
    beams.material.uniforms.time.value = t;
    motes.material.uniforms.time.value = t;
    plume.material.uniforms.time.value = t;
    const tip = ash.tip();
    plume.position.copy(tip);
    plume.rotation.y = Math.atan2(camera.position.x - tip.x, camera.position.z - tip.z);
    ash.ember.material.emissiveIntensity = 2.6 + Math.sin(t * 2.3) * 0.6 + Math.sin(t * 7.1) * 0.3;
  }

  return {
    scene, camera, exhibits, update,
    lights: { street, lampLight, pic },
    setDustScale(px) { motes.material.uniforms.px.value = px; },
  };
}

/* screen-space box of an object: project its world AABB, return fractions of the frame */
const _box = new THREE.Box3(), _v = new THREE.Vector3();
export function screenBox(obj, camera, shrink = 0.06) {
  _box.setFromObject(obj);
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, behind = 0;
  for (let i = 0; i < 8; i++) {
    _v.set(i & 1 ? _box.max.x : _box.min.x, i & 2 ? _box.max.y : _box.min.y, i & 4 ? _box.max.z : _box.min.z);
    _v.applyMatrix4(camera.matrixWorldInverse);
    if (_v.z > -camera.near) behind++;
    _v.applyMatrix4(camera.projectionMatrix);
    const x = (_v.x + 1) / 2, y = (1 - _v.y) / 2;
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  if (behind) return null;
  const w = x1 - x0, h = y1 - y0;
  return { l: x0 + w * shrink / 2, t: y0 + h * shrink / 2, w: w * (1 - shrink), h: h * (1 - shrink) };
}
