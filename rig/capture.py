"""Webcam grab, JPEG encode, and the frame-diff gate.

SCAN_ALWAYS=1 sends every sample to the model. The gate is otherwise the
thing that keeps a static shot from burning an API call.
"""
from __future__ import annotations

import base64
import sys

import cv2
import numpy as np

from rig import config

_last_gray = None
_streak = 0
_preferred = None


def backend_order() -> list[int]:
    """Backends to try, first one most likely to open a camera on this OS.

    On Windows the default backend often misses the webcam. DirectShow, then
    Media Foundation, then whatever OpenCV picks. CAM_BACKEND overrides that.
    """
    named = {
        "dshow": getattr(cv2, "CAP_DSHOW", None),
        "msmf": getattr(cv2, "CAP_MSMF", None),
        "v4l2": getattr(cv2, "CAP_V4L2", None),
        "any": cv2.CAP_ANY,
    }
    prefer = config.env_str("CAM_BACKEND").lower()
    if prefer:
        flag = named.get(prefer)
        return [cv2.CAP_ANY if flag is None else flag]
    if sys.platform == "win32":
        return [flag for flag in (named["dshow"], named["msmf"], cv2.CAP_ANY) if flag is not None]
    if sys.platform.startswith("linux"):
        return [flag for flag in (named["v4l2"], cv2.CAP_ANY) if flag is not None]
    return [cv2.CAP_ANY]


def scan_always() -> bool:
    return config.env_flag("SCAN_ALWAYS", False)


def open_camera():
    """Open CAM_INDEX. A failed try is released so the device is not stuck open."""
    global _preferred
    index = config.env_int("CAM_INDEX", 0)
    order = list(backend_order())
    if _preferred is not None and _preferred in order:
        order.remove(_preferred)
        order.insert(0, _preferred)
    last = None
    for backend in order:
        cam = cv2.VideoCapture(index) if backend == cv2.CAP_ANY else cv2.VideoCapture(index, backend)
        if cam is not None and cam.isOpened():
            _preferred = backend
            try:
                cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            for _ in range(8):
                cam.read()
            return cam
        if cam is not None:
            cam.release()
        last = cam
    return last if last is not None else cv2.VideoCapture(index)


def grab_frame(cam):
    if cam is None or not cam.isOpened():
        return None
    ok, frame = cam.read()
    if not ok or frame is None:
        return None
    return frame


def frame_jpeg(frame, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()


def frame_b64(frame) -> str:
    # Sharper than the dashboard still, so a logo or model line is readable.
    return base64.b64encode(frame_jpeg(frame, quality=92)).decode("ascii")


def scene_confirm() -> int:
    """Consecutive samples a new view must hold before a look. Flicker guard."""
    return config.env_int("SCENE_CONFIRM", 2, lo=1)


def scene_thresh() -> float:
    """Mean pixel diff that counts as a new view. SCENE_THRESH tunes it on site."""
    return config.env_float("SCENE_THRESH", 8.0)


def scene_changed(frame, thresh: float | None = None, confirm: int | None = None) -> bool:
    """True only when a new view has held for SCENE_CONFIRM samples.

    The diff is measured against the last frame the model was actually shown,
    not the previous sample, so one noisy frame (a light flickering, sensor
    noise) cannot fake a scene: it differs from the reference, and so does
    the return to it, but neither view ever holds. The first frame after a
    reset always does.
    """
    global _last_gray, _streak
    if scan_always():
        return True
    if thresh is None:
        thresh = scene_thresh()
    need = scene_confirm() if confirm is None else max(1, confirm)
    gray = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
    if _last_gray is None:
        _last_gray = gray
        _streak = 0
        return True
    if float(cv2.absdiff(gray, _last_gray).mean()) > thresh:
        _streak += 1
        if _streak >= need:
            _last_gray = gray
            _streak = 0
            return True
        return False
    _streak = 0
    return False


def reset_gate() -> None:
    global _last_gray, _streak
    _last_gray = None
    _streak = 0


def crop_jpeg(frame, bbox) -> bytes:
    """Booking photo: the exhibit's box, widened to a 3:4 mugshot."""
    height, width = frame.shape[:2]
    if not bbox:
        x, y, w, h = 0.25, 0.1, 0.5, 0.8
    else:
        x, y, w, h = bbox
    cx, cy = (x + w / 2) * width, (y + h / 2) * height
    ch = max(h * height, w * width * 4 / 3)
    cw = ch * 3 / 4
    x0, y0 = int(max(0, cx - cw / 2)), int(max(0, cy - ch / 2))
    x1, y1 = int(min(width, cx + cw / 2)), int(min(height, cy + ch / 2))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        crop = frame
    return frame_jpeg(crop)


def paint_still(bbox, shade: int = 190) -> np.ndarray:
    """A stand-in frame for the scripted walk: a light block on a dark field."""
    img = np.full((480, 640, 3), 22, np.uint8)
    if bbox:
        x, y, w, h = bbox
        x0, y0 = int(x * 640), int(y * 480)
        x1, y1 = int((x + w) * 640), int((y + h) * 480)
        img[y0:y1, x0:x1] = shade
    return img
