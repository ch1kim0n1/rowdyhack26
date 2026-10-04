"""Rebuilds packs/assets and packs/animation from the live kit.

Every PNG and every clip is rendered by the real noir.css and noir.js, so the packs
can't drift from the code. Run after changing the kit:

    pip install playwright pillow && playwright install chromium   # or use installed Chrome
    python packs/tools/build_packs.py                               # needs ffmpeg on PATH

Takes about three minutes. Fonts in packs/fonts are downloaded, not generated.
"""
import pathlib, shutil, subprocess, time
from playwright.sync_api import sync_playwright

KIT = pathlib.Path(__file__).resolve().parents[2]            # ui-kit/
PACKS = KIT / "packs"
PNG, SVG, ANIM = PACKS / "assets" / "png", PACKS / "assets" / "svg", PACKS / "animation"
TMP = PACKS / "tools" / ".tmp"
for d in (PNG, SVG, ANIM, TMP): d.mkdir(parents=True, exist_ok=True)
DEMO = (KIT / "demo.html").as_uri()

FILTERS = """<svg width="0" height="0" style="position:absolute"><defs>
<filter id="noir-grade"><feComponentTransfer><feFuncR type="table" tableValues="0.02 0.10 0.50 0.88 0.97"/><feFuncG type="table" tableValues="0.02 0.10 0.50 0.88 0.97"/><feFuncB type="table" tableValues="0.02 0.10 0.50 0.88 0.97"/></feComponentTransfer></filter>
<filter id="rough" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="1.5"/></filter>
<filter id="stamp-rough" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="4"/></filter>
</defs></svg>"""

def harness(body, css="", bg="transparent"):
    """A page that loads the kit's own CSS and JS from ui-kit/."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><base href="{KIT.as_uri()}/">
<link rel="stylesheet" href="noir.css"><style>html,body{{background:{bg};height:auto}} .a{{display:inline-block;padding:24px}} {css}</style></head>
<body>{FILTERS}{body}<script src="noir.js"></script></body></html>"""

def page_from(html, name):
    f = TMP / f"{name}.html"; f.write_text(html, encoding="utf-8"); return f.as_uri()

# ---------------------------------------------------------------- assets
ASSETS = {
  "stamp-case-closed":   '<div class="a"><div class="stamp" style="transform:rotate(-6deg)">Case Closed</div></div>',
  "stamp-case-unsolved": '<div class="a"><div class="stamp" style="transform:rotate(-3deg)">Case Unsolved</div></div>',
  "stamp-approved":      '<div class="a"><div class="stamp" style="transform:rotate(6deg)">Approved</div></div>',
  "stamp-rejected":      '<div class="a"><div class="stamp" style="transform:rotate(-8deg)">Rejected</div></div>',
  "stamp-evidence-paper":'<div class="a"><div class="stamp" style="transform:rotate(-14deg);font-size:44px;border-color:var(--stamp);color:var(--stamp);opacity:.85">Evidence</div></div>',
  "stamp-filed-paper":   '<div class="a"><div class="stamp" style="transform:rotate(5deg);font-size:16px;border-color:var(--stamp);color:var(--stamp);opacity:.85">Filed 09/26/2026</div></div>',
  "marker":              '<div class="a" style="padding:34px 40px 40px"><div class="marker" style="position:relative;width:260px;height:190px;animation:none"><span class="tag">Exhibit 07</span><span class="cap">"WATCH, WRIST" · $4,200</span></div></div>',
  "marker-top5":         '<div class="a" style="padding:34px 40px 40px"><div class="marker" style="position:relative;width:260px;height:190px;animation:none"><span class="tag" style="background:var(--paper);color:var(--ink)">Exhibit 07</span><span class="cap">"WATCH, WRIST" · $4,200</span></div></div>',
  "placard":             '<div class="a"><div class="suspect in" style="width:260px"><div class="photo" style="animation:none"><div class="placard">Suspect No. 1</div></div></div></div>',
  "picture-start":       '<div class="a" style="background:var(--carbon);padding:60px 90px"><div style="font-family:var(--f-display);font-size:120px;line-height:.9;letter-spacing:.08em;text-align:center;text-transform:uppercase;color:var(--paper)">Picture<br>Start</div></div>',
  "cue-mark":            '<div class="a"><div style="width:48px;aspect-ratio:1;border-radius:50%;background:var(--paper);filter:url(#stamp-rough);opacity:.9"></div></div>',
  "film-band-top":       '<div class="a" style="padding:0"><div class="film-band top" style="width:1200px"></div></div>',
  "film-band-bottom":    '<div class="a" style="padding:0"><div class="film-band bot" style="width:1200px"><div class="film-label">Roll A · Cam 01 · Room 3</div></div></div>',
  "the-end-title":       '<div class="a" style="background:var(--ink);padding:40px 80px"><div class="t-view cut" style="font-size:220px;line-height:.85">The End</div></div>',
  "title-lettering":     '<div class="a" style="background:var(--ink);padding:40px 80px"><div class="tc-title cut" style="font-size:200px;text-align:center">The<br>Appraisal<br>Job</div></div>',
  "grain-tile":          '<div id="g" style="width:160px;height:160px;background-image:url(\'data:image/svg+xml;utf8,<svg xmlns=&quot;http://www.w3.org/2000/svg&quot; width=&quot;160&quot; height=&quot;160&quot;><filter id=&quot;n&quot;><feTurbulence type=&quot;fractalNoise&quot; baseFrequency=&quot;0.9&quot; numOctaves=&quot;2&quot; stitchTiles=&quot;stitch&quot;/><feColorMatrix type=&quot;saturate&quot; values=&quot;0&quot;/></filter><rect width=&quot;160&quot; height=&quot;160&quot; filter=&quot;url(%23n)&quot;/></svg>\')"></div>',
}
for n in "8 7 SIX 5 4 3".split():
    ASSETS[f"leader-{n.lower()}"] = f'<div class="a" style="background:var(--carbon)"><div class="leader" data-static style="width:360px"><span class="leader-n{" word" if len(n) > 1 else ""}">{n}</span></div></div>'

