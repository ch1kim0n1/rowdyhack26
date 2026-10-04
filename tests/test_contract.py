"""The dashboard contract, dedup, crops, the scan loop, and the two hardware fixes.

No camera and no API keys. A fake capture stands in for the webcam.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("RIG_VOICE", "0")   # the suite never talks out loud
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("SERPAPI_API_KEY", None)
os.environ.pop("VULTR_API_KEY", None)     # no Vultr provider or network in the suite
os.environ.pop("TIGER_DB_URL", None)      # no Tiger writes in the suite

# Keep every store's case file out of the repo and out of each other's way.
_TMP = Path(tempfile.mkdtemp(prefix="heist-tests-"))
os.environ["RIG_STATE_FILE"] = str(_TMP / "module-case.json")

import cv2
import numpy as np
from PIL import Image, ImageDraw

from rig import app as rig_app
from rig import button, capture, display, pricing, vision
from rig.store import Store

# Speech must not start during a route hit, and pricing must not touch the network.
rig_app.voice.announce = lambda *a, **k: None
rig_app.voice.announce_top5 = lambda *a, **k: None
rig_app.pricing.resolve = lambda name, value: (float(value or 0), False)
rig_app.pricing.resolve_detailed = lambda name, value: (float(value or 0), False, "serpapi")


def fresh_store() -> Store:
    """A store whose case file cannot leak into another test."""
    path = Path(tempfile.mkdtemp(prefix="heist-store-")) / "case.json"
    return Store(path)


def blank(store: Store) -> None:
    with store._lock:
        store._items.clear()
        store._jpeg = None
        store._frame_id = 0
        store._camera_ok = True
        store._pending = False
        store._revealed = False
        store._case_no = 1138
    store.state_path().unlink(missing_ok=True)
    capture.reset_gate()
    display.show_take(0, 0, 1138)


class DedupAndBbox(unittest.TestCase):
    def test_same_category_fuzzy_name_is_one_exhibit(self):
        store = fresh_store()
        frame = capture.paint_still([0.1, 0.2, 0.3, 0.4])
        added, hot = store.add_item(
            {"item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200,
             "bbox": [0.12, 0.2, 0.26, 0.36]},
            frame,
        )
        self.assertTrue(added and hot)
        again, _hot = store.add_item(
            {"item": "vintage rolex sub", "category": "watch", "value_usd": 100},
            frame,
        )
        self.assertFalse(again)
        self.assertEqual(store.count(), 1)

    def test_missing_and_tiny_bbox_keep_the_label(self):
        store = fresh_store()
        added, _hot = store.add_item(
            {"item": "FIRST-ED. HEMINGWAY", "category": "book", "value_usd": 950,
             "estimated": True, "bbox": None},
        )
        self.assertTrue(added)
        row = store.snapshot()["items"][0]
        self.assertNotIn("bbox", row)
        parsed = vision.parse_response(
            '{"item": "Lamp", "value_usd": 12, "bbox": [0, 0, 0.01, 0.9]}'
        )
        self.assertEqual(parsed["item"], "Lamp")
        self.assertIsNone(parsed["bbox"])
        self.assertIsNone(vision.parse_response('{"item": null}'))

    def test_second_press_clears_the_case(self):
        store = fresh_store()
        store.add_item({"item": "LAMP", "value_usd": 40, "bbox": [0.1, 0.1, 0.2, 0.2]})
        self.assertTrue(store.mark_revealed())
        self.assertFalse(store.add_item({"item": "LATE", "value_usd": 1})[0])
        self.assertTrue(store.reset_case())
        snap = store.snapshot()
        self.assertFalse(snap["revealed"])
        self.assertEqual(snap["items"], [])
        self.assertEqual(snap["case_no"], 1139)


class ModelPrice(unittest.TestCase):
    def test_sold_comps_do_not_mix_a_razer_with_a_sony(self):
        rows = [
            {"title": "Sony WH-1000XM6 headphones", "price": {"extracted": 480}},
            {"title": "Sony WH-1000XM6 black", "price": {"extracted": 510}},
            {"title": "Sony WH-1000XM6 used", "price": {"extracted": 450}},
            {"title": "Razer BlackShark V2 headset", "price": {"extracted": 70}},
            {"title": "Razer BlackShark V2 X", "price": {"extracted": 60}},
            {"title": "headphone replacement cable", "price": {"extracted": 8}},
        ]
        self.assertEqual(pricing.comps("Sony WH-1000XM6", rows), 480)
        self.assertEqual(pricing.comps("Razer BlackShark V2", rows), 65)
        self.assertIsNone(pricing.comps("headphones", rows))

    def test_serpapi_toggle_default_off_and_endpoint(self):
        pricing.set_serpapi_enabled(False)
        self.assertFalse(pricing.is_serpapi_enabled())
        # With SerpAPI disabled, market_value returns None without network calls
        self.assertIsNone(pricing._lookup("Sony WH-1000XM6"))
        pricing.toggle_serpapi()
        self.assertTrue(pricing.is_serpapi_enabled())
        client = rig_app.app.test_client()
        res = client.get("/api/serpapi")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["enabled"])
        res_post = client.post("/api/serpapi", json={"enabled": False})
        self.assertEqual(res_post.status_code, 200)
        self.assertFalse(res_post.get_json()["enabled"])
        self.assertFalse(pricing.is_serpapi_enabled())


class OfflineFallback(unittest.TestCase):
    def setUp(self):
        vision.reset_offline_fallback()

    def test_offline_fallback_cycles_catalog(self):
        first = vision.offline_fallback()
        self.assertEqual(first["item"], "Sony WH-1000XM6")
        self.assertEqual(first["value_usd"], 480.0)
        self.assertIsNotNone(first["bbox"])

        second = vision.offline_fallback()
        self.assertEqual(second["item"], "Razer BlackShark V2")
        self.assertEqual(second["value_usd"], 70.0)

    def test_identify_offline_when_no_keys_or_rig_offline(self):
        item = vision.identify("fake_b64")
        self.assertIsNotNone(item)
        self.assertEqual(item["item"], "Sony WH-1000XM6")

        os.environ["RIG_OFFLINE"] = "1"
        try:
            item2 = vision.identify("fake_b64")
            self.assertEqual(item2["item"], "Razer BlackShark V2")
        finally:
            os.environ.pop("RIG_OFFLINE", None)

    def test_a_failed_openai_call_falls_back_to_anthropic(self):
        def boom(_b64):
            vision._last_call_failed = True
            return None

        vision.reset_offline_fallback()
        saved = (vision._identify_openai, vision._identify_anthropic)
        vision._identify_openai = boom
        vision._identify_anthropic = lambda _b64: {"item": "ANTHROPIC LAMP", "value_usd": 9}
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            self.assertEqual(vision.identify("fake_b64")["item"], "ANTHROPIC LAMP")
        finally:
            vision._identify_openai, vision._identify_anthropic = saved
            vision._last_call_failed = False
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_unparseable_openai_body_counts_as_failure(self):
        """A 200 carrying junk JSON is a failed call, not an empty frame —
        the next provider still gets its shot."""
        vision.reset_offline_fallback()
        saved = (vision._openai_still, vision._identify_anthropic)
        vision._openai_still = lambda *a, **k: "this is not json"
        vision._identify_anthropic = lambda _b64: {"item": "ANTHROPIC LAMP", "value_usd": 9}
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            self.assertEqual(vision.identify("fake_b64")["item"], "ANTHROPIC LAMP")
        finally:
            vision._openai_still, vision._identify_anthropic = saved
            vision._last_call_failed = False
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_all_providers_down_still_lands_on_the_catalog(self):
        def boom(_b64):
            vision._last_call_failed = True
            return None

        vision.reset_offline_fallback()
        saved = (vision._identify_openai, vision._identify_anthropic)
        vision._identify_openai = boom
        vision._identify_anthropic = boom
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            item = vision.identify("fake_b64")
            self.assertEqual(item["source"], "offline")
        finally:
            vision._identify_openai, vision._identify_anthropic = saved
            vision._last_call_failed = False
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)


class FrameHashFallback(unittest.TestCase):
    """Item 12 per the build guide: a frame-hash lookup of canned responses."""

    def test_same_still_returns_the_same_exhibit(self):
        b64 = capture.frame_b64(capture.paint_still([0.2, 0.2, 0.3, 0.4], 200))
        one = vision.offline_fallback(b64)
        two = vision.offline_fallback(b64)
        self.assertEqual(one["item"], two["item"])
        self.assertEqual(one["source"], "offline")

    def test_a_distinct_scene_can_yield_a_distinct_exhibit(self):
        specs = [
            {"bbox": [0.05, 0.05, 0.25, 0.25], "shade": 220},
            {"bbox": [0.60, 0.55, 0.30, 0.30], "shade": 200},
            {"bbox": [0.40, 0.10, 0.30, 0.30], "shade": 180},
        ]
        hashes = {vision.frame_hash(capture.frame_b64(capture.paint_still(s["bbox"], s["shade"]))) for s in specs}
        self.assertGreater(len(hashes), 1)

    def test_garbage_still_falls_back_to_the_catalog_cycle(self):
        vision.reset_offline_fallback()
        item = vision.offline_fallback("not-a-jpeg")
        self.assertEqual(item["item"], "Sony WH-1000XM6")
        self.assertEqual(item["source"], "offline")


class Persistence(unittest.TestCase):
    def test_case_file_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            first = Store(path)
            frame = capture.paint_still([0.1, 0.1, 0.2, 0.2], 200)
            first.add_item({"item": "LAMP", "category": "lamp", "value_usd": 40, "why": "w",
                            "bbox": [0.1, 0.1, 0.2, 0.2]}, frame)
            first.mark_revealed()
            second = Store(path)
            self.assertEqual(second.count(), 1)
            self.assertTrue(second.revealed)
            self.assertEqual(second.manifest_rows()[0]["why"], "w")
            still, bbox = second.item_frame(1)
            self.assertIsNotNone(still)
            self.assertEqual(bbox, [0.1, 0.1, 0.2, 0.2])
            self.assertTrue(second.reset_case())
            self.assertFalse((Path(tmp) / "case-stills").exists())
            third = Store(path)
            self.assertEqual(third.count(), 0)
            self.assertFalse(third.revealed)
            self.assertEqual(third.case_no(), second.case_no())

    def test_a_corrupt_case_file_starts_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text("{not json")
            store = Store(path)
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.case_no(), 1138)


class HealthAndWhy(unittest.TestCase):
    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()

    def test_health_reports_subsystems_without_secrets(self):
        body = self.client.get("/health").get_json()
        for key in ("ok", "uptime_s", "camera_ok", "vision_provider", "serpapi",
                    "voice", "oled_mode", "persistence", "case_no", "items", "take"):
            self.assertIn(key, body)
        self.assertNotIn("sk-", json.dumps(body))

    def test_why_travels_to_snapshot_and_manifest(self):
        rig_app.store.add_item(
            {"item": "BRASS DESK LAMP", "category": "lamp", "value_usd": 180,
             "why": "priced from live eBay sold-listing comps"},
        )
        snap = self.client.get("/state.json").get_json()
        self.assertEqual(snap["items"][0]["why"], "priced from live eBay sold-listing comps")
        page = self.client.get("/manifest").get_data(as_text=True)
        self.assertIn("sold-listing", page)


class PremiereAndDesk(unittest.TestCase):
    """The premiere page, the dispatch desk and the kit files they load."""

    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()

    def test_pages_and_their_files_are_served(self):
        for path in ("/premiere", "/desk", "/premiere.css", "/premiere.js", "/intro.js",
                     "/desk.css", "/desk.js", "/wrist-oled.js", "/shots/live.png",
                     "/motion.js", "/motion.css", "/motion.html", "/motion-lab.js",
                     "/vault.js", "/vault.css", "/operations.css"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            res.close()

    def test_live_screens_load_conditional_motion_before_the_runtime(self):
        for path in ("/", "/desk", "/demo.html"):
            response = self.client.get(path)
            try:
                page = response.get_data(as_text=True)
            finally:
                response.close()
            self.assertIn("data-motion-status", page, path)
            self.assertLess(page.index('src="/motion.js"') if path != "/demo.html"
                            else page.index('src="motion.js"'), page.index('noir.js'), path)

    def test_media_routes_stay_inside_their_folders(self):
        for path in ("/media/../noir.css", "/shots/../../rig/app.py", "/brand/%2e%2e/noir.js"):
            self.assertIn(self.client.get(path).status_code, (400, 404), path)

    def test_motion_preserves_current_main_ui(self):
        with self.client.get("/premiere") as response:
            premiere = response.get_data(as_text=True)
        for marker in ('data-vault-stage', 'class="intro"', 'src="intro.js"',
                       'brand/appraisal-job-hero-wide.webp', 'data-vault-motion'):
            self.assertIn(marker, premiere)
        with self.client.get("/") as response:
            dashboard = response.get_data(as_text=True)
        for marker in ('data-job="appraisal"', 'data-job="mastermind"',
                       'id="job-sheet"', 'id="report-link"', 'id="skip-reveal"',
                       'class="vault-theme projector"', 'data-vault-motion'):
            self.assertIn(marker, dashboard)
        with self.client.get("/vault.js") as response:
            runtime = response.get_data(as_text=True)
        self.assertIn("appraisal-motion", runtime)
        self.assertIn("noirmotionchange", runtime)

    def test_public_pitch_is_authorized_reconnaissance(self):
        response = self.client.get("/premiere")
        try:
            page = response.get_data(as_text=True)
        finally:
            response.close()
        for phrase in ("Authorized Physical Red-Team Reconnaissance",
                       "assessor's wrist", "approved assessment area",
                       "not a security-risk score", "demo data, not observed findings"):
            self.assertIn(phrase, page)
        for phrase in ("thief's wrist", "Best Heist Theme Project", "robbing"):
            self.assertNotIn(phrase, page)
        response = self.client.get("/premiere.js")
        try:
            captions = response.get_data(as_text=True)
        finally:
            response.close()
        self.assertIn("authorized red-team walkthrough", captions)
        self.assertIn("not by security risk", captions)

    def test_internal_track_notes_are_not_served(self):
        for path in ("/INTERNAL-NOTES.md", "/internal-notes"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        notes = (rig_app.ROOT / "INTERNAL-NOTES.md").read_text()
        self.assertIn("Best Heist Theme Project", notes)

    def test_desk_never_renders_the_token(self):
        os.environ["RIG_TOKEN"] = "crew-secret"
        try:
            page = self.client.get("/desk").get_data(as_text=True)
            self.assertNotIn("crew-secret", page)
        finally:
            os.environ.pop("RIG_TOKEN", None)

    def test_health_reports_last_seen_without_addresses(self):
        rig_app._rover.seen = 0.0
        rig_app._rover.addr = None
        body = self.client.get("/health").get_json()
        self.assertEqual(body["rover"], {"registered": False, "seen_s_ago": None})
        rig_app._wrist_seen = 0.0
        self.client.get("/wrist.json?peek")
        self.assertIsNone(self.client.get("/health").get_json()["wrist"]["seen_s_ago"])
        self.client.get("/wrist.json")
        self.client.post("/api/rover_ping", json={})
        body = self.client.get("/health").get_json()
        self.assertTrue(body["rover"]["registered"])
        self.assertLess(body["wrist"]["seen_s_ago"], 5)
        self.assertNotIn("127.0.0.1", json.dumps(body))


class WristAndRover(unittest.TestCase):
    """The wrist unit's compact feed and the rover's filing endpoint."""

    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()

    def tearDown(self):
        os.environ.pop("RIG_TOKEN", None)

    def test_wrist_json_is_compact_and_sorted(self):
        rig_app.store.add_item({"item": "CHEAP MUG", "value_usd": 4})
        rig_app.store.add_item({"item": "VINTAGE ROLEX", "value_usd": 4200})
        body = self.client.get("/wrist.json").get_json()
        for key in ("case_no", "take", "count", "pending", "revealed", "top"):
            self.assertIn(key, body)
        self.assertEqual(body["top"][0]["item"], "VINTAGE ROLEX")
        self.assertEqual(len(body["top"]), 2)

    def test_rover_files_an_exhibit_and_dedup_still_applies(self):
        res = self.client.post("/api/exhibit", json={
            "item": "ROVER-SPOTTED VASE", "category": "vase", "value_usd": 300,
        })
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.get_json()["added"])
        snap = self.client.get("/state.json").get_json()
        self.assertEqual(snap["items"][0]["origin"], "rover")
        dupe = self.client.post("/api/exhibit", json={
            "item": "rover-spotted vase", "category": "vase", "value_usd": 1,
        })
        self.assertFalse(dupe.get_json()["added"])
        self.assertEqual(rig_app.store.count(), 1)

    def test_exhibit_post_honors_rig_token(self):
        os.environ["RIG_TOKEN"] = "crew"
        denied = self.client.post("/api/exhibit", json={"item": "X", "value_usd": 1})
        self.assertEqual(denied.status_code, 401)
        ok = self.client.post("/api/exhibit", json={"item": "X", "value_usd": 1},
                              headers={"X-Rig-Token": "crew"})
        self.assertEqual(ok.status_code, 201)

    def test_rover_queue_holds_then_drains(self):
        from rig import rover
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        cam = _Frames([frame, frame.copy(), frame.copy()])
        attempts, sent = [], []

        def flaky_post(payload):
            attempts.append(1)
            if len(attempts) == 1:
                return False  # hub blinked; the queue has to hold it
            sent.append(payload["item"])
            return True

        def identify(_b64):
            return {"item": "ROVER PROP", "category": "prop", "value_usd": 12,
                    "bbox": [0.2, 0.2, 0.3, 0.4]}

        rover.run(opener=lambda: cam, identify=identify, post=flaky_post,
                  ping=lambda _url: True, sleep=lambda _s: None, ticks=3)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sent, ["ROVER PROP"])

    def test_rover_ping_retries_on_interval_not_every_tick(self):
        """A dead hub must not hot-loop a blocking connect per frame."""
        from rig import rover
        frame = capture.paint_still(None, 40)
        cam = _Frames([frame, frame.copy(), frame.copy()])
        pings = []

        def dead_ping(url):
            pings.append(url)
            return False

        rover.run(opener=lambda: cam, identify=lambda _b: None,
                  post=lambda _p: True, ping=dead_ping,
                  sleep=lambda _s: None, ticks=3)
        self.assertEqual(len(pings), 1)  # stamped at attempt; not per-tick

    def test_radio_answers_from_the_ledger(self):
        from rig import radio
        rig_app.store.add_item({"item": "ROLEX", "value_usd": 4200})
        r = radio.Radio(lambda: rig_app.store, autostart=False, speak=False)
        job, _ = r.submit("text", "how much is in the bag")
        r.drain()
        reply = r.get(job["job_id"])["reply"]
        self.assertIn("$4,200", reply)
        self.assertIn("1 exhibit", reply)

    def test_radio_without_a_key_says_its_dead(self):
        from rig import narration, radio, voice
        sp = voice.Speaker(autostart=False)
        voice.set_speaker(sp)
        narration.set_narrator(narration.Narrator(speaker=sp, seed=1))
        try:
            r = radio.Radio(lambda: rig_app.store, autostart=False)
            job, _ = r.submit("mic")
            r.drain()
            sp.drain()
            self.assertEqual(r.get(job["job_id"])["state"], "failed")
            self.assertIn("dead", sp.transcript[0]["text"])
        finally:
            voice.set_speaker(None)
            narration.set_narrator(None)


class DriveChain(unittest.TestCase):
    """Laptop keypress -> hub /api/drive -> rover :5001/drive -> wheels."""

    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()
        self._saved_rover = (rig_app._rover.addr, rig_app._rover.seen)

    def tearDown(self):
        rig_app._rover.addr, rig_app._rover.seen = self._saved_rover
        os.environ.pop("RIG_TOKEN", None)

    def test_drive_503s_until_the_rover_pings(self):
        rig_app._rover.addr = None
        res = self.client.post("/api/drive", json={"dir": "forward", "secs": 0.4})
        self.assertEqual(res.status_code, 503)
        self.assertTrue(self.client.post("/api/rover_ping", json={}).get_json()["ok"])
        self.assertEqual(rig_app._rover.addr, "127.0.0.1")

    def test_exhibit_post_does_not_register_teleop(self):
        """Only /api/rover_ping may claim the wheels, exhibits can't hijack."""
        rig_app._rover.addr = None
        res = self.client.post("/api/exhibit", json={"item": "PROP", "value_usd": 5})
        self.assertIn(res.status_code, (200, 201))
        self.assertIsNone(rig_app._rover.addr)

    def test_drive_forwards_after_registration(self):
        rig_app._rover.addr = "10.0.0.9"
        rig_app._rover.seen = time.monotonic()
        seen = []
        saved = rig_app._drive_forward
        rig_app._drive_forward = lambda addr, body: (seen.append((addr, body)), (200, b'{"ok":true}'))[1]
        try:
            res = self.client.post("/api/drive", json={"dir": "left", "secs": 0.4})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(seen[0][0], "10.0.0.9")
            self.assertIn(b"left", seen[0][1])
        finally:
            rig_app._drive_forward = saved

    def test_drive_honors_token_via_header(self):
        """The dashboard sends RIG_TOKEN as X-Rig-Token, teleop must not 401."""
        os.environ["RIG_TOKEN"] = "crew"
        rig_app._rover.addr = "10.0.0.9"
        rig_app._rover.seen = time.monotonic()
        saved = rig_app._drive_forward
        rig_app._drive_forward = lambda addr, body: (200, b'{"ok":true}')
        try:
            denied = self.client.post("/api/drive", json={"dir": "forward"})
            self.assertEqual(denied.status_code, 401)
            ok = self.client.post("/api/drive", json={"dir": "forward"},
                                  headers={"X-Rig-Token": "crew"})
            self.assertEqual(ok.status_code, 200)
        finally:
            rig_app._drive_forward = saved

    def test_drive_forgets_a_silent_rover(self):
        """A rover that stops pinging should drop out of teleop, not 502 forever."""
        rig_app._rover.addr = "10.0.0.9"
        rig_app._rover.seen = time.monotonic() - rig_app.ROVER_TTL - 1
        res = self.client.post("/api/drive", json={"dir": "forward"})
        self.assertEqual(res.status_code, 503)
        self.client.post("/api/rover_ping", json={})
        saved = rig_app._drive_forward
        rig_app._drive_forward = lambda addr, body: (200, b'{"ok":true}')
        try:
            ok = self.client.post("/api/drive", json={"dir": "forward"})
            self.assertEqual(ok.status_code, 200)
        finally:
            rig_app._drive_forward = saved

    def test_exhibit_bad_value_does_not_500(self):
        """A non-numeric value_usd coerces to 0 instead of crashing mid-post."""
        res = self.client.post("/api/exhibit",
                               json={"item": "WEIRD VASE", "value_usd": "abc"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(rig_app.store.snapshot()["items"][0]["value_usd"], 0.0)

    def test_exhibit_rejects_non_object_and_bad_item_types(self):
        for body in ('[1,2,3]', '"hello"', '42'):
            res = self.client.post("/api/exhibit", data=body,
                                   content_type="application/json")
            self.assertEqual(res.status_code, 200)  # lands as a no-op, not a 500
        for item in (123, ["x"], {"k": 1}):
            res = self.client.post("/api/exhibit",
                                   json={"item": item, "value_usd": 5})
            self.assertNotEqual(res.status_code, 500)

    def test_robot_driver_latest_wins_and_stop_is_authoritative(self):
        """Stop must kill an in-flight move AND leave the next move working."""
        import types as _t

        from rig import drive

        calls = []

        class FakeRobot:
            def __init__(self, left=None, right=None):
                pass
            def forward(self): calls.append("forward")
            def backward(self): calls.append("back")
            def left(self): calls.append("left")
            def right(self): calls.append("right")
            def stop(self): calls.append("stop")

        sys.modules["gpiozero"] = _t.SimpleNamespace(Robot=FakeRobot)
        try:
            drv = drive.RobotDriver()
            # in-flight move, then a stop, then a fresh move must still roll
            t = threading.Thread(target=drv.move, args=("forward", 5.0))
            t.start()
            threading.Event().wait(0.05)
            drv.move("stop")
            t.join(timeout=2)
            drv.move("forward", 0.01)
            threading.Event().wait(0.1)
            self.assertGreaterEqual(calls.count("forward"), 2)
        finally:
            sys.modules.pop("gpiozero", None)

    def test_nan_never_poison_the_json_contract(self):
        """value_usd=nan must not corrupt /state.json, the wrist feed, or disk."""
        res = self.client.post("/api/exhibit",
                               json={"item": "GHOST VASE", "value_usd": "nan"})
        self.assertEqual(res.status_code, 201)
        snap = rig_app.store.snapshot()
        self.assertEqual(snap["items"][0]["value_usd"], 0.0)
        self.assertEqual(snap["take"], 0.0)
        raw = self.client.get("/state.json").get_data(as_text=True)
        self.assertNotIn("NaN", raw)
        json.loads(raw)  # strict parse must not throw
        raw_wrist = self.client.get("/wrist.json").get_data(as_text=True)
        self.assertNotIn("NaN", raw_wrist)

    def test_reload_sanitizes_a_poisoned_case(self):
        """A case.json written by the buggy version reloads clean."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "case.json"
            # Python's json module round-trips NaN natively: a poisoned file
            # used to reload the poison into every response forever.
            path.write_text(json.dumps({
                "case_no": 7, "revealed": False,
                "items": [{"n": 1, "item": "GHOST", "value_usd": float("nan"),
                           "bbox": "abcd"}],
            }))
            s = Store(path)
            snap = s.snapshot()
            self.assertEqual(snap["items"][0]["value_usd"], 0.0)
            self.assertIsNone(snap["items"][0].get("bbox"))
            self.assertNotIn("NaN", json.dumps(snap))

    def test_garbage_bbox_is_dropped_not_stored(self):
        import base64 as _b64
        ok, jpg = cv2.imencode(".jpg", capture.paint_still(None, 40))
        self.assertTrue(ok)
        res = self.client.post("/api/exhibit",
                               json={"item": "ODD BOX", "value_usd": 9,
                                     "bbox": "abcd",
                                     "frame_b64": _b64.b64encode(jpg.tobytes()).decode()})
        self.assertEqual(res.status_code, 201)
        snap = rig_app.store.snapshot()
        item = snap["items"][-1]
        self.assertIsNone(item.get("bbox"))
        self.assertEqual(self.client.get(f"/crop/{item['n']}.jpg").status_code, 200)

    def test_rover_exit_exhibit_gets_no_callout(self):
        from rig import narration, voice
        n = narration.Narrator(speaker=voice.Speaker(autostart=False), seed=1)
        narration.set_narrator(n)
        try:
            n.prime(rig_app.store)
            self.client.post("/api/exhibit",
                             json={"item": "FIRE DOOR", "category": "exit", "value_usd": 0})
            self.assertEqual(n.events, [])
            self.client.post("/api/exhibit",
                             json={"item": "ROLEX", "value_usd": 4200})
            self.assertEqual([e["event"] for e in n.events], ["first_exhibit", "value_milestone"])
        finally:
            narration.set_narrator(None)

    def test_mutating_posts_respect_the_token(self):
        """Case-wipe and price-toggle must not be open when RIG_TOKEN is set."""
        os.environ["RIG_TOKEN"] = "crew"
        try:
            self.assertEqual(self.client.post("/trigger_reveal").status_code, 401)
            self.assertEqual(self.client.post("/api/serpapi", json={}).status_code, 401)
            # ?token= is gone entirely: not even a valid one authenticates;
            # and GET never mutates: it serves a confirm page, 200, no reveal.
            before = rig_app.store.snapshot()["revealed"]
            res = self.client.get("/trigger_reveal?token=crew")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(rig_app.store.snapshot()["revealed"], before)
            # GET /api/serpapi is read-only status, open LAN either way.
            self.assertEqual(self.client.get("/api/serpapi").status_code, 200)
            res = self.client.post("/trigger_reveal", headers={"X-Rig-Token": "crew"})
            self.assertEqual(res.status_code, 200)
            # The reveal just fired; a second call resets: both authorized.
        finally:
            os.environ.pop("RIG_TOKEN", None)

    def test_serpapi_env_flag_reaches_lookup(self):
        """SERPAPI_ENABLED=1 from .env must actually reach _lookup, not no-op."""
        from urllib.error import URLError

        from rig import pricing
        os.environ["SERPAPI_ENABLED"] = "1"
        os.environ["SERPAPI_API_KEY"] = "k"
        pricing._serpapi_enabled = None
        called = []
        saved = pricing.urlopen
        pricing.urlopen = lambda *a, **k: (called.append(a), (_ for _ in ()).throw(URLError("x")))[1]
        try:
            pricing._lookup("ROLEX")
            self.assertTrue(called, "env-enabled SerpAPI never queried")
        finally:
            pricing.urlopen = saved
            pricing._serpapi_enabled = None
            os.environ.pop("SERPAPI_ENABLED", None)
            os.environ.pop("SERPAPI_API_KEY", None)

    def test_dashboard_never_renders_the_token(self):
        """RIG_TOKEN must not appear in page source, a scrapable secret
        protects nothing."""
        os.environ["RIG_TOKEN"] = "crew-secret"
        try:
            page = self.client.get("/").get_data(as_text=True)
            self.assertNotIn("crew-secret", page)
        finally:
            os.environ.pop("RIG_TOKEN", None)

    def test_return_command_replays_the_trail(self):
        """dir=return walks the breadcrumb stack backwards, inverted."""
        from rig import drive_server
        from rig.drive import ConsoleDriver
        drv = ConsoleDriver()
        drv.move("forward", 0.5)
        drv.move("left", 0.2)
        drv.move("stop")
        self.assertEqual(drv.return_home(), 2)
        # a second return with no new crumbs does nothing
        self.assertEqual(ConsoleDriver().return_home(), 0)
        server = drive_server.drive_server(drv, port=0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/drive",
                data=b'{"dir":"return"}',
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
        finally:
            server.shutdown()
            server.server_close()

    def test_drive_server_ignores_non_object_json(self):
        """A valid-JSON non-object body ('hello', [1], 42) must not crash."""
        from rig import drive_server
        from rig.drive import ConsoleDriver
        drv = ConsoleDriver()
        server = drive_server.drive_server(drv, port=0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for body in ('"hello"', '[1,2,3]', '42'):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/drive", data=body.encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
            self.assertTrue(all(m[0] == "stop" for m in drv.moves))
        finally:
            server.shutdown()
            server.server_close()

    def test_drive_server_runs_the_wheels(self):
        from rig import drive_server
        from rig.drive import ConsoleDriver
        drv = ConsoleDriver()
        server = drive_server.drive_server(drv, port=0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/drive",
                data=json.dumps({"dir": "forward", "secs": 0.2}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            self.assertEqual(drv.moves, [("forward", 0.2)])
            bad = urllib.request.Request(
                f"http://127.0.0.1:{port}/drive",
                data=json.dumps({"dir": "through-the-floor"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(drv.moves[-1], ("stop", 0.4))
        finally:
            server.shutdown()
            server.server_close()

    def test_drive_server_survives_a_bad_content_length(self):
        """A negative/garbage Content-Length must not hang or kill the handler."""
        import http.client

        from rig import drive_server
        from rig.drive import ConsoleDriver
        drv = ConsoleDriver()
        server = drive_server.drive_server(drv, port=0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.putrequest("POST", "/drive", skip_accept_encoding=True)
            conn.putheader("Content-Length", "-5")
            conn.endheaders()
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 200)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_tripwire_is_inert_unpinned(self):
        """No TRIPWIRE_PIN / DIAL_PINS = nothing arms, nothing crashes."""
        from rig import tripwire
        os.environ.pop("TRIPWIRE_PIN", None)
        os.environ.pop("DIAL_PINS", None)
        tripwire.start(lambda: None)   # must not raise
        self.assertIsNone(tripwire._env_pins("TRIPWIRE_PIN"))
        self.assertIsNone(tripwire._env_pins("DIAL_PINS"))
        os.environ["DIAL_PINS"] = "bogus"
        try:
            self.assertIsNone(tripwire._env_pins("DIAL_PINS"))
        finally:
            os.environ.pop("DIAL_PINS", None)

    def test_dial_arms_without_threshold_kwargs(self):
        """gpiozero 2.x RotaryEncoder takes no int threshold_steps, the dial
        must construct cleanly on a mocked encoder to prove the call shape."""
        from rig import tripwire

        built = {}

        class FakeDial:
            def __init__(self, a, b, max_steps=None, **kw):
                if kw:
                    raise TypeError(f"unexpected kwargs: {kw}")
                built["max_steps"] = max_steps
                self.steps = 0
                self.when_rotated = None

        import types as _t
        fake_gpiozero = _t.SimpleNamespace(RotaryEncoder=FakeDial)
        sys.modules["gpiozero"] = fake_gpiozero
        os.environ["DIAL_PINS"] = "20,21"
        fired = []
        try:
            self.assertTrue(tripwire._arm_dial(lambda: fired.append(1)))
            self.assertEqual(built["max_steps"], tripwire.DIAL_TICKS)
            # clockwise past the count fires; counter-clockwise only rearms
            tripwire._held_dial.steps = tripwire.DIAL_TICKS
            tripwire._held_dial.when_rotated()
            self.assertEqual(fired, [1])
            tripwire._held_dial.steps = -tripwire.DIAL_TICKS
            tripwire._held_dial.when_rotated()
            self.assertEqual(fired, [1])
            self.assertEqual(tripwire._held_dial.steps, 0)
        finally:
            sys.modules.pop("gpiozero", None)
            os.environ.pop("DIAL_PINS", None)
            tripwire._held_dial = None

    def test_dial_ticks_zero_is_clamped(self):
        """DIAL_TICKS=0 must never mean 'fire on every detent'."""
        from rig import tripwire

        class FakeDial:
            def __init__(self, a, b, max_steps=None, **kw):
                self.max_steps = max_steps
                self.steps = 0
                self.when_rotated = None
                built["max_steps"] = max_steps

        built = {}
        import types as _t
        sys.modules["gpiozero"] = _t.SimpleNamespace(RotaryEncoder=FakeDial)
        os.environ["DIAL_PINS"] = "20,21"
        os.environ["DIAL_TICKS"] = "0"
        try:
            self.assertTrue(tripwire._arm_dial(lambda: None))
            self.assertGreaterEqual(built["max_steps"], 1)
        finally:
            sys.modules.pop("gpiozero", None)
            os.environ.pop("DIAL_PINS", None)
            os.environ.pop("DIAL_TICKS", None)
            tripwire._held_dial = None

    def test_keyboard_fallback_is_inert_without_hardware(self):
        """No evdev / no keyboard = the watcher refuses cleanly, doesn't spawn."""
        from rig import keys
        self.assertFalse(keys.start(lambda: None))

    def test_home_marker_detects_and_guides_return(self):
        """Generated beacon frame is found; a driver with the beacon in view
        abandons breadcrumbs and steers onto it."""
        import types as _t

        from rig import drive

        # generate the real marker in-memory, padded like the shipped PNG
        img = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 0, 300)
        frame = cv2.copyMakeBorder(img, 40, 40, 40, 40,
                                   cv2.BORDER_CONSTANT, value=255)
        hit = drive.find_home_marker(frame)
        self.assertIsNotNone(hit)
        cx, w = hit
        self.assertTrue(0.4 < cx < 0.6)

        # Small marker = beacon far away: the approach loop must drive legs.
        far = np.full((480, 640), 255, dtype="uint8")
        small = cv2.resize(img, (80, 80))
        far[200:280, 280:360] = small
        hit_far = drive.find_home_marker(far)
        self.assertIsNotNone(hit_far)
        self.assertLess(hit_far[1], 0.28)
        # a blank frame must not hallucinate a beacon
        self.assertIsNone(drive.find_home_marker(
            np.zeros((64, 64), dtype="uint8")))

        calls = []

        class FakeRobot:
            def __init__(self, left=None, right=None): pass
            def forward(self): calls.append("forward")
            def backward(self): calls.append("back")
            def left(self): calls.append("left")
            def right(self): calls.append("right")
            def stop(self): calls.append("stop")

        sys.modules["gpiozero"] = _t.SimpleNamespace(Robot=FakeRobot)
        saved_src = drive._frame_source
        drive.set_frame_source(lambda: far)
        try:
            drv = drive.RobotDriver()
            drv._trail = [("forward", 0.2), ("left", 0.1)]
            drv._home_on_marker = lambda timeout=0.6: drive.RobotDriver._home_on_marker(drv, timeout)
            legs = drv.return_home()
            # beacon visible but far: breadcrumbs abandoned, correction legs
            # drove forward at it until the approach timed out.
            self.assertNotIn("back", calls)
            self.assertIn("forward", calls)
            self.assertGreater(legs, 0)
        finally:
            sys.modules.pop("gpiozero", None)
            drive.set_frame_source(saved_src)

    def test_console_driver_is_the_no_gpio_path(self):
        """Force the off-Pi path: never claim real GPIO pins in a test run."""
        from rig import drive

        class NoGpio(Exception):
            pass

        saved = drive.RobotDriver
        drive.RobotDriver = lambda: (_ for _ in ()).throw(NoGpio())
        try:
            drv = drive.get_driver()
            self.assertIsInstance(drv, drive.ConsoleDriver)
            drv.move("forward", 0.4)
            self.assertEqual(drv.moves, [("forward", 0.4)])
        finally:
            drive.RobotDriver = saved


class ExitsMode(unittest.TestCase):
    def test_exits_never_get_priced(self):
        """A door is not inventory: category=exit bypasses the pricing ladder."""
        from rig import rover
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        cam = _Frames([frame, frame.copy()])
        sent = []
        os.environ["RIG_MODE"] = "exits"
        try:
            rover.run(
                opener=lambda: cam,
                identify=lambda _b: {"item": "FIRE DOOR", "category": "exit",
                                     "value_usd": 999},
                post=lambda p: sent.append(p) or True,
                ping=lambda _u: True, sleep=lambda _s: None, ticks=2,
            )
        finally:
            os.environ.pop("RIG_MODE", None)
        self.assertTrue(sent)
        self.assertEqual(sent[0]["value_usd"], 0.0)
        self.assertEqual(sent[0]["why"], "exit scouted; not for sale")

    def test_hub_examine_lands_an_exit_without_crashing(self):
        """Hub path: category=exit must bind price/estimated, not NameError."""
        blank(rig_app.store)
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        rig_app._examine(frame, identify=lambda _b: {
            "item": "FIRE DOOR", "category": "exit", "value_usd": 999})
        snap = rig_app.store.snapshot()
        self.assertEqual(len(snap["items"]), 1)
        self.assertEqual(snap["items"][0]["value_usd"], 0.0)
        self.assertFalse(snap["items"][0]["estimated"])
        self.assertEqual(snap["take"], 0.0)

    def test_exit_in_top_five_is_not_announced(self):
        """A $0 door that lands in the top 5 must not trigger the callout."""
        from rig import narration, voice
        blank(rig_app.store)
        n = narration.Narrator(speaker=voice.Speaker(autostart=False), seed=1)
        narration.set_narrator(n)
        try:
            n.prime(rig_app.store)
            frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
            rig_app._examine(frame, identify=lambda _b: {
                "item": "FIRE DOOR", "category": "exit", "value_usd": 0})
        finally:
            narration.set_narrator(None)
        self.assertEqual(rig_app.store.count(), 1)
        self.assertEqual(n.events, [])

    def test_two_distinct_exits_both_land(self):
        """Exits dedup on name only: same-category tightening must not drop
        'BACK DOOR' just because 'SIDE DOOR' is already on the board."""
        store = fresh_store()
        os.environ["RIG_MODE"] = "exits"
        try:
            a, _ = store.add_item({"item": "SIDE DOOR", "category": "exit", "value_usd": 0})
            b, _ = store.add_item({"item": "BACK DOOR", "category": "exit", "value_usd": 0})
            c, _ = store.add_item({"item": "FIRE DOOR", "category": "exit", "value_usd": 0})
            dup, _ = store.add_item({"item": "SIDE DOOR", "category": "exit", "value_usd": 0})
        finally:
            os.environ.pop("RIG_MODE", None)
        self.assertTrue(a and b and c)
        self.assertFalse(dup)
        self.assertEqual(store.count(), 3)

    def test_exits_mode_swaps_the_prompt(self):
        from rig import vision
        self.assertFalse(vision.exits_mode())
        self.assertEqual(vision.active_prompt(), vision.PROMPT)
        os.environ["RIG_MODE"] = "exits"
        try:
            self.assertTrue(vision.exits_mode())
            self.assertEqual(vision.active_prompt(), vision.EXITS_PROMPT)
            self.assertIn("exit", vision.EXITS_PROMPT.lower())
        finally:
            os.environ.pop("RIG_MODE", None)


class CropAndCamera(unittest.TestCase):
    def test_crop_is_a_three_by_four_jpeg(self):
        still = capture.paint_still([0.2, 0.2, 0.3, 0.4], 200)
        jpg = capture.crop_jpeg(still, [0.2, 0.2, 0.3, 0.4])
        arr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        height, width = arr.shape[:2]
        self.assertLess(abs((width / height) - 0.75), 0.05)
        bare = capture.crop_jpeg(still, None)
        self.assertTrue(bare.startswith(b"\xff\xd8"))

    def test_windows_tries_directshow_before_the_default(self):
        if sys.platform != "win32":
            self.skipTest("backend order is per OS")
        order = capture.backend_order()
        self.assertEqual(order[0], cv2.CAP_DSHOW)
        self.assertIn(cv2.CAP_ANY, order)

    def test_a_missed_camera_is_closed(self):
        previous = os.environ.get("CAM_BACKEND")
        os.environ["CAM_BACKEND"] = "any"
        capture._preferred = None
        try:
            cam = capture.open_camera()
            self.assertIsNotNone(cam)
            try:
                if not cam.isOpened():
                    self.assertFalse(cam.isOpened())
            finally:
                cam.release()
        finally:
            if previous is None:
                os.environ.pop("CAM_BACKEND", None)
            else:
                os.environ["CAM_BACKEND"] = previous
            capture._preferred = None


class ScanLoop(unittest.TestCase):
    def setUp(self):
        blank(rig_app.store)

    def test_a_held_change_looks_but_a_flicker_does_not(self):
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.4], 180)
        other = capture.paint_still([0.5, 0.4, 0.3, 0.4], 40)
        cam = _Frames([frame, frame.copy(), other, other.copy()])
        calls = []

        def identify(_b64):
            self.assertTrue(rig_app.store.snapshot()["pending"])
            calls.append(1)
            return {"item": "VASE", "category": "vase", "value_usd": 80,
                    "bbox": [0.2, 0.2, 0.3, 0.4]}

        rig_app.scan_loop(opener=lambda: cam, identify=identify, sleep=lambda _s: None, ticks=4)
        snap = rig_app.store.snapshot()
        self.assertEqual(snap["frame_id"], 4)
        self.assertEqual(calls, [1, 1])
        self.assertEqual(snap["items"][0]["item"], "VASE")
        self.assertEqual(len(snap["items"]), 1)
        self.assertFalse(snap["pending"])
        self.assertTrue(snap["camera_ok"])
        self.assertEqual(cam.releases, 0)

    def test_one_noisy_sample_never_reaches_the_model(self):
        base = capture.paint_still(None, 40)
        flick_a = capture.paint_still([0.3, 0.3, 0.3, 0.3], 220)
        flick_b = capture.paint_still([0.3, 0.3, 0.3, 0.3], 200)
        seq = [capture.scene_changed(f, confirm=2) for f in (base, base.copy(), flick_a, base.copy())]
        self.assertEqual(seq, [True, False, False, False])
        capture.reset_gate()
        held = [capture.scene_changed(f, confirm=2) for f in (base, base.copy(), flick_a, flick_b)]
        self.assertEqual(held, [True, False, False, True])

    def test_a_dead_camera_is_released_and_marked_lost(self):
        dead = _Closed()
        rig_app.scan_loop(opener=lambda: dead, sleep=lambda _s: None, ticks=1)
        snap = rig_app.store.snapshot()
        self.assertFalse(snap["camera_ok"])
        self.assertEqual(snap["frame_id"], 0)
        self.assertEqual(dead.releases, 1)
        self.assertEqual(display._state["mode"], "lost")


