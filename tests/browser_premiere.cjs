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
async function atStory(page, p) {
  await page.evaluate(p => {
    const el = document.querySelector('.case-statement');
    scrollTo({top:PremiereScroll.top(el) + (el.offsetHeight - innerHeight) * p, behavior:'instant'});
  }, p);
  await settle(page);
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
    for(const asset of ['premiere-scroll.js','premiere-scroll.css','premiere-sequence.js','premiere-diamond-type.js','media/crew-hat-wrist.webp','media/crew-hat.webp','media/scroll-frames/manifest.json'])
    { const res=await fetch(base+'/'+asset); await res.arrayBuffer(); assert.equal(res.status,200,asset); }   // read it: an unread image body crashes Node's fetch when the server closes
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
    for(const p of [0,.68,.1]) {
      await page.evaluate(p=>{
        const el=document.querySelector('.case-statement');
        scrollTo({top:PremiereScroll.top(el)+(el.offsetHeight-innerHeight)*p,behavior:'instant'});
      },p); await settle(page);
      const opacity=await page.locator('.statement-second').evaluate(el=>Number(getComputedStyle(el).opacity));
      assert.ok(p>.6?opacity>.95:opacity<.05, `story progress=${p}, opacity=${opacity}`);
      if(p>.6) await page.screenshot({path:path.join(output,'story-desktop.png')});
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
        for(const [p,name] of [[.08,'story-mobile-first.png'],[.68,'story-mobile-second.png']]) {
          await page.evaluate(p=>{
            const el=document.querySelector('.case-statement');
            scrollTo({top:PremiereScroll.top(el)+(el.offsetHeight-innerHeight)*p,behavior:'instant'});
          },p); await settle(page);
          await page.waitForFunction(()=>[...document.querySelectorAll('.statement-line')].every(l=>getComputedStyle(l).opacity==='0'));   // type out, stones alone
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
  await check('Story scene: photographs on a flush plate, type flush beside it, headlines set in stones',async()=>{
    await page.setViewportSize({width:1440,height:900}); await page.goto('about:blank'); await page.goto(base+'/premiere?intro=off#top'); await settle(page);
    await atStory(page,.08);
    await page.waitForFunction(()=>[...document.querySelectorAll('.statement-image')].every(i=>i.complete&&i.naturalWidth>0));
    await page.waitForFunction(()=>document.querySelector('.statement-first .statement-stones')?.dataset.running==='true'
      &&getComputedStyle(document.querySelector('.statement-first .statement-line')).opacity==='0');
    const g=await page.evaluate(()=>{
      const box=s=>document.querySelector(s).getBoundingClientRect();
      const range=document.createRange(); range.selectNodeContents(document.querySelector('.statement-first .statement-line'));
      const type=[...range.getClientRects()].filter(r=>r.width);
      const plate=box('.statement-plate'), stage=box('.statement-stage'), foot=box('.statement-foot');
      return {plate:{l:plate.left,t:plate.top,r:plate.right,b:plate.bottom}, stage:{t:box('.marquee').bottom,r:stage.right,b:stage.bottom},
        typeLeft:Math.min(...type.map(r=>r.left)), typeRight:Math.max(...type.map(r=>r.right)), footLeft:foot.left, footRight:foot.right,
        stones:[...document.querySelectorAll('.statement-stones')].map(c=>Number(c.dataset.particleCount)),
        srcs:[...document.querySelectorAll('.statement-image')].map(i=>i.getAttribute('src'))};
    });
    assert.deepEqual(g.srcs,['media/crew-hat-wrist.webp','media/crew-hat.webp']);
    for(const side of ['t','r','b']) assert.ok(Math.abs(g.plate[side]-g.stage[side])<=1,`plate is flush on ${side}: ${JSON.stringify(g)}`);
    assert.ok(g.typeRight<=g.plate.l&&g.plate.l-g.typeRight<64,`longest line ends at the plate: ${JSON.stringify(g)}`);
    assert.ok(Math.abs(g.typeLeft-g.footLeft)<=3&&g.footRight<=g.plate.l,`type and footer share one gutter: ${JSON.stringify(g)}`);
    assert.ok(g.stones.length===2&&g.stones.every(n=>n>3000),`both headlines are set in stones: ${g.stones}`);
    await audit(page,'story-desktop');
    // No section is ruled off or ends on an edge. By the time the scene lets go, everything on it has left...
    assert.equal(await page.locator('.statement-rule').count(),0);
    await atStory(page,.995);
    const gone=await page.evaluate(()=>['.statement-plate','.statement-second','.statement-foot'].map(s=>Number(getComputedStyle(document.querySelector(s)).opacity)));
    assert.ok(gone.every(o=>o<.02),`plate, type and footer have left before the scene lets go: ${gone}`);
    // ...and its ground thins out into the next section's. Measured in the page margin, where there is only ground:
    // a block ending or a ruled line would show as a jump in brightness between two neighbouring rows.
    const probe=await context.newPage();
    for(const beyond of [.2,.45,.7]) {
      await page.evaluate(v=>{
        const el=document.querySelector('.case-statement');
        scrollTo({top:PremiereScroll.top(el)+el.offsetHeight-innerHeight+v*innerHeight,behavior:'instant'});
      },beyond); await settle(page);
      const jump=await probe.evaluate(async b64=>{
        const img=new Image(); img.src='data:image/png;base64,'+b64; await img.decode();
        const c=document.createElement('canvas'); c.width=img.width; c.height=img.height;
        const g=c.getContext('2d'); g.drawImage(img,0,0);
        const w=Math.round(img.width*.03), d=g.getImageData(Math.round(img.width*.004),0,w,img.height).data;
        let worst=0, prev=null;
        for(let r=Math.round(img.height*.12); r<img.height-2; r++) {
          let sum=0; for(let i=r*w*4,e=i+w*4; i<e; i+=4) sum+=d[i]*.299+d[i+1]*.587+d[i+2]*.114;
          if(prev!==null) worst=Math.max(worst,Math.abs(sum/w-prev)); prev=sum/w;
        }
        return worst;
      },(await page.screenshot()).toString('base64'));
      assert.ok(jump<3,`no hard edge where the story ends (${beyond} screens past): brightest row-to-row jump ${jump.toFixed(1)} of 255`);
    }
    await probe.close();
    await page.screenshot({path:path.join(output,'story-first-desktop.png')});
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
    assert.equal(await p.locator('.statement-first .statement-stones').evaluate(el=>el.dataset.running),'false');
    assert.equal(await p.locator('.statement-first .statement-line').evaluate(el=>getComputedStyle(el).opacity),'1');
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
  // The marquee fades out as the film starts; audited mid-fade, its button reads as low contrast.
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('.marquee')).opacity==='0');
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
