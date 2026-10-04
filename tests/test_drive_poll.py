"""Pull-mode teleop + rover frame push: the hub-side queue, the rover's
poller, and /api/cam/frame. Covers the hosted-backend path where the hub
can't reach rover:5001 inbound. No camera, no GPIO, no outside network."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("RIG_VOICE", "0")
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

_TMP = Path(tempfile.mkdtemp(prefix="heist-poll-tests-"))
os.environ["RIG_STATE_FILE"] = str(_TMP / "module-case.json")

import cv2
import numpy as np

from rig import app as rig_app
from rig import drive_server
from rig.drive import ConsoleDriver

rig_app.voice.announce = lambda *a, **k: None
rig_app.voice.announce_top5 = lambda *a, **k: None


def _jpeg() -> bytes:
    frame = np.full((8, 8, 3), 128, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


class DrivePoll(unittest.TestCase):
    """Hub queues teleop for a pull-only rover; the rover drains it."""

    def setUp(self):
        self.client = rig_app.app.test_client()
        rig_app._rover.addr = None
        rig_app._rover.seen = 0.0
        rig_app._rover.poll = False
        with rig_app._drive_cond:
            rig_app._drive_queue.clear()
        rig_app._pushed_frame = None

    def tearDown(self):
        os.environ.pop("RIG_TOKEN", None)
        rig_app._rover.addr = None
        rig_app._rover.seen = 0.0
        rig_app._rover.poll = False
        with rig_app._drive_cond:
            rig_app._drive_queue.clear()
        rig_app._pushed_frame = None

    def ping(self, poll: bool):
        return self.client.post("/api/rover_ping", json={"poll": poll})

    def test_poll_rover_gets_queued_commands(self):
        self.assertEqual(self.ping(poll=True).status_code, 200)
        res = self.client.post("/api/drive", json={"dir": "forward", "secs": 0.4})
        self.assertEqual(res.status_code, 202)
        self.assertTrue(res.get_json()["queued"])
        res = self.client.get("/api/drive/pending?wait=0")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["cmd"], {"dir": "forward", "secs": 0.4})
        # Drained: the next poll finds an empty queue.
        self.assertEqual(self.client.get("/api/drive/pending?wait=0").status_code, 204)

    def test_nonpoll_rover_still_takes_the_forward_path(self):
        self.ping(poll=False)
        # 127.0.0.1:5001 answers nothing in the suite: forward, not queue.
        res = self.client.post("/api/drive", json={"dir": "stop"})
        self.assertIn(res.status_code, (200, 502))
        self.assertNotEqual(res.status_code, 202)
        self.assertFalse(rig_app._drive_queue)

    def test_no_rover_registered_is_503_not_queue(self):
        res = self.client.post("/api/drive", json={"dir": "forward"})
        self.assertEqual(res.status_code, 503)
        self.assertFalse(rig_app._drive_queue)

    def test_pending_long_poll_wakes_on_command(self):
        self.ping(poll=True)
        got = {}

        def drain():
            got["res"] = self.client.get("/api/drive/pending?wait=5")

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        time.sleep(0.2)
        self.assertNotIn("res", got)   # still held open
        self.client.post("/api/drive", json={"dir": "left"})
        thread.join(3)
        self.assertEqual(got["res"].status_code, 200)
        self.assertEqual(got["res"].get_json()["cmd"]["dir"], "left")

    def test_pending_poll_refreshes_registration(self):
        self.ping(poll=True)
        rig_app._rover.seen = 0.0
        self.assertFalse(rig_app._rover.wants_poll())   # expired
        self.client.get("/api/drive/pending?wait=0")    # a poll is a heartbeat too
        self.assertTrue(rig_app._rover.wants_poll())

    def test_pending_expired_rover_drains_nothing_new(self):
        self.ping(poll=True)
        rig_app._rover.seen = 0.0   # registration expired
        res = self.client.post("/api/drive", json={"dir": "forward"})
        self.assertEqual(res.status_code, 503)

    def test_pending_requires_token_when_set(self):
        os.environ["RIG_TOKEN"] = "crew"
        self.assertEqual(self.client.get("/api/drive/pending?wait=0").status_code, 401)
        res = self.client.get("/api/drive/pending?wait=0",
                              headers={"X-Rig-Token": "crew"})
        self.assertEqual(res.status_code, 204)

    def test_cam_frame_accepts_and_serves_pushed_jpeg(self):
        res = self.client.post("/api/cam/frame", data=_jpeg(),
                               content_type="image/jpeg")
        self.assertEqual(res.status_code, 200)
        cam = rig_app._RoverCamera()
        self.assertTrue(cam.isOpened())   # pushed frame alone opens the feed
        ok, frame = cam.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (8, 8, 3))

    def test_cam_frame_stale_is_not_open(self):
        rig_app._pushed_frame = (b"x", time.monotonic() - 60)
        self.assertFalse(rig_app._RoverCamera().isOpened())

    def test_cam_frame_rejects_empty_and_requires_token(self):
        self.assertEqual(self.client.post("/api/cam/frame").status_code, 400)
        os.environ["RIG_TOKEN"] = "crew"
        self.assertEqual(self.client.post(
            "/api/cam/frame", data=_jpeg(),
            content_type="image/jpeg").status_code, 401)


class ApplyCommand(unittest.TestCase):
    """Shared drive-command parsing: push and pull paths behave identically."""

    def setUp(self):
        self.driver = ConsoleDriver()

    def test_directions_and_clamps(self):
        drive_server.apply_command(self.driver, {"dir": "forward", "secs": 99})
        drive_server.apply_command(self.driver, {"dir": "nonsense", "secs": "x"})
        drive_server.apply_command(self.driver, {"dir": "back"})
        moves = self.driver.moves
        self.assertEqual(moves[0], ("forward", drive_server.MAX_SECS))
        self.assertEqual(moves[1], ("stop", 0.4))
        self.assertEqual(moves[2], ("back", 0.4))

    def test_return_spawns_home_walk(self):
        direction = drive_server.apply_command(self.driver, {"dir": "return"})
        self.assertEqual(direction, "return")
        self.assertEqual(self.driver.moves, [])   # nothing moved directly


class Poller(unittest.TestCase):
    """drive_server.start_poller drains a hub's pending queue over HTTP."""

    def test_poller_applies_queued_commands(self):
        cmds = [{"cmd": {"dir": "forward", "secs": 0.2}}, {"cmd": {"dir": "right"}}]

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(cmds.pop(0) if cmds else {}).encode() \
                    if cmds else b""
                if body:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(204)
                    self.end_headers()

            def log_message(self, *a):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        driver = ConsoleDriver()
        try:
            drive_server.start_poller(
                driver, f"http://127.0.0.1:{server.server_address[1]}", wait=0)
            deadline = time.time() + 5
            while len(driver.moves) < 2 and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(driver.moves[:2], [("forward", 0.2), ("right", 0.4)])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