class Pages(unittest.TestCase):
    def setUp(self):
        blank(rig_app.store)
        self.client = rig_app.app.test_client()

    def test_dispatch_can_file_the_lineup_with_its_rendered_nonce(self):
        with patch.dict(os.environ, {"RIG_TOKEN": ""}):
            page = self.client.get("/desk").get_data(as_text=True)
            nonce = re.search(r'<meta name="case-nonce" content="([0-9a-f]+)">', page)
            self.assertIsNotNone(nonce)
            self.assertEqual(self.client.post("/trigger_reveal").status_code, 403)
            response = self.client.post("/trigger_reveal", headers={"X-Case-Nonce": nonce.group(1)})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["revealed"])

    def test_state_frame_crop_manifest_and_reveal(self):
        state = self.client.get("/state.json")
        self.assertEqual(state.status_code, 200)
        body = state.get_json()
        for key in ("frame_id", "camera_ok", "pending", "revealed", "take", "items"):
            self.assertIn(key, body)
        self.assertEqual(body["items"], [])
        self.assertIn("no-store", state.headers["Cache-Control"])

        still = capture.paint_still([0.12, 0.2, 0.26, 0.36], 210)
        rig_app.store.set_frame(capture.frame_jpeg(still))
        rig_app.store.add_item(
            {"item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200,
             "bbox": [0.12, 0.2, 0.26, 0.36]},
            still,
        )
        rig_app.store.add_item(
            {"item": "FIRST-ED. HEMINGWAY", "category": "book", "value_usd": 950,
             "estimated": True},
            still,
        )
        snap = self.client.get("/state.json").get_json()
        self.assertNotIn("bbox", snap["items"][1])
        self.assertEqual(self.client.get("/frame.jpg").data[:2], b"\xff\xd8")
        self.assertEqual(self.client.get("/crop/1.jpg").status_code, 200)
        self.assertEqual(self.client.get("/crop/2.jpg").data[:2], b"\xff\xd8")
        self.assertEqual(self.client.get("/crop/9.jpg").status_code, 404)

        page = self.client.get("/manifest").get_data(as_text=True)
        self.assertLess(page.index("VINTAGE ROLEX"), page.index("HEMINGWAY"))
        self.assertIn("est.", page)
        self.assertIn("$5,150.00", page)

        revealed = self.client.post("/trigger_reveal", headers={"X-Case-Nonce": rig_app._nonce()}).get_json()
        self.assertTrue(revealed["revealed"])
        self.assertEqual(len(revealed["items"]), 2)
        reset = self.client.post("/trigger_reveal", headers={"X-Case-Nonce": rig_app._nonce()}).get_json()
        self.assertFalse(reset["revealed"])
        self.assertEqual(reset["items"], [])
        self.assertEqual(reset["case_no"], 1139)
        self.assertEqual(display._state["case"], 1139)
        self.assertEqual(display._state["mode"], "live")