SVGS = {
  "favicon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#0f0e0c"/><rect x="6" y="3" width="20" height="26" fill="#efe9db"/><g fill="#0f0e0c"><rect x="8" y="5" width="3" height="3"/><rect x="8" y="11" width="3" height="3"/><rect x="8" y="17" width="3" height="3"/><rect x="8" y="23" width="3" height="3"/><rect x="21" y="5" width="3" height="3"/><rect x="21" y="11" width="3" height="3"/><rect x="21" y="17" width="3" height="3"/><rect x="21" y="23" width="3" height="3"/></g></svg>""",
  "registration-mark.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12" width="12" height="12"><path d="M0.5 12V0.5H12" fill="none" stroke="#d8d4c7" stroke-opacity=".5"/></svg>""",
  "leader-frame.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200"><rect width="200" height="200" fill="#1a1916"/><circle cx="100" cy="100" r="98" fill="none" stroke="#d8d4c7" stroke-width="2"/><circle cx="100" cy="100" r="87" fill="none" stroke="#57564f"/><path d="M100 2V198M2 100H198" stroke="#57564f"/></svg>""",
  "cue-mark.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40"><circle cx="20" cy="20" r="19" fill="#efe9db" fill-opacity=".9"/></svg>""",
  "sprocket-strip.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 16" width="520" height="16"><rect width="520" height="16" fill="#1a1916"/><g fill="#0f0e0c">""" + "".join(f'<circle cx="{13 + 26*i}" cy="8" r="4"/>' for i in range(20)) + """</g></svg>""",
  "marker-frame.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 230" width="280" height="230"><rect x="10.5" y="30.5" width="260" height="190" fill="none" stroke="#000" stroke-opacity=".4" stroke-width="3"/><rect x="10.5" y="30.5" width="260" height="190" fill="none" stroke="#d8d4c7"/><rect x="10.5" y="10.5" width="86" height="20" fill="#0f0e0c" stroke="#d8d4c7"/><text x="53.5" y="24" text-anchor="middle" font-family="Courier Prime, Courier New, monospace" font-size="10" letter-spacing="1.2" fill="#efe9db">EXHIBIT 07</text></svg>""",
  "title-card-bars.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 900" width="1440" height="900"><rect width="1440" height="900" fill="#0f0e0c"/><g fill="#efe9db">
<polygon points="129.6,16.7 158.4,0 201.6,11.2 201.6,541.2 174.6,558 129.6,546.8"/>
<polygon points="244.8,198 254.3,198 276.5,212 276.5,882.4 262.3,900 244.8,896.5"/>
<polygon points="1224,72 1264.3,72 1324.8,82.1 1324.8,683.1 1287,702 1224,695.7"/>
<polygon points="0,630 662.4,633.5 655.8,658.8 0,655"/>
<polygon points="892.8,153 1440,155.8 1434.5,167.4 892.8,165"/></g></svg>""",
}
for name, (text, rot, size, color) in {"stamp-case-closed": ("CASE CLOSED", -6, 30, "#d9604f"), "stamp-evidence": ("EVIDENCE", -14, 44, "#a5382f"),
                                       "stamp-filed": ("FILED 09/26/2026", 5, 16, "#a5382f"), "stamp-case-unsolved": ("CASE UNSOLVED", -3, 30, "#d9604f")}.items():
    w = int(len(text) * size * .62 + size * 1.4); h = int(size * 1.5)
    SVGS[f"{name}.svg"] = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w + 40} {h + 60}" width="{w + 40}" height="{h + 60}"><defs><filter id="r" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="4"/></filter></defs>
<g transform="rotate({rot} {(w + 40) / 2} {(h + 60) / 2})" filter="url(#r)" opacity=".9"><rect x="20" y="30" width="{w}" height="{h}" rx="3" fill="none" stroke="{color}" stroke-width="3"/>
<text x="{(w + 40) / 2}" y="{30 + h * .72}" text-anchor="middle" font-family="League Gothic, Bebas Neue, Impact, sans-serif" font-size="{size}" letter-spacing="{size * .12:.1f}" fill="{color}">{text}</text></g></svg>"""

def build_assets(b):
    for f, s in SVGS.items(): (SVG / f).write_text(s, encoding="utf-8")
    ctx = b.new_context(device_scale_factor=2, viewport={"width": 1600, "height": 900})
    for name, body in ASSETS.items():
        pg = ctx.new_page(); pg.goto(page_from(harness(body), name)); pg.wait_for_timeout(250)
        target = pg.locator("#g") if name == "grain-tile" else pg.locator(".a").first
        target.screenshot(path=str(PNG / f"{name}.png"), omit_background=True); pg.close()
    # sheets from the Case Index: palette, type, components
    kp = ctx.new_page(); kp.set_viewport_size({"width": 1440, "height": 900}); kp.goto((KIT / "kit.html").as_uri()); kp.wait_for_timeout(1200)
    kp.locator("#swatches").screenshot(path=str(PNG / "sheet-palette.png"))
    kp.locator("#typerows").screenshot(path=str(PNG / "sheet-type.png"))
    kp.locator("#components").screenshot(path=str(PNG / "sheet-components.png"))
    kp.locator("#states table").screenshot(path=str(PNG / "sheet-states.png"))
    ctx.close()
    # cover stills straight from the demo at 1920x1080 and a 3:2 thumbnail
    cc = b.new_context(viewport={"width": 1920, "height": 1080})
    cp = cc.new_page(); cp.goto(DEMO); cp.wait_for_timeout(300); cp.keyboard.press("?"); cp.wait_for_timeout(6500)
    cp.screenshot(path=str(PNG / "cover-title-1920x1080.png"))
    cp.set_viewport_size({"width": 1500, "height": 1000}); cp.wait_for_timeout(600)
    cp.screenshot(path=str(PNG / "cover-title-1500x1000.png"))
    for state in ("live", "reveal"):
        sp = cc.new_page(); sp.goto(DEMO + "#" + state); sp.wait_for_timeout(7500)
        sp.screenshot(path=str(PNG / f"cover-{state}-1920x1080.png")); sp.close()
    cc.close()
    shutil.copy(KIT / "oled-preview.png", PNG / "oled-preview.png")

# ---------------------------------------------------------------- animation
def to_media(webm, name, start, dur, width):
    base = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, start):.2f}", "-t", f"{dur:.2f}", "-i", str(webm)]
    subprocess.run(base + ["-vf", f"scale={width}:-2:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(ANIM / f"{name}.mp4")], check=True)
    subprocess.run(base + ["-vf", f"fps=12,scale={min(width, 720)}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                           str(ANIM / f"{name}.gif")], check=True)

def record(b, name, url, size, script, dur, width=1280):
    """script(page) runs the moment and returns seconds to skip from the start of the clip."""
    ctx = b.new_context(viewport=size, record_video_dir=str(TMP), record_video_size=size)
    pg = ctx.new_page(); t0 = time.time(); pg.goto(url)
    start = script(pg, lambda: time.time() - t0)
    pg.wait_for_timeout(int(dur * 1000) + 300)
    webm = pg.video.path(); ctx.close()
    to_media(webm, name, start, dur, width)

FULL = {"width": 1280, "height": 800}
def at(pg, ms): pg.wait_for_timeout(ms)

def build_animation(b):
    def reel(pg, now): pg.keyboard.press("?"); return now() - .1        # hide the demo key hint
    record(b, "reel-start", DEMO, FULL, reel, 5.2)

    def title(pg, now): pg.keyboard.press("?"); at(pg, 5600); return now()
    record(b, "title-card", DEMO, FULL, title, 12.5, 960)

    def beat(pg, now):
        pg.keyboard.press("?"); at(pg, 5600); pg.evaluate("Noir.exitIdle()"); t = now(); pg.evaluate("scan(LOOT[0])"); return t - .2
    record(b, "scan-beat", DEMO, FULL, beat, 3.6)

    def reveal(pg, now): at(pg, 2500); t = now(); pg.keyboard.press("r"); return t - .4
    record(b, "reveal", DEMO + "#live", FULL, reveal, 7.4)

    # THE END on its own page, so nothing follows it into the clip
    end_url = page_from(harness('<div class="grain"></div><div class="flicker"></div><div class="vignette"></div>', "", "var(--ink)"), "anim-the-end")
    def end(pg, now): at(pg, 500); t = now(); pg.evaluate("Noir.theEnd()"); return t - .15
    record(b, "the-end", end_url, FULL, end, 3.5)

    def lost(pg, now): at(pg, 2500); t = now(); pg.keyboard.press("f"); return t - .2
    record(b, "footage-lost", DEMO + "#live", FULL, lost, 4.2)

    def dead(pg, now): at(pg, 2500); t = now(); pg.keyboard.press("w"); return t - .2
    record(b, "line-dead", DEMO + "#live", FULL, dead, 4.2)

    # component loops at 2x on ink
    comp = {"width": 640, "height": 400}
    def one(name, body, js, dur, css=""):
        url = page_from(harness(f'<div style="display:grid;place-items:center;height:400px">{body}</div>', css, "var(--ink)"), "anim-" + name)
        def go(pg, now): at(pg, 400); t = now(); pg.evaluate(js); return t - .15
        record(b, name, url, comp, go, dur, 640)
    one("stamp-slam", '<div id="w"><div class="stamp" id="s" style="--rot:-6deg;opacity:0;font-size:56px">Case Closed</div></div>',
        "const s=document.getElementById('s');s.style.opacity=1;s.classList.add('enter');setTimeout(()=>document.getElementById('w').classList.add('shake'),250)", 1.4)
    one("odometer-roll", '<div class="odo" id="o" style="font-size:150px"></div>',
        "window.o=Noir.makeOdo(document.getElementById('o'));setTimeout(()=>o.set(7420),50)", 2.0)
    one("typewriter-line", '<div class="log" style="flex:none;width:560px;font-size:20px"><div class="log-line" id="l"><span class="txt"></span><span class="leaders"></span><span class="amt"></span></div></div>',
        "Noir.typeInto(document.getElementById('l'),'EXHIBIT 07: \"WATCH, WRIST\"','$4,200.00')", 1.6)
    one("marker-in", '<div style="position:relative;width:420px;height:260px;background:radial-gradient(ellipse at 40% 40%,#2e2c26,#0a0908)"><div id="m" style="position:absolute;inset:0"></div></div>',
        "document.getElementById('m').innerHTML='<div class=\"marker hot\" style=\"left:18%;top:22%;width:50%;height:56%\"><span class=\"tag\">Exhibit 07</span><span class=\"cap\">\"WATCH, WRIST\" · $4,200</span></div>'", 1.4)
    one("hard-cut", '<div style="position:relative;width:560px;height:350px" class="feed" id="f"><div style="position:absolute;inset:0;background:radial-gradient(ellipse at 40% 40%,#2e2c26,#0a0908)"></div><div class="cut"></div></div>',
        "const f=document.getElementById('f');f.classList.add('cutting')", 0.8)
    one("film-texture", '<div class="t-view">Reel 1</div><div class="grain"></div><div class="flicker"></div><div class="vignette"></div><div id="scratch"></div>',
        "0", 4.0)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        build_assets(b)
        build_animation(b)
        b.close()
    shutil.rmtree(TMP, ignore_errors=True)
    for d in (PNG, SVG, ANIM):
        files = sorted(x for x in d.iterdir() if x.is_file())
        print(f"{d.relative_to(PACKS)}: {len(files)} files, {sum(x.stat().st_size for x in files) // 1024} KB")

if __name__ == "__main__":
    main()
