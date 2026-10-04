"""A live video feed someone else serves, kept down to its newest frame.

The rover's camera can arrive as an MJPEG stream (SunFounder's vilib serves one
at http://<pi>:9000/mjpg). Polling it for stills costs a connection per frame
and tops out at a few frames a second. This reader holds one connection open,
slices the JPEGs out as they land, and keeps only the latest — the hub relays
those bytes to the consoles untouched, so the picture runs at the camera's own
frame rate and never queues up old frames.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from urllib.request import Request, urlopen

log = logging.getLogger("rig.feed")

SOI = b"\xff\xd8"   # JPEG start / end markers; camera MJPEG carries no thumbnails,
EOI = b"\xff\xd9"   # so the first EOI after an SOI closes the frame
BUFFER_MAX = 8 * 1024 * 1024
STALE_AFTER = 2.0   # seconds without a frame before the feed counts as lost


def is_stream_url(url: str | None) -> bool:
    """A URL is a stream unless it names a still (…/mjpg.jpg)."""
    if not url:
        return False
    path = url.split("?", 1)[0].lower()
    return not path.endswith((".jpg", ".jpeg", ".png"))


class StreamReader:
    def __init__(self, url: str, connect_timeout: float = 5.0):
        self.url = url
        self._timeout = connect_timeout
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._seq = 0
        self._at = 0.0
        self._stamps: deque[float] = deque(maxlen=120)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> StreamReader:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="feed-reader")
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> tuple[int, bytes | None]:
        """(sequence number, newest JPEG) — None once the feed has gone stale."""
        with self._cond:
            if self._jpeg is None or time.monotonic() - self._at > STALE_AFTER:
                return self._seq, None
            return self._seq, self._jpeg

    def wait(self, after: int, timeout: float = 1.0) -> tuple[int, bytes | None]:
        """Block until a frame newer than `after` lands, or the timeout."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != after, timeout)
            return self._seq, self._jpeg

    def fps(self) -> float:
        """Frames per second over the last couple of seconds."""
        now = time.monotonic()
        with self._cond:
            recent = [t for t in self._stamps if now - t <= 2.0]
        return round(len(recent) / 2.0, 1)

    def _publish(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._seq += 1
            self._at = time.monotonic()
            self._stamps.append(self._at)
            self._cond.notify_all()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._read_stream()
            except Exception as exc:               # noqa: BLE001 - reconnect on anything
                log.debug("feed read ended (%s); reconnecting", type(exc).__name__)
            self._stop.wait(1.0)

    def _read_stream(self) -> None:
        with urlopen(Request(self.url), timeout=self._timeout) as resp:
            buf = bytearray()
            while not self._stop.is_set():
                chunk = resp.read1(65536)
                if not chunk:
                    return
                buf += chunk
                # Take every whole frame in the buffer, publish only the last:
                # a slow moment must never turn into a queue of old pictures.
                newest = None
                while True:
                    start = buf.find(SOI)
                    if start < 0:
                        buf.clear()
                        break
                    end = buf.find(EOI, start + 2)
                    if end < 0:
                        del buf[:start]
                        break
                    newest = bytes(buf[start:end + 2])
                    del buf[:end + 2]
                if newest is not None:
                    self._publish(newest)
                if len(buf) > BUFFER_MAX:
                    buf.clear()
