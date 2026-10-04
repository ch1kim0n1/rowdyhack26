"""The TigerData + Vultr integration and the near-zero-delay change bus.

No database, no Vultr key, no network: every new path is exercised in its
disabled/offline form plus its in-process push logic. Mirrors the rest of the
suite — the rig behaves exactly as before when neither sponsor is configured.
"""
from __future__ import annotations

import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import numpy as np

os.environ.setdefault("RIG_VOICE", "0")
for _var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SERPAPI_API_KEY",
             "VULTR_API_KEY", "TIGER_DB_URL", "RIG_TOKEN", "VULTR_VISION_FIRST"):
    os.environ.pop(_var, None)

from test_contract import _Frames, blank

from rig import app as rig_app
from rig import capture, sync, timescale, vision, vultr


class MultiObjectVisionTests(unittest.TestCase):
    def test_parse_many_reads_an_objects_array(self):
        text = ('{"objects":[{"item":"Sony WH-1000XM6","value_usd":480},'
                '{"item":"Wooden Chair","value_usd":40},{"item":"Desk Fan","value_usd":25}]}')
        objs = vision.parse_many(text, 8)
        self.assertEqual([o["item"] for o in objs], ["Sony WH-1000XM6", "Wooden Chair", "Desk Fan"])

    def test_parse_many_reads_a_bare_array_and_respects_the_cap(self):
        text = '[{"item":"A","value_usd":1},{"item":"B","value_usd":2},{"item":"C","value_usd":3}]'
        self.assertEqual(len(vision.parse_many(text, 2)), 2)

    def test_parse_many_tolerates_a_lone_object(self):
        objs = vision.parse_many('{"item":"Lamp","value_usd":180}', 8)
        self.assertEqual(objs[0]["item"], "Lamp")

    def test_parse_many_masks_a_payment_card_in_any_object(self):
        text = '{"objects":[{"item":"note 4111 1111 1111 1111","value_usd":0}]}'
        self.assertNotIn("4111 1111 1111 1111", vision.parse_many(text, 8)[0]["item"])

    def test_only_named_and_priced_objects_are_worth_filing(self):
        text = ('{"objects":[{"item":"Sony WH-1000XM4","value_usd":180},'
                '{"item":"laptop (unbranded)","value_usd":200},'
                '{"item":"Unknown dark headset/earpiece","value_usd":25},'
                '{"item":"Desk/table silhouette (background)","value_usd":50},'
                '{"item":"Person with dark hair","value_usd":5},'
                '{"item":"conference lanyard","value_usd":0}]}')
        kept = [o["item"] for o in vision.parse_many(text, 8) if vision.worth_filing(o)]
        self.assertEqual(kept, ["Sony WH-1000XM4", "laptop (unbranded)"])

    def test_identify_all_drops_guesses_before_the_cap(self):
        reply = ('{"objects":[{"item":"Unknown object","value_usd":9},'
                 '{"item":"Free flyer","value_usd":0},{"item":"Leica M3","value_usd":1850}]}')
        env = {"VULTR_API_KEY": "k", "VISION_MAX_OBJECTS": "1", "RIG_OFFLINE": "0",
               "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "RIG_MODE": ""}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(vultr, "raw", return_value=reply):
            out = vision.identify_all("ZmFrZQ==")
        self.assertEqual([o["item"] for o in out], ["Leica M3"])

    def test_a_cut_off_reply_keeps_the_objects_that_arrived_whole(self):
        cut = ('{"objects":[\n  {"item":"Sony WH-1000XM6","value_usd":230,'
               '"bbox":[0.45,0.18,0.22,0.12]},\n  {"item":"Desk Fan","value_usd":25},\n  {"item":"Half')
        self.assertEqual([o["item"] for o in vision.parse_many(cut, 8)],
                         ["Sony WH-1000XM6", "Desk Fan"])
        with self.assertRaises(ValueError):
            vision.parse_many("no json here at all", 8)

    def test_a_failed_provider_files_nothing_rather_than_a_stand_in(self):
        env = {"VULTR_API_KEY": "k", "RIG_OFFLINE": "0", "OPENAI_API_KEY": "",
               "ANTHROPIC_API_KEY": "", "RIG_MODE": ""}
        for reply in ("the model rambled and sent no json", None):
            def raw(image_b64, prompt, reply=reply):
                vision._last_call_failed = reply is None
                return reply
            with mock.patch.dict(os.environ, env), mock.patch.object(vultr, "raw", raw):
                self.assertEqual(vision.identify_all("ZmFrZQ=="), [])

    def test_identify_all_offline_returns_a_list(self):
        os.environ["RIG_OFFLINE"] = "1"
        try:
            out = vision.identify_all("ZmFrZQ==")
            self.assertIsInstance(out, list)
            self.assertTrue(out and out[0]["item"])
        finally:
            os.environ.pop("RIG_OFFLINE", None)


class MultiObjectFlowTests(unittest.TestCase):
    """Every object in a frame reaches the ledger — hat and rover."""

    def setUp(self):
        blank(rig_app.store)
        capture.reset_gate()

    def test_examine_files_every_object_and_pushes_once(self):
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        before = rig_app.bus.version()
        rig_app._examine(frame, identify=lambda _b: [
            {"item": "Sony WH-1000XM6", "category": "headphones", "value_usd": 480,
             "bbox": [0.2, 0.2, 0.3, 0.3]},
            {"item": "Wooden Chair", "category": "chair", "value_usd": 40},
            {"item": "Desk Fan", "category": "fan", "value_usd": 25},
        ])
        self.assertEqual(rig_app.store.count(), 3)
        self.assertGreater(rig_app.bus.version(), before)

    def test_examine_still_accepts_a_single_object(self):
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        rig_app._examine(frame, identify=lambda _b: {
            "item": "Vintage Rolex", "category": "watch", "value_usd": 4200})
        self.assertEqual(rig_app.store.count(), 1)

    def test_rover_files_every_object_per_look(self):
        from rig import rover
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        cam = _Frames([frame, frame.copy(), frame.copy()])
        sent = []
        rover.run(
            opener=lambda: cam,
            identify=lambda _b: [
                {"item": "HEADPHONES", "category": "headphones", "value_usd": 480,
                 "bbox": [0.2, 0.2, 0.3, 0.3]},
                {"item": "CHAIR", "category": "chair", "value_usd": 40},
            ],
            post=lambda p: (sent.append(p["item"]), True)[1],
            ping=lambda _u: True, sleep=lambda _s: None, ticks=3)
        self.assertEqual(sorted(sent), ["CHAIR", "HEADPHONES"])


class ChangeBusTests(unittest.TestCase):
    def test_publish_bumps_version_and_keeps_payload(self):
        bus = sync.ChangeBus()
        self.assertEqual(bus.version(), 0)
        v = bus.publish({"take": 10})
        self.assertEqual(v, 1)
        self.assertEqual(bus.snapshot(), (1, {"take": 10}))

    def test_wait_returns_at_once_when_already_ahead(self):
        bus = sync.ChangeBus()
        bus.publish({"a": 1})
        start = time.monotonic()
        version, payload = bus.wait(since=0, timeout=5)   # caller is behind; no block
        self.assertEqual(version, 1)
        self.assertEqual(payload, {"a": 1})
        self.assertLess(time.monotonic() - start, 0.5)

    def test_wait_times_out_quietly(self):
        bus = sync.ChangeBus()
        start = time.monotonic()
        version, _ = bus.wait(since=0, timeout=0.2)
        self.assertEqual(version, 0)
        self.assertGreaterEqual(time.monotonic() - start, 0.15)

    def test_wait_wakes_on_a_later_publish(self):
        bus = sync.ChangeBus()
        threading.Timer(0.1, lambda: bus.publish({"hot": True})).start()
        version, payload = bus.wait(since=0, timeout=3)
        self.assertEqual(version, 1)
        self.assertEqual(payload, {"hot": True})

    def test_stream_primes_then_heartbeats(self):
        bus = sync.ChangeBus()
        bus.publish({"take": 5})
        gen = bus.stream(timeout=0.1)
        first = next(gen)                       # primed with current state
        self.assertEqual(first, (1, {"take": 5}))
        beat = next(gen)                        # nothing new -> heartbeat
        self.assertEqual(beat, (1, None))


class TimescaleDisabledTests(unittest.TestCase):
    def setUp(self):
        blank(rig_app.store)

    def test_disabled_record_is_a_no_op(self):
        self.assertFalse(timescale.enabled())
        # Must not raise and must not import psycopg or start a worker.
        timescale.record_detection(rig_app.store, {"item": "X", "value_usd": 9})
        st = timescale.status()
        self.assertFalse(st["enabled"])
        self.assertEqual(st["queued"], 0)

    def test_sql_splitter_keeps_the_notify_function_whole(self):
        stmts = timescale._split_sql(timescale.SCHEMA_FILE.read_text())
        fn = [s for s in stmts if "pg_notify" in s]
        self.assertEqual(len(fn), 1)                 # the $$ body is not cut at its inner ;
        self.assertIn("RETURN NEW", fn[0])
        self.assertIn("LANGUAGE plpgsql", fn[0])
        self.assertTrue(any(s.startswith("CREATE TABLE") for s in stmts))

    def test_ensure_schema_async_is_a_no_op_when_disabled(self):
        timescale.ensure_schema_async()             # no TIGER_DB_URL: must not raise or connect

    def test_enqueue_without_a_live_worker(self):
        os.environ["TIGER_DB_URL"] = "postgres://nobody@localhost:1/none"
        saved = timescale._ensure_worker
        timescale._ensure_worker = lambda: None   # isolate enqueue from the DB worker
        try:
            self.assertTrue(timescale.enabled())
            timescale.record_detection(rig_app.store, {
                "item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200,
                "estimated": False, "source": "vultr", "price_source": "serpapi",
            }, device="rover", hot=True)
            self.assertEqual(timescale.status()["queued"], 1)
        finally:
            timescale._ensure_worker = saved
            timescale._queue.clear()
            os.environ.pop("TIGER_DB_URL", None)


class VultrProviderTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("VULTR_API_KEY", None)
        os.environ.pop("VULTR_VISION_FIRST", None)

    def test_disabled_by_default(self):
        self.assertFalse(vultr.enabled())
        self.assertIsNone(vultr.analyze([{"item": "x", "value_usd": 1}], 1))

    def test_identify_uses_vultr_when_it_is_the_only_key(self):
        os.environ["VULTR_API_KEY"] = "vk-test"
        calls = {}

        def fake(image_b64):
            calls["hit"] = image_b64
            return {"item": "VULTR VASE", "value_usd": 300, "estimated": True,
                    "bbox": None, "category": "vase"}

        saved = vultr.identify
        vultr.identify = fake
        try:
            out = vision.identify("ZmFrZQ==")
            self.assertEqual(out["item"], "VULTR VASE")
            self.assertEqual(calls["hit"], "ZmFrZQ==")
        finally:
            vultr.identify = saved

    def test_vision_first_puts_vultr_ahead_of_openai(self):
        os.environ["VULTR_API_KEY"] = "vk-test"
        os.environ["VULTR_VISION_FIRST"] = "1"
        os.environ["OPENAI_API_KEY"] = "sk-test"
        order = []
        saved_v, saved_o = vultr.identify, vision._identify_openai
        vultr.identify = lambda b: (order.append("vultr"), {"item": "V", "value_usd": 1,
                                    "estimated": True, "bbox": None, "category": "x"})[1]
        vision._identify_openai = lambda b: (order.append("openai"), None)[1]
        try:
            vision.identify("ZmFrZQ==")
            self.assertEqual(order[0], "vultr")
        finally:
            vultr.identify, vision._identify_openai = saved_v, saved_o
            os.environ.pop("OPENAI_API_KEY", None)


class HubWiringTests(unittest.TestCase):
    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()

    def test_wrist_plain_get_is_unchanged_and_carries_version(self):
        body = self.client.get("/wrist.json").get_json()
        for key in ("case_no", "take", "count", "pending", "revealed", "top", "v"):
            self.assertIn(key, body)

    def test_wrist_longpoll_returns_at_once_when_timeout_is_zero(self):
        v0 = rig_app.bus.version()
        start = time.monotonic()
        body = self.client.get(f"/wrist.json?since={v0 + 5}&wait=0").get_json()
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertIn("v", body)

    def test_a_rover_exhibit_pushes_the_bus(self):
        before = rig_app.bus.version()
        res = self.client.post("/api/exhibit", json={
            "item": "PUSHED VASE", "category": "vase", "value_usd": 300})
        self.assertEqual(res.status_code, 201)
        self.assertGreater(rig_app.bus.version(), before)

    def test_events_requires_token_when_set(self):
        os.environ["RIG_TOKEN"] = "crew"
        try:
            self.assertEqual(self.client.get("/events").status_code, 401)
        finally:
            os.environ.pop("RIG_TOKEN", None)

    def test_events_streams_the_payload(self):
        # Keep the stream finite so the test client doesn't block on the real
        # forever-generator.
        saved = rig_app.bus.stream
        rig_app.bus.stream = lambda timeout=15.0: iter([(1, {"take": 42})])
        try:
            res = self.client.get("/events")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.mimetype.startswith("text/event-stream"))
            self.assertIn(b'"take": 42', res.get_data())
        finally:
            rig_app.bus.stream = saved

    def test_insights_is_empty_without_vultr(self):
        rig_app.store.add_item({"item": "LAMP", "value_usd": 180})
        body = self.client.get("/api/insights").get_json()
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["insight"])

    def test_health_reports_the_new_subsystems(self):
        h = self.client.get("/health").get_json()
        self.assertIn("tiger", h)
        self.assertIn("vultr", h)
        self.assertIn("sync", h)
        self.assertFalse(h["tiger"]["enabled"])
        self.assertFalse(h["vultr"]["enabled"])


