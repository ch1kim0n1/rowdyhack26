"""Rover wheels.

A TB6612/L298N pair on four GPIOs through gpiozero.Robot. No GPIO (a laptop,
a test) gets the console driver: the moves log, nothing rolls. Pins come
from DRIVE_PINS="lf,lb,rf,rb", the default below assumes TB6612 AIN1/AIN2
and BIN1/BIN2 with the PWM enables tied high.

    python -m rig.drive          # console driver, arrow-key friendly REPL
"""
from __future__ import annotations

import logging
import threading
import time

from rig import config, journal

log = logging.getLogger("rig.drive")

DIRECTIONS = {"forward", "back", "left", "right", "stop"}
MAX_SECS = 3.0

DEFAULT_PINS = "22,23,24,25"


def drive_pins() -> tuple[int, int, int, int]:
    pins = config.env_ints("DRIVE_PINS", DEFAULT_PINS)
    if len(pins) == 4:
        return tuple(pins)
    log.warning("bad DRIVE_PINS; using %s", DEFAULT_PINS)
    return tuple(int(p) for p in DEFAULT_PINS.split(","))


class Driver:
    def move(self, direction: str, secs: float = 0.4) -> None:
        raise NotImplementedError

    def return_home(self) -> int:
        """Replay the breadcrumb trail backwards. Returns legs walked."""
        return 0


_frame_source = None


def set_frame_source(fn) -> None:
    """Rover hands us its latest frame so return_home can sight the beacon."""
    global _frame_source
    _frame_source = fn


def find_home_marker(frame) -> tuple[float, float] | None:
    """HOME_MARKER_ID in view? -> (center x 0-1, width 0-1). None if absent."""
    if frame is None:
        return None
    try:
        import cv2

        from rig.marker import marker_id
        det = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
        corners, ids, _ = det.detectMarkers(frame)
    except Exception:
        return None
    if ids is None:
        return None
    target = marker_id()
    for cornerset, mid in zip(corners, ids.flatten(), strict=True):
        if int(mid) != target:
            continue
        pts = cornerset.reshape(4, 2)
        width = frame.shape[1]
        return float(pts[:, 0].mean() / width), float(
            (pts[:, 0].max() - pts[:, 0].min()) / width)
    return None


class ConsoleDriver(Driver):
    """No wheels attached: log the move so teleop plumbing is testable."""

    def __init__(self):
        self.moves: list[tuple[str, float]] = []

    def move(self, direction: str, secs: float = 0.4, record: bool = True) -> None:
        secs = min(max(secs, 0.0), MAX_SECS)
        self.moves.append((direction, secs))
        log.info("drive %s %.2fs", direction, secs)

    def return_home(self) -> int:
        legs = 0
        inverse = {"forward": "back", "back": "forward",
                   "left": "right", "right": "left"}
        trail = [(d, s) for d, s in self.moves if d in inverse]
        for direction, secs in reversed(trail):
            log.info("return leg: %s %.2fs", inverse[direction], secs)
            legs += 1
        return legs


