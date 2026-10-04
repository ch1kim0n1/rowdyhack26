/* The kit on top of the footage: header, evidence markers, the typed ledger,
   the odometer, then the dashboard, the lineup and THE END. All of it is the
   real NOIRKIT markup and CSS; this file only decides, for a given t, where
   each piece is and how far along it is. */
import { T, FPS, FINDS, beats, ez, span, lerp, odometer } from './story.js';

const pad = (n, w = 2) => String(n).padStart(w, '0');
const el = (tag, cls = '', html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};
const whole = v => '$' + Math.round(v).toLocaleString('en-US');
const EST = ' <span class="est">est.</span>';
const typed = (text, t0, t) => text.slice(0, Math.max(0, Math.floor((t - t0) / T.typeChar)));
const LEADER = ['8', '7', 'SIX', '5', '4', '3', '2', '1'];
const LH = 64;

function odoView(root) {
  const cur = el('span', 'odo-cur', '$'), cols = [], seps = [];
  return state => {
    root.style.setProperty('--odo-k', state.k);
    root.setAttribute('aria-label', '$' + state.text);
    const order = [cur];
    let di = 0, si = 0;
    for (const ch of state.text) {
      if (ch === ',') { seps[si] ??= el('span', 'odo-sep', ','); order.push(seps[si++]); continue; }
      if (!cols[di]) {
        const d = el('span', 'odo-digit'), st = el('span', 'odo-strip');
        for (let i = 0; i < 10; i++) st.append(el('span', '', String(i)));
        d.append(st); cols[di] = { d, st };
      }
      cols[di].st.style.setProperty('--d', state.cols[di].toFixed(4));
      order.push(cols[di++].d);
    }
    root.replaceChildren(...order);
  };
}

function header(left, reel, fr) {
  return `<div class="label">${left}</div><div class="meta">${reel} &nbsp;·&nbsp; ${fr ? '<span class="fr"></span> &nbsp;·&nbsp; ' : ''}<span class="line-live"><span class="rec">●</span> REC</span></div>`;
}

