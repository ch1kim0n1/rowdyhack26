/* Decorative motion is optional; the artwork and every control work without it. */
(() => {
  const body = document.body;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const precisePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const buttons = [...document.querySelectorAll('[data-vault-motion]')];
  let paused = false;
  try { paused = localStorage.getItem('appraisal-motion') === 'paused'; } catch { /* Storage is optional. */ }

  function sync() {
    const stopped = paused || reduced.matches;
    body.classList.toggle('motion-paused', stopped);
    document.documentElement.dataset.motion = stopped ? 'reduce' : 'full';
    buttons.forEach(button => {
      button.setAttribute('aria-pressed', String(stopped));
      button.textContent = reduced.matches ? 'Motion reduced' : paused ? 'Resume motion' : 'Pause motion';
      button.disabled = reduced.matches;
      button.title = reduced.matches ? 'Following your device’s reduced-motion preference' : '';
    });
    document.dispatchEvent(new CustomEvent('vaultmotionchange', { detail: { paused: stopped } }));
  }
  buttons.forEach(button => button.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('appraisal-motion', paused ? 'paused' : 'running'); } catch { /* Keep the setting for this page. */ }
    sync();
  }));
  reduced.addEventListener('change', sync);
  document.addEventListener('noirmotionchange', event => { paused = event.detail.paused; sync(); });
  addEventListener('storage', event => {
    if(event.key === 'appraisal-motion'){ paused = event.newValue === 'paused'; sync(); }
  });
  document.addEventListener('visibilitychange', () => body.classList.toggle('vault-suspended', document.hidden));
  /* The dissolve from one screen to the next (vault.css) is motion too. */
  addEventListener('pageswap', event => { if (paused || reduced.matches) event.viewTransition?.skipTransition(); });

  document.querySelectorAll('[data-vault-stage]').forEach(stage => {
    stage.addEventListener('pointermove', event => {
      if (paused || reduced.matches || !precisePointer.matches) return;
      const bounds = stage.getBoundingClientRect();
      stage.style.setProperty('--vault-x', `${((event.clientX - bounds.left) / bounds.width - .5) * 3}px`);
      stage.style.setProperty('--vault-y', `${((event.clientY - bounds.top) / bounds.height - .5) * 2}px`);
    }, { passive: true });
    stage.addEventListener('pointerleave', () => {
      stage.style.setProperty('--vault-x', '0px');
      stage.style.setProperty('--vault-y', '0px');
    });
  });
  sync();
})();
