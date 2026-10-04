"""The rover: same eyes as the hat, but the ledger lives on the hub.

Runs on the second Pi 4 (2GB). Grabs frames, gates on the scene, identifies
and prices like the hat does, then POSTs each exhibit to the hub's
/api/exhibit. A short queue holds finds if the hub drops off Wi-Fi; they get
re-filed the next tick. A heartbeat every ~10s registers this address so the
hub can relay teleop to /drive on :5001 (rig/drive.py + rig/drive_server.py).

    HUB_URL=http://raspberrypi.local:5000 RIG_TOKEN=crew python -m rig.rover
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from urllib.error import URLError
from urllib.request import Request, urlopen

from rig import capture, config, journal

log = logging.getLogger("rig.rover")

POST_TIMEOUT = 4
QUEUE_MAX = 50


def hub_url() -> str:
    return config.env_str("HUB_URL", "http://raspberrypi.local:5000").rstrip("/")


def ping_hub(url: str) -> bool:
    """Tell the hub where teleop reaches us; the hub forwards /api/drive."""
    token = config.env_str("RIG_TOKEN")
    req = Request(
        url.rstrip("/") + "/api/rover_ping",
        data=b"{}",
        headers={"Content-Type": "application/json",
                 **({"X-Rig-Token": token} if token else {})},
        method="POST",
    )
    try:
        with urlopen(req, timeout=POST_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (URLError, TimeoutError, OSError):
        return False


def post_exhibit(url: str, payload: dict) -> bool:
    token = config.env_str("RIG_TOKEN")
    req = Request(
        url.rstrip("/") + "/api/exhibit",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"X-Rig-Token": token} if token else {})},
        method="POST",
    )
    try:
        with urlopen(req, timeout=POST_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (URLError, TimeoutError, OSError):
        return False


def look_every() -> float:
    return config.env_float("LOOK_EVERY", 2.5, lo=0.5)


def rover_vision() -> bool:
    """ROVER_VISION=0 leaves the looking to the hub: the rover only streams its
    camera (GET :5001/frame.jpg) and drives, so it needs no model keys and a
    hub on CAM_SOURCE=rover doesn't file every find twice."""
    return config.env_flag("ROVER_VISION", True)


_latest_frame = None   # return_home sights the beacon through this; :5001/frame.jpg serves it


def run(opener=None, identify=None, post=None, ping=None, sleep=time.sleep, ticks=None) -> None:
    """Grab, gate, price, file at the hub. Injectable like app.scan_loop."""
    global _latest_frame
    opener = opener or capture.open_camera
    look = rover_vision()
    if look:
        # Imported here, not at the top: a feed-only rover (ROVER_VISION=0) never
        # identifies or prices, so it runs on a Pi without rapidfuzz or model SDKs.
        from rig import pricing, vision
        identify = identify or vision.identify_all
    post = post or (lambda payload: post_exhibit(hub_url(), payload))
    ping = ping_hub if ping is None else ping
    from rig import drive
    drive.set_frame_source(lambda: _latest_frame)
    queue: deque[dict] = deque(maxlen=QUEUE_MAX)
    cam = None
    seen = 0
    last_look = 0.0
    last_ping = float("-inf")  # first tick always pings, even right after boot
    hub_up = False             # drains only attempt while the last ping landed
    while ticks is None or seen < ticks:
        seen += 1
        if time.monotonic() - last_ping >= 10:
            # Stamp the attempt, not the success: a dead hub must not hot-loop
            # a blocking connect inside the frame loop. Retry every ~10s.
            last_ping = time.monotonic()
            hub_up = ping(hub_url())
            journal.event("hub-link", hub_up, hub_url())
            if not hub_up and (seen == 1 or seen % 60 == 0):
                log.warning("hub ping failed; will retry")
        if cam is None or not cam.isOpened():
            try:
                if cam is not None:
                    try:
                        cam.release()
                    except Exception:
                        pass
            except Exception:
                pass
            cam = opener()
            if cam is None or not cam.isOpened():
                cam = None
                journal.event("camera", False, "open failed; retrying")
                log.warning("rover camera lost; retrying")
                sleep(2)
                continue
            journal.event("camera", True)
        frame = capture.grab_frame(cam)
        _latest_frame = frame
        if frame is None:
            cam.release()
            cam = None
            journal.event("camera", False, "grab returned nothing")
            sleep(1)
            continue
        if (look and capture.scene_changed(frame)
                and (time.monotonic() - last_look) >= look_every()):
            last_look = time.monotonic()
            b64 = capture.frame_b64(frame)
            result = identify(b64)
            # identify_all returns a list; an injected single-object function is
            # normalized, so the rover files every object it sees, one POST each.
            objects = result if isinstance(result, list) else ([] if not result else [result])
            for parsed in objects:
                pricing.finalize_exhibit(parsed, vision.exits_mode())
                parsed["frame_b64"] = b64
                queue.append(parsed)
        # Drain only while the heartbeat says the hub answers: a doomed POST
        # blocks up to POST_TIMEOUT, so retrying every tick would stall the
        # frame loop at ~4s per frame for the whole outage.
        while queue and hub_up:
            payload = queue[0]
            if post(dict(payload)):
                queue.popleft()
                log.info("filed exhibit %s $%s (%s queued)", payload["item"],
                         payload["value_usd"], len(queue))
            else:
                # Dead mid-drain: stop posting, but re-probe next tick — if the
                # hub only blinked, the queue drains on the very next frame.
                hub_up = False
                last_ping = float("-inf")
                journal.event("hub-link", False, "POST failed mid-drain")
                log.warning("hub unreachable; %s exhibit(s) queued", len(queue))
                break
        sleep(1 / 12)


def main() -> None:
    try:
        from pathlib import Path

        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
    except ImportError:
        pass
    journal.setup()                     # after dotenv so .env can set RIG_LOG_*
    from rig import drive, drive_server
    server = drive_server.start(drive.get_driver(), frame_source=lambda: _latest_frame)
    log.info("rover filing to %s%s", hub_url(),
             "" if rover_vision() else " (camera feed only; the hub does the looking)")
    try:
        run()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
