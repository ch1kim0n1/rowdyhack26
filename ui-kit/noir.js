/* ============================================================
   NOIRKIT runtime. Include after the markup (demo.html shows the full markup).

   Production:  Noir.connect('/state.json')   // that's the whole integration
   Demo:        drive the same functions with fake data (see demo.html)

   Every timing comes from the motion tokens in noir.css, so changing a
   duration there changes it here too. Missing elements are skipped, so
   any page can include this file (board.html uses only cutType).
   ============================================================ */
const Noir = (() => {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];

  /* motion token in ms: '600ms' -> 600, '12s' -> 12000 */
  const reduced = () => window.NoirMotion?.reduced() || matchMedia('(prefers-reduced-motion: reduce)').matches || document.body.classList.contains('motion-paused');
  const motion = window.NoirMotion?.create($('[data-motion-status]'));
  let connected = false, demoPending = false, demoRevealed = false, demoCamera = true;
  function demoMotion(){
    if(!connected) motion?.update({case_no:caseNo, items:found, pending:demoPending, revealed:demoRevealed, camera_ok:demoCamera});
  }
  const ms = name => {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v.endsWith('ms') ? parseFloat(v) : parseFloat(v) * 1000;
  };
  const money = v => '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  const EST = '<span class="est">est.</span>';

  /* every timer goes through later() so a view change cancels the whole take */
  const T = [];
  const later = (t, fn) => { const id = setTimeout(fn, t); T.push(id); return id; };
  const sleep = t => new Promise(r => later(t, r));
  const clearLater = () => {
    T.splice(0).forEach(clearTimeout);
    typists.forEach(job => job.finish());
    typists.clear();
  };

  let found = [], take = 0, caseNo = 1138;
  let plan = null, planRev = null, planNews = null;   /* Mastermind: the live plan from /state.json */

  /* ---------- sound (off by default; ?sound in the URL, or Noir.sfx.toggle()) ----------
     Synthesized, no files: typewriter keys, carriage return, stamp thud, projector cut. */
  const sfx = (() => {
    let ac = null, buf = null, projSrc = null;
    let gesture = false;                               // fallback for browsers without navigator.userActivation
    for(const type of ['pointerdown', 'keydown']) addEventListener(type, () => { gesture = true; }, {once: true, capture: true});
    // 'noir-muted' persists across reloads: 'false' means the operator turned sound on.
    let on = sessionStorage.getItem('noir-muted') === 'false';
    const files = {};                                  // /assets/sfx cache
    const file = (name, {vol = 1} = {}) => {           // one-shot real audio; false if missing
      const a = files[name] ??= new Audio('/assets/sfx/' + name);
      if(!a) return false;
      a.volume = vol; a.currentTime = 0;
      a.play().catch(() => { files[name] = null; });
      return true;
    };
    const noise = () => {
      if(buf) return buf;
      buf = ac.createBuffer(1, ac.sampleRate * .25, ac.sampleRate);
      const d = buf.getChannelData(0); for(let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      return buf;
    };
    const burst = (freq, q, dur, gain, type = 'bandpass') => {
      const t = ac.currentTime, src = ac.createBufferSource(), f = ac.createBiquadFilter(), g = ac.createGain();
      src.buffer = noise(); f.type = type; f.frequency.value = freq; f.Q.value = q;
      g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
      src.connect(f).connect(g).connect(ac.destination); src.start(t, Math.random() * .2); src.stop(t + dur);
    };
    const tone = (from, to, dur, gain) => {
      const t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain();
      o.frequency.setValueAtTime(from, t); o.frequency.exponentialRampToValueAtTime(to, t + dur);
      g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
      o.connect(g).connect(ac.destination); o.start(t); o.stop(t + dur);
    };
    return {
      get on(){ return on; },
      toggle(v = !on){
        on = v;
        if(on){
          try { ac ??= new (window.AudioContext || window.webkitAudioContext)(); ac.resume(); }
          catch { on = false; }
        }
        sessionStorage.setItem('noir-muted', String(!on));
        this.projector(on);
        const btn = $('#sound-toggle');
        if(btn){ btn.textContent = on ? 'Mute (M)' : 'Sound (M)'; btn.setAttribute('aria-pressed', String(on)); }
        return on;
      },
      key(){ if(on) burst(2600 + Math.random() * 900, 1.4, .025, .22); },
      ret(){ if(on && !file('typewriter-ding.wav', {vol: .25})) burst(700, .8, .09, .25, 'lowpass'); },
      thud(){ if(on){ file('stamp.ogg', {vol: .7}); tone(120, 42, .22, .7); burst(300, .7, .06, .5, 'lowpass'); } },
      cut(){ if(on) burst(5000, 2, .012, .05); },
      /* the gunshot plays by default once the page has had a click or key press (the
         browser allows audio from then on), unless the viewer explicitly muted the kit */
      shot(){
        const muted = sessionStorage.getItem('noir-muted') === 'true';
        const gestured = navigator.userActivation ? navigator.userActivation.hasBeenActive : gesture;
        if(!on && (muted || !gestured)) return;
        try { ac ??= new (window.AudioContext || window.webkitAudioContext)(); if(ac.state === 'suspended') ac.resume(); }
        catch { return; }
        burst(3000, .4, .04, 1); burst(900, .5, .12, .9); burst(260, .5, .45, .9, 'lowpass'); tone(150, 32, .3, .8);   // crack, report, body, thump
      },
      beep(){ if(on) tone(1000, 1000, .042, .18); },                  // the leader's beep on 3: one frame
      squelch(){ if(on){ file('radio-static.wav', {vol: .5}); burst(1400, .6, .07, .4); burst(2600, 2, .04, .25); } },   // radio key-up
      hum(run){                                                       // motor hum while a drive key is held
        if(!ac) return;
        if(!run){ this._hum?.stop(); this._hum = null; return; }
        if(this._hum) return;
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'sawtooth'; o.frequency.value = 68; g.gain.value = .03;
        o.connect(g).connect(ac.destination); o.start();
        this._hum = o;
      },
      /* the projector motor: real projector audio when the asset exists,
         else filtered noise chopped by a 24Hz shutter, very low */
      projector(run){
        if(!ac) return;
        if(!run){
          projSrc?.stop(); projSrc = null;
          if(files._proj){ files._proj.pause(); }
          return;
        }
        if(files._proj === undefined){
          files._proj = new Audio('/assets/sfx/projector.ogg');
          files._proj.loop = true; files._proj.volume = .12;
        }
        files._proj.play().catch(() => { files._proj = null; });
        if(files._proj) return;                     // real audio rolling; skip the synth
        if(projSrc) return;
        const src = ac.createBufferSource(), f = ac.createBiquadFilter(), g = ac.createGain(), lfo = ac.createOscillator(), depth = ac.createGain();
        src.buffer = noise(); src.loop = true; f.type = 'bandpass'; f.frequency.value = 900; f.Q.value = .9;
        g.gain.value = .018; lfo.type = 'square'; lfo.frequency.value = 24; depth.gain.value = .012;
        lfo.connect(depth).connect(g.gain);
        src.connect(f).connect(g).connect(ac.destination); src.start(); lfo.start();
        projSrc = src;
      },
      // the hardening pass's callers still say motor/radio/paper: same sounds.
      motor(run){ this.hum(run); },
      radio(){ this.squelch(); },
      paper(){ if(on) burst(1600, 1.2, .14, .18); },
    };
  })();

  /* ---------- odometer ---------- */
  function makeOdo(el){
    if(!el) return {set(){}};
    let previous = null;
    el.setAttribute('role', 'img');
    function set(value, estimated = false, instant = false){
      const amount = Math.max(0, Math.round(Number(value) || 0));
      const formatted = amount.toLocaleString('en-US');
      el.setAttribute('aria-label', '$' + formatted + (estimated ? ', estimated' : ''));
      if(previous === amount){
        const flag = el.querySelector('.est'); if(flag) flag.hidden = !estimated;
        return;
      }
      const old = String(previous ?? 0).padStart(String(amount).length, '0');
      const digits = document.createDocumentFragment();
      const currency = document.createElement('span'); currency.className = 'odo-cur'; currency.textContent = '$';
      digits.append(currency);
      let i = 0;
      for(const ch of formatted){
        const col = document.createElement('span');
        if(ch === ','){ col.className = 'odo-sep'; col.textContent = ','; }
        else {
          col.className = 'odo-digit';
          const strip = document.createElement('span'); strip.className = 'odo-strip';
          for(const n of [old[i] || '0', ch]){
            const digit = document.createElement('span'); digit.textContent = n; strip.append(digit);
          }
          strip.style.setProperty('--digit-delay', i * 24 + 'ms');
          if(!reduced() && !instant && previous !== null && old[i] !== ch) strip.classList.add('rolling');
          else strip.classList.add('settled');
          col.append(strip); i++;
        }
        digits.append(col);
      }
      const flag = document.createElement('span'); flag.className = 'est'; flag.textContent = 'est.'; flag.hidden = !estimated;
      digits.append(flag); el.replaceChildren(digits);
      el.style.setProperty('--odo-k', Math.min(1, 7 / (formatted.length + 1)));
      if(previous !== null && !instant && !reduced()){
        el.animate([{transform:'scale(1.04)'},{transform:'scale(1)'}], {duration:200});
        el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump');   /* the red underline flashes */
      }
      previous = amount;
    }
    set(0, false, true); return {set};
  }

  let odoLive, odoTotal;

  /* ---------- exhibit log (teletype) ---------- */
  const typists = new Set();
  let typingFrame = null, followLog = true, logScrollFrame = null;
  function scrollLog(){
    if(!followLog || logScrollFrame) return;
    logScrollFrame = requestAnimationFrame(() => {
      logScrollFrame = null; const log = $('#log'); if(log && followLog) log.scrollTop = log.scrollHeight;
    });
  }
  function logEmpty(){
    const log = $('#log'); if(!log) return;
    log.innerHTML = '<div class="log-line empty">&gt; SCENE STABLE. AWAITING TARGETS...</div>';
    followLog = true; $('#jump-live')?.setAttribute('hidden', '');
    $('#log-sr')?.replaceChildren();
  }
  function newLine(cls = ''){
    const log = $('#log'); if(!log) return null;
    log.querySelector('.empty')?.remove();
    log.lastElementChild?.classList.add('old');
    while(log.children.length >= 60){ log.firstElementChild._job?.finish(); log.firstElementChild.remove(); }
    const line = document.createElement('div'); line.className = 'log-line ' + cls;
    line.innerHTML = '<span class="txt"></span><span class="leaders"></span><span class="amt"></span>';
    log.append(line); scrollLog(); return line;
  }
  function typingTick(now){
    for(const job of typists){
      if(!job.line.isConnected){ job.finish(); continue; }
      const next = Math.min(job.text.length, Math.floor((now - job.start) / ms('--dur-type-char')) + 1);
      if(next !== job.index){ job.target.textContent = job.text.slice(0, next); job.index = next; }
      if(next === job.text.length) job.finish();
    }
    scrollLog(); typingFrame = typists.size ? requestAnimationFrame(typingTick) : null;
  }
  function typeInto(line, left, rightHTML, into){
    if(!line) return Promise.resolve();
    line._job?.finish();
    return new Promise(done => {
      const job = {line, text:left, target:into || line.querySelector('.txt'), index:0, start:performance.now(), finish(){
        job.target.textContent = left; line.querySelector('.amt').innerHTML = rightHTML;
        line.classList.remove('typing'); typists.delete(job); line._job = null; done();
      }};
      line._job = job; line.classList.add('typing');
      if(reduced()){ job.finish(); return; }
      typists.add(job); if(!typingFrame) typingFrame = requestAnimationFrame(typingTick);
    });
  }
  const wireLine = text => typeInto(newLine(text.includes('REVEAL') ? 'reveal-line' : 'wire'), text, '');
  function announceExhibit(it){
    const log = $('#log-sr'); if(!log) return;
    const entry = document.createElement('div');
    entry.textContent = `Exhibit ${it.n}: ${it.item}, ${money(it.value_usd)}${it.estimated ? ', estimated' : ''}.`;
    while(log.children.length >= 60) log.firstElementChild.remove(); log.append(entry);
  }
  $('#log')?.addEventListener('scroll', () => {
    const log = $('#log'); followLog = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
    $('#jump-live')?.toggleAttribute('hidden', followLog);
  });
  $('#jump-live')?.addEventListener('click', () => { followLog = true; scrollLog(); $('#jump-live').hidden = true; });

  /* ---------- evidence markers ---------- */
  const useAnime = () => window.anime && !reduced();
  const markerNodes = new Map();
  let markerFrame = null;
  function updateMarkers(items){
    const box = $('#markers'); if(!box) return;
    const ids = new Set(items.filter(it => it.bbox).map(it => it.n));
    for(const [id, node] of markerNodes) if(!ids.has(id)){ node.remove(); markerNodes.delete(id); }
    for(const it of items){
      if(!it.bbox) continue;
      let node = markerNodes.get(it.n);
      if(!node){
        node = document.createElement('div'); node.className = 'evidence-marker'; node.dataset.n = it.n;
        node.style.setProperty('--tilt', ((it.n % 5 - 2) * .75) + 'deg');
        node.innerHTML = '<svg class="evidence-outline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect x="0" y="0" width="100" height="100" vector-effect="non-scaling-stroke"/><path class="eo-corners" d="M0 18V0H18M82 0H100V18M100 82V100H82M18 100H0V82" vector-effect="non-scaling-stroke"/></svg><span class="tag"></span><span class="cap"></span>';
        box.append(node); markerNodes.set(it.n, node);
      }
      node._bbox = it.bbox;
      node.querySelector('.tag').textContent = `EXHIBIT ${pad(it.n)}`;
      node.querySelector('.cap').textContent = `${it.item} · ${money(it.value_usd)}${it.estimated ? ' est.' : ''}`;
    }
    if(!markerFrame) markerFrame = requestAnimationFrame(() => {
      markerFrame = null;
      // Unit-sized outlines use transforms for all bbox geometry. Labels scale independently.
      for(const node of markerNodes.values()){
        const {l,t,w,h} = node._bbox;
        node.style.transform = `translate(${l}cqw, ${t}cqh)`;
        // Size the box itself, not a scale() on the svg: non-scaling-stroke ignores CSS
        // transforms, so a scaled outline drew strokes tens of pixels thick.
        node.style.width = `${w}cqw`; node.style.height = `${h}cqh`;
        node.querySelector('.cap').style.transform = `translateY(${h}cqh)`;
      }
    });
  }
  function addMarker(it){
    updateMarkers([...found.filter(x => x.n !== it.n), it]);
    return markerNodes.get(it.n);
  }

  /* booking-photo crop from the current still (production passes /crop/<n>.jpg instead) */
  function cropFrom(src, b){
    const W = src?.naturalWidth || src?.width, H = src?.naturalHeight || src?.height;
    if(!W || !b || src.hidden) return null;
    let sx = b.l/100*W, sy = b.t/100*H, sw = b.w/100*W, sh = b.h/100*H;
    if(sw/sh > 3/4){ const nh = sw*4/3; sy -= (nh-sh)/2; sh = nh; }   // widen the box to 3:4
    else           { const nw = sh*3/4; sx -= (nw-sw)/2; sw = nw; }
    const c = Object.assign(document.createElement('canvas'), {width: 300, height: 400});
    c.getContext('2d').drawImage(src, sx, sy, sw, sh, 0, 0, 300, 400);
    return c.toDataURL('image/jpeg', .85);
  }

  /* ---------- the scan beat: examining, typed, marked, counted ---------- */
  function pending(n){
    demoPending = true; demoMotion();
    exitIdle(); const line = newLine('pending');
    typeInto(line, `> SCENE MOVE. EXAMINING EXHIBIT ${pad(n)}...`, ''); return line;
  }
  function claimLine(line){
    line ??= $('.log-line.pending') || newLine('filed');
    line._job?.finish(); line.classList.remove('pending', 'typing'); line.classList.add('filed');
    line.querySelector('.txt').textContent = ''; return line;
  }
  function voidExhibit(line){
    demoPending = false; demoMotion();
    line = claimLine(line); line.classList.add('void');
    return typeInto(line, 'EXHIBIT ??: UNIDENTIFIED', 'NO APPRAISAL');
  }
  function showExhibit(it, line){
    demoPending = false;
    exitIdle(); line = claimLine(line); line.dataset.n = it.n;   /* the plan marks BAG / LEAVE by number */
    found.push(it); announceExhibit(it);
    it.crop ??= cropFrom($('#frame'), it.bbox);
    if(it.crop){
      const slot = document.createElement('span'); slot.className = 'file-still on';
      const img = new Image(); img.alt = `Exhibit ${pad(it.n)}: ${it.item}`; authedImg(img, it.crop);
      slot.append(img); line.prepend(slot);
    }
    const txt = line.querySelector('.txt');
    txt.innerHTML = `<span class="ex-k">${pad(it.n)}</span><span class="ex-name"></span>`;
    addMarker(it); sfx.paper();
    take = found.reduce((sum, item) => sum + item.value_usd, 0);
    odoLive.set(take, found.some(item => item.estimated));
    $('#count') && ($('#count').textContent = found.length);
    demoMotion();
    return typeInto(line, it.item, '$' + Math.round(it.value_usd).toLocaleString('en-US') + (it.estimated ? EST : ''), txt.querySelector('.ex-name'));
  }



  /* ---------- feed states ---------- */
  function cutFeed(){
    const f = $('#feed'); if(!f) return;
    f.classList.remove('cutting'); void f.offsetWidth; f.classList.add('cutting'); sfx.cut();
  }
  const SLATES = {
    lost: ['LINE DEAD', 'camera lost · reconnecting...'],
    dead: ['LINE DEAD', 'hub unreachable · redialing...'],
  };
  const SLATE_COUNT = ['8', '7', '6', '5', '4', '3', '2', '1', '0'];
  let slateTimer = null;
  function stopSlateCount(){
    clearInterval(slateTimer);
    slateTimer = null;
  }
  function runSlateCount(){
    const lead = $('#feed .slate .leader');
    if(!lead) return;
    stopSlateCount();
    let i = 0;
    paintLeader(lead, SLATE_COUNT[0]);
    slateTimer = setInterval(() => {
      if(!$('#feed')?.classList.contains('lost')){ stopSlateCount(); return; }
      i += 1;
      if(i >= SLATE_COUNT.length){ stopSlateCount(); return; }   // hold on 0; do not wrap back to 8
      paintLeader(lead, SLATE_COUNT[i]);
    }, ms('--dur-leader-foot'));
  }
  function setFeed(state){                  // 'ok' | 'lost' (camera) | 'dead' (rig)
    demoCamera = state === 'ok'; demoMotion();
    const f = $('#feed'); if(!f) return;
    const wasLost = f.classList.contains('lost');
    const lost = state !== 'ok';
    if(lost && !wasLost){                     // one frame of static, one tracking wobble, then the slate
      f.classList.add('burst');
      setTimeout(() => f.classList.remove('burst'), 320);
    }
    f.classList.toggle('lost', lost);
    if(SLATES[state]){ f.querySelector('.slate-title').textContent = SLATES[state][0]; f.querySelector('.slate-meta').textContent = SLATES[state][1]; }
    if(!lost){
      stopSlateCount();
      if(wasLost){                          // a restored feed gets its own beat
        f.querySelector('.slate-title').textContent = 'SIGNAL RESTORED';
        f.querySelector('.slate-meta').textContent = 'back on the wire';
        if(!reduced()){ f.classList.add('restoring'); setTimeout(() => f.classList.remove('restoring'), 300); }
      }
    }
    else if(!wasLost) runSlateCount();      // start once, when the slate appears, not on every poll
  }
  let offline = false;
  function setOffline(value){
    if(value === offline) return;
    offline = value; document.body.classList.toggle('offline', value);
    if(value){ bootSkip?.(); exitIdle(); setFeed('dead'); }
    else setFeed('ok');
    motion?.setConnection(value ? 'offline' : 'online');
    if($('#log')) wireLine(value ? '> LINE TO THE RIG IS DEAD. REDIALING...' : '> SIGNAL RESTORED.');
  }

  /* ---------- Academy leader: 8, 7, SIX, 5, 4, 3, one number per foot of film ----------
     Boot (reelStart) still runs that sequence once. A dead line counts 8 down to 0 and holds. */
  const LEADER = ['8', '7', 'SIX', '5', '4', '3'];
  function paintLeader(el, label){
    let n = el.querySelector('.leader-n');
    if(!n){ n = document.createElement('span'); n.className = 'leader-n'; el.append(n); }
    n.textContent = label;
    n.classList.toggle('word', String(label).length > 1);
    if(useAnime()){
      window.anime.remove(n);
      window.anime({
        targets: n,
        opacity: [0, 1],
        scale: [0.9, 1],
        duration: Math.round(ms('--dur-leader-foot') * .55),
        easing: 'easeOutCubic',
      });
    } else {
      n.classList.remove('tick'); void n.offsetWidth; n.classList.add('tick');
    }
  }
  function leaderFrame(el, i){
    paintLeader(el, LEADER[i % LEADER.length]);
  }

  const overlay = (cls, html) => {
    let el = $('.' + cls);
    if(!el){ el = document.createElement('div'); el.className = cls; el.setAttribute('aria-hidden', 'true'); el.innerHTML = html; document.body.append(el); }
    return el;
  };

  /* reel start: PICTURE START, then the countdown, then two black frames. Page boot only. */
  let bootSkip = null, bootAt = 0, bootPending = null;
  const BOOT_HOLD = 1500;   /* the title card holds at least this long before the rig cuts it; a key or click still skips */
  function reelStart(){
    if(reduced()){ document.body.classList.remove('idle'); return Promise.resolve(); }
    return new Promise(done => {
      document.body.classList.add('cold-open');
      bootAt = performance.now();
      let timer;
      const finish = () => {
        clearTimeout(timer); bootSkip = null;
        document.body.classList.remove('cold-open', 'idle');
        removeEventListener('keydown', skip, true); removeEventListener('pointerdown', skip, true);
        done();
        const next = bootPending; bootPending = null; next?.();   /* a reveal that waited for the card */
      };
      const skip = e => { e.preventDefault(); e.stopImmediatePropagation(); finish(); };
      bootSkip = finish;
      addEventListener('keydown', skip, true); addEventListener('pointerdown', skip, true);
      timer = setTimeout(finish, 4000);
      later(700, () => { if(bootSkip) sfx.thud(); });
    });
  }

  /* changeover cue: the white circle a projectionist watches for, 4 frames, as reel 1 ends */
  function cue(){
    if(reduced()) return;
    const el = overlay('cue', '');
    el.classList.add('on'); setTimeout(() => el.classList.remove('on'), ms('--dur-cue'));
  }

  /* THE END, when a run finishes. Fades out only after the caller has
     put the next picture underneath, so the dissolve doesn't uncover a cut. */
  function mountEnd(){
    const el = overlay('the-end', '<div class="meta">A RowdyHacks XII Picture</div><div class="end-title cut">The End</div><div class="meta end-case"></div>');
    const title = el.querySelector('.end-title'); if(!title.querySelector('.ch')) cutType(title);
    el.querySelector('.end-case').textContent = `Case No. ${caseNo} · Closed`;
    return el;
  }
  async function theEnd(){
    const el = mountEnd();
    el.classList.add('on');
    await sleep(ms('--dur-fade') + ms('--dur-the-end'));
    el.classList.remove('on');
    await sleep(ms('--dur-fade'));
  }

  /* ---------- ticker tape: the evidence feed in the footer ---------- */
  function tickTape(items){
    const belt = $('.ticker .belt'); if(!belt) return;
    belt.textContent = '';
    if(!items.length){ belt.innerHTML = '<span>AWAITING TARGETS · SCENE STABLE ·</span>'; return; }
    const sorted = [...items].sort((a, b) => b.value_usd - a.value_usd);
    for(const it of sorted.slice(0, 8)){
      const s = document.createElement('span');
      s.textContent = `EXHIBIT ${pad(it.n)} · ${it.item} · $${(Number(it.value_usd) || 0).toLocaleString()}${it.estimated ? ' EST.' : ''} ·`;
      belt.appendChild(s);
    }
  }

  /* ---------- iris wipe between views ---------- */
  function iris(){
    if(reduced()) return Promise.resolve();
    const el = overlay('iris', '');
    el.classList.remove('on'); void el.offsetWidth; el.classList.add('on');
    sfx.cut();
    return sleep(700);
  }

  /* ---------- attract mode ---------- */
  let idleTimer = null;
  function exitIdle(){ document.body.classList.remove('idle'); clearTimeout(idleTimer); }
  function enterIdle(){
    document.body.classList.remove('idle');
    void document.body.offsetWidth;          /* replay the title from the first frame */
    document.body.classList.add('idle');
  }
  function armIdle(t = ms('--idle-after')){
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if($('#v-live')?.classList.contains('on')) enterIdle(); }, t);
  }
  const credits = ['Case No. 1138', 'Starring whatever\'s on the shelves',
                   'Prices from the camera', 'Filmed in Room 3, Exhibits Wing'];

  /* ---------- a new run: next case number, clean ledger ---------- */
  function setCase(n){
    caseNo = n; credits[0] = `CASE NO. ${pad(n, 4)}`;
    $('#tc-credit') && ($('#tc-credit').textContent = credits[0]);
    $$('.case-no').forEach(e => e.textContent = pad(n, 4));
  }
  async function newCase({idle = false} = {}){
    demoPending = false; demoRevealed = false;
    cancelReveal(); clearLater();
    exitIdle();
    const afterReveal = $('#v-reveal')?.classList.contains('on');
    const closed = caseNo;
    found = []; take = 0;
    odoLive.set(0); $('#count') && ($('#count').textContent = 0);
    updateMarkers([]); logEmpty();
    if(afterReveal) setCase(caseNo + 1);
    if(afterReveal) await rollTo('v-live', {endTitle: true, closed});
    else show('v-live');
    if(idle) enterIdle();
    demoMotion();
  }

  /* ---------- view switching ---------- */
  function show(id){
    $$('.view').forEach(v => v.classList.toggle('on', v.id === id));
  }

  /* The outgoing picture, a soft black tail, and the next picture are one strip.
     Sprocket holes ride the same roll. endTitle holds THE END in the black, then the tape continues. */
  let rollChain = Promise.resolve();
  function rollTo(id, opts){
    const job = rollChain.then(() => rollNow(id, opts || {}));
    rollChain = job.catch(() => {});
    return job;
  }
  function mountTape(){
    let el = $('#tape');
    if(!el){
      el = document.createElement('div');
      el.id = 'tape';
      el.className = 'tape';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<div class="tape-strip"></div>';
      document.body.appendChild(el);
    }
    return el;
  }
  function pin(node){
    const marker = document.createComment('');
    node.parentNode.insertBefore(marker, node);
    return marker;
  }
  function unpin(node, marker){
    if(marker.parentNode) marker.parentNode.insertBefore(node, marker);
    marker.remove();
  }
  function rollNow(id, opts){
    const next = document.getElementById(id);
    const current = $('.view.on');
    if(!next || !current || current.id === id || !useAnime()){
      show(id);
      return Promise.resolve();
    }
    const gate = mountTape();
    const strip = gate.querySelector('.tape-strip');
    const markCurrent = pin(current);
    const markNext = pin(next);
    const black = document.createElement('div');
    black.className = 'tape-black';
    const legend = document.createElement('div');
    legend.className = 'tape-legend';
    if(opts.endTitle){
      legend.innerHTML = `<div class="meta">A RowdyHacks XII Picture</div><div class="end-title">The End</div><div class="meta">Case No. ${opts.closed || caseNo} · Closed</div>`;
    }
    black.appendChild(legend);
    const holes = (side) => { const el = document.createElement('div'); el.className = 'tape-perfs ' + side; return el; };
    strip.replaceChildren(holes('l'), holes('r'), current, black, next);
    current.classList.add('on');
    next.classList.add('on');
    gate.classList.add('on');
    const H = gate.clientHeight || window.innerHeight;
    const overlap = Math.round(H * 0.18);
    black.style.height = Math.round(H * (opts.endTitle ? 0.86 : 0.48)) + 'px';
    black.style.marginTop = -overlap + 'px';
    black.style.marginBottom = -overlap + 'px';
    const toNext = next.offsetTop;
    const toBlack = Math.max(0, black.offsetTop + black.offsetHeight / 2 - H / 2);
    strip.style.transform = 'translateY(0px)';
    const finish = () => {
      unpin(current, markCurrent);
      unpin(next, markNext);
      show(id);
      strip.replaceChildren();
      strip.style.transform = '';
      gate.classList.remove('on');
    };
    if(toNext < 8){ finish(); return Promise.resolve(); }
    return new Promise(done => {
      const tl = window.anime.timeline({ easing: 'easeInOutCubic', complete(){ finish(); done(); } });
      if(opts.endTitle){
        tl.add({ targets: strip, translateY: -toBlack, duration: 860, easing: 'easeInOutCubic' });
        tl.add({ targets: legend, opacity: [0, 1], duration: 380, easing: 'easeOutCubic' }, '-=160');
        tl.add({ targets: legend, opacity: 1, duration: 1100 });
        tl.add({ targets: legend, opacity: [1, 0], duration: 280, easing: 'easeInCubic' });
        tl.add({ targets: strip, translateY: -toNext, duration: 920, easing: 'easeInOutCubic' }, '-=60');
      } else {
        tl.add({
          targets: strip,
          translateY: [0, -toNext],
          duration: ms('--dur-tape'),
          easing: 'easeInOutCubic',
        });
      }
    });
  }

  /* ---------- reveal choreography (spec §7), handles 0 to 5 suspects ---------- */
  let revealFinish = null, revealTimers = [];
  function cancelReveal(){
    revealTimers.splice(0).forEach(clearTimeout); revealFinish = null;
    $('.the-end')?.classList.remove('on'); document.body.classList.remove('revealing');
  }
  function skipReveal(){ if(!revealFinish) return false; revealFinish(); return true; }
  function runReveal(items){
    const held = bootSkip ? BOOT_HOLD - (performance.now() - bootAt) : 0;
    if(held > 0){                         // a case already in the lineup waits for the title card
      bootPending = () => runReveal(items);
      later(held, () => bootSkip?.());
      return;
    }
    demoPending = false; demoRevealed = true;
    if(!connected){ found = items; demoMotion(); }
    cancelReveal(); clearLater(); bootSkip?.(); exitIdle();
    const top = [...items].sort((a,b) => b.value_usd - a.value_usd).slice(0,5);
    const total = items.reduce((sum,it) => sum + it.value_usd, 0);
    const estimated = items.some(it => it.estimated);
    const schedule = (delay, fn) => revealTimers.push(setTimeout(fn, delay));
    const slots = $$('.suspect'), stamp = $('#stamp-closed');
    if(!stamp) return;
    wireLine('> REVEAL. THE CASE IS FILED.');
    $('#reveal-title').textContent = top.length ? 'The Usual Suspects' : 'No Suspects';
    cutType($('#reveal-title'));
    $('#reveal-sub').textContent = 'FLED · CASE NO. ' + pad(caseNo, 4);
    stamp.textContent = 'FILED'; stamp.style.opacity = 0; stamp.classList.remove('enter');
    const copy = $('#v-reveal .file-copy'); if(copy){ copy.classList.remove('ready'); copy.inert = true; }
    slots.forEach((slot,i) => {
      const it = top[i]; slot.classList.remove('in'); slot.classList.toggle('vacant', !it);
      slot.style.setProperty('--photo-tilt', (i % 2 ? 1.5 : -1.5) + 'deg');
      const photo = slot.querySelector('.photo'); photo.querySelector('img')?.remove();
      slot.querySelector('.placard').textContent = it ? `EXHIBIT ${pad(it.n)}` : 'NO EXHIBIT';
      const badge = !!it && it.category === 'badge';
      slot.classList.toggle('cloned', badge);
      slot.querySelector('.name').textContent = it?.item || '';
      slot.querySelector('.price').textContent = it
        ? (badge ? 'CLONED' : 'APPRAISED') + ': ' + money(it.value_usd) + (it.estimated ? ' est.' : '')
        : 'VACANT';
      const whyEl = slot.querySelector('.why');
      if(whyEl) whyEl.textContent = badge && it.card ? cardLine(it.card) : (it?.why ? 'WHY · ' + it.why : '');
      if(it?.crop){ const img = new Image(); img.alt = `Exhibit ${pad(it.n)}: ${it.item}`; authedImg(img, it.crop); photo.prepend(img); }
      if(plan) photo.dataset.plan = plan.selected.includes(it.n) ? 'Bagged' : 'Left';   /* Mastermind verdict */
    });
    buildManifest(items); odoTotal.set(0, estimated, true);
    const planTake = $('#plan-take');
    if(planTake){
      planTake.hidden = !plan;
      if(plan) planTake.textContent = `In the bag ${money(plan.totals.value_usd)} · ${lb(plan.totals.weight_lb)}/${lb(plan.constraints.bag_lb)} lb · ${plan.totals.grab_seconds}/${plan.constraints.time_s}s`;
    }
    const finish = (instant = false) => {
      revealTimers.splice(0).forEach(clearTimeout); revealFinish = null;
      document.body.classList.remove('revealing'); $('.the-end')?.classList.remove('on');
      show('v-reveal'); slots.forEach(slot => slot.classList.add('in'));
      odoTotal.set(total, estimated, instant || reduced());
      stamp.style.opacity = 1; if(!reduced() && !instant) stamp.classList.add('enter');
      if(copy){ copy.classList.add('ready'); copy.inert = false; }
      $('#reveal-sr') && ($('#reveal-sr').textContent = `Filed. ${top.length} exhibits. Total take ${money(total)}.`);
      sfx.thud();
    };
    revealFinish = () => finish(true);
    if(reduced()){ finish(true); return; }
    document.body.classList.add('revealing');
    schedule(300, () => show('v-reveal'));
    slots.forEach((slot,i) => schedule(420 + i * 120, () => slot.classList.add('in')));
    schedule(1350, () => odoTotal.set(total, estimated));
    schedule(1900, () => { stamp.style.opacity = 1; stamp.classList.add('enter'); sfx.thud(); });
    schedule(2550, () => { if(copy){ copy.classList.add('ready'); copy.inert = false; } });
    schedule(3400, () => mountEnd().classList.add('on'));
    schedule(4800, () => { $('.the-end')?.classList.remove('on'); });
    schedule(5500, () => { revealFinish = null; document.body.classList.remove('revealing'); });
  }

  /* badge text off the card, cardholder first: "TEMOC COMET · ID# 2020000001 · STUDENT" */
  function cardLine(card){
    return [card.name, card.id && `ID# ${card.id}`, card.role || card.org].filter(Boolean).join(' · ');
  }

  /* ---------- Mastermind: the plan panel, BAG / LEAVE marks, revision news ---------- */
  const lb = v => (Math.round(Number(v) * 10) / 10).toLocaleString('en-US');
  const clock = secs => secs % 60 === 0 && secs >= 60 ? `${secs / 60} min` : `${secs}s`;
  const jobLine = p => `Mastermind · ${lb(p.settings.bag_lb)} lb · ${clock(p.settings.time_s)} · ${p.level.label}`;
  function gauge(sel, used, cap, text){
    const g = $(sel); if(!g) return;
    const pct = cap > 0 ? Math.min(100, used / cap * 100) : 0;
    g.querySelector('.g-bar i').style.width = pct + '%';
    g.classList.toggle('full', pct >= 99.5);
    g.querySelector('.g-txt').textContent = text;
  }
  function markLog(p){
    $$('.log-line[data-n]').forEach(line => {
      const n = Number(line.dataset.n), k = line.querySelector('.ex-k');
      if(!k) return;
      const left = p && p.left.find(l => l.n === n);
      const mark = !p ? '' : (p.collected || []).includes(n) ? 'Collected'
        : p.selected.includes(n) ? 'Bag' : left ? `Leave · ${left.short}` : '';
      if((k.dataset.mark || '') === mark) return;
      if(mark) k.dataset.mark = mark; else delete k.dataset.mark;
      line.classList.toggle('bag', mark === 'Bag' || mark === 'Collected');
      line.classList.toggle('leave', mark.startsWith('Leave'));
      line.title = left ? left.text : '';
    });
  }
  function applyJob(s){
    const p = s.mode === 'mastermind' && s.plan ? s.plan : null;
    document.body.classList.toggle('mode-mastermind', !!p);
    const chip = $('#mode-chip');
    if(chip){ const t = p ? jobLine(p) : 'Appraisal'; if(chip.textContent !== t) chip.textContent = t; }
    const panel = $('#plan-panel'); if(panel) panel.hidden = !p;
    plan = p;
    if(!p){ planRev = null; markLog(null); return; }
    $('#plan-level').textContent = p.level.label;
    $('#plan-value').textContent = money(p.totals.value_usd);
    gauge('#g-weight', p.totals.weight_lb, p.constraints.bag_lb, `${lb(p.totals.weight_lb)} / ${lb(p.constraints.bag_lb)} lb`);
    gauge('#g-time', p.totals.grab_seconds, p.constraints.time_s, `${p.totals.grab_seconds} / ${p.constraints.time_s} s`);
    $('#plan-next').textContent = p.next ? `Next: ${p.next.item}` : (s.items.length ? 'Nothing fits this job.' : 'Waiting on the first find.');
    markLog(p);
    const c = p.change;
    if(planRev !== null && p.revision !== planRev && c && !s.revealed){
      const sign = c.delta_usd >= 0 ? '+' : '−', amt = `${sign}${money(Math.abs(c.delta_usd))}`;
      if(c.settings_changed) planNews = `> NEW PLAN · ${jobLine(p).toUpperCase()} · ${money(p.totals.value_usd)} IN THE BAG`;
      else if(c.dropped.length)                         /* a plain addition shows as its BAG mark */
        planNews = `> PLAN REVISED ${amt}${c.added.length ? ' · IN: ' + c.added.map(a => a.item).join(', ') : ''} · OUT: ${c.dropped.map(d => d.item).join(', ')}`;
    }
    planRev = p.revision;
  }

  /* the job sheet: Appraisal (no plan) or Mastermind (bag, clock, job size) */
  function jobSheet(){
    const dlg = $('#job-sheet'), form = $('#job-form'), err = $('#job-err');
    if(!dlg || !form) return;
    const presets = () => $$('#job-form [data-set]').forEach(b =>
      b.setAttribute('aria-pressed', String(Number(form.elements[b.dataset.set].value) === Number(b.dataset.val))));
    const fail = msg => { err.textContent = msg; err.hidden = false; };
    const open = (msg) => {
      if(plan){
        form.elements.bag_lb.value = plan.settings.bag_lb;
        form.elements.time_s.value = plan.settings.time_s;
        form.querySelector(`[name=level][value="${plan.settings.level}"]`).checked = true;
      }
      err.hidden = true; presets();
      if(!dlg.open) dlg.showModal();
      if(msg) fail(msg);
    };
    const send = async body => {
      const r = await authFetch('/api/plan', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      if(r && r.ok){ if(dlg.open) dlg.close(); exitIdle(); armIdle(); return true; }
      let msg = 'The rig did not answer. Try again.';
      try { msg = (await r.json()).error || msg; } catch {}
      open(msg);
      return false;
    };
    form.addEventListener('submit', e => {
      e.preventDefault();
      const bag = Number(form.elements.bag_lb.value), secs = Number(form.elements.time_s.value);
      if(!(bag >= 1 && bag <= 200)) return fail('The bag holds 1 to 200 lb.');
      if(!(secs >= 10 && secs <= 1800)) return fail('The clock runs from 10 seconds to 30 minutes.');
      send({mode: 'mastermind', bag_lb: bag, time_s: Math.round(secs), level: form.elements.level.value});
    });
    form.addEventListener('input', presets);
    $$('#job-form [data-set]').forEach(b => b.addEventListener('click', () => {
      form.elements[b.dataset.set].value = b.dataset.val; presets();
    }));
    $$('[data-job="appraisal"]').forEach(b => b.addEventListener('click', () => send({mode: 'appraisal'})));
    $$('[data-job="mastermind"]').forEach(b => b.addEventListener('click', () => open()));
    $('#mode-chip')?.addEventListener('click', () => open());
    $$('#job-form [data-close]').forEach(b => b.addEventListener('click', () => dlg.close()));
    addEventListener('keydown', e => {          /* P: plan the job; M stays the sound toggle */
      if(e.key.toLowerCase() !== 'p' || e.repeat || dlg.open) return;
      if(e.target.matches('input,textarea,select')) return;
      if(!$('#v-live')?.classList.contains('on')) return;
      open();
    });
  }

  /* ---------- manifest ---------- */
  function buildManifest(items){
    const rows = $('#doc-rows'); if(!rows) return;
    rows.innerHTML = '';
    const sorted = [...items].sort((a, b) => b.value_usd - a.value_usd);
    if(!sorted.length) rows.innerHTML = '<div class="row"><span>NO EXHIBITS RECOVERED</span></div>';
    sorted.forEach(it => {
      const r = document.createElement('div'); r.className = 'row';
      const name = document.createElement('span'); name.textContent = `"${it.item}"`;
      if(it.category === 'badge'){
        const tag = document.createElement('span'); tag.className = 'est'; tag.textContent = 'cloned';
        name.append(' ', tag);
      }
      if(plan){
        const tag = document.createElement('span'); tag.className = 'est plan-mark' + (plan.selected.includes(it.n) ? ' bag' : '');
        tag.textContent = plan.selected.includes(it.n) ? 'in the bag' : 'left';
        name.append(' ', tag);
      }
      const leaders = document.createElement('span'); leaders.className = 'leaders';
      const amt = document.createElement('span'); amt.className = 'amt';
      amt.textContent = money(Number(it.value_usd) || 0);
      if(it.estimated){ const flag = document.createElement('span'); flag.className = 'est'; flag.textContent = 'est.'; amt.append(' ', flag); }
      r.append(name, leaders, amt);
      rows.appendChild(r);
      if(it.why){
        const w = document.createElement('div'); w.className = 'why';
        w.textContent = it.why;
        rows.appendChild(w);
      }
    });
    $('#doc-total').textContent = money(items.reduce((a, b) => a + b.value_usd, 0));
    const d = new Date();
    $('#filed') && ($('#filed').textContent = `Filed ${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()}`);
  }

  /* ---------- cut-paper lettering for .cut titles (spec §3) ---------- */
  function cutType(el){
    const jit = (i, k) => { const x = Math.sin((i + 1) * 12.9898 + k * 78.233) * 43758.5453; return x - Math.floor(x) - .5; };
    const text = el.textContent;
    let i = 0;
    const walk = node => [...node.childNodes].forEach(n => {
      if(n.nodeType === 3){
        const frag = document.createDocumentFragment();
        for(const part of n.textContent.split(/(\s+)/)){
          if(!part.trim()){ frag.append(part); continue; }
          const w = document.createElement('span'); w.className = 'w';      // words never break mid-letter
          w.setAttribute('aria-hidden', 'true');
          for(const ch of part){
            const s = document.createElement('span'); s.className = 'ch'; s.textContent = ch;
            s.style.setProperty('--r', (jit(i, 1) * 5).toFixed(2) + 'deg');   // -2.5..2.5deg
            s.style.setProperty('--y', (jit(i, 2) * .07).toFixed(3) + 'em');  // baseline wobble
            w.append(s); i++;
          }
          frag.append(w);
        }
        n.replaceWith(frag);
      } else walk(n);
    });
    walk(el);
    el.setAttribute('aria-label', text.replace(/\s+/g, ' ').trim());
  }

  /* ---------- film texture: gate hair and dust ---------- */
  function scheduleScratch(){
    setTimeout(() => {
      const sc = $('#scratch');
      sc.style.left = (8 + Math.random() * 84) + '%';
      sc.classList.add('on');
      for(let i = 0; i < 2; i++){
        const d = document.createElement('div'); d.className = 'dust';
        d.style.left = (10 + Math.random() * 80) + '%'; d.style.top = (5 + Math.random() * 35) + '%';
        document.body.appendChild(d); setTimeout(() => d.remove(), 540);
      }
      setTimeout(() => sc.classList.remove('on'), 700);
      scheduleScratch();
    }, 6000 + Math.random() * 6000);
  }

  /* ---------- production: poll the rig (BUILD-GUIDE §4.2 contract) ---------- */
  function connect(url = '/state.json', {every = 80, frameUrl = '/frame.jpg', cropUrl = n => `/crop/${n}.jpg`} = {}){
    connected = true;
    let seen = new Set(), frameId = null, revealed = false, loading = false, activeCase = null;
    let lastHealthy = performance.now(), stopped = false, timer, requestController;
    const img = $('#frame');
    const normalize = it => {
      const [x,y,w,h] = it.bbox || [];
      return {...it, crop:cropUrl(it.n), bbox:it.bbox ? {l:x*100,t:y*100,w:w*100,h:h*100} : null};
    };
    // A separate wall-clock watchdog also catches a request that never answers.
    const watchdog = setInterval(() => { if(performance.now() - lastHealthy > 2000) setOffline(true); }, 100);
    async function tick(){
      if(stopped) return;
      let state;
      requestController = new AbortController();
      const timeout = setTimeout(() => requestController.abort(), 2200);
      try {
        const response = await fetch(url, {cache:'no-store', signal:requestController.signal, headers: tokenHdrs()});
        if(response.status === 401){ _authd = true; ensureToken(); }
        if(response.ok){ const body = await response.json(); if(Array.isArray(body.items)) state = body; }
      } catch {} finally { clearTimeout(timeout); }
      if(stopped) return;
      if(state){
        motion?.update(state);
        lastHealthy = performance.now(); setOffline(false);
        const changed = activeCase !== state.case_no;
        if(changed){
          cancelReveal(); clearLater(); seen = new Set(); found = []; take = 0; revealed = false;
          updateMarkers([]); logEmpty(); odoLive.set(0, false, true); $('#count').textContent = '0';
          show('v-live'); activeCase = state.case_no; setCase(state.case_no);
        }
        setFeed(state.camera_ok ? 'ok' : 'lost');
        const scout = $('#scout-status');
        if(scout){ scout.textContent = state.rover_ok ? 'SCOUT ONLINE' : 'SCOUT OFFLINE'; scout.classList.toggle('down', !state.rover_ok); }
        if(state.frame_id !== frameId && img && !loading && state.camera_ok){
          loading = true; const id = state.frame_id, caseAtLoad = activeCase;
          authedImg(img, `${frameUrl}?${id}`,
            () => { loading = false; if(caseAtLoad !== activeCase || stopped) return; frameId = id; },
            () => { loading = false; });
        }
        const items = state.items.map(normalize);
        const reportLink = $('#report-link');                // the owner's Defender Report, once filed
        if(reportLink){
          const href = state.report && state.report.url;
          reportLink.hidden = !href;
          if(href && reportLink.getAttribute('href') !== href) reportLink.setAttribute('href', href);
        }
        if(!state.revealed) tickTape(items);                    // the tape keeps ticking while the walk runs
        if(state.revealed && !revealed){ revealed = true; seen = new Set(items.map(it => it.n)); found = items; runReveal(items); }
        else if(!state.revealed){
          if(revealed){ revealed = false; seen = new Set(); await newCase({idle: true}); }   /* THE END dissolves onto the title card */
          if(state.pending && !$('.log-line.pending')) pending(state.items.length + 1);
          let freshShown = false;
          for(const it of items) if(!seen.has(it.n)){ seen.add(it.n); showExhibit(it); freshShown = true; }
          found = items; updateMarkers(items); take = state.take;
          odoLive.set(take, items.some(it => it.estimated)); $('#count').textContent = items.length;
          if(!state.pending) $('.log-line.pending')?.remove();
          if(freshShown) armIdle();                              // a new exhibit pushes the idle title card out
          if(planNews){
            const news = planNews; planNews = null;
            typeInto(newLine('wire plan-news'), news, '');
            const sr = $('#log-sr');
            if(sr){ const d = document.createElement('div'); d.textContent = news.slice(2);
                    while(sr.children.length >= 60) sr.firstElementChild.remove(); sr.append(d); }
          }

        }
      }
      timer = setTimeout(tick, every);
    }
    document.body.classList.add('idle');
    reelStart(); tick();
    // Live push: the hub's SSE stream refreshes the view the instant the case
    // changes. Polling above stays as the fallback (and covers token mode,
    // where EventSource can't send the X-Rig-Token header).
    let es = null;
    // No EventSource in token mode: it can't send X-Rig-Token, so it would just
    // 401-reconnect forever. Polling (which does send the header) covers it.
    if(!_tok && typeof EventSource !== 'undefined'){
      try {
        es = new EventSource('/events');
        es.onmessage = () => { if(!stopped){ clearTimeout(timer); tick(); } };
        es.onerror = () => { if(_authd){ es.close(); es = null; } };   // hub asked for a token: stop retrying
      } catch {}
    }
    return () => { stopped = true; clearTimeout(timer); clearInterval(watchdog); requestController?.abort(); es?.close(); };
  }

  /* close: back to the page that opened this one, or to the premiere when there isn't one */
  $$('[data-close-page]').forEach(a => a.addEventListener('click', e => {
    if(history.length > 1 && document.referrer.startsWith(location.origin)){ e.preventDefault(); history.back(); }
  }));

  /* ---------- init: wire whatever markup is on this page ---------- */
  odoLive = makeOdo($('#odo'));
  jobSheet();
  odoTotal = makeOdo($('#odo-total'));
  logEmpty();
  $$('.cut').forEach(cutType);
  if($('#scratch')) scheduleScratch();
  if($('#fr')){
    let ff = 0;
    setInterval(() => {
      ff++; const s = Math.floor(ff / 24);
      $('#fr').textContent = `FR 00:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}:${pad(ff % 24)}`;
      const tc = $('#hud-tc'); if(tc) tc.textContent = `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}:${pad(ff % 24)}`;
    }, 42);
  }
  if($('#hud-clock')){                       // the camera's date stamp, burned into the corner
    const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
    const stamp = () => { const d = new Date();
      $('#hud-clock').textContent = `${months[d.getMonth()]} ${pad(d.getDate())} ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
    stamp(); setInterval(stamp, 1000);
  }


  // no mouse pointer on the projected film: hide it after 2 s of stillness
  if(window.anime) document.documentElement.classList.add('has-anime');
  // Shared secret for mutating endpoints: sessionStorage only, asked for the
  // first time the hub answers 401. Never rendered into page source. A 401
  // prompts and retries once, so a wrong or rotated token doesn't silently
  // deaden the reveal button.
  let _tok = sessionStorage.getItem('rig-token');   // null = never asked
  let _authd = false;   // learned: the hub 401'd a read, so it wants the token
  const ensureToken = () => {
    if(_tok === null){
      _tok = prompt('rig token (leave blank if none)') || '';
      sessionStorage.setItem('rig-token', _tok);
    }
    return _tok;
  };
  const authed = () => _authd && !!_tok;
  const tokenHdrs = () => (_tok ? {'X-Rig-Token': _tok} : {});
  const _nonce = document.querySelector('meta[name="case-nonce"]')?.content;
  // A hub with no RIG_TOKEN (the open-LAN demo) never prompts at all.
  const authFetch = (url, init = {}) => {
    const sentToken = _tok;
    const hdrs = () => ({...(init.headers || {}),
      ...(_tok ? {'X-Rig-Token': _tok} : {}),
      ...(_nonce ? {'X-Case-Nonce': _nonce} : {})});
    return fetch(url, {...init, headers: hdrs(), cache: 'no-store'}).then(r => {
      if(r.status !== 401) return r;
      _authd = true;
      // Held controls can have several requests in flight. A late 401 for
      // an old token must reuse a token another request has already refreshed.
      if(_tok === sentToken){
        _tok = null;
        sessionStorage.removeItem('rig-token');
        ensureToken();
      }
      return fetch(url, {...init, headers: hdrs(), cache: 'no-store'});
    }).catch(() => {});
  };
  /* Reads stay anonymous until the hub 401s one; then polls and images carry
     the same session token mutations use. <img> tags can't send headers, so
     authedImg fetches a blob and hands the tag a short-lived object URL. */
  const getJSON = async url => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      let response = await fetch(url, {cache:'no-store', signal:controller.signal});
      if(response.status === 401){ _authd = true; response = await authFetch(url, {signal:controller.signal}); }
      return response?.ok ? await response.json() : null;
    } catch { return null; }
    finally { clearTimeout(timeout); }
  };
  const authedImg = (img, url, onload, onerror) => {
    if(!authed()){
      img.onload = onload || null;
      img.onerror = onerror || null;
      img.src = url;
      return;
    }
    fetch(url, {headers: tokenHdrs(), cache: 'no-store'})
      .then(r => r.ok ? r.blob() : Promise.reject(r.status))
      .then(b => {
        const obj = URL.createObjectURL(b);
        img.onload = () => { URL.revokeObjectURL(obj); onload && onload(); };
        img.onerror = () => { URL.revokeObjectURL(obj); onerror && onerror(); };
        img.src = obj;
      })
      .catch(() => onerror && onerror());
  };
  /* log scroll: operator scrolls up → pause auto-follow + JUMP TO LIVE pill */
  const _log = $('#log'), _jump = $('#jump-live');
  if(_log && _jump){
    _log.addEventListener('scroll', () => {
      const bottom = _log.scrollHeight - _log.scrollTop - _log.clientHeight;
      _log.closest('.log-wrap').classList.toggle('paused', bottom > 40);
    });
    _jump.addEventListener('click', () => {
      _log.closest('.log-wrap').classList.remove('paused');
      _log.scrollTop = _log.scrollHeight;
    });
  }
  $$('.rig-stop').forEach(btn => btn.addEventListener('click', () => {
    if(useAnime()) window.anime({ targets: btn, scale: [1, 0.96, 1], duration: 280, easing: 'easeOutCubic' });
    if(motion) motion.action([btn], signal => authFetch('/trigger_reveal', {method: 'POST', signal}),
      {loading:'Sending…', success:'Case command confirmed.'});
    else authFetch('/trigger_reveal', {method: 'POST'});
  }));
  // The red-dot crosshair is the only pointer on every page, for mice only:
  // touch screens get nothing. The system cursor stays hidden throughout
  // (noir.css, html.red-cursor); the dot itself hides when the mouse leaves
  // the window and, on the projected dashboard, after 2s idle.
  if(matchMedia('(hover: hover) and (pointer: fine)').matches){
    const xhair = document.createElement('div');
    xhair.className = 'xhair'; xhair.setAttribute('aria-hidden', 'true');
    document.body.appendChild(xhair);
    document.documentElement.classList.add('red-cursor');
    document.body.classList.add('quiet-cursor');     // hidden until the mouse first moves
    const idles = !!$('.view');
    let quiet;
    addEventListener('mousemove', e => {
      // A modal <dialog> sits in the browser's top layer, above any z-index, so the
      // dot rides inside whichever dialog is open (the job sheet) to stay on top.
      const host = document.querySelector('dialog[open]') || document.body;
      if(xhair.parentNode !== host) host.appendChild(xhair);
      xhair.style.left = e.clientX + 'px'; xhair.style.top = e.clientY + 'px';
      xhair.classList.toggle('hot', !!e.target.closest?.('a,button,summary,label,select,input,textarea,[role=button],[tabindex]:not([tabindex="-1"])'));
      document.body.classList.remove('quiet-cursor');
      if(idles){ clearTimeout(quiet); quiet = setTimeout(() => { if(!document.querySelector('dialog[open]')) document.body.classList.add('quiet-cursor'); }, 2000); }   // a form keeps its pointer
    }, {passive: true});
    document.documentElement.addEventListener('mouseleave', () => document.body.classList.add('quiet-cursor'));
  }

  /* 'r' radios dispatch — same as the GPIO27 button, over HTTP */
  addEventListener('keydown', e => {
    if(e.key.toLowerCase() !== 'r' || e.repeat) return;
    if(!connected) return; // offline demo and rehearsal never send microphone commands
    if(e.target.matches('input,textarea')) return;
    const f = $('#feed');
    if(f) f.classList.add('radio');
    sfx.squelch();
    authFetch('/api/radio', {method: 'POST'}).then(r => {
      if(r && r.ok) setTimeout(() => f?.classList.remove('radio'), 4000);
      else f?.classList.remove('radio');
    });
  });
  const soundButton = $('#sound-toggle');
  if(soundButton){ soundButton.textContent = sfx.on ? 'Mute (M)' : 'Sound (M)'; soundButton.setAttribute('aria-pressed', String(sfx.on)); }
  soundButton?.addEventListener('click', () => sfx.toggle());
  $('#skip-reveal')?.addEventListener('click', skipReveal);
  const isControl = target => target?.closest('input, textarea, select, button, a, [contenteditable="true"], [role="textbox"]');
  addEventListener('keydown', event => {
    if(isControl(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
    if(event.key.toLowerCase() === 'm'){ event.preventDefault(); if(!event.repeat) sfx.toggle(); }
    if(event.key.toLowerCase() === 'q' && !event.repeat) sfx.radio();
    if(event.key === 'Enter' && skipReveal()) event.preventDefault();
  });
  addEventListener('pointerdown', event => { if(!isControl(event.target)) skipReveal(); });
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', event => {
    if(event.matches){ skipReveal(); bootSkip?.(); typists.forEach(job => job.finish()); }
  });
  const settleMotion = () => {
    if(reduced()){ skipReveal(); bootSkip?.(); typists.forEach(job => job.finish()); }
  };
  document.addEventListener('vaultmotionchange', settleMotion);
  document.addEventListener('noirmotionchange', settleMotion);

  // ?sound turns sound on at the first key press or click (browsers need a gesture)
  if(new URLSearchParams(location.search).has('sound')){
    const go = () => { sfx.toggle(true); removeEventListener('keydown', go); removeEventListener('pointerdown', go); };
    addEventListener('keydown', go); addEventListener('pointerdown', go);
  }

  /* ---------- rover teleop: wasd/arrows -> POST /api/drive on the hub ----------
     Hold a key to keep rolling: a move is re-sent every ~300ms while held,
     and a stop is sent on release. Hub 503s harmlessly when no rover is up. */
  function drive(url = '/api/drive'){
    const map = {w:'forward',s:'back',a:'left',d:'right',
                 arrowup:'forward',arrowdown:'back',arrowleft:'left',arrowright:'right'};
    let held = null, timer = null;
    const send = (dir, secs) => authFetch(url, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(secs === undefined ? {dir} : {dir, secs})});
    const release = () => {
      if(timer){ clearInterval(timer); timer = null; }
      if(held){ held = null; sfx.hum(false); send('stop'); }
    };
    addEventListener('keydown', e => {
      if(isControl(e.target) || e.ctrlKey || e.metaKey || e.altKey || !$('#v-live')?.classList.contains('on')) return;
      const dir = map[e.key.toLowerCase()];
      if(!dir) return;
      e.preventDefault();                     // arrows must not scroll the case file
      if(held === dir) return;
      release();
      held = dir; sfx.hum(true);
      send(dir, 0.35);
      timer = setInterval(() => send(dir, 0.35), 300);
    });
    addEventListener('keyup', e => {
      const dir = map[e.key.toLowerCase()];
      if(dir && dir === held){ e.preventDefault(); release(); }
    });
    addEventListener('blur', release);
    addEventListener('visibilitychange', () => { if(document.hidden) release(); });
    const live = $('#v-live');                // the projector only; the desk drives without a live view
    if(live) new MutationObserver(() => { if(!live.classList.contains('on')) release(); }).observe(live, {attributes:true, attributeFilter:['class']});
  }

  return {
    motion,
    connect, show, rollTo, newCase, setCase, reelStart, cue, theEnd, drive, authFetch,
    getJSON, authedImg,
    pending, showExhibit, voidExhibit, runReveal, buildManifest,
    cutFeed, setFeed, setOffline, updateMarkers, skipReveal, exitIdle, enterIdle, armIdle,
    cutType, sfx, money, pad, later, sleep, clearLater, makeOdo, typeInto,
    get found(){ return found; }, get caseNo(){ return caseNo; },
  };
})();
