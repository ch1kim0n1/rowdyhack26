"""SSD1306 readout, in the same black and white as the dashboard.

On a machine with no I2C display, the same frame is written to oled-live.png.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rig import journal

log = logging.getLogger("rig.display")

FONT_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "ui-kit" / "fonts" / "LeagueGothic-Regular.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),
)
LIVE_PREVIEW = Path(__file__).resolve().parent / "oled-live.png"

_state = {"take": 0.0, "count": 0, "mode": "live", "case": 1138}  # live | lost | reveal


def _font(size: int):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


MID, SMALL = _font(16), _font(11)
BIGS = [_font(n) for n in (34, 28, 23, 19)]


def _text_width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return font.getlength(text)
    return font.getbbox(text)[2]


def _stamp(text: str) -> Image.Image:
    w, h = _text_width(MID, text) + 10, 22
    img = Image.new("1", (int(w), h))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, int(w) - 1, h - 1), outline=1, width=2)
    draw.text((5, 3), text, font=MID, fill=1)
    return img.rotate(6, expand=True)


def render(draw: ImageDraw.ImageDraw, blink: bool) -> None:
    s = _state
    draw.text((0, 0), f"CASE NO. {_state['case']}", font=SMALL, fill=1)
    if blink:
        draw.ellipse((101, 3, 106, 8), fill=1)
    draw.text((109, 0), "REC", font=SMALL, fill=1)
    draw.line((0, 13, 127, 13), fill=1)

    if s["mode"] == "reveal":
        st = _stamp("CASE CLOSED")
        draw.bitmap(((128 - st.width) // 2, 14), st, fill=1)
        draw.text((64, 62), f"TAKE ${s['take']:,.0f}", font=SMALL, fill=1, anchor="md")
        return
    if s["mode"] == "lost":
        draw.text((64, 32), "FOOTAGE LOST", font=MID, fill=1, anchor="mm")
        draw.text((64, 62), "RECONNECTING", font=SMALL, fill=1, anchor="md")
        return

    take = f"${s['take']:,.0f}"
    big = next((f for f in BIGS if _text_width(f, take) <= 128), BIGS[-1])
    draw.text((0, 33), take, font=big, fill=1, anchor="lm")
    for x in range(0, 128, 3):
        draw.point((x, 49), fill=1)
    draw.text((0, 63), f"EXHIBITS {s['count']:02d}", font=SMALL, fill=1, anchor="ld")
    draw.text((127, 63), "ESTIMATED", font=SMALL, fill=1, anchor="rd")


def show_take(take_usd: float, item_count: int, case_no: int | None = None) -> None:
    if case_no is not None:
        _state["case"] = int(case_no)
    _state.update(take=take_usd, count=item_count, mode="live")


def show_lost(lost: bool = True) -> None:
    """Footage state only. The case number stays put across a camera drop."""
    _state["mode"] = "lost" if lost else "live"


def show_reveal(case_no: int | None = None) -> None:
    if case_no is not None:
        _state["case"] = int(case_no)
    _state["mode"] = "reveal"


def start() -> None:
    try:
        from luma.core.interface.serial import i2c
        from luma.core.render import canvas
        from luma.oled.device import ssd1306
        device = ssd1306(i2c(port=1, address=0x3C))

        def _device():
            blink = True
            while True:
                with canvas(device) as draw:
                    render(draw, blink)
                blink = not blink
                time.sleep(0.5)

        threading.Thread(target=_device, daemon=True, name="oled").start()
        log.info("OLED on I2C 0x3C")
        journal.event("display-oled", True)
        return
    except Exception:
        log.info("no OLED; writing %s", LIVE_PREVIEW.name)
        journal.event("display-oled", False, "no I2C device; PNG preview fallback")

    def _file():
        blink = True
        while True:
            img = Image.new("1", (128, 64))
            render(ImageDraw.Draw(img), blink)
            img.convert("L").resize((512, 256), Image.Resampling.NEAREST).save(LIVE_PREVIEW)
            blink = not blink
            time.sleep(0.5)

    threading.Thread(target=_file, daemon=True, name="oled-preview").start()


if __name__ == "__main__":
    frames = []
    for mode, take, count in (
        ("live", 7420, 4), ("live", 1282600, 6), ("lost", 7420, 4), ("reveal", 7600, 5),
    ):
        _state.update(take=take, count=count, mode=mode)
        img = Image.new("1", (128, 64))
        render(ImageDraw.Draw(img), blink=True)
        assert img.getbbox(), f"{mode} rendered blank"
        frames.append(img.convert("L").resize((512, 256), Image.Resampling.NEAREST))
    sheet = Image.new("L", (512 * 2 + 24, 256 * 2 + 24), 40)
    for i, frame in enumerate(frames):
        sheet.paste(frame, ((i % 2) * (512 + 24), (i // 2) * (256 + 24)))
    out = Path(__file__).resolve().parent / "oled-preview.png"
    sheet.save(out)
    print(out)
