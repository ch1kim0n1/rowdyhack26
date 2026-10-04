// Real-browser acceptance checks. Run npm ci, npx playwright install chromium, npm run test:ui.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-artifacts');
const base = `http://127.0.0.1:${process.env.UI_TEST_PORT || 5127}`;
const python = process.env.PYTHON || (process.platform === 'win32' ? path.join(root, '.venv/Scripts/python.exe') : 'python');
const server = spawn(python, ['tests/ui_server.py'], {cwd:root, env:process.env, stdio:['ignore','pipe','pipe']});
let serverLog = '';
server.stderr.on('data', data => { serverLog = (serverLog + data).slice(-3000); });
server.stdout.on('data', data => { serverLog = (serverLog + data).slice(-3000); });
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const errors = [], results = [];
let browser;
async function fixture(data){
  const response = await fetch(base + '/__fixture', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  assert.equal(response.status, 200); return response.json();
}
async function check(name, run){ await run(); results.push(name); console.log('PASS', name); }
async function axe(page, name){
  await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
  const report = await page.evaluate(() => axe.run(document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}));
  fs.writeFileSync(path.join(output, `axe-${name}.json`), JSON.stringify(report, null, 2));
  const serious = report.violations.filter(v => ['serious','critical'].includes(v.impact));
  assert.deepEqual(serious.map(v => ({id:v.id, nodes:v.nodes.map(n => n.target)})), []);
}
(async () => {
  fs.mkdirSync(output, {recursive:true});
  for(let attempt = 0; attempt < 80; attempt++){
    try { if((await fetch(base + '/health')).ok) break; } catch {}
    if(attempt === 79) throw new Error('Fixture server did not start: ' + serverLog);
    await wait(100);
  }
  const launch = {headless:true};
  if(process.env.BROWSER_CHANNEL) launch.channel = process.env.BROWSER_CHANNEL;
  else if(process.platform === 'win32' && fs.existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')) launch.channel = 'chrome';
  browser = await chromium.launch(launch);
  const context = await browser.newContext({viewport:{width:1440,height:900}});
  const page = await context.newPage(); page.on('pageerror', error => errors.push(String(error)));
  // Keep the connector's cleanup handle available for isolated component checks.
  await page.route(base + '/', async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace("Noir.connect('/state.json');", "window.stopPolling = Noir.connect('/state.json');");
    await route.fulfill({response,body});
  });
  await fixture({count:0});
  await check('Cold open skips instantly and does not replay', async () => {
    await page.goto(base); await page.waitForFunction(() => document.body.classList.contains('cold-open'));
    await page.screenshot({path:path.join(output,'cold-open.png')});
    await page.keyboard.press('Space');
    assert.equal(await page.evaluate(() => document.body.classList.contains('cold-open')), false);
    await page.waitForTimeout(750);
    assert.equal(await page.evaluate(() => document.body.classList.contains('idle')), false);
  });
  await check('Polls stay responsive through 65 rapid exhibits; log caps at 60', async () => {
    let polls = 0; page.on('request', request => { if(request.url().endsWith('/state.json')) polls++; });
    await fixture({count:65});
    await page.waitForFunction(() => document.querySelector('#count').textContent === '65');
    await wait(1000); assert.ok(polls >= 8, `only ${polls} polls`);
    assert.equal(await page.locator('#log .log-line').count(), 60);
    assert.equal(await page.locator('#log-sr > div').count(), 60);
    await page.locator('#log').evaluate(log => { log.scrollTop = 0; });
    await page.waitForFunction(() => !document.querySelector('#jump-live').hidden);
    await page.locator('#jump-live').click();
    await page.waitForFunction(() => document.querySelector('#jump-live').hidden);
  });
  await check('Marker bbox updates reuse nodes and preserve entrance animations', async () => {
    await page.evaluate(() => window.stopPolling());
    const result = await page.evaluate(async () => {
      // A fresh ID keeps this check independent of the previous 65-exhibit
      // burst: its old entrance animation could finish between these frames.
      const item = {n:1001,item:'SAFE <img onerror=alert(1)>',value_usd:100,bbox:{l:10,t:20,w:30,h:40}};
      Noir.updateMarkers([item]); await new Promise(requestAnimationFrame);
      const original = document.querySelector('.evidence-marker');
      const animation = original.querySelector('.tag').getAnimations()[0];
      Noir.updateMarkers([{...item,bbox:{l:15,t:25,w:35,h:45}}]); await new Promise(requestAnimationFrame);
      return {same:original === document.querySelector('.evidence-marker'), animationSame:animation === original.querySelector('.tag').getAnimations()[0],
        transform:original.style.transform, width:original.style.width, images:original.querySelectorAll('img').length};
    });
    assert.ok(result.same && result.animationSame); assert.equal(result.width, '35cqw'); assert.equal(result.images, 0);
    assert.match(result.transform, /15cqw, 25cqh/);
  });
  await check('Odometer rolls upward, fits $999,999, and leaves equal values still', async () => {
    const result = await page.evaluate(() => {
      const el = document.querySelector('#odo'); const odo = Noir.makeOdo(el);
      odo.set(999999, true);
      const first = el.firstChild; odo.set(999999, true);
      const box = el.getBoundingClientRect();
      return {same:first === el.firstChild, label:el.getAttribute('aria-label'), visibleFlag:!el.querySelector('.est').hidden,
        right:box.right, parentRight:el.parentElement.getBoundingClientRect().right,
        delay:el.querySelector('.odo-strip').style.getPropertyValue('--digit-delay'), animations:el.querySelectorAll('.rolling').length};
    });
    assert.ok(result.same && result.visibleFlag); assert.equal(result.label, '$999,999, estimated');
    assert.ok(result.right <= result.parentRight + 1); assert.ok(result.animations > 0); assert.equal(result.delay, '0ms');
  });
  await fixture({count:5}); await page.reload(); await page.keyboard.press('Space');
  await page.waitForFunction(() => document.querySelector('#count').textContent === '5');
  await page.waitForTimeout(1800);
  await check('Dashboard live axe scan has zero serious/critical WCAG violations', () => axe(page,'live'));
  await page.screenshot({path:path.join(output,'live.png')});
  await check('A stalled request goes LINE DEAD after two seconds, then recovers without layout shift', async () => {
    const layout = () => page.locator('#feed').evaluate(feed => ({width:feed.offsetWidth,height:feed.offsetHeight,left:feed.offsetLeft,top:feed.offsetTop}));
    const before = await layout();
    let hung = true;
    await page.route('**/state.json', async route => { if(hung) await wait(2600); await route.continue().catch(() => {}); });
    const started = Date.now();
    await page.waitForFunction(() => document.body.classList.contains('offline'), {timeout:4000});
    assert.ok(Date.now() - started >= 1800);
    assert.equal(await page.locator('.slate-title').textContent(), 'LINE DEAD');
    assert.match(await page.locator('.slate-meta').textContent(), /hub unreachable/);
    assert.deepEqual(await layout(), before);
    await page.screenshot({path:path.join(output,'line-dead.png')});
    hung = false; await page.waitForFunction(() => !document.body.classList.contains('offline'));
    assert.deepEqual(await layout(), before); await page.unroute('**/state.json');
  });
  await check('Camera loss and scout timeout have separate reasons', async () => {
    await fixture({count:0,camera_ok:false});
    await page.waitForFunction(() => document.querySelector('#feed').classList.contains('lost'));
    assert.match(await page.locator('.slate-meta').textContent(), /camera lost/);
    await fixture({count:5}); await page.waitForFunction(() => !document.querySelector('#feed').classList.contains('lost'));
    assert.equal(await page.locator('#scout-status').textContent(), 'SCOUT OFFLINE');
  });
  await check('Reveal can skip to FILED and reconstruct after a reload', async () => {
    await fixture({count:5,revealed:true});
    await page.waitForFunction(() => document.body.classList.contains('revealing'));
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#stamp-closed').textContent(), 'FILED');
    assert.equal(await page.locator('.suspect.in:not(.vacant)').count(), 5);
    assert.equal(await page.locator('#odo-total').getAttribute('aria-label'), '$750, estimated');
    await page.reload();
    await page.waitForFunction(() => document.body.classList.contains('revealing'));
    await page.mouse.click(700,150);
    await page.waitForFunction(() => document.querySelector('#stamp-closed').style.opacity === '1');
    assert.equal(await page.locator('.suspect .photo img[alt^="Exhibit"]').count(), 5);
    await page.waitForTimeout(800);
    await axe(page,'reveal');
    await page.screenshot({path:path.join(output,'reveal.png')});
  });
  await check('Full reveal ends within eight seconds and returns the manifest link', async () => {
    await page.evaluate(() => Noir.runReveal(Noir.found));
    await page.waitForFunction(() => document.querySelector('.the-end')?.classList.contains('on'));
    await page.waitForFunction(() => !document.body.classList.contains('revealing'), {timeout:8000});
    assert.equal(await page.locator('#v-reveal .file-copy').getAttribute('class'), 'file-copy ready');
  });
  await check('Mute persists through reload; keyboard controls respect focused buttons', async () => {
    await page.locator('#sound-toggle').click();
    assert.equal(await page.locator('#sound-toggle').getAttribute('aria-pressed'), 'true');
    await page.locator('#sound-toggle').click();
    assert.equal(await page.evaluate(() => sessionStorage.getItem('noir-muted')), 'true');
    await page.reload(); await page.keyboard.press('Space');
    assert.equal(await page.evaluate(() => Noir.sfx.on), false);
    await page.locator('#sound-toggle').focus();
    const before = await page.evaluate(() => Noir.sfx.on); await page.keyboard.press('m');
    assert.equal(await page.evaluate(() => Noir.sfx.on), before);
    await page.locator('#sound-toggle').blur(); await page.keyboard.press('m');
    assert.equal(await page.evaluate(() => Noir.sfx.on), true);
    await page.keyboard.press('m');
  });
  const reduced = await browser.newContext({viewport:{width:1440,height:900}, reducedMotion:'reduce'});
  const still = await reduced.newPage(); still.on('pageerror', error => errors.push(String(error)));
  await check('Reduced motion makes title, typing and reveal immediate', async () => {
    await fixture({count:5,revealed:true}); await still.goto(base);
    await still.waitForFunction(() => document.querySelector('#stamp-closed').style.opacity === '1');
    assert.equal(await still.evaluate(() => document.body.classList.contains('revealing')), false);
    assert.equal(await still.locator('.suspect.in:not(.vacant)').count(), 5);
    assert.equal(await still.locator('.odo-strip.rolling').count(), 0);
    await fixture({count:3}); await still.waitForFunction(() => document.querySelector('#count').textContent === '3');
    assert.equal(await still.locator('.log-line.typing').count(), 0);
    await axe(still,'reduced-motion');
  });
  await check('Vault UI stays intact; loading feedback and both motion controls share one preference', async () => {
    const live = await context.newPage(); live.on('pageerror', error => errors.push(String(error)));
    const lab = await context.newPage(); lab.on('pageerror', error => errors.push(String(error)));
    await fixture({count:0,pending:true}); await live.goto(base);
    await live.waitForFunction(() => document.querySelector('[data-motion-status]').dataset.phase === 'analyzing');
    assert.equal(await live.locator('[data-motion-status] .motion-toggle').isVisible(), false);
    assert.equal(await live.locator('[data-job="mastermind"]').count(), 1);
    await live.keyboard.press('Space'); await live.keyboard.press('p');
    await live.waitForFunction(() => document.querySelector('#job-sheet').open);
    await live.keyboard.press('Escape');
    await live.locator('[data-vault-motion]').click();
    assert.equal(await live.evaluate(() => localStorage.getItem('appraisal-motion')), 'paused');
    await lab.goto(base + '/motion.html');
    assert.equal(await lab.locator('.motion-toggle').textContent(), 'Motion: reduced');
    await lab.locator('.motion-toggle').click();
    await live.waitForFunction(() => document.querySelector('[data-vault-motion]').textContent === 'Pause motion');
    assert.equal(await live.evaluate(() => document.documentElement.dataset.motion), 'full');
    await live.goto(base + '/premiere#top');
    assert.equal(await live.locator('.vault-art').count(), 1);
    assert.equal(await live.locator('.intro canvas').count(), 1);
    assert.match(await live.locator('.hero-brief').textContent(), /Authorized Physical Red-Team Reconnaissance/);
    await live.locator('[data-vault-motion]').click();
    await lab.waitForFunction(() => document.querySelector('.motion-toggle').textContent === 'Motion: reduced');
    assert.equal(await live.locator('.vault-art').evaluate(el => getComputedStyle(el).animationName), 'none');
    await lab.locator('.motion-toggle').click();
    await live.waitForFunction(() => document.querySelector('[data-vault-motion]').textContent === 'Pause motion');
    await fixture({count:1}); await live.goto(base + '/desk');
    await live.waitForFunction(() => document.querySelector('[data-motion-status]').dataset.phase === 'observing');
    assert.equal(await live.locator('#radio-form').count(), 1);
    assert.equal(await live.locator('#narrator-log').count(), 1);
    await live.close(); await lab.close();
  });
  await check('Letter manifest fits one sheet for 0–15 long-name exhibits', async () => {
    const print = await context.newPage();
    for(const count of [0,1,5,15]){
      await fixture({count, why:'Model quote; conservative estimate based on condition and comparable sold listings. '.repeat(2)});
      await print.goto(base + '/manifest'); await print.emulateMedia({media:'print'});
      await print.evaluate(async () => {
        // Print emulation changes the used fonts. Flush that layout first,
        // and let the existing view entrance settle before contrast auditing.
        void document.body.offsetHeight;
        await document.fonts.ready;
        await Promise.all(document.querySelector('.view').getAnimations().map(animation => animation.finished.catch(() => {})));
      });
      const buffer = await print.pdf({format:'Letter',preferCSSPageSize:true,printBackground:true});
      fs.writeFileSync(path.join(output,`manifest-${count}.pdf`), buffer);
      const pdf = buffer.toString('latin1');
      assert.equal((pdf.match(/\/Type\s*\/Page\b/g) || []).length, 1, `${count} exhibits exceeded one page`);
      await axe(print,`manifest-${count}`);
      if(count === 15){ await print.emulateMedia({media:'screen'}); await print.screenshot({path:path.join(output,'manifest-15.png'),fullPage:true}); }
    }
    await print.close();
  });
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output,'results.json'), JSON.stringify({checks:results, errors}, null, 2));
  console.log(`${results.length} browser checks passed. Artifacts: ${output}`);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  await browser?.close(); server.kill();
});
