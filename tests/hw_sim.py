"""Simulated hardware for the certification pass.

Every fake sits at the hardware boundary — cv2.VideoCapture, gpiozero,
luma/OLED, escpos, arecord/aplay subprocesses, urllib — so everything above
the seam runs real production code.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np


class FakeCam:
    """Scripted camera. mode: 'ok' | 'empty' | 'frozen' | 'corrupt' | 'dead'.

    'ok' emits a new scene each read (unique shade) so scene_changed fires.
    'frozen' emits the same frame forever — the gate must hold.
    'corrupt' returns ok=False like a dropped read.
    'empty' opens but never returns a frame.
    'dead' refuses to open.
    """
    def __init__(self, mode: str = "ok", w: int = 640, h: int = 480):
        self.mode = mode
        self.w, self.h = w, h
        self.reads = 0
        self.released = 0
        self._frozen = np.full((h, w, 3), 40, np.uint8)
        self._shade = 0

    def isOpened(self):
        return self.mode != "dead"

    def read(self):
        self.reads += 1
        if self.mode in {"dead", "empty"}:
            return False, None
        if self.mode == "corrupt":
            return False, None
        if self.mode == "frozen":
            return True, self._frozen.copy()
        self._shade = (self._shade + 60) % 200
        frame = np.full((self.h, self.w, 3), 20 + self._shade, np.uint8)
        cv2.circle(frame, (self.w // 2, self.h // 2), 60, (200, 200, 200), -1)
        return True, frame

    def release(self):
        self.released += 1
        self.mode = "dead"

    def set(self, *a, **k):
        # cv2 VideoCapture.set(prop, value) — noop for the fake. Change modes
        # with cam.mode = 'dead', not set().
        pass


def fake_gpiozero():
    """In-memory gpiozero: Button/LightSensor/RotaryEncoder/Robot record events."""
    calls = {"robot": [], "buttons": {}, "encoders": {}}

    class FakeButton:
        def __init__(self, pin, bounce_time=0.15, **kw):
            self.pin, self.bounce_time = pin, bounce_time
            self.when_pressed = None
            calls["buttons"][pin] = self

        def fire(self):
            if self.when_pressed:
                self.when_pressed()

        def close(self):
            pass

    class FakeSensor(FakeButton):
        pass

    class FakeEncoder:
        def __init__(self, a, b, max_steps=16, **kw):
            self.steps = 0
            self.when_rotated = None
            calls["encoders"][(a, b)] = self

        def rotate(self, n: int):
            self.steps += n
            if self.when_rotated:
                self.when_rotated()

    class FakeRobot:
        def __init__(self, left=None, right=None):
            self.last = None

        def _go(self, name):
            self.last = name
            calls["robot"].append(name)

        def forward(self): self._go("forward")
        def backward(self): self._go("back")
        def left(self): self._go("left")
        def right(self): self._go("right")
        def stop(self): self._go("stop")

    mod = types.SimpleNamespace(Button=FakeButton, LightSensor=FakeSensor,
                                RotaryEncoder=FakeEncoder, Robot=FakeRobot)
    return mod, calls


def fake_luma(calls: dict):
    """In-memory luma OLED: canvas() hands render() a real PIL draw."""
    from PIL import Image, ImageDraw

    class FakeDevice:
        def __init__(self, serial=None):
            self.width, self.height = 128, 64
            calls["device"] = self
            self.frames = 0

        def display(self, img):
            self.frames += 1

    class FakeI2C:
        def __init__(self, port=1, address=0x3C):
            calls["i2c"] = (port, address)

    class _Canvas:
        def __init__(self, device): self.device = device
        def __enter__(self):
            img = Image.new("1", (128, 64))
            self.draw = ImageDraw.Draw(img)
            calls.setdefault("draws", []).append(self.draw)
            return self.draw
        def __exit__(self, *a):
            self.device.frames += 1
            return False

    luma_core = types.ModuleType("luma.core")
    luma_serial = types.ModuleType("luma.core.interface.serial")
    luma_serial.i2c = FakeI2C
    luma_render = types.ModuleType("luma.core.render")
    luma_render.canvas = _Canvas
    luma_oled = types.ModuleType("luma.oled.device")
    luma_oled.ssd1306 = FakeDevice
    luma_iface = types.ModuleType("luma.core.interface")
    luma_iface.serial = luma_serial
    luma_root = types.ModuleType("luma")
    luma_oled_pkg = types.ModuleType("luma.oled")
    return {
        "luma": luma_root, "luma.core": luma_core, "luma.core.interface": luma_iface,
        "luma.core.interface.serial": luma_serial, "luma.core.render": luma_render,
        "luma.oled": luma_oled_pkg, "luma.oled.device": luma_oled,
    }


def fake_escpos(calls: dict):
    class FakeUsb:
        def __init__(self, vid, pid, *a, **k):
            calls["usb"] = (vid, pid)
            self.lines = []

        def set(self, **k): pass
        def text(self, s): self.lines.append(s)
        def cut(self): calls["cut"] = True
        def close(self): calls["closed"] = True
        def open(self): pass

    escpos = types.ModuleType("escpos")
    escpos_printer = types.ModuleType("escpos.printer")
    escpos_printer.Usb = FakeUsb
    escpos.printer = escpos_printer
    return {"escpos": escpos, "escpos.printer": escpos_printer}


class FakeMic:
    """Patches listen's arecord subprocess. out_bytes=-1 means 'command fails'."""
    def __init__(self, out_bytes: int = 4096, fail: bool = False):
        self.out_bytes = out_bytes
        self.fail = fail

    def runner(self, cmd, **kw):
        import subprocess
        if self.fail:
            raise OSError("no such device")
        if isinstance(cmd, list) and cmd and cmd[0] in {"arecord", "rec"}:
            path = cmd[-1] if cmd[0] == "arecord" else cmd[4]
            # rec writes to cmd index 'path'; arecord's path is last arg
            if cmd[0] == "rec":
                for _i, a in enumerate(cmd):
                    if a.endswith(".wav"):
                        path = a
            with open(path, "wb") as fh:
                fh.write(b"RIFF" + b"\x00" * max(0, self.out_bytes - 4))
            return subprocess.CompletedProcess(cmd, 0)
        raise OSError("unknown cmd")


