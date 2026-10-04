"""Rover drive endpoint: POST /drive {"dir": "forward", "secs": 0.4}.

Tiny stdlib server on port 5001 so the rover needs no extra deps. The hub
forwards laptop teleop here (see app.py /api/drive); RIG_TOKEN, when set on
the rover, is honored the same way via the X-Rig-Token header.

GET /frame.jpg is the rover camera's latest frame, for a hub running with
CAM_SOURCE=rover.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rig import config
from rig.drive import DIRECTIONS, MAX_SECS, Driver

log = logging.getLogger("rig.drive_server")

PORT = 5001


def _token_ok(headers) -> bool:
    token = config.env_str("RIG_TOKEN")
    if not token:
        return True
    return headers.get("X-Rig-Token") == token


def _return_after() -> float:
    """Idle seconds with no drive command before the rover walks itself home.
    DRIVE_RETURN_AFTER=0 disables the auto-return watchdog."""
    return config.env_float("DRIVE_RETURN_AFTER", 60.0, lo=0.0)


_last_cmd = [0.0]  # mutable cell; stamped on every /drive hit


def drive_server(driver: Driver, port: int = PORT, frame_source=None) -> ThreadingHTTPServer:
    """`frame_source` is a no-arg callable returning the rover camera's latest
    frame (or None). When given, GET /frame.jpg serves it so the hub can show
    the rover's view (CAM_SOURCE=rover on the hub)."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path.split("?")[0].rstrip("/") != "/drive":
                self.send_response(404)
                self.end_headers()
                return
            if not _token_ok(self.headers):
                self.send_response(401)
                self.end_headers()
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            # Negative or absurd lengths stall the handler: clamp hard.
            length = max(0, min(length, 64 * 1024))
            # And cap the read itself: a declared-but-never-sent body can't
            # pin this thread in a blocking recv forever.
            self.connection.settimeout(5)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, OSError):
                body = {}
            if not isinstance(body, dict):
                body = {}
            direction = str(body.get("dir") or "stop")
            secs = body.get("secs")
            try:
                secs = 0.4 if secs is None else float(secs)
            except (TypeError, ValueError):
                secs = 0.4
            if not math.isfinite(secs):
                secs = 0.4
            secs = min(max(secs, 0.0), MAX_SECS)
            if direction == "return":
                threading.Thread(target=driver.return_home, daemon=True,
                                 name="drive-return").start()
            else:
                if direction not in DIRECTIONS:
                    direction = "stop"
                driver.move(direction, secs)
            _last_cmd[0] = time.monotonic()
            payload = json.dumps({"ok": True, "dir": direction}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path == "/health":
                payload = json.dumps({"ok": True, "driver": type(driver).__name__}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif path == "/frame.jpg" and frame_source is not None:
                # The camera is a read like the hub's own /frame.jpg: token-gated.
                if not _token_ok(self.headers):
                    self.send_response(401)
                    self.end_headers()
                    return
                frame = frame_source()
                if frame is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                from rig import capture  # lazy: /drive alone needs no OpenCV
                payload = capture.frame_jpeg(frame)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            log.debug("drive http: " + (args[0] if args else ""), *args[1:])

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    return server


def start(driver: Driver, port: int = PORT, frame_source=None) -> ThreadingHTTPServer:
    server = drive_server(driver, port, frame_source)
    threading.Thread(target=server.serve_forever, daemon=True, name="drive-http").start()
    log.info("drive endpoint on :%s", port)
    after = _return_after()
    if after > 0:
        threading.Thread(target=_auto_return, args=(driver, after),
                         daemon=True, name="drive-home").start()
        log.info("auto-return after %.0fs idle", after)
    return server


def _auto_return(driver: Driver, after: float) -> None:
    """Silence the teleop for `after` seconds and the rover walks its
    breadcrumb trail back to where the crew dropped it."""
    _last_cmd[0] = time.monotonic()
    while True:
        time.sleep(5)
        if _last_cmd[0] and time.monotonic() - _last_cmd[0] >= after:
            log.info("teleop idle %.0fs — returning home", after)
            legs = driver.return_home()
            log.info("return complete: %d leg(s)", legs)
            _last_cmd[0] = time.monotonic()   # reset so it doesn't refire
