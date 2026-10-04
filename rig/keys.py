"""USB-keyboard fallback, the no-SSH, no-network rung.

When stdin isn't a tty (systemd service), keys on a plugged-in USB keyboard
reach us through evdev instead: Enter = reveal, q = radio dispatch. Works on
the same Pi that drives the kiosk monitor, so a dead venue Wi-Fi still has a
full control path: monitor shows the dashboard, keyboard runs the buttons.
"""
from __future__ import annotations

import logging
import select
import threading

log = logging.getLogger("rig.keys")


def _devices() -> list:
    try:
        from evdev import InputDevice, ecodes, list_devices
    except ImportError:
        log.info("evdev not installed; USB keyboard fallback unavailable")
        return []
    found = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_ENTER in keys and ecodes.KEY_Q in keys:
                found.append(dev)
                log.info("keyboard fallback on %s (%s)", dev.name, path)
            else:
                dev.close()
        except OSError:
            continue
    return found


def _close_all(devices) -> None:
    for dev in devices:
        try:
            dev.close()
        except OSError:
            pass


def start(reveal_handler, on_mic=None) -> bool:
    devices = _devices()
    if not devices:
        return False

    def watch():
        import time
        while True:
            try:
                from evdev import ecodes
                readable, _, _ = select.select(devices, [], [])
                for dev in readable:
                    try:
                        events = dev.read()
                    except BlockingIOError:
                        continue   # select() lied; nothing to read
                    for event in events:
                        if event.type != ecodes.EV_KEY or event.value != 1:
                            continue
                        if event.code == ecodes.KEY_Q and on_mic is not None:
                            on_mic()
                        elif event.code == ecodes.KEY_ENTER:
                            reveal_handler()
            except OSError:
                # Keyboard unplugged: close stale fds, then keep rescanning.
                # This fallback exists for dead-network day; it must survive
                # the keyboard being pulled and replugged.
                log.warning("keyboard dropped; rescanning every 5s", exc_info=True)
                _close_all(devices)
                devices[:] = []
                while not devices:
                    time.sleep(5)
                    try:
                        devices[:] = _devices()
                    except Exception:
                        pass   # rescan hiccup, keep waiting for a keyboard
                log.info("keyboard fallback re-armed")
            except Exception:
                log.exception("keyboard watcher failed")
                return

    threading.Thread(target=watch, daemon=True, name="keys").start()
    return True
