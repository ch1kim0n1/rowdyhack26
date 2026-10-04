"""The change bus: one in-process nerve that turns a store mutation into an
instant push to every device.

The dashboard polls /state.json fast, the desk slower, and the Whisplay wrist
every few seconds. Polling a quick database is still as slow as the poll
interval, so "near real-time" has to come from a *push*, not from a faster
read. This module is that push: every write path (a new exhibit, the reveal,
a reset, a status or plan change) calls `bus.publish(...)`, and anyone waiting
on the bus wakes at once.

Three transports ride one bus (see rig/app.py): SSE `/events` for the browser
consoles, a `?since=&wait=` long-poll on `/wrist.json` for the wrist, and a
Postgres `LISTEN` bridge for a second hub. The bus itself is pure stdlib and
always on, so the zero-delay sync works with no cloud dependency at all.
"""
from __future__ import annotations

import threading
import time


class ChangeBus:
    """A monotonic version counter plus the last payload, guarded by a
    Condition. `publish` bumps the version and wakes every waiter; `wait`
    blocks until the version moves past what the caller already has."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._version = 0
        self._payload: dict | None = None
        self._stamp = time.time()

    def publish(self, payload: dict | None = None) -> int:
        """Record a change and wake every waiter. Returns the new version."""
        with self._cond:
            self._version += 1
            if payload is not None:
                self._payload = payload
            self._stamp = time.time()
            self._cond.notify_all()
            return self._version

    def version(self) -> int:
        with self._cond:
            return self._version

    def snapshot(self) -> tuple[int, dict | None]:
        """The current version and the last published payload, for a client
        that just connected and wants state before the next change."""
        with self._cond:
            return self._version, self._payload

    def wait(self, since: int, timeout: float) -> tuple[int, dict | None]:
        """Block until the version passes `since` or `timeout` elapses.

        Returns (version, payload). If it already moved on, returns at once —
        a client that fell behind never misses the update by one tick.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        with self._cond:
            while self._version <= since:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return self._version, self._payload

    def stream(self, timeout: float = 15.0):
        """Yield (version, payload) each time the bus changes, forever.

        A heartbeat (version unchanged, payload None) is yielded every
        `timeout` seconds so an SSE client and the proxy between it and us
        both learn the connection is still alive. The caller stops iterating
        to disconnect.
        """
        last, payload = self.snapshot()
        yield last, payload                       # prime the client with current state
        while True:
            version, payload = self.wait(last, timeout)
            if version > last:
                last = version
                yield version, payload
            else:
                yield version, None               # heartbeat: nothing new