class HardwareFixes(unittest.TestCase):
    def test_oled_case_follows_the_reset(self):
        display.show_take(4200, 2, case_no=1142)
        display.show_lost(True)
        texts = _drawn_text()
        self.assertIn("CASE NO. 1142", texts)
        self.assertEqual(display._state["mode"], "lost")
        display.show_reveal(1142)
        self.assertEqual(display._state["case"], 1142)
        display.show_take(0, 0, 1143)
        self.assertIn("CASE NO. 1143", _drawn_text())

    def test_gpio_button_is_kept_alive(self):
        created = []

        class FakeButton:
            def __init__(self, pin, bounce_time=0):
                self.pin = pin
                self.bounce_time = bounce_time
                self.when_pressed = None
                created.append(self)

        fake = types.ModuleType("gpiozero")
        fake.Button = FakeButton
        previous = sys.modules.get("gpiozero")
        sys.modules["gpiozero"] = fake
        try:
            def handler():
                return None
            button.start(handler)
            self.assertIs(button._held, created[0])
            self.assertEqual(button._held.pin, 17)
            self.assertIs(button._held.when_pressed, handler)
        finally:
            if previous is None:
                sys.modules.pop("gpiozero", None)
            else:
                sys.modules["gpiozero"] = previous
            button._held = None