class StreamFeedTests(unittest.TestCase):
    """CAM_SOURCE as an MJPEG stream: the hub keeps the newest frame, scans it,
    and relays it to the consoles as a stream of its own."""

    def setUp(self):
        blank(rig_app.store)
        self.frames = [capture.frame_jpeg(np.full((48, 64, 3), shade, np.uint8))
                       for shade in (20, 120, 220)]
        frames = self.frames

        class Mjpeg(BaseHTTPRequestHandler):
            def do_GET(handler):
                handler.send_response(200)
                handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                handler.end_headers()
                try:
                    for i in range(400):
                        jpeg = frames[i % len(frames)]
                        handler.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                                            + jpeg + b"\r\n")
                        time.sleep(0.01)
                except OSError:
                    pass

            def log_message(handler, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Mjpeg)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mjpg"
        self.env = mock.patch.dict(os.environ, {"CAM_SOURCE": self.url, "RIG_TOKEN": ""})
        self.env.start()
        # Another test's rover ping would still be registered and win the camera.
        self.no_rover = mock.patch.object(rig_app._rover, "target", return_value=None)
        self.no_rover.start()
        self.addCleanup(self.no_rover.stop)

    def tearDown(self):
        if rig_app._reader is not None:
            rig_app._reader.stop()
            rig_app._reader = None
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()

    def _wait_for_frames(self):
        reader = rig_app._stream_reader()
        seq, jpeg = reader.wait(0, 5.0)
        self.assertIsNotNone(jpeg)
        return reader

    def test_a_still_url_is_not_a_stream(self):
        from rig import feed
        self.assertTrue(feed.is_stream_url("http://pi:9000/mjpg"))
        self.assertFalse(feed.is_stream_url("http://pi:9000/mjpg.jpg"))
        self.assertFalse(feed.is_stream_url(None))

    def test_the_reader_slices_whole_jpegs_out_of_the_stream(self):
        reader = self._wait_for_frames()
        _, jpeg = reader.latest()
        self.assertIn(jpeg, self.frames)
        time.sleep(0.5)
        self.assertGreater(reader.fps(), 5)

    def test_the_hub_camera_reads_the_newest_stream_frame(self):
        self._wait_for_frames()
        cam = rig_app._remote_camera()
        self.assertIsInstance(cam, rig_app._UrlCamera)
        ok, frame = cam.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (48, 64, 3))

    def test_the_console_gets_a_steady_id_and_a_stream(self):
        self._wait_for_frames()
        client = rig_app.app.test_client()
        frame_id = client.get("/state.json").get_json()["frame_id"]
        self.assertTrue(str(frame_id).startswith("live-"))
        self.assertEqual(client.get("/state.json").get_json()["frame_id"], frame_id)
        res = client.get(f"/frame.jpg?{frame_id}", buffered=False)
        self.assertTrue(res.mimetype.startswith("multipart/x-mixed-replace"))
        first = next(res.response)
        self.assertTrue(first.startswith(b"--frame"))
        self.assertTrue(any(jpeg in first for jpeg in self.frames))
        res.close()
        # A plain request is still one JPEG, for crops, the wrist and old consoles.
        self.assertEqual(client.get("/frame.jpg").mimetype, "image/jpeg")

    def test_token_mode_keeps_the_numbered_stills(self):
        self._wait_for_frames()
        with mock.patch.dict(os.environ, {"RIG_TOKEN": "crew"}):
            body = rig_app.app.test_client().get(
                "/state.json", headers={"X-Rig-Token": "crew"}).get_json()
        self.assertIsInstance(body["frame_id"], int)


