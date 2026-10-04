/* Simulated UI only. No fetch, token prompt, radio call, or motor command. */
(() => {
  const motion = NoirMotion.create(document.querySelector('[data-motion-status]'));
  let snapshot = {case_no: 1138, camera_ok: true, pending: false, revealed: false, items: []};
  const update = () => {
    motion.update({...snapshot, items: [...snapshot.items]});
    document.querySelector('#lab-summary').textContent = `Simulated case ${snapshot.case_no} · ${snapshot.items.length} observation(s) · ${snapshot.revealed ? 'debrief' : snapshot.pending ? 'analyzing' : 'ready'}.`;
  };
  document.querySelectorAll('[data-state]').forEach(button => button.addEventListener('click', () => {
    const state = button.dataset.state;
    if(state === 'offline'){ motion.setConnection('offline'); return; }
    if(state === 'reset') snapshot = {case_no: snapshot.case_no + 1, camera_ok: true, pending: false, revealed: false, items: []};
    else {
      snapshot = {...snapshot, camera_ok: state !== 'camera-lost', pending: state === 'analyzing', revealed: state === 'debrief'};
      if(state === 'filed') snapshot.items = [...snapshot.items, {n: snapshot.items.length + 1,
        item: `Demo camera ${snapshot.items.length + 1}`, value_usd: 1850, estimated: true, source: 'offline', why: 'offline catalog; simulated preview'}];
      if(state === 'empty') snapshot.items = [];
    }
    update();
  }));
  for(const id of ['lab-success', 'lab-error']) {
    const button = document.getElementById(id);
    button.addEventListener('click', () => motion.action([button], () => new Promise(resolve => {
      setTimeout(() => resolve({ok: id === 'lab-success', status: id === 'lab-success' ? 200 : 503}), 1200);
    }), {loading: 'Sending…', success: 'Simulated action confirmed.'}));
  }
  update();
})();