class BadgeCapture(unittest.TestCase):
    """Issue #26: a badge or school ID files with its printed text; a payment
    card number never files in the clear."""

    VISA = "4111111111111111"          # Luhn-valid test numbers, one per network
    MASTERCARD = "5500000000000004"
    AMEX = "378282246310005"

    def setUp(self):
        blank(rig_app.store)
        vision.reset_offline_fallback()
        self.client = rig_app.app.test_client()

    def test_legible_badge_parses_with_its_card(self):
        parsed = vision.parse_response(json.dumps({
            "item": "Initech Employee Badge", "desc": "photo ID keycard", "category": "Badge",
            "value_usd": 650, "bbox": [0.3, 0.3, 0.3, 0.4],
            "card": {"name": "P. Gibbons", "id": "INT-0451", "org": "Initech", "pin": "1234"},
        }))
        self.assertEqual(parsed["category"], "badge")
        self.assertEqual(parsed["card"], {"name": "P. Gibbons", "id": "INT-0451", "org": "Initech"})

    def test_school_id_keeps_every_printed_field(self):
        """The demo card: a student ID, long public numbers and all."""
        parsed = vision.parse_response(json.dumps({
            "item": "State University Student ID", "category": "badge", "value_usd": 25,
            "card": {"name": "Jordan Rivera", "id": "@01234567",
                     "org": "The University of Texas at San Antonio Downtown Campus",
                     "role": "Student", "expires": "08/2028"},
        }))
        self.assertEqual(parsed["card"], {
            "name": "Jordan Rivera", "id": "@01234567",
            "org": "The University of Texas at San Antonio Downtown Campus",
            "role": "Student", "expires": "08/2028"})
        for barcode in ("21234001234567", "6009 1234 5678 9012", "4111111111111112",
                        "601234567890123456"):
            card = vision.parse_response(json.dumps({
                "item": "Student ID", "category": "badge", "value_usd": 5,
                "card": {"name": "J. RIVERA", "id": barcode}}))["card"]
            self.assertEqual(card["id"], barcode)   # library/campus numbers are not payment cards

    # Made-up values in the Comet Card's real format.
    UTD_FRONT = {"item": "UTD Comet Card", "category": "badge", "value_usd": 650,
                 "card": {"name": "Temoc Comet Jr", "id": "2020000001",
                          "org": "The University of Texas at Dallas", "role": "STUDENT"}}
    UTD_BACK = {"item": "UTD Comet Card", "category": "badge", "value_usd": 650,
                "card": {"name": "Temoc Comet", "card_no": "6036790000000017",
                         "issued": "6/2/2023", "org": "The University of Texas at Dallas"}}

    def test_prompt_knows_the_comet_card(self):
        for words in ("UTD Comet Card", "UTD ID#", "card_no", "issued", "upside-down"):
            self.assertIn(words, vision.PROMPT)

    def test_comet_card_back_number_is_not_mistaken_for_a_payment_card(self):
        parsed = vision.parse_response(json.dumps(self.UTD_BACK))
        self.assertEqual(parsed["card"]["card_no"], "6036790000000017")
        self.assertEqual(parsed["card"]["issued"], "6/2/2023")
        line = vision.parse_response(json.dumps({**self.UTD_BACK, "card": {
            "card_no": "6036790000000017 0 6/2/2023 9:03:27 AM"}}))["card"]["card_no"]
        self.assertTrue(line.startswith("6036790000000017"))

    def test_front_then_back_fill_one_exhibit(self):
        store = rig_app.store
        self.assertTrue(store.add_item(json.loads(json.dumps(self.UTD_FRONT)))[0])
        self.assertFalse(store.add_item(json.loads(json.dumps(self.UTD_BACK)))[0])
        self.assertEqual(store.count(), 1)
        card = self.client.get("/state.json").get_json()["items"][0]["card"]
        self.assertEqual(card, {
            "name": "Temoc Comet Jr", "id": "2020000001", "org": "The University of Texas at Dallas",
            "role": "STUDENT", "card_no": "6036790000000017", "issued": "6/2/2023"})
        self.assertIn("6036790000000017", store.state_path().read_text())

    def test_back_then_front_takes_the_full_name(self):
        store = rig_app.store
        store.add_item(json.loads(json.dumps(self.UTD_BACK)))
        store.add_item(json.loads(json.dumps(self.UTD_FRONT)))
        self.assertEqual(store.count(), 1)
        card = store.snapshot()["items"][0]["card"]
        self.assertEqual(card["name"], "Temoc Comet Jr")
        self.assertEqual(card["id"], "2020000001")
        self.assertEqual(card["card_no"], "6036790000000017")

    def test_two_students_comet_cards_are_two_exhibits(self):
        store = rig_app.store
        other = json.loads(json.dumps(self.UTD_FRONT))
        other["card"].update(name="Jane Doe", id="2020000002")
        store.add_item(json.loads(json.dumps(self.UTD_FRONT)))
        self.assertTrue(store.add_item(other)[0])
        self.assertEqual(store.count(), 2)

    def test_numeric_id_is_kept_as_text(self):
        parsed = vision.parse_response(
            '{"item": "Student ID", "category": "badge", "value_usd": 5,'
            ' "card": {"name": "J. RIVERA", "id": 1234567}}')
        self.assertEqual(parsed["card"]["id"], "1234567")

    def test_card_fields_are_short_strings_or_gone(self):
        parsed = vision.parse_response(json.dumps({
            "item": "Acme Keycard", "category": "badge", "value_usd": 300,
            "card": {"name": "X" * 90, "id": True, "org": "   ", "role": ["Staff"]},
        }))
        self.assertEqual(parsed["card"], {"name": "X" * 60})

    def test_illegible_badge_files_without_fabricated_card(self):
        no_card = vision.parse_response(
            '{"item": "Employee Badge", "category": "badge", "value_usd": 200}')
        self.assertNotIn("card", no_card)
        blank_card = vision.parse_response(
            '{"item": "Employee Badge", "category": "badge", "value_usd": 200,'
            ' "card": {"name": "", "id": null}}')
        self.assertNotIn("card", blank_card)
        # A card object on anything that is not a badge is dropped.
        lamp = vision.parse_response(
            '{"item": "Lamp", "category": "lamp", "value_usd": 12, "card": {"name": "BOB"}}')
        self.assertNotIn("card", lamp)
        self.assertIsNone(vision.parse_response('{"item": null}'))

    def test_payment_card_numbers_are_masked_not_filed(self):
        for raw in (self.VISA, "4111 1111 1111 1111", "5500-0000-0000-0004", self.AMEX):
            parsed = vision.parse_response(json.dumps({
                "item": "Card", "category": "badge", "value_usd": 1,
                "card": {"name": "J DOE", "id": raw}}))
            digits = raw.replace(" ", "").replace("-", "")
            self.assertEqual(parsed["card"]["id"], "****" + digits[-4:])
            self.assertEqual(parsed["card"]["name"], "J DOE")
        parsed = vision.parse_response(json.dumps({
            "item": f"Card {self.MASTERCARD}", "desc": f"receipt {self.VISA} 2026", "value_usd": 1}))
        self.assertEqual(parsed["item"], "Card ****0004")
        self.assertEqual(parsed["desc"], "receipt ****1111 2026")

    def test_no_payment_number_reaches_case_json_or_state(self):
        saved, rig_app.store = rig_app.store, fresh_store()
        self.addCleanup(setattr, rig_app, "store", saved)
        store = rig_app.store
        frame = capture.paint_still([0.3, 0.3, 0.3, 0.4], 200)
        store.add_item({"item": "Badge", "category": "badge", "value_usd": 5,
                        "card": {"name": "A", "id": self.VISA}}, frame)
        store.add_item({"item": "Card", "category": "badge", "value_usd": 5,
                        "card": {"id": int(self.MASTERCARD)}}, frame)
        store.add_item({"item": "Lamp", "desc": f"receipt {self.AMEX}", "value_usd": 5,
                        "why": self.VISA}, frame)
        resp = self.client.post("/api/exhibit", json={
            "item": "Rover Badge", "category": "badge", "value_usd": 5,
            "card": {"name": "J DOE", "id": "3782 822463 10005"},
        })
        self.assertTrue(resp.get_json()["added"])
        self.assertEqual(store.count(), 4)
        for text in (store.state_path().read_text(),
                     self.client.get("/state.json").get_data(as_text=True),
                     self.client.get("/manifest").get_data(as_text=True)):
            for number in (self.VISA, self.MASTERCARD, self.AMEX):
                self.assertNotIn(number, text)
        self.assertIn("****1111", store.state_path().read_text())

    def test_a_saved_payment_number_is_masked_on_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps({"case_no": 1138, "items": [
                {"n": 1, "item": f"Card {self.VISA}", "value_usd": 1},
                {"n": 2, "item": "Badge", "category": "badge", "value_usd": 9,
                 "card": {"name": "P. GIBBONS", "id": self.VISA}},
            ]}))
            items = Store(path).snapshot()["items"]
            self.assertEqual(items[0]["item"], "Card ****1111")
            self.assertEqual(items[1]["card"], {"name": "P. GIBBONS", "id": "****1111"})

    def test_offline_catalog_demos_a_badge(self):
        os.environ["RIG_OFFLINE"] = "1"
        try:
            for _ in range(len(vision.OFFLINE_CATALOG)):
                item = vision.identify("fake_b64")
                if item["category"] == "badge":
                    break
        finally:
            os.environ.pop("RIG_OFFLINE", None)
        self.assertEqual(item["category"], "badge")
        self.assertTrue(item["card"]["name"] and item["card"]["id"])
        item["card"]["name"] = "MUTATED"
        self.assertNotEqual(next(c for c in vision.OFFLINE_CATALOG if c["category"] == "badge")
                            ["card"]["name"], "MUTATED")

    def test_badge_files_as_a_cloned_credential(self):
        badge = next(c for c in vision.OFFLINE_CATALOG if c["category"] == "badge")
        spec = {**badge, "card": dict(badge["card"]), "source": "offline"}
        rig_app._examine(capture.paint_still(badge["bbox"]), identify=lambda _b: dict(spec))
        row = self.client.get("/state.json").get_json()["items"][0]
        self.assertEqual(row["category"], "badge")
        self.assertEqual(row["card"], badge["card"])
        self.assertEqual(row["value_usd"], badge["value_usd"])
        self.assertTrue(row["estimated"])
        self.assertIn("credential cloned", row["why"])
        self.assertIn("cloned", self.client.get("/manifest").get_data(as_text=True))
        wrist = self.client.get("/wrist.json?peek").get_json()
        self.assertEqual(set(wrist["top"][0]), {"item", "value_usd"})

    def test_reshowing_a_badge_does_not_refile_it(self):
        store = rig_app.store
        base = {"item": "Initech Employee Badge", "category": "badge", "value_usd": 650}
        self.assertTrue(store.add_item({**base, "card": {"name": "P. GIBBONS", "id": "INT-0451"}})[0])
        self.assertFalse(store.add_item({**base, "card": {"name": "P. GIBBONS", "id": "INT-0451"}})[0])
        self.assertFalse(store.add_item({**base, "item": "Initech Badge",
                                         "card": {"id": "int-0451"}})[0])
        self.assertFalse(store.add_item(dict(base))[0])          # same name, no card: name dedup
        # A second employee's badge off the same issuer is a second credential.
        self.assertTrue(store.add_item({**base, "card": {"name": "M. BOLTON", "id": "INT-0452"}})[0])
        self.assertEqual(store.count(), 2)

    def test_card_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            Store(path).add_item({"item": "Initech Employee Badge", "category": "badge",
                                  "value_usd": 650, "card": {"name": "P. GIBBONS", "id": "INT-0451"}})
            row = Store(path).snapshot()["items"][0]
            self.assertEqual(row["card"], {"name": "P. GIBBONS", "id": "INT-0451"})

    def test_radio_counts_cloned_badges(self):
        from rig import radio
        store = rig_app.store
        store.add_item({"item": "ROLEX", "category": "watch", "value_usd": 4200})
        store.add_item({"item": "Initech Badge", "category": "badge", "value_usd": 650,
                        "card": {"id": "INT-0451"}})
        store.add_item({"item": "Acme Keycard", "category": "badge", "value_usd": 300,
                        "card": {"id": "ACM-7"}})
        r = radio.Radio(lambda: store, autostart=False, speak=False)
        job, _ = r.submit("text", "how many keycards have we cloned")
        r.drain()
        self.assertEqual(r.get(job["job_id"])["reply"], "2 credentials cloned: Initech Badge, Acme Keycard.")

    def test_prompt_asks_for_legible_card_text_only(self):
        self.assertIn('"card"', vision.PROMPT)
        self.assertIn('"badge"', vision.PROMPT)
        self.assertIn("credit", vision.PROMPT.lower())
        self.assertIn("student", vision.PROMPT.lower())

    def test_reveal_lineup_renders_cloned_flavor(self):
        with self.client.get("/noir.js") as resp:
            js = resp.get_data(as_text=True)
        with self.client.get("/noir.css") as resp:
            css = resp.get_data(as_text=True)
        self.assertIn("'CLONED'", js)
        self.assertIn("it.category === 'badge'", js)
        self.assertIn(".suspect.cloned", css)


class _Frames:
    def __init__(self, frames):
        self.frames = list(frames)
        self.opened = True
        self.releases = 0

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.releases += 1
        self.opened = False


class _Closed:
    def __init__(self):
        self.releases = 0

    def isOpened(self):
        return False

    def release(self):
        self.releases += 1


def _drawn_text():
    img = Image.new("1", (128, 64))
    draw = ImageDraw.Draw(img)
    texts = []
    original = draw.text

    def grab(xy, text, *args, **kwargs):
        texts.append(text)
        return original(xy, text, *args, **kwargs)

    draw.text = grab
    display.render(draw, True)
    return texts


if __name__ == "__main__":
    unittest.main()