export function makeOverlay(frame, { exhibits, mugs, qr, Noir, shot, boxAt }) {
  const items = exhibits.map((x, i) => ({ ...x, item: x.item.toUpperCase(), b: beats(FINDS[i], x.item) }));
  let run = 0;
  const odoEvents = items.map(it => ({ t: it.b.count, value: (run += it.value) }));
  const total = run;
  const top = [...items].sort((a, b) => b.value - a.value).slice(0, 5);

  /* ---------- reel 1: the leader ---------- */
  const reel = el('div', 'reel-start', '<div class="leader"><span class="leader-n"></span></div><div class="picture-start">Picture<br>Start</div>');
  const leaderN = reel.querySelector('.leader-n');
  const blackout = el('div', 'layer blackout');

  /* ---------- the walk: HUD over the footage ---------- */
  const hud = el('div', 'layer hud', `
    <div class="hud-scrim top"></div><div class="hud-scrim bot"></div>
    <header class="chrome film-chrome">${header('Case NO. 1138 · The Appraisal Job', 'Reel 1', true)}</header>
    <div class="hud-log"></div>
    <div class="hud-take"><div class="label">Estimated take</div><div class="odo"></div><div class="meta hud-count"></div></div>`);
  const hudLog = hud.querySelector('.hud-log');
  const hudOdo = odoView(hud.querySelector('.odo'));
  const markers = shot.querySelector('.markers');

  const lines = items.map(it => {
    const line = el('div', 'log-line', '<span class="file-still"></span><span class="txt"></span><span class="leaders"></span><span class="amt"></span>');
    const img = el('img'); img.src = mugs[it.n]; img.alt = '';
    line.querySelector('.file-still').append(img);
    hudLog.append(line);
    const marker = el('div', 'marker hot', `<span class="tag">Exhibit ${pad(it.n)}</span><span class="cap"></span>`);
    marker.querySelector('.cap').textContent = `"${it.item}" · $${it.value.toLocaleString()}${it.estimated ? ' est.' : ''}`;
    markers.append(marker);
    const chip = el('div', 'case-chip'); const cimg = el('img'); cimg.src = mugs[it.n]; chip.append(cimg);
    return { it, line, marker, chip, txt: line.querySelector('.txt'), amt: line.querySelector('.amt'), still: line.querySelector('.file-still') };
  });

  /* ---------- the dashboard the room watches ---------- */
  const live = el('section', 'view view-live on', `
    <header class="chrome">${header('Case NO. <span>1138</span> · The Appraisal Job', 'Reel 1', true)}</header>
    <main class="live-grid">
      <div class="film">
        <div class="film-band top"></div>
        <div class="feed"><div class="frame-box" style="--ar:16/9"></div>
          <span class="reg tl"></span><span class="reg tr"></span><span class="reg bl"></span><span class="reg br"></span></div>
        <div class="film-band bot"><div class="film-label">Roll A · Cam 01 · Optic Surveillance</div></div>
      </div>
      <aside class="live-side">
        <div><div class="label">Estimated Take</div><div class="odo"></div></div>
        <div class="count-row"><span class="stat"><b id="count">6</b><span class="label">Items</span></span><span class="meta"><span class="est" style="margin:0">est.</span> is a guess</span></div>
        <div class="label">Case File</div>
        <div class="log"></div>
        <div class="note">the good stuff's never on the first shelf.</div>
      </aside>
    </main>
    <footer class="foot"><span class="meta">Stop files the lineup. Hit it again to close the case.</span><button type="button" class="rig-stop" tabindex="-1">Stop</button></footer>`);
  const liveOdo = odoView(live.querySelector('.odo'));
  const liveLog = live.querySelector('.log');
  items.forEach((it, i) => {
    const line = el('div', 'log-line' + (i < items.length - 1 ? ' old' : ''), `<span class="file-still on"><img alt="" src="${mugs[it.n]}"></span><span class="txt"><span class="ex-k">${pad(it.n)}</span><span class="ex-name"></span></span><span class="leaders"></span><span class="amt">${whole(it.value)}${it.estimated ? EST : ''}</span>`);
    line.querySelector('.ex-name').textContent = it.item;
    liveLog.append(line);
  });
  const frameBox = live.querySelector('.frame-box');
  const feed = live.querySelector('.feed');
  const liveCount = live.querySelector('#count');

  /* ---------- reel 2: cue, curtain, lineup ---------- */
  const cue = el('div', 'cue');
  const curtain = el('div', 'curtain');
  const reveal = el('section', 'view view-reveal', `
    <header class="chrome">${header('Case NO. 1138 · Identification Parade', 'Reel 2', false)}</header>
    <h1 class="reveal-title cut">The Usual Suspects</h1>
    <div class="reveal-sub meta"></div>
    <div class="lineup-wall">
      <div class="wall-marks" aria-hidden="true"><span>4'0"</span><span>4'6"</span><span>5'0"</span><span>5'6"</span><span>6'0"</span><span>6'6"</span><span>7'0"</span></div>
      ${'<div class="suspect"><div class="photo"><img alt=""><div class="placard"></div></div><div class="name"></div><div class="price"></div><div class="why"></div></div>'.repeat(5)}
    </div>
    <footer class="reveal-foot">
      <div class="reveal-total"><div class="label">Total take</div><div class="odo sm"></div></div>
      <div class="stamp" style="--rot:-6deg">Case Closed</div>
      <div class="file-copy"><div class="qr-mat"><img alt="" src="${qr}"></div><div class="cap meta">Scan this. It's the file.</div></div>
      <button type="button" class="rig-stop" tabindex="-1">Stop</button>
    </footer>`);
  const totalOdo = odoView(reveal.querySelector('.odo'));
  const stamp = reveal.querySelector('.stamp');
  const wall = reveal.querySelector('.lineup-wall');
  const titleEl = reveal.querySelector('.reveal-title');
  const slots = [...reveal.querySelectorAll('.suspect')].map((s, k) => {
    const rank = 5 - k, it = top[rank - 1];
    s.querySelector('img').src = mugs[it.n];
    s.querySelector('.placard').textContent = `Suspect NO. ${rank}`;
    s.querySelector('.name').textContent = it.item;
    s.querySelector('.why').textContent = it.why;
    return { s, it, photo: s.querySelector('.photo'), placard: s.querySelector('.placard'), name: s.querySelector('.name'), price: s.querySelector('.price') };
  });

  const theEnd = el('div', 'the-end', '<div class="meta">A RowdyHacks XII Picture</div><div class="end-title cut">The End</div><div class="meta end-case">Case No. 1138 · Closed</div>');
  const vignette = el('div', 'vignette');

  frame.append(live, hud, ...lines.map(l => l.chip), reveal, cue, curtain, theEnd, blackout, reel, vignette);
  Noir.cutType(titleEl);
  Noir.cutType(theEnd.querySelector('.end-title'));

  const show = (node, on) => { node.style.display = on ? '' : 'none'; };
  const fr = i => `FR 00:00:${pad(Math.floor(i / FPS))}:${pad(i % FPS)}`;
  const rec = t => (0.6 + 0.4 * Math.cos(t / 2.4 * Math.PI * 2)).toFixed(3);

  function update(t, cam) {
    const frameNo = Math.round(t * FPS);
    frame.querySelectorAll('.fr').forEach(n => { n.textContent = fr(frameNo); });
    frame.querySelectorAll('.rec').forEach(n => { n.style.opacity = rec(t); });

    /* leader */
    const inLeader = t < T.countEnd;
    reel.classList.toggle('on', inLeader);
    reel.classList.toggle('ps', t < T.countFrom);
    if (inLeader && t >= T.countFrom) {
      const foot = (T.countEnd - T.countFrom) / LEADER.length;
      const i = Math.min(LEADER.length - 1, Math.floor((t - T.countFrom) / foot));
      const k = ez.outCubic(span(t, T.countFrom + i * foot, foot * 0.55));
      leaderN.textContent = LEADER[i];
      leaderN.classList.toggle('word', LEADER[i].length > 1);
      leaderN.style.opacity = k; leaderN.style.transform = `scale(${lerp(0.9, 1, k)})`;
    } else leaderN.textContent = '';
    blackout.style.opacity = t < T.fadeUp ? 1 : 1 - ez.film(span(t, T.fadeUp, T.fadeUpDur));

    /* the walk */
    const toDash = ez.film(span(t, T.toDash, T.toDashDur));
    const walkHud = t < T.toDash ? ez.film(span(t, T.fadeUp + 0.3, 0.6)) : 1 - ez.film(span(t, T.toDash, 0.45));
    show(hud, walkHud > 0.001); hud.style.opacity = walkHud;
    hudOdo(odometer(odoEvents, t));
    const counted = odoEvents.filter(e => e.t <= t).length;
    hud.querySelector('.hud-count').textContent = `Items cataloged: ${pad(counted)}`;
    const caret = (0.55 + 0.45 * Math.cos(t / 1.1 * Math.PI * 2)).toFixed(3);

    lines.forEach((L, j) => {
      const b = L.it.b;
      const visible = t >= b.pend;
      let slot = 0;
      for (let k = j + 1; k < lines.length; k++) slot += ez.settle(span(t, lines[k].it.b.pend, 0.45));
      const rise = ez.settle(span(t, b.pend, 0.68));
      const fade = 1 - span(slot, 2, 0.6);
      show(L.line, visible && fade > 0.001);
      L.line.style.bottom = `${slot * LH}px`;
      L.line.style.opacity = rise * fade;
      L.line.style.transform = `translateY(${(1 - rise) * 8}px)`;
      L.line.style.setProperty('--caret', caret);
      L.line.classList.toggle('old', slot > 0.5);
      if (t < b.land) {
        L.line.classList.add('pending', 'typing');
        L.txt.textContent = typed(`> EXAMINING EXHIBIT ${pad(L.it.n)}...`, b.pend, t);
        L.amt.innerHTML = '';
      } else {
        L.line.classList.remove('pending');
        L.line.classList.toggle('typing', t < b.typed);
        if (!L.txt.querySelector('.ex-name')) L.txt.innerHTML = `<span class="ex-k">${pad(L.it.n)}</span><span class="ex-name"></span>`;
        L.txt.querySelector('.ex-name').textContent = typed(L.it.item, b.land, t);
        L.amt.innerHTML = t >= b.typed ? whole(L.it.value) + (L.it.estimated ? EST : '') : '';
        L.amt.style.opacity = ez.settle(span(t, b.typed, 0.36));
      }
      L.still.classList.toggle('on', t >= b.fly);
      L.still.querySelector('img').style.visibility = t >= b.landed ? 'visible' : 'hidden';

      /* the marker, tracking the object while the cap moves */
      const m = L.marker, on = t >= b.marker && t < b.retire + 0.7;
      const box = on ? boxAt(L.it.target) : null;
      show(m, !!box);
      if (box) {
        const k = ez.outCubic(span(t, b.marker, T.marker));
        const out = ez.inOutCubic(span(t, b.retire, 0.68));
        m.style.left = `${box.l * 100}%`; m.style.top = `${box.t * 100}%`;
        m.style.width = `${box.w * 100}%`; m.style.height = `${box.h * 100}%`;
        m.style.opacity = k * (1 - out);
        m.style.transform = `translateY(${(1 - k) * 14}px) scale(${lerp(0.92, 1, k)})`;
        [m.querySelector('.tag'), m.querySelector('.cap')].forEach((n, i) => {
          const q = ez.outCubic(span(t, b.marker + 0.14 + i * 0.08, T.marker * 0.72));
          n.style.opacity = q; n.style.transform = `translateY(${(1 - q) * 8}px)`;
        });
        const hp = span(t, b.marker + 0.64, 1.2);
        const hk = hp < 0.2 ? 0 : hp < 0.42 ? (hp - 0.2) / 0.22 : hp < 0.58 ? 1 : hp < 1 ? 1 - (hp - 0.58) / 0.42 : 0;
        const tag = m.querySelector('.tag');
        tag.style.background = `color-mix(in srgb, var(--paper) ${(hk * 100).toFixed(1)}%, var(--ink))`;
        tag.style.color = `color-mix(in srgb, var(--ink) ${(hk * 100).toFixed(1)}%, var(--paper))`;
      }

      /* the booking photo lifts off the frame and lands in the case file */
      const flying = t >= b.fly && t < b.landed && walkHud > 0;
      show(L.chip, flying);
      if (flying) {
        /* lift a 3:4 print off the object, the way the dashboard crops its booking photo */
        const sb = boxAt(L.it.target, b.fly) || { l: 0.45, t: 0.4, w: 0.1, h: 0.14 };
        const cx = (sb.l + sb.w / 2) * 1600, cy = (sb.t + sb.h / 2) * 900;
        const sh = Math.min(240, Math.max(96, sb.h * 900, sb.w * 1600 * 4 / 3));
        const start = { left: cx - sh * 3 / 8, top: cy - sh / 2, width: sh * 3 / 4, height: sh };
        const end = L.still.getBoundingClientRect();
        const p = span(t, b.fly, 0.98);
        const kx = ez.inOutCubic(p), mid = Math.min(start.top, end.top) - 28;
        const up = span(t, b.fly, 0.42), down = span(t, b.fly + 0.42, 0.56);
        const top = t < b.fly + 0.42 ? lerp(start.top, mid, ez.outCubic(up)) : lerp(mid, end.top, down * down * down);
        Object.assign(L.chip.style, {
          left: `${lerp(start.left, end.left, kx)}px`, top: `${top}px`,
          width: `${lerp(start.width, end.width, kx)}px`, height: `${lerp(start.height, end.height, kx)}px`,
          transform: `rotate(${lerp(2, -3, kx)}deg)`,
        });
      }
    });

    /* into the dashboard: the footage lands in the feed, the desk fades up round it */
    const inLive = t >= T.toDash && t < T.lineup;
    show(live, inLive);
    let sx = 0, sy = 0, sc = 1;
    if (inLive) {
      live.style.opacity = ez.film(span(t, T.toDash + 0.25, 0.75));
      liveOdo(odometer(odoEvents, t));
      liveCount.textContent = counted;
      const r = frameBox.getBoundingClientRect();
      sx = lerp(0, r.left, toDash); sy = lerp(0, r.top, toDash); sc = lerp(1, r.width / 1600, toDash);
      /* the freeze: the grabbed frame settles instead of kicking */
      const jp = span(t, T.freeze, T.judder);
      if (jp > 0 && jp < 1) {
        const keys = [[0, 1.6, -1], [0.38, -1, 0.7], [0.7, 0.35, -0.2], [1, 0, 0]];
        let a = keys[0], c = keys[keys.length - 1];
        for (let i = 0; i < keys.length - 1; i++) if (jp >= keys[i][0] && jp <= keys[i + 1][0]) { a = keys[i]; c = keys[i + 1]; break; }
        const q = ez.film((jp - a[0]) / (c[0] - a[0] || 1));
        sx += lerp(a[1], c[1], q); sy += lerp(a[2], c[2], q);
        feed.style.transform = `translate(${lerp(a[1], c[1], q)}px, ${lerp(a[2], c[2], q)}px)`;
      } else feed.style.transform = '';
    }
    show(shot, t >= T.fadeUp && t < T.lineup);
    shot.style.transform = `translate(${sx}px, ${sy}px) scale(${sc})`;
    /* CCTV stills in the dashboard: a bone wash on every new still */
    const wash = shot.querySelector('.wash');
    const base = T.toDash + T.toDashDur * 0.5;
    if (t > base && t < T.freeze) {
      const since = (t - base) % T.stillEvery;
      const w = since / 0.34;
      wash.style.opacity = w < 0.28 ? (w / 0.28) * 0.14 : w < 1 ? 0.14 * (1 - (w - 0.28) / 0.72) : 0;
    } else wash.style.opacity = 0;

    /* changeover cue, top right, as reel 1 ends */
    const cueIn = ez.film(span(t, T.cue, 0.36)), cueOut = ez.film(span(t, T.cue + T.cueDur, 0.36));
    cue.style.opacity = (0.9 * cueIn * (1 - cueOut)).toFixed(3);
    cue.style.transform = `scale(${lerp(0.9, 1, cueIn)})`;

    /* dissolve to black, then the lineup fades up */
    curtain.style.opacity = t < T.lineup ? ez.film(span(t, T.curtain, T.dissolve)) : 1 - ez.film(span(t, T.lineup, T.fadeup));

    /* reel 2 */
    const inReveal = t >= T.lineup && t < T.end + T.endFade;
    show(reveal, inReveal);
    reveal.classList.toggle('on', inReveal);
    if (inReveal) {
      const r = ez.settle(span(t, T.lineup, T.fadeup));
      titleEl.style.opacity = r; titleEl.style.transform = `translateY(${(1 - r) * 8}px)`;
      slots.forEach((S, k) => {
        const st = T.suspects + k * T.suspectStagger;
        S.s.classList.toggle('in', t >= st);
        S.s.style.opacity = ez.settle(span(t, st, T.drop));
        S.photo.style.transform = `translateY(${(1 - ez.outCubic(span(t, st, T.drop))) * -28}px)`;
        const pk = ez.settle(span(t, st + 0.12, T.drop * 0.8));
        S.placard.style.opacity = pk; S.placard.style.transform = `translateY(${(1 - pk) * 8}px)`;
        const nk = ez.outCubic(span(t, st + 0.16, T.drop * 0.85));
        for (const n of [S.name, S.price]) { n.style.opacity = nk; n.style.transform = `translateY(${(1 - nk) * 10}px)`; }
        const lin = span(t, st, T.count);
        S.price.innerHTML = `APPRAISED: $${Math.round(S.it.value * ez.smooth(lin)).toLocaleString()}${lin >= 1 && S.it.estimated ? EST : ''}`;
      });
      totalOdo(odometer([{ t: T.totalRoll, value: total }], t));
      const sp = span(t, T.stampAt, T.stamp);
      const scales = [1.16, 0.988, 1.018, 0.997, 1];
      const seg = Math.min(3, Math.floor(sp * 4)), local = ez.outCubic(sp * 4 - seg);
      stamp.style.opacity = t < T.stampAt ? 0 : ez.outCubic(sp);
      stamp.style.transform = `scale(${lerp(scales[seg], scales[seg + 1], sp >= 1 ? 1 : local)}) rotate(-6deg)`;
      const thud = T.stampAt + T.stamp * 0.42, hp = span(t, thud, T.shake);
      const shakeKeys = [[0, 0], [0.16, 2.4], [0.36, -1.5], [0.56, 0.8], [0.76, -0.3], [1, 0]];
      let y = 0;
      for (let i = 0; i < shakeKeys.length - 1; i++) if (hp > shakeKeys[i][0] && hp <= shakeKeys[i + 1][0]) {
        y = lerp(shakeKeys[i][1], shakeKeys[i + 1][1], (hp - shakeKeys[i][0]) / (shakeKeys[i + 1][0] - shakeKeys[i][0]));
      }
      wall.style.transform = hp > 0 && hp < 1 ? `translateY(${y}px)` : '';
    }

    /* THE END */
    const e = ez.film(span(t, T.end, T.endFade));
    show(theEnd, t >= T.end);
    theEnd.classList.toggle('on', t >= T.end);
    theEnd.style.opacity = e;
    void cam;
  }

  return { update, items };
}