def fake_openai_tts(calls: dict):
    class FakeSpeech:
        def create(self, model=None, voice=None, input=None, response_format=None):
            calls["tts"] = (model, voice, len(input or ""))
            class _R:
                def read(self):
                    return b"RIFF" + b"\x24\x00" * 100   # fake wav
            return _R()

    class FakeAudio:
        speech = FakeSpeech()

        def __init__(self):
            self.transcriptions = self._T()

        class _T:
            def create(self, model=None, file=None):
                calls["whisper"] = True
                return types.SimpleNamespace(text="how long do we have")

    class FakeChat:
        class completions:
            @staticmethod
            def create(model=None, max_tokens=None, messages=None):
                calls["chat"] = model
                msg = types.SimpleNamespace(content="Eleven minutes. Move quiet.")
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class FakeClient:
        def __init__(self, timeout=None):
            self.audio = FakeAudio()
            self.chat = FakeChat()

    openai = types.ModuleType("openai")
    openai.OpenAI = FakeClient
    return {"openai": openai}


class FakeHub:
    """A latency-injectable /api/exhibit+rover_ping server for rover tests."""
    def __init__(self, latency: float = 0.0, drop: float = 0.0):
        self.latency = latency
        self.drop = drop
        self.hits = {"exhibit": 0, "ping": 0}
        self.bodies = []
        self._server = None
        self._thread = None

    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> None:
        outer = self

        class H(BaseHTTPRequestHandler):
            def _handle(self):
                if outer.drop and (outer.hits["exhibit"] + outer.hits["ping"]) % int(1 / outer.drop) == 0:
                    self.connection.close()
                    return
                if outer.latency:
                    time.sleep(outer.latency)
                length = int(self.headers.get("Content-Length") or 0)
                outer.bodies.append(self.rfile.read(length))
                body = json.dumps({"ok": True, "added": True, "hot": False}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path == "/api/exhibit":
                    outer.hits["exhibit"] += 1
                elif self.path == "/api/rover_ping":
                    outer.hits["ping"] += 1
                self._handle()

            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a): pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()


def install(mapping: dict):
    """Patch sys.modules for a cert test; returns a restore callable."""
    saved = {name: sys.modules.get(name) for name in mapping}
    sys.modules.update(mapping)

    def restore():
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
    return restore


def fd_count() -> int:
    import os
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:
        return -1


def thread_names() -> set:
    return {t.name for t in threading.enumerate()}
