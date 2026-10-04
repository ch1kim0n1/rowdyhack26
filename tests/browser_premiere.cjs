// Focused acceptance suite for the cinematic premiere. Uses isolated fixture data.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-artifacts', 'premiere-scroll');
const port = process.env.UI_TEST_PORT || '5131', base = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON || (process.platform === 'win32' ? path.join(root, '.venv/Scripts/python.exe') : 'python');
const server = spawn(python, ['tests/ui_server.py'], {cwd:root, env:{...process.env, UI_TEST_PORT:port}, stdio:'pipe'});
let log = '', browser;
server.stderr.on('data', b => log = (log + b).slice(-3000));
const checks = [], errors = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
async function check(name, run) { await run(); checks.push(name); console.log('PASS', name); }
async function settle(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => window.PremiereScroll && !PremiereScroll.state.pending && Math.abs(PremiereScroll.state.rawY - scrollY) < 1);
}
async function atFilm(page, p) {
  await page.evaluate(p => {
    const reel = document.querySelector('.reel');
    scrollTo({top:PremiereScroll.top(reel) + (reel.offsetHeight - innerHeight) * p, behavior:'instant'});
  }, p);
  await settle(page);
  await page.waitForFunction(() => {
    const s = PremiereFilm.stats; return s && Math.abs(s.target - s.shown) <= 1;
  });
}
async function audit(page, label) {
  await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
  const result = await page.evaluate(() => axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}}));
  fs.writeFileSync(path.join(output, `axe-${label}.json`), JSON.stringify(result, null, 2));
  assert.deepEqual(result.violations.filter(v => ['serious','critical'].includes(v.impact)).map(v => ({id:v.id, nodes:v.nodes.map(n=>n.target)})), []);
}
(async () => {
  fs.mkdirSync(output, {recursive:true});
  for (let i=0; i<100; i++) {
    try { if ((await fetch(base+'/health')).ok) break; } catch {}
    if(i===99) throw Error(log); await wait(100);
  }
  const launch = {headless:true};
  if(process.env.BROWSER_CHANNEL) launch.channel=process.env.BROWSER_CHANNEL;
  else if(process.platform==='win32' && fs.existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')) launch.channel='chrome';
  browser=await chromium.launch(launch);
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  const page=await context.newPage(); page.on('pageerror', e=>errors.push(String(e)));
  await page.goto(base+'/premiere?intro=off#top');
  await check('New routes and all sequence frames are served', async()=>{
    for(const asset of ['premiere-scroll.js','premiere-scroll.css','premiere-sequence.js','media/scroll-frames/manifest.json'])
      assert.equal((await fetch(base+'/'+asset)).status,200,asset);
    const manifest=await (await fetch(base+'/media/scroll-frames/manifest.json')).json();
    assert.equal(manifest.count,501);
    assert.equal(fs.readdirSync(path.join(root,'ui-kit/media/scroll-frames')).filter(n=>n.endsWith('.webp')).length,501);
  });
  await check('Forward and reverse scrubbing reach exact frames with bounded memory',async()=>{
    for(const p of [0,.16,.53,.92,.34,.01]) await atFilm(page,p);
    const s=await page.evaluate(()=>PremiereFilm.stats);
    assert.ok(s.cached<=56); assert.ok(s.pending<=6);
    assert.equal(await page.locator('.reel').evaluate(el=>el.style.getPropertyValue('--portal-ui')),'1.000');
    await atFilm(page,.34); await page.screenshot({path:path.join(output,'film-desktop.png')});
  });
  await check('Shared scroll clock sleeps after input settles',async()=>{
    await settle(page); await wait(200);
    assert.equal(await page.evaluate(()=>PremiereScroll.state.pending),false);
  });
  await check('Chapter navigation, editorial crossfade and reverse restore correctly',async()=>{
    await page.getByRole('link',{name:'The Lineup',exact:true}).click();
    await settle(page);
    await page.waitForFunction(()=>PremiereFilm.stats.target>310);
    for(const p of [0,.82,.1]) {
      await page.evaluate(p=>{
        const el=document.querySelector('.case-statement');
        scrollTo({top:PremiereScroll.top(el)+(el.offsetHeight-innerHeight)*p,behavior:'instant'});
      },p); await settle(page);
      const opacity=await page.locator('.statement-second').evaluate(el=>Number(getComputedStyle(el).opacity));
      assert.ok(p>.8?opacity>.95:opacity<.05, `story progress=${p}, opacity=${opacity}`);
      if(p>.8) await page.screenshot({path:path.join(output,'story-desktop.png')});
    }
  });
  await check('Pause and resume switch to a readable manual player',async()=>{
    await page.getByRole('button',{name:'Pause motion',exact:true}).click();
    assert.ok(await page.locator('body').evaluate(el=>el.classList.contains('film-static')));
    assert.ok(await page.locator('video').evaluate(el=>el.controls));
    assert.equal(await page.locator('.statement-second').evaluate(el=>getComputedStyle(el).opacity),'1');
    await page.getByRole('button',{name:'Resume motion',exact:true}).click();
    await settle(page);
    assert.equal(await page.locator('video').evaluate(el=>el.controls),false);
  });
  await check('Desktop and mobile have no horizontal overflow or script errors',async()=>{
    for(const size of [{width:1440,height:900},{width:1366,height:768},{width:390,height:844},{width:360,height:640}]) {
      // Going to the URL the page is already on only moves to its #fragment; leave first so each size is a real load.
      await page.setViewportSize(size); await page.goto('about:blank'); await page.goto(base+'/premiere?intro=off#top'); await settle(page);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),JSON.stringify(size));
      if(size.width===390) await page.screenshot({path:path.join(output,'hero-mobile.png')});
      await atFilm(page,.3);
      assert.ok(await page.locator('.gate').evaluate(el=>el.getBoundingClientRect().right<=innerWidth));
      const stats = await page.evaluate(() => PremiereFilm.stats);
      assert.ok(stats.cached <= stats.limit);
      assert.equal(stats.limit,size.width<=720?32:56,JSON.stringify(size));
      if(size.width===390) {
        // The loading card fades once the first frame is drawn; it must be gone, not just fading.
        await page.waitForFunction(()=>getComputedStyle(document.querySelector('.gate-loading')).opacity==='0');
        await page.screenshot({path:path.join(output,'film-mobile.png')});
        for(const [p,name] of [[.08,'story-mobile-first.png'],[.82,'story-mobile-second.png']]) {
          await page.evaluate(p=>{
            const el=document.querySelector('.case-statement');
            scrollTo({top:PremiereScroll.top(el)+(el.offsetHeight-innerHeight)*p,behavior:'instant'});
          },p); await settle(page);
          await page.screenshot({path:path.join(output,name)});
        }
      }
    }
  });
  await check('Narrowing the window shrinks the frame budget without a reload',async()=>{
    await page.setViewportSize({width:1440,height:900}); await page.goto('about:blank'); await page.goto(base+'/premiere?intro=off#top'); await settle(page);
    for(const p of [.2,.5,.8]) await atFilm(page,p);
    await page.waitForFunction(()=>PremiereFilm.stats.pending===0);
    assert.ok((await page.evaluate(()=>PremiereFilm.stats.cached))>32,'the desktop cache should hold more than a phone budget before narrowing');
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(()=>PremiereFilm.stats.limit===32&&PremiereFilm.stats.cached<=32);
    await atFilm(page,.6);
    await page.waitForFunction(()=>PremiereFilm.stats.pending===0);
    assert.ok((await page.evaluate(()=>PremiereFilm.stats.cached))<=32);
  });
  await check('Title sequence plays on every load, deep links included, and can be skipped',async()=>{
    const p=await context.newPage(); p.on('pageerror',e=>errors.push(String(e)));
    const playing=()=>p.evaluate(()=>document.documentElement.classList.contains('intro-on')&&!!document.querySelector('.intro.running'));
    for(const url of ['/premiere','/premiere','/premiere#crew']) {     // a repeat load in one session, then a deep link
      await p.goto('about:blank'); await p.goto(base+url);
      assert.ok(await playing(),url);
    }
    // Left alone it runs to the end, takes its overlay away and leaves the page usable.
    await p.waitForFunction(()=>!document.querySelector('.intro')&&!document.documentElement.classList.contains('intro-on'),null,{timeout:9000});
    assert.equal(await p.locator('.intro-skip').count(),0);
    await p.goto('about:blank'); await p.goto(base+'/premiere');
    await p.waitForTimeout(3500); await p.screenshot({path:path.join(output,'intro-run.png')});
    await p.keyboard.press('Escape');
    await p.waitForFunction(()=>!document.querySelector('.intro'),null,{timeout:2000});
    await p.goto('about:blank'); await p.goto(base+'/premiere?intro=off');
    assert.equal(await playing(),false);
    await p.close();
  });
  await check('System reduced motion loads no sequence and remains accessible',async()=>{
    const c=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
    const p=await c.newPage(); let frames=0;
    p.on('request',r=>{if(r.url().includes('/scroll-frames/'))frames++;});
    await p.goto(base+'/premiere#crew'); await p.waitForLoadState('networkidle');
    assert.equal(await p.evaluate(()=>document.documentElement.classList.contains('intro-on')),false,'reduced motion gets no title sequence');
    assert.equal(frames,0); assert.ok(await p.locator('video').evaluate(el=>el.controls));
    await audit(p,'reduced-mobile');
    await p.emulateMedia({reducedMotion:'no-preference'}); await settle(p);
    assert.equal(await p.locator('body').evaluate(el=>el.classList.contains('film-static')),false);
    await c.close();
  });
  await check('Missing image sequence falls back to the video',async()=>{
    const p=await context.newPage();
    await p.route('**/scroll-frames/*.webp',r=>r.abort());
    await p.goto(base+'/premiere?intro=off#film');
    await p.waitForFunction(()=>document.querySelector('video').readyState>=2);
    assert.equal(await p.locator('.reel-canvas').evaluate(el=>el.classList.contains('is-ready')),false);
    await p.close();
  });
  await check('JavaScript-disabled reading keeps both story beats visible',async()=>{
    const c=await browser.newContext({javaScriptEnabled:false}); const p=await c.newPage();
    await p.goto(base+'/premiere');
    assert.equal(await p.locator('.statement-second').evaluate(el=>getComputedStyle(el).opacity),'1');
    await c.close();
  });
  await page.setViewportSize({width:1440,height:900}); await page.goto(base+'/premiere?intro=off#film'); await atFilm(page,.25);
  await check('Animated film passes serious/critical accessibility checks',()=>audit(page,'film-desktop'));
  // Diagnostic only: hardware/CI timings are not a universal frame-rate guarantee.
  const timing=await page.evaluate(()=>new Promise(resolve=>{
    let last=0; const gaps=[];
    function tick(t) {
      if(last) gaps.push(t-last); last=t; scrollBy(0,3);
      if(gaps.length<120) requestAnimationFrame(tick);
      else { gaps.sort((a,b)=>a-b); resolve({samples:gaps.length,medianMs:gaps[60],p95Ms:gaps[114],over34ms:gaps.filter(n=>n>34).length}); }
    } requestAnimationFrame(tick);
  }));
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({checks,errors,timing},null,2));
  console.log(JSON.stringify({checks:checks.length,timing}));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();});