class PicarXDriverTests(unittest.TestCase):
    """A SunFounder PiCar-X drives through its own library: steer, then roll."""

    def _driver(self, calls):
        import sys
        import types

        class Picarx:
            def forward(self, speed):
                calls.append(("forward", speed))

            def backward(self, speed):
                calls.append(("backward", speed))

            def set_dir_servo_angle(self, angle):
                calls.append(("steer", angle))

            def stop(self):
                calls.append(("stop",))

        fake = types.ModuleType("picarx")
        fake.Picarx = Picarx
        from rig import drive
        with mock.patch.dict(sys.modules, {"picarx": fake}),                 mock.patch.dict(os.environ, {"DRIVE_KIT": "picarx", "PICARX_SPEED": "55"}):
            return drive.get_driver()

    def test_left_steers_then_rolls_and_stops_when_time_is_up(self):
        calls = []
        self._driver(calls).move("left", 0.01)
        self.assertEqual(calls, [("steer", -30), ("forward", 55), ("stop",), ("steer", 0)])

    def test_back_and_stop(self):
        calls = []
        driver = self._driver(calls)
        driver.move("back", 0.01)
        driver.move("stop")
        self.assertEqual(calls[:2], [("steer", 0), ("backward", 55)])
        self.assertEqual(calls[-2:], [("stop",), ("steer", 0)])

    def test_a_missing_library_falls_back(self):
        import sys

        from rig import drive
        with mock.patch.dict(sys.modules, {"picarx": None}),                 mock.patch.dict(os.environ, {"DRIVE_KIT": ""}):
            self.assertNotIsInstance(getattr(drive.get_driver(), "_robot", None), drive._PicarX)


