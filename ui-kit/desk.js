/* The dispatch desk. Polls the hub and draws what it says; every change goes
   back through Noir.authFetch, so RIG_TOKEN is asked for once and kept in
   sessionStorage, never in the page. Item names are remote text: textContent
   only, never innerHTML. */
(() => {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  const money = v => '$' + Math.round(Number(v) || 0).toLocaleString('en-US');
  const ago = s => s == null ? 'never' : s < 2 ? 'just now' : s < 90 ? `${Math.round(s)}s ago` : `${Math.round(s / 60)}m ago`;
  const send = (url, init) => Noir.authFetch(url, init);

  const odo = Noir.makeOdo($('#desk-odo'));
  const ledger = $('#ledger');
  let lastKey = '', fails = 0, revealed = null, frameId = null, lastCase = null;
  let lastContact = performance.now();
  let filed = new Set(), hydrated = false;

  function setState(post, state, text) {
    const el = $(`#post-${post} .state`);
    if(el.dataset.state === state && el.textContent === text) return;
    el.dataset.state = state;
    el.textContent = text;
    const card = el.closest('.post');
    card.classList.remove('post-changed'); void card.offsetWidth; card.classList.add('post-changed');
  }

  /* ---------- the plan (Mastermind) on the ledger ---------- */
  const lbs = v => (Math.round(Number(v) * 10) / 10).toLocaleString('en-US');
  function planMark(plan, it) {
    if (!plan) return null;
    if (plan.collected.includes(it.n)) return { text: 'Collected', cls: 'bag' };
    if (plan.excluded.includes(it.n)) return { text: 'Excluded by the crew', cls: 'leave' };
    if (plan.selected.includes(it.n)) return { text: 'Bag', cls: 'bag' };
    const left = plan.left.find(l => l.n === it.n);
    return left ? { text: `Leave · ${left.text}`, cls: 'leave' } : null;
  }
  function paintPlan(s) {
    const line = $('#plan-line'), plan = s.plan;
    line.hidden = !plan;
    if (!plan) return;
    const t = plan.totals, c = plan.constraints;
    line.textContent = [`Mastermind · ${plan.level.label} · revision ${plan.revision}`,
      `${money(t.value_usd)} in the bag`, `${lbs(t.weight_lb)}/${lbs(c.bag_lb)} lb`, `${t.grab_seconds}/${c.time_s} s`,
      plan.next ? `next: ${plan.next.item}` : 'nothing left to grab',
      plan.conflict.length ? `CONFLICT: collected exhibits overflow the ${plan.conflict.join(' and ')}` : ''].filter(Boolean).join(' · ');
  }
  async function setStatus(n, status, note, caseNo) {
    note.textContent = '';
    const r = await send('/api/exhibit_status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ n, status, case_no: caseNo }) });
    if (!r) { note.textContent = 'No answer from the hub.'; return; }
    if (!r.ok) { try { note.textContent = (await r.json()).message || `The hub said ${r.status}.`; } catch { note.textContent = `The hub said ${r.status}.`; } return; }
    lastKey = '';                                   /* repaint with the new plan right away */
    pollNow();
  }

  /* ---------- the case ---------- */
  function paintLedger(items, take, s = {}) {
    const plan = s.plan || null, live = plan && !s.revealed;
    const key = JSON.stringify([lastCase, take, plan?.revision, s.revealed, s.case_no,
      items.map(it => [it.n, it.item, it.value_usd, it.estimated, it.origin, it.why, it.status])]);
    if (key === lastKey) return;
    lastKey = key;
    ledger.replaceChildren();
    if (!items.length) {
      const li = document.createElement('li');
      li.className = 'ledger-empty';
      li.textContent = '> Scene stable. Awaiting targets...';
      ledger.append(li);
      filed.clear(); hydrated = true;
      return;
    }
    for (const it of items) {
      const li = document.createElement('li');
      if(hydrated && !filed.has(it.n)) li.classList.add('filed-now');
      const n = Object.assign(document.createElement('span'), { className: 'n', textContent: pad(it.n) });
      const mug = Object.assign(document.createElement('img'), { className: 'mug', alt: '', loading: 'lazy' });
      Noir.authedImg(mug, `/crop/${it.n}.jpg?${key.length}`, null, () => { mug.style.visibility = 'hidden'; });
      const what = Object.assign(document.createElement('span'), { className: 'what' });
      const name = Object.assign(document.createElement('span'), { className: 'name', textContent: it.item });
      const why = Object.assign(document.createElement('span'), { className: 'why' });
      why.textContent = [it.origin === 'rover' ? 'filed by the rover' : 'filed by the hat', it.why].filter(Boolean).join(' · ');
      what.append(name, why);
      const amt = Object.assign(document.createElement('span'), { className: 'amt', textContent: money(it.value_usd) });
      if (it.estimated) amt.append(Object.assign(document.createElement('span'), { className: 'est', textContent: 'est.' }));
      const mark = planMark(plan, it);
      if (mark) {
        what.append(Object.assign(document.createElement('span'), { className: `plan-tag ${mark.cls}`, textContent: mark.text }));
        li.classList.toggle('leave', mark.cls === 'leave');
      }
      li.append(n, mug, what, amt);
      if (live && (it.category || '').toLowerCase() !== 'exit') {
        const acts = Object.assign(document.createElement('div'), { className: 'acts' });
        const note = Object.assign(document.createElement('span'), { className: 'act-note' });
        note.setAttribute('role', 'status');
        acts.setAttribute('role', 'group');
        acts.setAttribute('aria-label', `Status of exhibit ${pad(it.n)}`);
        for (const [label, status] of [['Available', 'available'], ['Collected', 'collected'], ['Excluded', 'excluded']]) {
          const b = Object.assign(document.createElement('button'), { type: 'button', textContent: label });
          b.setAttribute('aria-pressed', String((it.status || 'available') === status));
          b.setAttribute('aria-label', `${label}: exhibit ${pad(it.n)} ${it.item}`);
          b.addEventListener('click', () => setStatus(it.n, status, note, s.case_no));
          acts.append(b);
        }
        acts.append(note);
        li.append(acts);
      }
      ledger.append(li);
    }
    const total = document.createElement('li');
    total.className = 'total';
    total.append(Object.assign(document.createElement('span'), { textContent: 'TOTAL TAKE' }),
                 Object.assign(document.createElement('span'), { textContent: money(take) }));
    ledger.append(total);
    filed = new Set(items.map(it => it.n)); hydrated = true;
  }

  async function pollState() {
    try {
      const s = await Noir.getJSON('/state.json');
      if (!s) throw new Error('state poll');
      fails = 0;
      lastContact = performance.now();
      document.body.classList.remove('offline');
      Noir.motion?.update(s);
      if(lastCase !== s.case_no){ filed.clear(); hydrated = false; lastCase = s.case_no; }
      odo.set(s.take);
      $('#desk-count').textContent = s.items.length;
      $('.feed-print').classList.toggle('lost', !s.camera_ok);
      if (s.frame_id !== frameId) { frameId = s.frame_id; Noir.authedImg($('#desk-frame'), `/frame.jpg?${s.frame_id}`); }
      $('#walk-state').textContent = s.revealed ? 'Lineup filed. Case on the projector.'
        : s.pending ? `> Examining exhibit ${pad(s.items.length + 1)}...` : 'Scene stable. Awaiting targets.';
      const btn = $('#file-btn');
      if(btn.dataset.busy !== 'true') btn.textContent = s.revealed ? 'Close the case' : 'File the lineup';
      $('#file-note').textContent = s.revealed
        ? 'The lineup is up. Closing it rolls THE END and opens the next case.'
        : 'Same as the button on the cap. The projector cuts to the lineup.';
      if (revealed === false && s.revealed) {
        const st = $('#desk-stamp');
        st.classList.remove('enter'); void st.offsetWidth; st.classList.add('enter');
        if (window.anime && !NoirMotion.reduced()) anime({ targets: st, scale: [1.16, 0.988, 1.018, 1], opacity: [0, 0.95], duration: 820, easing: 'easeOutCubic' });
        Noir.sfx.thud();
      }
      if (!s.revealed) $('#desk-stamp').classList.remove('enter');
      revealed = s.revealed;
      $$('.case-no').forEach(e => { e.textContent = s.case_no; });
      paintPlan(s);
      paintLedger(s.items, s.take, s);
    } catch {
      if (++fails >= 3 || performance.now() - lastContact >= 3000) {
        document.body.classList.add('offline'); Noir.motion?.setConnection('offline');
      }
    }
    clearTimeout(stateTimer);
    stateTimer = setTimeout(pollState, 1000);
  }
  let stateTimer = null;
  const pollNow = () => { clearTimeout(stateTimer); pollState(); };

  /* ---------- the crew ---------- */
  async function pollHealth() {
    try {
      const h = await Noir.getJSON('/health');
      if (!h) throw new Error('health poll');
      const up = Math.round(h.uptime_s);
      $('#uptime').textContent = `up ${Math.floor(up / 3600) ? Math.floor(up / 3600) + ':' : ''}${pad(Math.floor(up / 60) % 60)}:${pad(up % 60)}`;
      setState('hat', h.camera_ok ? 'ok' : 'down', h.camera_ok ? 'On the job' : 'Footage lost');
      $('#hat-camera').textContent = h.camera_ok ? 'Rolling' : 'No picture';
      $('#hat-vision').textContent = { openai: 'OpenAI, then Anthropic, then the catalog', anthropic: 'Anthropic, then the catalog', 'offline-catalog': 'Offline catalog only' }[h.vision_provider] || h.vision_provider;
      $('#hat-voice').textContent = h.voice ? 'Speaking up' : 'Muted';
      $('#hat-oled').textContent = h.oled_mode ? `OLED: ${h.oled_mode}` : 'No OLED';
      $('#hat-saved').textContent = h.persistence?.last_saved_epoch ? ago(Date.now() / 1000 - h.persistence.last_saved_epoch) : 'Nothing filed yet';
      paintSerp(h.serpapi);

      const w = h.wrist?.seen_s_ago;
      setState('wrist', w != null && w < 8 ? 'ok' : 'down', w == null ? 'Not seen' : w < 8 ? 'Polling' : 'Gone quiet');
      $('#wrist-note').textContent = w == null ? 'The wrist has not asked for /wrist.json yet. This is what it would show.' : `Last asked ${ago(w)}. This is what it shows.`;

      const rv = h.rover || {};
      setState('rover', rv.registered ? 'ok' : 'down', rv.registered ? 'On the line' : rv.seen_s_ago == null ? 'Not seen' : 'Gone quiet');
      $('#rover-note').textContent = rv.seen_s_ago == null ? 'No heartbeat yet. Start it with python -m rig.rover.' : `Last heartbeat ${ago(rv.seen_s_ago)}.`;
    } catch { /* the state poll already reports a dead line */ }
    setTimeout(pollHealth, 3000);
  }

  async function pollWrist() {
    try {
      const d = await Noir.getJSON('/wrist.json?peek');
      if (!d) throw new Error('wrist poll');
      WristOLED.draw($('#wrist-oled'), d);
    } catch {
      WristOLED.dead($('#wrist-oled'), 'hub err');
    }
    setTimeout(pollWrist, 2000);
  }

  /* ---------- the price source ---------- */
  function paintSerp(sp = {}) {
    $$('.switch button').forEach(b => b.setAttribute('aria-checked', String((b.dataset.serp === 'true') === !!sp.enabled)));
    $('#serp-note').textContent = !sp.has_key
      ? 'No SERPAPI_API_KEY on the hub, so prices come from a model quote either way.'
      : sp.enabled ? 'Sold listings first. A model quote if nothing sold.' : 'A model quote for every find. Sold comps are off.';
  }
  $$('.switch button').forEach(b => b.addEventListener('click', async () => {
    const r = await Noir.motion.action($$('.switch button'), signal => send('/api/serpapi', {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: b.dataset.serp === 'true' })
    }), {loading: 'Updating…', success: 'Price-source setting confirmed.'});
    if (r && r.ok) paintSerp(await r.json());
  }));

  /* ---------- the button ---------- */
  $('#file-btn').addEventListener('click', async e => {
    const btn = e.currentTarget;
    await Noir.motion.action([btn], signal => send('/trigger_reveal', { method: 'POST', signal }),
      {loading: revealed ? 'Closing…' : 'Filing…', success: 'Case change confirmed.'});
  });

  /* ---------- the wheels: hold a button, or use WASD ---------- */
  const note = $('#drive-note');
  const say = r => {
    if (!r) { note.textContent = 'No answer from the hub.'; return; }
    note.textContent = r.ok ? 'Rolling.' : r.status === 503 ? 'No rover on the line.' : r.status === 502 ? 'Rover unreachable.' : r.status === 401 ? 'Wrong rig token.' : `The rover said ${r.status}.`;
  };
  const drive = (dir, secs) => send('/api/drive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(secs === undefined ? { dir } : { dir, secs }) });
  $$('.pad button').forEach(b => {
    let timer = null;
    const stop = () => {
      if (!timer) return;
      clearInterval(timer); timer = null;
      b.classList.remove('held');
      drive('stop').then(() => { note.textContent = 'Stopped.'; });
    };
    b.addEventListener('pointerdown', e => {
      e.preventDefault();
      b.setPointerCapture(e.pointerId);
      b.classList.add('held');
      drive(b.dataset.dir, 0.35).then(say);
      timer = setInterval(() => drive(b.dataset.dir, 0.35), 300);
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(ev => b.addEventListener(ev, stop));
  });
  Noir.drive('/api/drive');

  /* ---------- the radio: typed or keyed calls, answered from the plan ---------- */
  const STATES = { queued: 'Queued', listening: 'Listening on the hub mic...', transcribing: 'Transcribing...',
    thinking: 'Thinking...', applying: 'Applying the change...', speaking: 'Speaking...', done: 'Answered',
    clarify: 'Needs one more detail', unsupported: "Didn't catch a command", failed: 'Failed', cancelled: 'Cancelled', expired: 'Expired' };
  const jobId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/[^A-Za-z0-9]/g, '').slice(0, 24);
  const radioState = $('#radio-state');
  let radioKey = '', radioTimer = null;
  async function call(url, body) {
    const r = await send(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r) { radioState.textContent = 'No answer from the hub.'; return false; }
    if (r.status === 429) { radioState.textContent = 'Dispatch is busy. One call at a time.'; return false; }
    if (!r.ok) { try { radioState.textContent = (await r.json()).error || `The hub said ${r.status}.`; } catch { radioState.textContent = `The hub said ${r.status}.`; } return false; }
    radioState.textContent = 'Queued.';
    pollRadio();
    return true;
  }
  $('#radio-form').addEventListener('submit', async e => {
    e.preventDefault();
    const input = $('#radio-text'), text = input.value.trim();
    if (!text) return;
    const btn = e.submitter || $('#radio-form button[type=submit]');
    btn.disabled = true;
    if (await call('/api/radio/text', { text, job_id: jobId() })) input.value = '';
    btn.disabled = false;
    input.focus();
  });
  $('#radio-mic').addEventListener('click', () => call('/api/radio', { job_id: jobId() }));
  $$('#radio-hints [data-say]').forEach(b => b.addEventListener('click', () => call('/api/radio/text', { text: b.dataset.say, job_id: jobId() })));

  function paintRadio(d) {
    const jobs = d.jobs || [];
    if (jobs[0]) radioState.textContent = `${STATES[jobs[0].state] || jobs[0].state}${d.queued ? ` · ${d.queued} waiting` : ''}`;
    const key = jobs.map(j => `${j.job_id}:${j.state}:${j.spoken}`).join('|');
    if (key === radioKey) return;
    radioKey = key;
    const log = $('#radio-log');
    log.replaceChildren();
    if (!jobs.length) {
      log.append(Object.assign(document.createElement('li'), { className: 'radio-empty fine', textContent: 'No calls yet. Ask dispatch about the plan, or change it.' }));
      return;
    }
    for (const j of jobs.slice(0, 12)) {
      const li = document.createElement('li');
      li.dataset.state = j.state;
      const you = j.transcript || (j.source === 'mic' ? '(keyed the mic)' : '');
      li.append(Object.assign(document.createElement('span'), { className: 'who', textContent: j.source === 'mic' ? 'You, on the mic' : 'You, typed' }),
                Object.assign(document.createElement('span'), { className: 'you', textContent: you }));
      if (j.reply) li.append(Object.assign(document.createElement('span'), { className: 'reply', textContent: `Dispatch: ${j.reply}` }));
      if (j.error && j.error !== j.reply) li.append(Object.assign(document.createElement('span'), { className: 'err', textContent: j.error }));
      const rev = j.revision != null ? `plan rev ${j.revision}${j.revision_after != null && j.revision_after !== j.revision ? ` to ${j.revision_after}` : ''}` : '';
      const meta = [STATES[j.state] || j.state, j.intent ? j.intent.name.replace('_', ' ') : '', j.applied ? 'change applied' : '', rev,
        j.spoken && j.spoken !== 'queued' ? `voice: ${j.spoken}` : ''].filter(Boolean).join(' · ');
      li.append(Object.assign(document.createElement('span'), { className: 'job-meta', textContent: meta }));
      log.append(li);
    }
  }
  async function pollRadio() {
    clearTimeout(radioTimer);
    const d = await Noir.getJSON('/api/radio/jobs');
    if (d) paintRadio(d);
    radioTimer = setTimeout(pollRadio, 1000);
  }

  let narratorKey = '';
  async function pollNarrator() {
    const d = await Noir.getJSON('/narrator.json');
    if (d) {
      const st = $('#narrator-state');
      st.dataset.state = d.enabled ? 'ok' : 'down';
      st.textContent = d.enabled ? `Speaking up${d.queued ? ` · ${d.queued} queued` : ''}` : 'Muted · transcript only';
      const key = d.lines.map(l => `${l.at}:${l.state}`).join('|');
      if (key !== narratorKey) {
        narratorKey = key;
        const log = $('#narrator-log');
        log.replaceChildren();
        if (!d.lines.length) log.append(Object.assign(document.createElement('li'), { className: 'fine', textContent: 'Nothing said yet.' }));
        for (const l of d.lines.slice(0, 12)) {
          const li = document.createElement('li');
          li.dataset.state = l.state;
          li.append(Object.assign(document.createElement('span'), { textContent: l.text || '(silence)' }),
                    Object.assign(document.createElement('span'), { className: 'job-meta', textContent: [l.event.replace(/_/g, ' '), l.state, l.latency_ms != null ? `${l.latency_ms} ms to start` : ''].filter(Boolean).join(' · ') }));
          log.append(li);
        }
      }
    }
    setTimeout(pollNarrator, 1500);
  }

  WristOLED.draw($('#wrist-oled'), { case_no: Number($('.case-no').textContent) || 0, take: 0, count: 0, top: [] });
  pollState(); pollHealth(); pollWrist(); pollRadio(); pollNarrator();

  // Live push: the hub's SSE stream refreshes the desk the instant the case
  // changes, instead of waiting out the 1s poll. The timers above stay as a
  // fallback (and cover token mode, where EventSource can't send the header).
  liveEvents(pollNow);

  function liveEvents(onChange) {
    if (typeof EventSource === 'undefined') return;
    // Token mode: EventSource can't send X-Rig-Token, so it would 401-reconnect
    // forever. Polling via Noir.authFetch (which does send it) covers that.
    if (sessionStorage.getItem('rig-token')) return;
    let es;
    try { es = new EventSource('/events'); } catch { return; }
    es.onmessage = () => onChange();           // a change landed: refresh now
    es.onerror = () => {                      // a later 401 (token asked) closes it for good
      if (sessionStorage.getItem('rig-token')) { es.onerror = null; es.close(); }
    };
  }
})();
