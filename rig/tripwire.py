"""Optional flavor triggers, the vault-door props.

Two independent, both off unless pinned:

  TRIPWIRE_PIN=4     LDR + laser module: beam break = the thief crossed,
                     fires the same reveal/reset as the red button.
  DIAL_PINS=20,21    KY-040 rotary on A/B. DIAL_TICKS detents clockwise
                     (default 8) "crack the vault", fires the reveal.
                     Counter-clockwise winding just rearms: it never fires.

Both wire through gpiozero; absent GPIO or unset envs mean they simply
never arm. The GPIO17 button stays the primary trigger either way.
"""
from __future__ import annotations

import logging
import threading

from rig import config, journal

log = logging.getLogger("rig.tripwire")

DIAL_TICKS = 8

# gpiozero drops the pin when the sensor is garbage-collected: same
# convention as button.py: keep module references for the process life.
_held_tripwire = None
_held_dial = None


def _env_pins(name: str) -> tuple[int, ...] | None:
    raw = config.env_str(name)
    if not raw:
        return None
    pins = config.env_ints(name)
    if not pins:
        log.warning("bad %s=%r; skipped", name, raw)
        return None
    return tuple(pins)


def _arm_tripwire(reveal_handler) -> bool:
    global _held_tripwire
    pins = _env_pins("TRIPWIRE_PIN")
    if pins is None:
        return False
    if len(pins) != 1:
        log.warning("TRIPWIRE_PIN wants exactly 1 pin, got %r; skipped", pins)
        return False
    try:
        from gpiozero import LightSensor
        sensor = LightSensor(pins[0], queue_len=5, threshold=0.5)
        sensor.when_dark = reveal_handler   # beam broken = lights out = vault breached
        _held_tripwire = sensor
        log.info("tripwire armed on GPIO%s, beam break fires the reveal", pins[0])
        journal.event("tripwire-ldr", True, f"GPIO{pins[0]}")
        return True
    except Exception:
        log.info("no tripwire hardware on GPIO%s", pins[0])
        journal.event("tripwire-ldr", False, f"pinned on GPIO{pins[0]} but not found")
        return False


def _arm_dial(reveal_handler) -> bool:
    global _held_dial
    pins = _env_pins("DIAL_PINS")
    if pins is None:
        return False
    if len(pins) != 2:
        log.warning("DIAL_PINS wants exactly 2 pins (a,b), got %r; skipped", pins)
        return False
    ticks = config.env_int("DIAL_TICKS", DIAL_TICKS, lo=1)
    try:
        from gpiozero import RotaryEncoder
        # No threshold_steps: in gpiozero 2.x it takes a (min, max) pair and
        # only gates when_activated/is_active: when_rotated fires regardless.
        dial = RotaryEncoder(*pins, max_steps=ticks)
        lock = threading.Lock()

        def cranked():
            # Clockwise past the count = crack; counter-clockwise rearms.
            if dial.steps >= ticks:
                with lock:
                    dial.steps = 0   # rearms the dial for the next case
                reveal_handler()
            elif dial.steps <= -ticks:
                with lock:
                    dial.steps = 0

        dial.when_rotated = cranked
        _held_dial = dial
        log.info("safe dial armed on GPIO%s, %s detents crack the vault", pins, ticks)
        journal.event("dial-rotary", True, f"GPIO{list(pins)}")
        return True
    except Exception:
        log.info("no rotary dial on GPIO%s", pins)
        journal.event("dial-rotary", False, f"pinned on GPIO{list(pins)} but not found")
        return False


def start(reveal_handler) -> None:
    """Arm whatever props are pinned. Silent no-op when none are."""
    armed = [_arm_tripwire(reveal_handler), _arm_dial(reveal_handler)]
    if not any(armed):
        log.info("no prop triggers configured (TRIPWIRE_PIN / DIAL_PINS)")