class MarkerLifetimeTests(unittest.TestCase):
    """A find's box clears from the live view after MARKER_SECONDS; the find
    itself stays in the tally and the ledger."""

    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()
        rig_app.store.add_item({"item": "LAMP", "value_usd": 180, "bbox": [0.2, 0.2, 0.3, 0.3]})

    def _age(self, secs):
        with rig_app.store._lock:
            rig_app.store._items[0]["seen"] -= secs

    def test_a_fresh_find_has_its_box(self):
        self.assertIn("bbox", self.client.get("/state.json").get_json()["items"][0])

    def test_the_box_clears_but_the_find_stays_counted(self):
        self._age(10)
        body = self.client.get("/state.json").get_json()
        self.assertNotIn("bbox", body["items"][0])
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["take"], 180)
        # The ledger keeps the box: crops and the report still need it.
        self.assertIn("bbox", rig_app.store.snapshot()["items"][0])

    def test_a_repeat_sighting_puts_the_box_back_where_it_is_now(self):
        self._age(10)
        added, _ = rig_app.store.add_item(
            {"item": "LAMP", "value_usd": 180, "bbox": [0.5, 0.5, 0.2, 0.2]})
        self.assertFalse(added)                              # still one exhibit
        body = self.client.get("/state.json").get_json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["bbox"], [0.5, 0.5, 0.2, 0.2])
        # The filed box is untouched: it belongs to the filed still.
        self.assertEqual(rig_app.store.snapshot()["items"][0]["bbox"], [0.2, 0.2, 0.3, 0.3])

    def test_zero_keeps_every_box(self):
        self._age(10)
        with mock.patch.dict(os.environ, {"MARKER_SECONDS": "0"}):
            self.assertIn("bbox", self.client.get("/state.json").get_json()["items"][0])


