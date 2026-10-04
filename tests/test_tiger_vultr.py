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


if __name__ == "__main__":
    unittest.main()