class RobotDriver(Driver):
    """Latest command wins. Every move bumps the generation; a sleeper that
    wakes to find its generation stale does nothing, the newer command (or
    the stop) already owns the wheels. The wait happens outside the lock so
    rapid teleop sends don't queue: each move just supersedes the last."""

    def __init__(self, robot=None):
        if robot is None:
            from gpiozero import Robot
            lf, lb, rf, rb = drive_pins()
            robot = Robot(left=(lf, lb), right=(rf, rb))
        self._robot = robot     # anything with forward/backward/left/right/stop
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._gen = 0
        self._user_gen = 0   # teleop-command count; return_home watches it
        self._return_lock = threading.Lock()
        self._trail: list[tuple[str, float]] = []   # breadcrumbs for return_home

    INVERSE = {"forward": "back", "back": "forward",
               "left": "right", "right": "left"}

    def move(self, direction: str, secs: float = 0.4, record: bool = True) -> None:
        secs = min(max(secs, 0.0), MAX_SECS)
        if direction == "stop":
            with self._lock:
                self._gen += 1
                if record:
                    self._user_gen += 1   # a human said stop: abort any return
                self._robot.stop()
                # Inside the lock: a set() after release could race a fresh
                # move that already cleared the flag and silently kill it.
                self._stop.set()  # wake every sleeping move; all are stale
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
            if record:
                self._user_gen += 1   # teleop took the wheel mid-return
            self._stop.clear()
            if direction == "forward":
                self._robot.forward()
            elif direction == "back":
                self._robot.backward()
            elif direction == "left":
                self._robot.left()
            elif direction == "right":
                self._robot.right()
            else:
                self._robot.stop()
                return
            if record:
                self._trail.append((direction, secs))
        # Sleep outside the lock: a newer command or a stop makes us stale.
        self._stop.wait(secs)
        with self._lock:
            if self._gen == gen:      # still the latest command: time's up
                self._robot.stop()

    def return_home(self) -> int:
        """Breadcrumb replay + beacon correction: dead-reckon the trail, but
        the moment HOME_MARKER_ID is in frame, drop the reckoning and steer
        onto the marker instead. Return legs are never recorded, or the walk
        home would refill its own trail. A teleop command mid-return takes
        the wheels back — the human wins over the breadcrumb replay."""
        if not self._return_lock.acquire(blocking=False):
            log.info("return already walking; ignoring the duplicate")
            return 0
        try:
            legs = 0
            user_gen = self._user_gen
            while True:
                if self._user_gen != user_gen:
                    log.info("teleop took the wheel — abandoning the return")
                    return legs
                frame = _frame_source() if _frame_source else None
                hit = find_home_marker(frame)
                if hit is not None:
                    log.info("home beacon sighted — steering onto it")
                    legs += self._home_on_marker(user_gen)
                    return legs
                with self._lock:
                    if not self._trail:
                        return legs
                    direction, secs = self._trail.pop()
                self.move(self.INVERSE[direction], secs, record=False)
                legs += 1
        finally:
            self._return_lock.release()

    def _home_on_marker(self, user_gen: int, timeout: float = 25.0) -> int:
        """Beacon in view: nudge to center it, forward until it fills a
        quarter of the frame. Returns correction legs driven."""
        legs = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._user_gen != user_gen:
                log.info("teleop took the wheel — abandoning beacon approach")
                return legs
            frame = _frame_source() if _frame_source else None
            hit = find_home_marker(frame)
            if hit is None:
                # Lost the marker — a blind step forward may bring it back.
                self.move("forward", 0.2, record=False)
                legs += 1
                continue
            cx, w = hit
            if w >= 0.28:
                self.move("stop")
                log.info("beacon reached (%.0f%% of frame)", w * 100)
                return legs + 1
            if cx < 0.42:
                self.move("left", 0.15, record=False)
            elif cx > 0.58:
                self.move("right", 0.15, record=False)
            else:
                self.move("forward", 0.25, record=False)
            legs += 1
        log.info("beacon approach timed out")
        return legs


class _PicarX:
    """A SunFounder PiCar-X behind the same five verbs gpiozero's Robot has.

    Its motors hang off the Robot HAT, not bare GPIO pins, and it steers with a
    front servo like a car: left/right turn the wheels and roll forward. (So a
    breadcrumb return, which assumes a spin-in-place turn, only approximates
    the way back on this chassis.)"""

    TURN = 30   # degrees; the steering servo's limit

    def __init__(self):
        from picarx import Picarx
        self._px = Picarx()
        self._speed = config.env_int("PICARX_SPEED", 40, lo=10, hi=100)

    def _go(self, angle: int, backward: bool = False) -> None:
        self._px.set_dir_servo_angle(angle)
        (self._px.backward if backward else self._px.forward)(self._speed)

    def forward(self) -> None:
        self._go(0)

    def backward(self) -> None:
        self._go(0, backward=True)

    def left(self) -> None:
        self._go(-self.TURN)

    def right(self) -> None:
        self._go(self.TURN)

    def stop(self) -> None:
        self._px.stop()
        self._px.set_dir_servo_angle(0)


def drive_kit() -> str:
    """DRIVE_KIT: picarx = SunFounder PiCar-X (Robot HAT); gpio = a TB6612/L298N
    pair on DRIVE_PINS. Empty tries the PiCar-X first, then GPIO."""
    return config.env_str("DRIVE_KIT").lower()


def get_driver() -> Driver:
    kit = drive_kit()
    if kit in ("", "picarx"):
        try:
            driver = RobotDriver(_PicarX())
            log.info("drive wheels on a SunFounder PiCar-X (Robot HAT)")
            journal.event("motor-driver", True, "PiCar-X")
            return driver
        except Exception as exc:
            # No picarx library on a gpio rover is the normal case, not news.
            if kit == "picarx" or not isinstance(exc, ImportError):
                log.warning("PiCar-X driver unavailable (%s: %s)", type(exc).__name__, exc)
    try:
        driver = RobotDriver()
        log.info("drive wheels on DRIVE_PINS=%s", ",".join(map(str, drive_pins())))
        journal.event("motor-driver", True, f"DRIVE_PINS={','.join(map(str, drive_pins()))}")
        return driver
    except Exception:
        log.info("no motor GPIO; console driver (logs moves, rolls nothing)")
        journal.event("motor-driver", False, "no GPIO; console driver")
        return ConsoleDriver()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    d = get_driver()
    keys = {"w": "forward", "s": "back", "a": "left", "d": "right", "x": "stop"}
    print("wasd to drive, x to stop, q to quit")
    while True:
        k = input("> ").strip().lower()[:1]
        if k == "q":
            break
        if k in keys:
            d.move(keys[k], 0.4)