class RoverFeedTests(unittest.TestCase):
    """CAM_SOURCE=rover: the rover serves its latest frame on the drive port
    and the hub reads it through a VideoCapture-shaped camera."""

    def setUp(self):
        from rig import drive_server
        from rig.drive import ConsoleDriver
        self.frame = np.full((48, 64, 3), 90, np.uint8)
        self.server = drive_server.drive_server(ConsoleDriver(), 0, lambda: self.frame)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _camera(self):
        cam = rig_app._RoverCamera()
        cam.PORT = self.port
        return cam

    def test_hub_reads_the_rover_frame(self):
        with mock.patch.object(rig_app._rover, "target", return_value="127.0.0.1"):
            cam = self._camera()
            self.assertTrue(cam.isOpened())
            ok, frame = cam.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, self.frame.shape)

    def test_no_rover_registered_reads_as_a_lost_camera(self):
        with mock.patch.object(rig_app._rover, "target", return_value=None):
            cam = self._camera()
            self.assertFalse(cam.isOpened())
            self.assertEqual(cam.read(), (False, None))

    def test_a_rover_with_no_frame_yet_reads_as_a_lost_camera(self):
        self.frame = None
        with mock.patch.object(rig_app._rover, "target", return_value="127.0.0.1"):
            self.assertEqual(self._camera().read(), (False, None))

    def test_the_rover_frame_is_token_gated(self):
        with mock.patch.dict(os.environ, {"RIG_TOKEN": "crew"}), \
                mock.patch.object(rig_app._rover, "target", return_value="127.0.0.1"):
            ok, _ = self._camera().read()            # the hub sends its token
            self.assertTrue(ok)
            from urllib.error import HTTPError
            from urllib.request import urlopen
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"http://127.0.0.1:{self.port}/frame.jpg", timeout=5)
            self.assertEqual(caught.exception.code, 401)

    def test_a_url_source_is_read_without_a_rover_or_the_token(self):
        seen = {}

        class Snapshot(BaseHTTPRequestHandler):
            def do_GET(handler):
                seen["token"] = handler.headers.get("X-Rig-Token")
                body = capture.frame_jpeg(self.frame)
                handler.send_response(200)
                handler.send_header("Content-Type", "image/jpeg")
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(handler, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Snapshot)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/mjpg.jpg"
        try:
            with mock.patch.dict(os.environ, {"CAM_SOURCE": url, "RIG_TOKEN": "crew"}), \
                    mock.patch.object(rig_app._rover, "target", return_value=None):
                self.assertTrue(rig_app.rover_feed())
                cam = rig_app._remote_camera()
                self.assertIsInstance(cam, rig_app._UrlCamera)
                self.assertTrue(cam.isOpened())          # no rover has pinged
                ok, frame = cam.read()
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, self.frame.shape)
        self.assertIsNone(seen["token"])                 # our token stays home

    def test_rover_vision_off_skips_the_model(self):
        from rig import rover
        looks = []
        with mock.patch.dict(os.environ, {"ROVER_VISION": "0"}):
            rover.run(opener=lambda: _Frames([np.full((48, 64, 3), shade, np.uint8)
                                              for shade in (0, 255, 0)]),
                      identify=lambda b64: looks.append(b64) or [],
                      post=lambda payload: True, ping=lambda url: True,
                      sleep=lambda s: None, ticks=3)
        self.assertEqual(looks, [])


if __name__ == "__main__":
    unittest.main()
