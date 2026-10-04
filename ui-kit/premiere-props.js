/* Props: the small physical things on the page that answer the scroll. The red string
   is run from pin to pin as the crew's files land. Each file is stamped once it is
   down. The files are swept aside as the next scene arrives. The rover, the wrist
   unit and the hat are each turned through the photographs taken round them. And, top right, the
   projectionist's cue mark blinks twice before every change of scene, the way it
   does before a change of reel.
   All of it is the kit's own: its string, its stamp and thud, its cue mark. With
   motion paused or reduced the string is simply there, the files are stamped, and
   there is no cue. */
(() => {
  'use strict';
  const cinema = window.ScrollCinema, clock = window.PremiereScroll;
  if (!cinema || !clock) return;
  const { range, smooth } = cinema;
  const sfx = typeof Noir !== 'undefined' ? Noir.sfx : null;      /* heard only if the viewer turned sound on */

  /* ---------- the crew's desk: string, stamps, and the sweep ---------- */
  const dossiers = document.querySelector('.dossiers');
  const stamps = [...document.querySelectorAll('.dossier .stamp')].map(el => ({ el, top: 0, down: false }));
  let measured = '', filesTop = 0, string = '', sweep = '';
  if (dossiers) cinema.scene('crew', (scene, { y, vh, width, reduced }) => {
    const layout = `${width}x${vh}:${scene.top}:${scene.height}`;
    if (layout !== measured) {
      measured = layout;
      filesTop = clock.top(dossiers);
      for (const stamp of stamps) stamp.top = clock.top(stamp.el);
    }
    /* The string starts at the first pin as the files come up and reaches the last as they settle. */
    const run = reduced ? '' : smooth(range(y + vh * .94 - filesTop, vh * .12, vh * .6)).toFixed(3);
    if (run !== string) { string = run; run ? dossiers.style.setProperty('--string', run) : dossiers.style.removeProperty('--string'); }
    /* A stamp comes down once its file is well into the window, and is lifted again on the way back. */
    for (const stamp of stamps) {
      const down = reduced || y + vh * .8 > stamp.top;
      if (down === stamp.down) continue;
      stamp.down = down;
      stamp.el.classList.toggle('landed', down);
      if (down && !reduced && stamp.top > y && stamp.top < y + vh) sfx?.thud();
    }
    /* Swept aside as the next scene comes up; put back once the desk is out of the window. */
    const aside = reduced || width <= 720 || scene.exit >= 1 ? '' : smooth(range(scene.exit, .45, 1)).toFixed(3);
    if (aside !== sweep) { sweep = aside; Number(aside) ? dossiers.style.setProperty('--sweep', aside) : dossiers.style.removeProperty('--sweep'); }
  });

  /* ---------- the rover, the wrist and the hat, turned ----------
     Each .turntable is plates in one print, laid in the order they were taken round the
     thing. The scroll lays each over the last. A plate is held clean for the first half
     of its turn and the next comes through over the second: two angles laid together
     are a double image, so that is kept short. The print's caption says which side is
     showing. */
  const tables = [...document.querySelectorAll('.turntable')];
  for (const table of tables) {
    const plates = [...table.querySelectorAll('.plates li')], stage = table.querySelector('.turntable-stage');
    const named = table.querySelector('.turn-name'), counted = table.querySelector('.turn-count');
    if (plates.length < 2 || !named || !counted || !stage) continue;
    const sheet = [named.textContent, counted.textContent];      /* what the caption says of a contact sheet */
    let laid = '', facing = -2, sized = '', pinned = 1;
    cinema.scene(table.dataset.cinematicScene, (scene, { y, vh, width, reduced }) => {
      /* The turn runs for as long as the stage is pinned. On a phone the stage can be taller
         than the window (a second print is under the first screen), so that is less than the scene. */
      const layout = `${width}x${vh}:${scene.height}`;
      if (layout !== sized) { sized = layout; pinned = Math.max(1, scene.height - stage.offsetHeight); }
      /* The first and the last are held at either end of the turn. */
      const turn = range((y - scene.top) / pinned, .05, .95) * (plates.length - 1);
      const under = Math.min(plates.length - 2, Math.floor(turn)), over = smooth(range(turn - under, .55, 1));
      const state = reduced ? '' : `${under}:${over.toFixed(3)}`;
      if (state === laid) return;
      laid = state;
      plates.forEach((plate, i) => {
        plate.style.opacity = reduced ? '' : i === under ? '1' : i === under + 1 ? over.toFixed(3) : '0';
      });
      const front = reduced ? -1 : over > .5 ? under + 1 : under;
      if (front === facing) return;
      facing = front;
      named.textContent = front < 0 ? sheet[0] : plates[front].dataset.view;
      counted.textContent = front < 0 ? sheet[1] : `${front + 1} / ${plates.length}`;
    });
  }

  /* ---------- the cue mark ----------
     Two blinks as a scene's end comes up the window: one to stand by, one to change over. */
  const cue = Object.assign(document.createElement('div'), { className: 'cue' });
  cue.setAttribute('aria-hidden', 'true');
  document.body.append(cue);
  const BLINKS = [[.06, .16], [.26, .36]];
  const due = new Set();
  for (const name of ['film', 'story', 'crew', ...tables.map(table => table.dataset.cinematicScene), 'method', 'paperwork']) {
    cinema.scene(name, (scene, { reduced }) => {
      const on = !reduced && BLINKS.some(([from, to]) => scene.exit > from && scene.exit < to);
      if (on === due.has(name)) return;
      on ? due.add(name) : due.delete(name);
      cue.classList.toggle('on', due.size > 0);
    });
  }
})();
