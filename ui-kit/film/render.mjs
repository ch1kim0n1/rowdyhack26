/* Renders the film. Needs Node 18+, ffmpeg, and Chromium for Playwright
   (npx playwright install chromium if you don't have it).

     node render.mjs views views.json   photograph the set from test angles
     node render.mjs film                every frame to frames/, then encode
     node render.mjs encode              frames/ to ../media/film-*.mp4
     node render.mjs stills              poster, hero, rover still, mugshots

   The page is served from ui-kit/, so the film uses the kit's own CSS and fonts. */
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const KIT = path.resolve(HERE, '..');
const MEDIA = path.join(KIT, 'media');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json' };

function serve() {
  const srv = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]);
    const file = path.join(KIT, path.normalize(rel));
    if (!file.startsWith(KIT)) { res.writeHead(403); res.end(); return; }
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r(srv)));
}

async function open() {
  const srv = await serve();
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('pageerror', e => console.error('page error:', e.message));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.error('console:', m.text()); });
  await page.goto(`http://127.0.0.1:${srv.address().port}/film/film.html`);
  await page.waitForFunction(() => window.FILM && window.FILM.ready, null, { timeout: 120000 });
  const cdp = await page.context().newCDPSession(page);
  const grab = async (file, quality = 94) => {
    const { data } = await cdp.send('Page.captureScreenshot', { format: 'jpeg', quality, optimizeForSpeed: true });
    fs.writeFileSync(file, Buffer.from(data, 'base64'));
  };
  return { page, grab, async close() { await browser.close(); srv.close(); } };
}

const saveData = (file, dataUrl) => fs.writeFileSync(file, Buffer.from(dataUrl.split(',')[1], 'base64'));
const [, , mode = 'film', ...rest] = process.argv;

if (mode === 'views') {
  const views = JSON.parse(fs.readFileSync(rest[0], 'utf8'));
  const out = rest[1] || path.join(HERE, 'preview');
  fs.mkdirSync(out, { recursive: true });
  const f = await open();
  for (const v of views) {
    const t0 = Date.now();
    await f.page.evaluate(v => window.FILM.view(v), v);
    await f.grab(path.join(out, `${v.name}.jpg`));
    console.log(v.name, Date.now() - t0, 'ms');
  }
  await f.close();
}

if (mode === 'film') {
  const out = path.join(HERE, 'frames');
  fs.mkdirSync(out, { recursive: true });
  const f = await open();
  const total = await f.page.evaluate(() => window.FILM.frames);
  const from = Number(rest[0] ?? 0), to = Number(rest[1] ?? total - 1), step = Number(rest[2] ?? 1);
  const t0 = Date.now();
  for (let i = from; i <= to; i += step) {
    await f.page.evaluate(i => window.FILM.seek(i), i);
    await f.grab(path.join(out, `${String(i).padStart(4, '0')}.jpg`), 95);
    if (i % 24 === 0) console.log(`frame ${i}/${to}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await f.close();
}

if ((mode === 'film' && !rest.length) || mode === 'encode') {
  fs.mkdirSync(MEDIA, { recursive: true });
  const frames = path.join(HERE, 'frames', '%04d.jpg');
  /* short GOP, no B-frames: the premiere page scrubs this with the scroll wheel */
  const enc = (w, crf, file) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '24', '-i', frames,
    '-vf', `scale=${w}:-2:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-preset', 'slow', '-crf', String(crf),
    '-g', '6', '-keyint_min', '6', '-bf', '0', '-tune', 'film', '-movflags', '+faststart', '-an', path.join(MEDIA, file)], { stdio: 'inherit' });
  /* VP9 too: open-source Chromium builds have no H.264 decoder */
  const vp9 = (w, crf, file) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '24', '-i', frames,
    '-vf', `scale=${w}:-2:flags=lanczos,format=yuv420p`, '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', String(crf),
    '-g', '6', '-row-mt', '1', '-deadline', 'good', '-cpu-used', '2', '-an', path.join(MEDIA, file)], { stdio: 'inherit' });
  enc(1600, 24, 'film-1600.mp4');
  enc(960, 25, 'film-960.mp4');
  vp9(1600, 36, 'film-1600.webm');
  vp9(960, 38, 'film-960.webm');
  for (const f of ['film-1600.mp4', 'film-960.mp4', 'film-1600.webm', 'film-960.webm']) console.log(f, (fs.statSync(path.join(MEDIA, f)).size / 1e6).toFixed(2), 'MB');
  /* the poster is the first frame of the picture: PICTURE START */
  fs.copyFileSync(path.join(HERE, 'frames', '0000.jpg'), path.join(MEDIA, 'film-poster.jpg'));
}

if (mode === 'stills') {
  fs.mkdirSync(MEDIA, { recursive: true });
  const f = await open();
  const shots = await f.page.evaluate(() => window.FILM.stills());
  for (const [name, url] of Object.entries(shots)) { saveData(path.join(MEDIA, `${name}.jpg`), url); console.log('still', name); }
  await f.close();
}

if (mode === 'peek') {
  /* a contact sheet of single frames: node render.mjs peek 60 90 120 */
  const out = path.join(HERE, 'preview');
  fs.mkdirSync(out, { recursive: true });
  const f = await open();
  for (const i of rest.map(Number)) {
    const t0 = Date.now();
    await f.page.evaluate(i => window.FILM.seek(i), i);
    await f.grab(path.join(out, `f${String(i).padStart(4, '0')}.jpg`));
    console.log('frame', i, Date.now() - t0, 'ms');
  }
  await f.close();
}
