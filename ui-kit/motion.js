/* Conditional motion: real state in, a quiet piece of paperwork out.
   No fabricated percentage, inferred confidence, or repeated poll animation. */
(function (root) {
  try {
    const preference = root.localStorage?.getItem('appraisal-motion');
    if(preference === 'paused' || (!preference && root.localStorage?.getItem('noir-motion') === 'reduce')) root.document.documentElement.dataset.motion = 'reduce';
  } catch { /* blocked storage must not block the interface */ }
  const reduced = () => !!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches || root.document?.documentElement.dataset.motion === 'reduce' || !!root.document?.body.classList.contains('motion-paused');
  const phase = (snapshot, connection = 'online') => {
    if (connection === 'offline') return 'offline';
    if (!snapshot) return 'connecting';
    if (snapshot.revealed) return 'debrief';
    if (!snapshot.camera_ok) return 'camera-lost';
    if (snapshot.pending) return 'analyzing';
    return snapshot.items.length ? 'observing' : 'empty';
  };
  const events = (before, after) => {
    if (!before) return []; // hydration isn't a newly observed finding
    if (before.case_no !== after.case_no) return [{ kind: 'reset', text: `Case ${after.case_no} opened. Previous case cleared.` }];
    if (!before.revealed && after.revealed) return [{ kind: 'debrief', text: 'Debrief ready. Assets ranked by estimated value.' }];
    const known = new Set(before.items.map(it => it.n));
    const fresh = after.items.filter(it => !known.has(it.n));
    const top = new Set([...after.items].sort((a, b) => b.value_usd - a.value_usd).slice(0, 5).map(it => it.n));
    return fresh.map(it => ({ kind: 'filed', n: it.n,
      text: `${top.has(it.n) && it.category !== 'exit' ? 'Top-five asset' : 'Observation filed'}: ${it.item}${it.estimated ? ' · value estimated' : ''}.` }));
  };
  const LABELS = {
    connecting: ['Opening the line', 'Waiting for the first confirmed snapshot.'],
    analyzing: ['Analyzing the frame', 'Identification and appraisal in progress.'],
    observing: ['Watching for a new scene', 'Current findings stay visible in the case file.'],
    empty: ['Ready for the walkthrough', 'No observations filed yet. Look at an approved prop.'],
    debrief: ['Debrief ready', 'Ranked by estimated asset value, not security risk.'],
    'camera-lost': ['Waiting for the camera', 'Previous findings stay visible. No new footage yet.'],
    offline: ['Reconnecting to the hub', 'Last confirmed findings shown. Live data is unavailable.'],
  };

  function create(host) {
    if (!host) return null;
    const doc = host.ownerDocument;
    host.classList.add('motion-status');
    host.setAttribute('role', 'group');
    host.setAttribute('aria-label', 'Assessment status');
    host.innerHTML = '<div class="motion-reel" aria-hidden="true"><i></i><i></i><i></i></div>' +
      '<div class="motion-copy"><div class="motion-label" role="status" aria-live="polite"></div>' +
      '<p class="motion-detail"></p><div class="motion-meta"><span class="motion-source"></span>' +
      '<span class="motion-elapsed" aria-hidden="true"></span></div>' +
      '<button type="button" class="motion-toggle" aria-label="Reduce interface motion">Motion: full</button></div>' +
      '<div class="motion-track" aria-hidden="true"><i></i></div>';
    const label = host.querySelector('.motion-label'), detail = host.querySelector('.motion-detail');
    const source = host.querySelector('.motion-source'), elapsed = host.querySelector('.motion-elapsed');
    const toggle = host.querySelector('.motion-toggle');
    const paintPreference = () => {
      const systemReduced = !!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      toggle.textContent = `Motion: ${reduced() ? 'reduced' : 'full'}`;
      toggle.setAttribute('aria-pressed', String(reduced()));
      toggle.disabled = systemReduced;
    };
    toggle.addEventListener('click', () => {
      const value = reduced() ? 'full' : 'reduce';
      doc.documentElement.dataset.motion = value;
      try { root.localStorage?.setItem('appraisal-motion', value === 'reduce' ? 'paused' : 'running'); } catch { /* session-only preference */ }
      doc.dispatchEvent?.(new root.CustomEvent('noirmotionchange', {detail:{paused:value === 'reduce'}}));
      paintPreference();
    });
    const media = root.matchMedia?.('(prefers-reduced-motion: reduce)');
    media?.addEventListener('change', paintPreference); paintPreference();
    const storage = event => {
      if(event.key !== 'appraisal-motion') return;
      doc.documentElement.dataset.motion = event.newValue === 'paused' ? 'reduce' : 'full';
      paintPreference();
    };
    root.addEventListener?.('storage', storage);
    doc.addEventListener('vaultmotionchange', paintPreference);
    // The current live UI already has a motion control in its navigation.
    if(doc.querySelector?.('[data-vault-motion]')) toggle.hidden = true;
    let current = null, connection = 'online', active = '', began = 0, elapsedTimer = null, noticeTimer;
    const notice = doc.createElement('aside');
    notice.className = 'motion-notice'; notice.hidden = true;
    const noticeText = doc.createElement('span');
    noticeText.setAttribute('role', 'status'); noticeText.setAttribute('aria-live', 'polite');
    const dismiss = doc.createElement('button');
    dismiss.type = 'button'; dismiss.textContent = '×'; dismiss.setAttribute('aria-label', 'Dismiss notification');
    notice.append(noticeText, dismiss); doc.body.append(notice);
    dismiss.addEventListener('click', () => { clearTimeout(noticeTimer); notice.hidden = true; noticeText.textContent = ''; });

    const notify = (text, tone = 'info') => {
      clearTimeout(noticeTimer);
      notice.hidden = false; notice.dataset.tone = tone;
      noticeText.textContent = text; // names may be remote text; never interpolate HTML
      notice.classList.remove('arrive'); void notice.offsetWidth; notice.classList.add('arrive');
      noticeTimer = setTimeout(() => { notice.hidden = true; noticeText.textContent = ''; }, 8000);
    };
    const paintElapsed = () => {
      const seconds = Math.max(0, Math.floor((Date.now() - began) / 1000));
      elapsed.textContent = `${seconds}s elapsed`;
      if (seconds >= 10) detail.textContent = 'Still processing. Previous findings stay visible.';
    };
    const paint = () => {
      const next = phase(current, connection);
      const changed = active !== next;
      if (changed) {
        active = next; host.dataset.phase = next;
        doc.body.dataset.uiPhase = next;
        label.textContent = LABELS[next][0]; detail.textContent = LABELS[next][1];
        host.classList.remove('state-change'); void host.offsetWidth; host.classList.add('state-change');
      }
      if (next === 'analyzing' && !elapsedTimer) {
        began = Date.now(); paintElapsed(); elapsedTimer = setInterval(paintElapsed, 1000);
      } else if (next !== 'analyzing') {
        clearInterval(elapsedTimer); elapsedTimer = null; elapsed.textContent = '';
      }
      const latest = current?.items.at(-1);
      const sourceLabel = latest ? (latest.source === 'offline' || /offline/i.test(latest.why || '')
        ? 'DEMO CATALOG' : latest.estimated ? 'ESTIMATED VALUE' : 'VALUE SOURCE IN LEDGER') : 'NO FINDINGS YET';
      if(source.textContent !== sourceLabel) source.textContent = sourceLabel;
      const busy = String(next === 'connecting' || next === 'analyzing');
      if(host.dataset.busy !== busy) host.dataset.busy = busy;
    };
    const update = snapshot => {
      const fresh = events(current, snapshot);
      const reconnected = connection === 'offline';
      const cameraRestored = current && !current.camera_ok && snapshot.camera_ok;
      const pendingBegan = current && snapshot.pending && (!current.pending || current.case_no !== snapshot.case_no);
      if (pendingBegan) { clearInterval(elapsedTimer); elapsedTimer = null; }
      current = snapshot; connection = 'online'; paint();
      if (fresh.length) notify(fresh.length > 1 ? `${fresh.length} observations filed. Latest: ${fresh.at(-1).text}` : fresh[0].text, 'success');
      else if (reconnected) notify('Line restored. Live updates resumed.', 'success');
      else if (cameraRestored) notify('Camera restored. Observations can resume.', 'success');
    };
    const setConnection = value => {
      if (connection === value) return;
      connection = value; paint();
      if (value === 'offline') notify('Hub unreachable. Keeping the last confirmed case visible.', 'warning');
    };

    /* Buttons show network work, not decorative pretend success. A hung request
       releases the UI and asks the operator to check state before retrying. */
    async function action(buttons, operation, { loading = 'Sending…', success = 'Confirmed.' } = {}) {
      const list = [...buttons];
      if (list.some(b => b.dataset.busy === 'true')) return false;
      const originals = list.map(b => ({ b, text: b.textContent, disabled: b.disabled }));
      for (const { b } of originals) { b.dataset.busy = 'true'; b.disabled = true; b.setAttribute('aria-busy', 'true'); b.textContent = loading; }
      const controller = new AbortController();
      let timeout;
      try {
        const response = await Promise.race([operation(controller.signal), new Promise((_, reject) => {
          timeout = setTimeout(() => { controller.abort(); reject(new Error('timeout')); }, 12000);
        })]);
        if (!response?.ok) {
          notify(response?.status === 401 ? 'Token rejected. Check your rig token.'
            : response?.status === 429 ? 'Too many requests. Wait, then try again.'
            : 'No confirmation received. Check the case state before retrying.', 'warning');
          return false;
        }
        notify(success, 'success');
        for (const { b } of originals) { b.classList.add('action-confirmed'); setTimeout(() => b.classList.remove('action-confirmed'), 900); }
        return response;
      } catch {
        notify('No confirmation received. Check the case state before retrying.', 'warning'); return false;
      } finally {
        clearTimeout(timeout);
        for (const { b, text, disabled } of originals) { b.disabled = disabled; b.textContent = text; delete b.dataset.busy; b.removeAttribute('aria-busy'); }
      }
    }
    const visibility = () => doc.body.classList.toggle('motion-suspended', doc.hidden);
    doc.addEventListener('visibilitychange', visibility); visibility(); paint();
    return { update, setConnection, notify, action, get snapshot() { return current; },
      destroy() { clearInterval(elapsedTimer); clearTimeout(noticeTimer); doc.removeEventListener('visibilitychange', visibility); doc.removeEventListener('vaultmotionchange', paintPreference); media?.removeEventListener('change', paintPreference); root.removeEventListener?.('storage', storage); notice.remove(); } };
  }
  const api = { phase, events, create, reduced };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NoirMotion = api;
})(typeof window !== 'undefined' ? window : {});
