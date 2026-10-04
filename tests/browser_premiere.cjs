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
    for(const asset of ['premiere-scroll.js','premiere-scroll.css','premiere-sequence.js','premiere-diamond-type.js','scroll-cinema.js','motion-presets.js','webgl-scenes.js','cinematic-motion.css','anime.min.js','media/crew-hat-wrist.webp','media/crew-hat.webp','media/scroll-frames/manifest.json'])
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
      // Every entrance mid-way: the worst case for something sliding in from beyond the edge.
      for(const sel of ['#crew-title','#method-title','.credit-list']) {
        await page.evaluate(sel=>{ const el=document.querySelector(sel); scrollTo({top:PremiereScroll.top(el)-innerHeight*.8,behavior:'instant'}); },sel); await settle(page);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${sel} at ${JSON.stringify(size)}`);
      }
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
  await check('Every scene has a progress, and an entrance follows the scroll forward and back',async()=>{
    await page.setViewportSize({width:1440,height:900}); await page.goto('about:blank'); await page.goto(base+'/premiere?intro=off#top'); await settle(page);
    assert.deepEqual(await page.evaluate(()=>ScrollCinema.scenes.map(s=>s.name)),['premiere','hero','film','crew','story','method','paperwork','credits']);
    assert.ok(await page.evaluate(()=>document.documentElement.classList.contains('cine-on')&&ScrollCinema.motion.live&&ScrollCinema.motion.elements>30));
    // The crew's title, with its top `at` window-heights down the window.
    const title=async at=>{
      await page.evaluate(at=>{ const el=document.querySelector('#crew-title'); scrollTo({top:PremiereScroll.top(el)-innerHeight*at,behavior:'instant'}); },at); await settle(page);
      return page.evaluate(()=>{
        const el=document.querySelector('#crew-title'), glyphs=[...el.querySelectorAll('.ch')];
        const down=g=>{ const t=getComputedStyle(g).translate; return t==='none'?0:parseFloat(t.split(' ')[1]); };
        return {first:down(glyphs[0]), last:down(glyphs.at(-1)), rising:el.classList.contains('is-rising'),
          shown:Number(getComputedStyle(el).opacity), lifted:parseFloat(el.style.translate.split(' ')[1])||0,
          label:Number(getComputedStyle(document.querySelector('.crew .section-head .label')).opacity),
          lede:getComputedStyle(document.querySelector('.crew .section-lede')).filter, text:el.getAttribute('aria-label'), scene:ScrollCinema.motion.activeScene};
      });
    };
    const below=await title(1.1), part=await title(.78), rest=await title(.3), leaving=await title(-.02), gone=await title(-.3), back=await title(1.1);
    assert.deepEqual([below.first,below.last,below.rising,below.label],[125,125,true,0],`out of sight below the window: ${JSON.stringify(below)}`);
    assert.ok(part.first<part.last&&part.first<125&&part.last>0&&part.rising,`the glyphs rise one after another: ${JSON.stringify(part)}`);
    assert.deepEqual([rest.first,rest.last,rest.rising,rest.label,rest.lede,rest.scene],[0,0,false,1,'none','crew'],`at rest nothing of the motion is left on it: ${JSON.stringify(rest)}`);
    // It has a way out as well: it lifts away as it nears the marquee, and once it is above the window it is put back as it was.
    assert.ok(leaving.shown>0&&leaving.shown<.6&&leaving.lifted<0&&!leaving.rising,`on its way out under the marquee: ${JSON.stringify(leaving)}`);
    assert.deepEqual([gone.shown,gone.lifted,gone.label],[1,0,1],`out of the window nothing is left hidden: ${JSON.stringify(gone)}`);
    assert.deepEqual(back,below,'scrolling back runs it all backwards');
    assert.equal(rest.text,'The Crew','the title is still read as its words');
    assert.equal(await page.locator('.crew').getAttribute('data-active'),'true');
    await title(.6); await page.screenshot({path:path.join(output,'crew-entrance-desktop.png')});
  });
  await check('A film caption arrives and leaves by the film\'s own time, in both directions',async()=>{
    const at=async seconds=>{ await atFilm(page,seconds/(501/24)); return page.evaluate(()=>{ const el=document.querySelector('.reel-line');
      return {text:el.textContent, shown:Number(getComputedStyle(el).opacity), y:parseFloat(el.style.translate.split(' ')[1])||0}; }); };
    const arriving=await at(4.8), held=await at(5.6), going=await at(6.4), next=await at(6.7), again=await at(5.6);
    assert.match(held.text,/the cap takes a look/); assert.match(next.text,/the rig prices it/);
    assert.ok(arriving.text===held.text&&arriving.shown>0&&arriving.shown<1&&arriving.y>0,`coming up into place: ${JSON.stringify(arriving)}`);
    assert.deepEqual([held.shown,held.y],[1,0],'held, with nothing of the motion on it');
    assert.ok(going.text===held.text&&going.shown<1&&going.y<0,`lifting away before the next: ${JSON.stringify(going)}`);
    assert.ok(next.shown<1&&next.y>0,`the next one arriving: ${JSON.stringify(next)}`);
    assert.deepEqual(again,held,'and back again');
  });
  await check('The method board lays each print by the scroll, and a scene recedes as the next arrives',async()=>{
    const board=async into=>{      // `into`: how far through the first step the middle of the window is
      await page.evaluate(into=>{ const s=[...document.querySelectorAll('.step')].map(el=>PremiereScroll.top(el));
        scrollTo({top:s[0]+(s[1]-s[0])*into-innerHeight*.5,behavior:'instant'}); },into); await settle(page);
      return page.evaluate(()=>[...document.querySelectorAll('.board-print')].map(el=>Number(getComputedStyle(el).opacity)));
    };
    assert.deepEqual(await board(.3),[1,0,0,0,0,0]);
    const half=await board(.8);
    assert.ok(half[0]===1&&Math.abs(half[1]-.5)<.02&&half.slice(2).every(o=>o===0),`the second print is half laid over the first: ${half}`);
    await page.screenshot({path:path.join(output,'board-dissolve-desktop.png')});
    assert.deepEqual(await board(1.05),[0,1,0,0,0,0]);
    assert.deepEqual(await board(.3),[1,0,0,0,0,0],'and lifted again on the way back');
    // The crew's files are still on screen, dimmed and sinking, while the method's head is arriving.
    await page.evaluate(()=>{ const el=document.querySelector('.method'); scrollTo({top:PremiereScroll.top(el)-innerHeight*.45,behavior:'instant'}); }); await settle(page);
    const overlap=await page.evaluate(()=>({files:Number(getComputedStyle(document.querySelector('.dossiers')).opacity),
      bottom:document.querySelector('.dossiers').getBoundingClientRect().bottom, head:document.querySelector('#method-title').getBoundingClientRect().top, vh:innerHeight}));
    assert.ok(overlap.files<1&&overlap.files>.15&&overlap.bottom>0&&overlap.head<overlap.vh,`one scene overlaps the next: ${JSON.stringify(overlap)}`);
  });
  await check('The story photographs dissolve through WebGL, and through the CSS crossfade where there is none',async()=>{
    const plate=async p=>{ await atStory(page,p); return page.locator('.statement-plate').screenshot(); };
    await atStory(page,.2);
    await page.waitForFunction(()=>document.querySelector('.statement-morph')?.dataset.running==='true');
    const first=await plate(.2), mid=await plate(.38), second=await plate(.55);
    assert.ok(!first.equals(mid)&&!mid.equals(second)&&!first.equals(second),'the plate shows three different pictures at the start, the middle and the end of the dissolve');
    fs.writeFileSync(path.join(output,'story-morph-desktop.png'),mid);
    assert.deepEqual(await page.evaluate(()=>[...document.querySelectorAll('.statement-image')].map(i=>[getComputedStyle(i).opacity,!!i.alt])),[['0',true],['0',true]],'the photographs stay in the page, with their alt text, under the canvas');
    const c=await browser.newContext({viewport:{width:1440,height:900}}); const p=await c.newPage(); p.on('pageerror',e=>errors.push(String(e)));
    await p.addInitScript(()=>{ const real=HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext=function(kind,...rest){ return /webgl/.test(kind)?null:real.call(this,kind,...rest); }; });
    await p.goto(base+'/premiere?intro=off#top'); await settle(p); await atStory(p,.38);
    const plain=await p.evaluate(()=>({morph:!!document.querySelector('.statement-morph'), on:document.querySelector('.statement-plate').classList.contains('is-morphing'),
      room:getComputedStyle(document.querySelector('.statement-room')).opacity, evidence:Number(getComputedStyle(document.querySelector('.statement-evidence')).opacity)}));
    assert.deepEqual([plain.morph,plain.on,plain.room],[false,false,'1']);
    assert.ok(Math.abs(plain.evidence-.5)<.02,`without WebGL the second photograph fades across: ${JSON.stringify(plain)}`);
    await c.close();
  });
  await check('Pausing clears every entrance, navigation still works, and a settled scene passes the audit',async()=>{
    await page.evaluate(()=>{ const el=document.querySelector('#paperwork-title'); scrollTo({top:PremiereScroll.top(el)-innerHeight*1.2,behavior:'instant'}); }); await settle(page);
    const state=()=>page.evaluate(()=>({live:document.documentElement.classList.contains('cine-on'),
      moved:[...document.querySelectorAll('[data-motion], [data-motion] .ch, .motion-char, .reel-line, .board-print, .dossiers, .method-grid')].filter(el=>el.style.translate||el.style.opacity||el.style.filter||el.style.scale).length}));
    const running=await state(); assert.ok(running.live&&running.moved>20,JSON.stringify(running));
    await page.getByRole('button',{name:'Pause motion',exact:true}).click(); await settle(page);
    assert.deepEqual(await state(),{live:false,moved:0});
    await page.getByRole('button',{name:'Resume motion',exact:true}).click(); await settle(page);
    assert.ok((await state()).live);
    // The marquee's links still take the page to their section, whose head has then arrived.
    await page.evaluate(()=>scrollTo({top:0,behavior:'instant'})); await settle(page);
    await page.locator('.marquee-nav').getByRole('link',{name:'The Method',exact:true}).click(); await settle(page);
    await page.waitForFunction(()=>ScrollCinema.motion.activeScene==='method'&&!document.querySelector('#method-title').classList.contains('is-rising'));
    assert.ok(await page.evaluate(()=>{ const r=document.querySelector('#method-title').getBoundingClientRect(); return r.top>=0&&r.bottom<=innerHeight; }));
    await page.screenshot({path:path.join(output,'method-desktop.png')});
    await audit(page,'method-desktop');
    await page.evaluate(()=>scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})); await settle(page);
    assert.ok(await page.evaluate(()=>[...document.querySelectorAll('.credits [data-motion], .credits .motion-char')].every(el=>!el.style.opacity&&!el.style.translate)),'at the foot of the page every credit has arrived');
    await page.waitForTimeout(1200);      // the volley at THE END finishes; its flashes are not what is being audited
    await audit(page,'credits-desktop');
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
    // A reload plays it again over the top of the page: not where the page was left, nor at a #section it had been taken to.
    for(const url of ['/premiere','/premiere#crew']) {
      await p.goto('about:blank'); await p.goto(base+url); await p.keyboard.press('Escape');
      await p.waitForFunction(()=>!document.querySelector('.intro'),null,{timeout:2000});
      await p.evaluate(()=>scrollTo({top:PremiereScroll.top(document.querySelector('#method')),behavior:'instant'})); await settle(p);
      assert.ok(await p.evaluate(()=>scrollY>innerHeight*4),url);
      await p.reload();
      assert.ok(await playing(),`reloaded ${url}`);
      await p.waitForFunction(()=>!document.querySelector('.intro'),null,{timeout:9000}); await settle(p);
      assert.deepEqual(await p.evaluate(()=>[scrollY,location.hash,history.scrollRestoration]),[0,'','auto'],`reloaded ${url}`);
    }
    // A link to a section still lands on it.
    await p.goto('about:blank'); await p.goto(base+'/premiere#crew'); await p.keyboard.press('Escape');
    await p.waitForFunction(()=>!document.querySelector('.intro'),null,{timeout:2000}); await settle(p);
    assert.ok(await p.evaluate(()=>scrollY>innerHeight&&location.hash==='#crew'));
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
    const still=()=>p.evaluate(()=>({live:document.documentElement.classList.contains('cine-on'), built:ScrollCinema.motion.elements,
      masks:document.querySelectorAll('.motion-mask, .motion-char').length, morph:document.querySelector('.statement-plate').classList.contains('is-morphing'),
      moved:[...document.querySelectorAll('[data-motion], [data-motion] .ch, .motion-char, .reel-line, .board-print, .dossiers, .method-grid')]
        .filter(el=>el.style.translate||el.style.opacity||el.style.filter||el.style.scale).length}));
    assert.deepEqual(await still(),{live:false,built:0,masks:0,morph:false,moved:0},'reduced motion builds no scene motion and leaves none on the page');
    await audit(p,'reduced-mobile');
    await p.emulateMedia({reducedMotion:'no-preference'}); await settle(p);
    assert.equal(await p.locator('body').evaluate(el=>el.classList.contains('film-static')),false);
    const awake=await still(); assert.ok(awake.live&&awake.built>30,`motion allowed again brings the scenes back: ${JSON.stringify(awake)}`);
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
