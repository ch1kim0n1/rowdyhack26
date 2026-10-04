#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from whisplay_client import create_whisplay_hardware

HUB = os.environ["HUB_URL"].rstrip("/")
TOKEN = os.environ["RIG_TOKEN"]
WAIT = 5

board = create_whisplay_hardware(
    app_id="rowdy-hub-wrist",
    display_name="Hub Wrist",
    icon="H",
    use_daemon_default_log=True,
)
board.set_backlight(70)
W, H = board.LCD_WIDTH, board.LCD_HEIGHT


def font(size):
    return ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
    )


small = font(14)
body = font(18)
large = font(30)
previous_frame = None


def fit(draw, text, selected_font, max_width):
    text = str(text)
    if draw.textlength(text, font=selected_font) <= max_width:
        return text
    while text and draw.textlength(text + "...", font=selected_font) > max_width:
        text = text[:-1]
    return text + "..."


def money(value):
    try:
        return f"${float(value):,.0f}"
    except (ValueError, TypeError, OverflowError):
        return "$?"


def display(image):
    global previous_frame
    raw = image.tobytes()
    if raw == previous_frame:
        return

    frame = bytearray(W * H * 2)
    for offset in range(0, len(raw), 3):
        r, g, b = raw[offset:offset + 3]
        pixel = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        position = (offset // 3) * 2
        frame[position] = pixel >> 8
        frame[position + 1] = pixel & 255

    board.draw_image(0, 0, W, H, bytes(frame))
    previous_frame = raw


def error_screen(reason):
    image = Image.new("RGB", (W, H), (12, 18, 28))
    draw = ImageDraw.Draw(image)
    draw.text((12, 35), "LINE DEAD", font=large, fill=(255, 110, 100))
    draw.text((12, 100), fit(draw, reason, body, W - 24),
              font=body, fill="white")
    draw.text((12, 135), "Retrying automatically", font=small,
              fill=(175, 185, 200))
    display(image)


def render(data):
    image = Image.new("RGB", (W, H), (12, 18, 28))
    draw = ImageDraw.Draw(image)
    cyan = (70, 210, 230)
    green = (120, 240, 150)
    muted = (175, 185, 200)

    case = fit(draw, f"CASE {data.get('case_no', 0)}", body, W - 85)
    draw.text((12, 10), case, font=body, fill=cyan)

    revealed = bool(data.get("revealed", False))
    status = "FLED" if revealed else "LIVE"
    draw.text((W - 57, 12), status, font=small, fill=cyan)
    draw.line((12, 39, W - 12, 39), fill=cyan)

    draw.text((12, 49), "TOTAL TAKE", font=small, fill=muted)
    total = money(data.get("take", 0))
    draw.text((12, 69), fit(draw, total, large, W - 24),
              font=large, fill=green)

    count = fit(draw, f"{data.get('count', 0)} EXHIBITS FILED",
                small, W - 24)
    draw.text((12, 111), count, font=small, fill=muted)

    if revealed:
        draw.text((12, 158), "Case complete", font=body, fill="white")
    else:
        items = data.get("top", [])
        if not items:
            draw.text((12, 150), "Waiting for finds...", font=body,
                      fill="white")
        for index, item in enumerate(items[:5]):
            y = 143 + index * 22
            price = fit(draw, money(item.get("value_usd", 0)), small, 85)
            price_width = draw.textlength(price, font=small)
            name_width = max(20, W - 36 - price_width)
            name = fit(draw, item.get("item", "?"), small, name_width)
            draw.text((12, y), name, font=small, fill="white")
            draw.text((W - 12 - price_width, y), price, font=small,
                      fill=green)

    if data.get("pending"):
        footer = "Analysis pending"
    elif data.get("camera_ok"):
        footer = "Hub camera: OK"
    else:
        footer = "Hub camera: not ready"
    draw.text((12, H - 23), footer, font=small, fill=muted)
    display(image)


version = 0
try:
    error_screen("Connecting to hub")
    while True:
        query = urllib.parse.urlencode({"since": version, "wait": WAIT})
        request = urllib.request.Request(
            f"{HUB}/wrist.json?{query}",
            headers={
                "X-Rig-Token": TOKEN,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=WAIT + 5) as response:
                data = json.load(response)

            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            items = data.get("top", [])
            if not isinstance(items, list) or any(
                not isinstance(item, dict) for item in items
            ):
                raise ValueError("Invalid top list")

            new_version = int(data.get("v", version))

        except urllib.error.HTTPError as exc:
            reason = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            reason = "Network or TLS error"
            print(f"Connection error: {exc}", flush=True)
        except (TimeoutError, OSError):
            reason = "Connection timed out"
        except (ValueError, TypeError):
            reason = "Invalid hub response"
        else:
            render(data)
            version = new_version
            time.sleep(0.15)
            continue

        print(reason, flush=True)
        error_screen(reason)
        time.sleep(3)

except KeyboardInterrupt:
    print("Stopping hub display.", flush=True)
finally:
    board.cleanup()
