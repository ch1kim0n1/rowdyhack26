"""The reveal button, and the radio-mic button.

GPIO17 on the Pi files the lineup; a second press closes the case.
LISTEN_PIN (GPIO27 default) is the mic: press it to ask dispatch how long
the crew has left. On a laptop, Enter does reveal and 'q'+Enter does the mic.
"""
from __future__ import annotations

import logging
import sys
import threading

from rig import config, journal

log = logging.getLogger("rig.button")

# gpiozero drops the pin when the Button is garbage-collected. These stay
# referenced for the life of the process so a press still fires.
_held = None
_held_mic = None

LISTEN_PIN = 27


def start(reveal_handler, on_mic=None) -> None:
    global _held, _held_mic
    try:
        from gpiozero import Button
        _held = Button(17, bounce_time=0.15)
        _held.when_pressed = reveal_handler
        log.info("reveal button on GPIO17")
        journal.event("button-reveal", True)
    except Exception:
        log.info("no GPIO button; press Enter here, or open /trigger_reveal")
        journal.event("button-reveal", False, "no GPIO17; keyboard fallback")

    if on_mic is not None:
        try:
            from gpiozero import Button
            pin = config.env_int("LISTEN_PIN", LISTEN_PIN)
            _held_mic = Button(pin, bounce_time=0.15)
            _held_mic.when_pressed = on_mic
            log.info("mic button on GPIO%s", pin)
            journal.event("button-mic", True)
        except Exception:
            log.info("no mic button; type 'q' + Enter here to radio dispatch")
            journal.event("button-mic", False, f"no GPIO{LISTEN_PIN}; keyboard fallback")

    def _stdin():
        while True:
            try:
                line = input()
            except (EOFError, OSError):
                return
            if line.strip().lower() in {"q", "ask", "?"} and on_mic is not None:
                on_mic()
            else:
                reveal_handler()

    if not sys.stdin or not sys.stdin.isatty():
        # No console (systemd service): a plugged-in USB keyboard still works
        # through evdev: Enter reveals, q radios. The no-SSH rung.
        from rig import keys
        if keys.start(reveal_handler, on_mic):
            log.info("USB keyboard fallback armed (Enter=reveal, q=radio)")
        else:
            log.info("no tty and no keyboard; GPIO or /trigger_reveal only")
        return
    threading.Thread(target=_stdin, daemon=True, name="button").start()
