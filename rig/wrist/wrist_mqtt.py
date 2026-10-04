#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from whisplay_client import create_whisplay_hardware

host = os.environ["MQTT_HOST"]
password = os.environ["MQTT_PASSWORD"]

board = create_whisplay_hardware(
    app_id="rowdy-wrist",
    display_name="Rowdy Wrist",
    icon="R",
    use_daemon_default_log=True,
)
board.set_backlight(70)
width, height = board.LCD_WIDTH, board.LCD_HEIGHT


def font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


heading_font = font(22)
body_font = font(23)
price_font = font(30)
small_font = font(14)


def show(source, item, price="", footer="Waiting for a result"):
    image = Image.new("RGB", (width, height), (12, 18, 28))
    draw = ImageDraw.Draw(image)
    draw.text((12, 12), source[:18], font=heading_font,
              fill=(70, 210, 230))
    draw.line((12, 46, width - 12, 46), fill=(70, 210, 230))

    lines, line = [], ""
    for char in item[:300]:
        if char == "\n":
            lines.append(line)
            line = ""
        elif draw.textlength(line + char, font=body_font) > width - 24:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)

    for index, text in enumerate(lines[:4]):
        draw.text((12, 60 + index * 29), text,
                  font=body_font, fill="white")

    selected_font = price_font
    if draw.textlength(price, font=selected_font) > width - 24:
        selected_font = body_font
    draw.text((12, height - 77), price[:20],
              font=selected_font, fill=(120, 240, 150))
    draw.text((12, height - 29), footer[:28],
              font=small_font, fill=(175, 185, 200))

    raw = image.tobytes()
    frame = bytearray(width * height * 2)
    for offset in range(0, len(raw), 3):
        r, g, b = raw[offset:offset + 3]
        pixel = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        position = (offset // 3) * 2
        frame[position] = pixel >> 8
        frame[position + 1] = pixel & 0xFF

    board.draw_image(0, 0, width, height, bytes(frame))


proc = None
try:
    show("ROWDY WRIST", "Waiting for\nhat or rover...",
         footer="Connecting to MQTT")

    proc = subprocess.Popen(
        [
            "mosquitto_sub",
            "-h", host,
            "-i", "wrist-display",
            "-u", "rowdy",
            "-P", password,
            "-t", "rowdy/hat/result",
            "-t", "rowdy/rover/result",
            "-q", "1",
            "-v",
        ],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    print(f"Receiver started, broker: {host}", flush=True)

    for line in proc.stdout:
        try:
            topic, payload = line.rstrip("\n").split(" ", 1)
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")

            source = topic.split("/")[1].upper()
            item = str(data.get("item") or "Unknown item")
            value = data.get("price")
            price = "Price unavailable"

            if value is not None:
                number = Decimal(str(value))
                if not number.is_finite():
                    raise ValueError("Invalid price")
                currency = str(data.get("currency", "USD")).upper()
                price = (f"${number:,.2f}" if currency == "USD"
                         else f"{number:,.2f} {currency}")

            label = ("Estimated price"
                     if data.get("price_type", "estimate") == "estimate"
                     else "Reported price")

        except (ValueError, TypeError, InvalidOperation) as exc:
            print(f"Skipped invalid message: {exc}", flush=True)
            continue

        print(f"{source}: {item} — {price}", flush=True)
        show(source, item, price, label)

    show("MQTT STOPPED", "Check terminal\nfor errors.")
    print(f"MQTT client exited: {proc.wait()}", flush=True)

except KeyboardInterrupt:
    print("\nStopping receiver.", flush=True)
finally:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    board.cleanup()
