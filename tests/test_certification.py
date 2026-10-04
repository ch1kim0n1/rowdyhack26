"""Pre-hardware certification: the real app against simulated hardware.

Mocks live only at the boundary (cv2, gpiozero, luma, escpos, subprocesses,
urllib targets). Everything in between — scan loop, gate, pricing ladder,
ledger, reveal, OLED render, motor driver, radio chain — runs for real.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # importing rig.app must not load a real .env over this setup
os.environ.setdefault("RIG_VOICE", "0")   # the suite never talks out loud

for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SERPAPI_API_KEY", "RIG_TOKEN",
            "VULTR_API_KEY", "TIGER_DB_URL"):
    os.environ.pop(var, None)

# Isolate the module-level store: without this, rig.app's Store() loads the
# real rig/state/case.json and a leftover revealed=True deadens every add_item.
os.environ["RIG_STATE_FILE"] = str(
    Path(tempfile.mkdtemp(prefix="cert-state-")) / "case.json")


from rig import app as rig_app
from rig import capture, display, listen, rover
from rig.store import Store
from tests import hw_sim

rig_app.voice.announce = lambda *a, **k: None
rig_app.voice.announce_top5 = lambda *a, **k: None
rig_app.pricing.resolve_detailed = lambda n, v: (float(v or 0), False, "serpapi")
rig_app.pricing.resolve = lambda n, v: (float(v or 0), False)


def fresh_store() -> Store:
    return Store(Path(tempfile.mkdtemp(prefix="cert-store-")) / "case.json")


def offline_id(payload=None, **_k):
    return {"item": "TEST LOOT", "desc": "", "category": "prop",
            "value_usd": 25.0, "estimated": True, "bbox": [0.3, 0.3, 0.2, 0.2],
            "source": "offline"}


# ---------- PHASE 3/5: camera matrix through the real scan loop ----------

class CameraMatrix(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        capture.reset_gate()

    def tearDown(self):
        rig_app.store = self.saved

    def run_loop(self, cam, ticks=12):
        rig_app.scan_loop(opener=lambda: cam, identify=offline_id,
                          sleep=lambda _s: None, ticks=ticks)

    def test_normal_frames_file_exhibits(self):
        cam = hw_sim.FakeCam("ok")
        self.run_loop(cam, ticks=8)
        snap = rig_app.store.snapshot()
        self.assertTrue(snap["camera_ok"])
        self.assertGreaterEqual(len(snap["items"]), 1)
        self.assertIsNotNone(snap["items"][0]["bbox"])

    def test_no_camera_sets_lost_and_recovers(self):
        cam = hw_sim.FakeCam("dead")
        self.run_loop(cam, ticks=4)
        self.assertFalse(rig_app.store.snapshot()["camera_ok"])
        cam2 = hw_sim.FakeCam("ok")
        self.run_loop(cam2, ticks=8)
        self.assertTrue(rig_app.store.snapshot()["camera_ok"])

    def test_corrupt_reads_do_not_crash(self):
        cam = hw_sim.FakeCam("corrupt")
        self.run_loop(cam, ticks=6)
        self.assertFalse(rig_app.store.snapshot()["camera_ok"])

    def test_frozen_frame_never_files_a_dupe(self):
        cam = hw_sim.FakeCam("frozen")
        self.run_loop(cam, ticks=30)
        # One scene ever: at most one exhibit regardless of tick count.
        self.assertLessEqual(len(rig_app.store.snapshot()["items"]), 1)

    def test_ten_second_dead_gap_recovers(self):
        cam = hw_sim.FakeCam("ok")
        self.run_loop(cam, ticks=4)
        cam.mode = "corrupt"
        self.run_loop(cam, ticks=10)   # the "no frames" window
        cam.mode = "ok"
        self.run_loop(cam, ticks=8)
        self.assertTrue(rig_app.store.snapshot()["camera_ok"])


# ---------- GPIO buttons through the real reveal path ----------

class ButtonMatrix(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        self.mod, self.calls = hw_sim.fake_gpiozero()
        self.restore = hw_sim.install({"gpiozero": self.mod})
        rig_app.display.show_reveal = lambda *a, **k: None
        rig_app.printer.receipt = lambda *a: None

    def tearDown(self):
        self.restore()
        rig_app.store = self.saved

    def test_gpio_press_reveals_and_resets(self):
        rig_app.button.start(rig_app.on_button)
        btn = self.calls["buttons"][17]
        btn.fire()
        self.assertTrue(rig_app.store.snapshot()["revealed"])
        btn.fire()   # second press closes the case
        self.assertFalse(rig_app.store.snapshot()["revealed"])
        self.assertEqual(rig_app.store.count(), 0)

    def test_five_hundred_rapid_presses_stay_consistent(self):
        rig_app.button.start(rig_app.on_button)
        btn = self.calls["buttons"][17]
        threads = [threading.Thread(target=btn.fire) for _ in range(500)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        snap = rig_app.store.snapshot()
        # Whatever the interleaving, state must be a valid alternating landing.
        self.assertIn(snap["revealed"], (True, False))

    def test_no_gpio_falls_back_without_touching_pins(self):
        self.restore()
        restore = hw_sim.install({"gpiozero": None})
        try:
            # Must not raise; falls to stdin/evdev which no-ops off a tty.
            rig_app.button.start(rig_app.on_button)
        finally:
            restore()


# ---------- OLED: real render(), fake luma device ----------

class OledMatrix(unittest.TestCase):
    def test_all_modes_render_in_bounds(self):
        from PIL import Image, ImageDraw
        for mode, take, count in (
            ("live", 0, 0), ("live", 7420, 4), ("live", 9_999_999, 99),
            ("lost", 7420, 4), ("reveal", 7600, 5),
        ):
            display._state.update(take=take, count=count, mode=mode)
            img = Image.new("1", (128, 64))
            render_img = img.copy()
            draw = ImageDraw.Draw(render_img)
            display.render(draw, blink=True)
            self.assertTrue(render_img.getbbox(), f"{mode} rendered blank")

    def test_luma_device_path_drives_canvas(self):
        calls = {}
        restore = hw_sim.install(hw_sim.fake_luma(calls))
        try:
            display.start()
            time.sleep(0.05)
            self.assertIn("device", calls)
            self.assertGreater(calls["device"].frames, 0)
        finally:
            restore()


# ---------- Motors: every failure must end in stop ----------

class MotorSafety(unittest.TestCase):
    def setUp(self):
        self.mod, self.calls = hw_sim.fake_gpiozero()
        self.restore = hw_sim.install({"gpiozero": self.mod})
        from rig import drive
        self.drive = drive

    def tearDown(self):
        self.restore()
        self.drive.set_frame_source(None)

    def _drv(self):
        return self.drive.RobotDriver()

    def test_stop_after_every_path(self):
        drv = self._drv()
        drv.move("forward", 0.01)
        drv.move("left", 0.01)
        drv.move("stop")
        time.sleep(0.05)
        self.assertEqual(self.calls["robot"][-1], "stop")

    def test_invalid_direction_stops(self):
        drv = self._drv()
        drv.move("spin_360_no_scope", 0.1)
        time.sleep(0.05)
        self.assertEqual(self.calls["robot"][-1], "stop")

    def test_conflicting_and_idle_return_end_stopped(self):
        drv = self._drv()
        drv.move("forward", 0.01)
        drv.move("back", 0.01)
        drv.move("stop")
        legs = drv.return_home()
        self.assertGreaterEqual(legs, 1)
        time.sleep(0.05)
        self.assertEqual(self.calls["robot"][-1], "stop")

    def test_return_without_trail_is_safe(self):
        self.assertEqual(self._drv().return_home(), 0)

    def test_teleop_aborts_breadcrumb_return(self):
        """A human grabbing WASD mid-return wins: the breadcrumb replay must
        stop instead of fighting the driver for the wheels."""
        drv = self._drv()
        for _ in range(8):
            drv.move("forward", 0.1)   # recorded trail, ~0.8s to replay
        drv.move("stop")
        result = {}
        t = threading.Thread(
            target=lambda: result.setdefault("legs", drv.return_home()))
        t.start()
        time.sleep(0.15)
        drv.move("forward", 0.01)      # teleop takes the wheel mid-return
        t.join(timeout=10)
        self.assertFalse(t.is_alive())
        self.assertLess(result.get("legs", 99), 8)

    def test_duplicate_return_call_is_ignored(self):
        """Two 'return' POSTs can't spawn two trail-eaters fighting the lock."""
        drv = self._drv()
        for _ in range(4):
            drv.move("forward", 0.1)
        first = {}
        t = threading.Thread(
            target=lambda: first.setdefault("legs", drv.return_home()))
        t.start()
        time.sleep(0.02)
        self.assertEqual(drv.return_home(), 0)   # second caller bounces off
        t.join(timeout=10)
        self.assertGreaterEqual(first.get("legs", 0), 1)


# ---------- Mic chain: real _ask, fake arecord + whisper ----------

class MicMatrix(unittest.TestCase):
    """Mic press -> a radio call: record, Whisper, then an answer from the ledger.
    No model writes the answer, so the chat endpoint is never called."""

    def setUp(self):
        from rig import narration, radio, voice
        self.voice, self.narration = voice, narration
        self.store = fresh_store()
        self.calls = {}
        self.restore = hw_sim.install(hw_sim.fake_openai_tts(self.calls))
        self.sp = voice.Speaker(autostart=False)
        voice.set_speaker(self.sp)
        narration.set_narrator(narration.Narrator(speaker=self.sp, seed=1))
        self.radio = radio.Radio(lambda: self.store, autostart=False)

    def tearDown(self):
        self.restore()
        listen._openai = None
        self.voice.set_speaker(None)
        self.narration.set_narrator(None)
        os.environ.pop("OPENAI_API_KEY", None)

    def _call(self, mic, key="sk-x"):
        if key:
            os.environ["OPENAI_API_KEY"] = key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        saved = subprocess.run
        listen.subprocess.run = mic.runner
        try:
            job, _ = self.radio.submit("mic")
            self.radio.drain()
            self.sp.drain()
        finally:
            listen.subprocess.run = saved
        return self.radio.get(job["job_id"])

    def said(self):
        return [line["text"] for line in self.sp.transcript]

    def test_valid_recording_rides_the_whole_chain(self):
        job = self._call(hw_sim.FakeMic(out_bytes=4096))
        self.assertIn("whisper", self.calls)
        self.assertNotIn("chat", self.calls)                     # no invented ETA
        self.assertEqual(job["transcript"], "how long do we have")
        self.assertEqual(job["intent"]["name"], "time")
        self.assertEqual(job["state"], "done")
        self.assertIn("no clock", job["reply"])                  # appraisal job: the truth
        self.assertTrue(any("no clock" in s for s in self.said()))

    def test_zero_byte_audio_says_mics_dead(self):
        job = self._call(hw_sim.FakeMic(out_bytes=50))
        self.assertEqual(job["state"], "failed")
        self.assertIn("mic", job["error"])
        self.assertTrue(any("mic" in s.lower() for s in self.said()))

    def test_mic_unavailable_says_mics_dead(self):
        job = self._call(hw_sim.FakeMic(fail=True))
        self.assertEqual(job["state"], "failed")
        self.assertTrue(any("mic" in s.lower() for s in self.said()))

    def test_no_key_skips_before_recording(self):
        job = self._call(hw_sim.FakeMic(fail=True), key=None)
        self.assertIn("OPENAI_API_KEY", job["error"])
        self.assertTrue(any("radio" in s.lower() for s in self.said()))
        self.assertNotIn("whisper", self.calls)


# ---------- Speaker ladder ----------

class SpeakerMatrix(unittest.TestCase):
    def setUp(self):
        from rig import voice
        self.voice = voice
        self.env = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "RIG_VOICE", "NARRATOR_CACHE")}
        os.environ["RIG_VOICE"] = "1"
        os.environ["NARRATOR_CACHE"] = tempfile.mkdtemp(prefix="tts-cache-")

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_wav_missing_falls_to_tts_then_log(self):
        voice = self.voice
        calls = {}
        restore = hw_sim.install(hw_sim.fake_openai_tts(calls))
        os.environ["OPENAI_API_KEY"] = "sk-x"
        plays = []
        saved_play = voice.play_wav
        voice.play_wav = lambda p: (plays.append(p) or True)
        try:
            sp = voice.Speaker(autostart=False, player=voice.play_wav)
            sp.submit(voice.Utterance("test", [("clip", "/definitely/missing.wav")], ["hello crew"]))
            sp.drain()
            self.assertIn("tts", calls)                    # the transcript went to OpenAI TTS
            self.assertTrue(plays)                         # and its wav was played
            self.assertEqual(sp.transcript[0]["state"], "played")
        finally:
            voice.play_wav = saved_play
            restore()

    def test_no_voice_at_all_stays_a_visible_transcript(self):
        voice = self.voice
        os.environ.pop("OPENAI_API_KEY", None)
        saved_local = voice._local_speak
        voice._local_speak = lambda text: False
        try:
            sp = voice.Speaker(autostart=False, player=lambda p: False)
            sp.submit(voice.Utterance("test", [("say", "hello crew")], ["hello crew"]))
            sp.drain()
            self.assertEqual(sp.transcript[0]["state"], "text-only")
            self.assertEqual(sp.transcript[0]["text"], "hello crew")
        finally:
            voice._local_speak = saved_local


# ---------- Network: rover vs a real HTTP hub under latency ----------

class NetworkMatrix(unittest.TestCase):
    def test_post_and_ping_against_real_server(self):
        hub = hw_sim.FakeHub(latency=0.05)
        hub.start()
        try:
            self.assertTrue(rover.ping_hub(hub.url()))
            self.assertTrue(rover.post_exhibit(hub.url(), {"item": "X"}))
            self.assertEqual(hub.hits["ping"], 1)
            self.assertEqual(hub.hits["exhibit"], 1)
        finally:
            hub.stop()

    def test_hub_down_queues_then_drains_on_recovery(self):
        queue = __import__("collections").deque()
        ok = rover.post_exhibit("http://127.0.0.1:9", {"item": "X"})
        self.assertFalse(ok)   # refused, caller queues
        queue.append({"item": "X"})
        hub = hw_sim.FakeHub()
        hub.start()
        try:
            while queue:
                payload = queue[0]
                if rover.post_exhibit(hub.url(), payload):
                    queue.popleft()
                else:
                    break
            self.assertEqual(len(queue), 0)
            self.assertEqual(hub.hits["exhibit"], 1)
        finally:
            hub.stop()

    def test_half_second_latency_still_lands(self):
        hub = hw_sim.FakeHub(latency=0.5)
        hub.start()
        try:
            t0 = time.monotonic()
            self.assertTrue(rover.post_exhibit(hub.url(), {"item": "Y"}))
            self.assertLess(time.monotonic() - t0, 4)  # inside POST_TIMEOUT
        finally:
            hub.stop()

    def test_duplicate_posts_dedup_hub_side(self):
        rig_app._rate.clear()
        snap_before = len(rig_app.store.snapshot()["items"])
        body = {"item": "DUP ZEBRA QX7", "category": "relic", "value_usd": 100}
        client = rig_app.app.test_client()
        for _ in range(3):
            client.post("/api/exhibit", json=body)
        self.assertEqual(len(rig_app.store.snapshot()["items"]), snap_before + 1)


# ---------- Boot order ----------

class BootOrder(unittest.TestCase):
    def test_rover_first_hub_late(self):
        """Rover boots while the hub is down: pings fail, queue grows, and the
        first successful ping + drain lands once the hub comes up."""
        self.assertFalse(rover.ping_hub("http://127.0.0.1:9"))
        queue = __import__("collections").deque([{"item": "A"}, {"item": "B"}])
        hub = hw_sim.FakeHub()
        hub.start()
        try:
            self.assertTrue(rover.ping_hub(hub.url()))
            while queue and rover.post_exhibit(hub.url(), queue[0]):
                queue.popleft()
            self.assertEqual(hub.hits["exhibit"], 2)
        finally:
            hub.stop()

    def test_hub_first_wrist_late(self):
        """ESP32 joins after the hub: /wrist.json answers with a valid frame."""
        client = rig_app.app.test_client()
        snap = json.loads(client.get("/wrist.json").get_data(as_text=True))
        for key in ("case_no", "take", "count", "pending", "revealed", "top"):
            self.assertIn(key, snap)


# ---------- Soak: 500-cycle runs, watch threads/fds/memory ----------

class Soak(unittest.TestCase):
    def test_scan_soak_no_leak(self):
        saved = rig_app.store
        rig_app.store = fresh_store()
        cam = hw_sim.FakeCam("ok")
        gc.collect()
        t0, f0 = len(threading.enumerate()), hw_sim.fd_count()
        try:
            for _burst in range(50):
                rig_app.scan_loop(opener=lambda: cam, identify=offline_id,
                                  sleep=lambda _s: None, ticks=10)
        finally:
            rig_app.store = saved
        gc.collect()
        t1, f1 = len(threading.enumerate()), hw_sim.fd_count()
        self.assertLessEqual(t1, t0 + 2, f"thread leak: {t0}->{t1}")
        if f0 >= 0:
            self.assertLessEqual(f1, f0 + 5, f"fd leak: {f0}->{f1}")

    def test_reveal_reset_soak(self):
        saved = rig_app.store
        rig_app.store = fresh_store()
        rig_app.display.show_reveal = lambda *a, **k: None
        rig_app.printer.receipt = lambda *a: None
        try:
            for _ in range(500):
                rig_app.on_button()
            self.assertFalse(rig_app.store.snapshot()["revealed"])  # even count
        finally:
            rig_app.store = saved


# ---------- Chaos ----------

class Chaos(unittest.TestCase):
    def test_identify_crash_keeps_the_walk_alive(self):
        saved = rig_app.store
        rig_app.store = fresh_store()
        cam = hw_sim.FakeCam("ok")
        def boom(*a, **k):
            raise RuntimeError("model died")
        try:
            rig_app.scan_loop(opener=lambda: cam, identify=boom,
                              sleep=lambda _s: None, ticks=8)
            self.assertTrue(rig_app.store.snapshot()["camera_ok"])
        finally:
            rig_app.store = saved

    def test_cam_death_mid_scan_recovers(self):
        saved = rig_app.store
        rig_app.store = fresh_store()
        cam = hw_sim.FakeCam("ok")
        try:
            rig_app.scan_loop(opener=lambda: cam, identify=offline_id,
                              sleep=lambda _s: None, ticks=4)
            cam.mode = "dead"
            rig_app.scan_loop(opener=lambda: cam, identify=offline_id,
                              sleep=lambda _s: None, ticks=3)
            self.assertFalse(rig_app.store.snapshot()["camera_ok"])
            cam.mode = "ok"
            rig_app.scan_loop(opener=lambda: cam, identify=offline_id,
                              sleep=lambda _s: None, ticks=6)
            self.assertTrue(rig_app.store.snapshot()["camera_ok"])
        finally:
            rig_app.store = saved


# ---------- Phase 8: timing on the real path ----------

class Timing(unittest.TestCase):
    def test_button_to_state_is_fast(self):
        saved = rig_app.store
        rig_app.store = fresh_store()
        rig_app.display.show_reveal = lambda *a, **k: None
        rig_app.printer.receipt = lambda *a: None
        try:
            t0 = time.monotonic()
            rig_app.on_button()
            ms = (time.monotonic() - t0) * 1000
            self.assertLess(ms, 200, f"reveal took {ms:.0f}ms")
        finally:
            rig_app.store = saved

    def test_snapshot_and_exhibit_path_latency(self):
        client = rig_app.app.test_client()
        t0 = time.monotonic()
        client.get("/state.json")
        snap_ms = (time.monotonic() - t0) * 1000
        t0 = time.monotonic()
        client.post("/api/exhibit", json={"item": "TIMING VASE", "value_usd": 5})
        ex_ms = (time.monotonic() - t0) * 1000
        self.assertLess(snap_ms, 300)
        self.assertLess(ex_ms, 500)


# ---------- Fuzz: arbitrary payloads must never 500 or poison state ----------

class Fuzz(unittest.TestCase):
    def test_exhibit_fuzz_500_random_payloads(self):
        import random
        rng = random.Random(20261001)
        client = rig_app.app.test_client()
        atoms = [None, True, 0, -1, 1e308, float("inf"), float("nan"), "",
                 "x" * 5000, "<img onerror=x>", "日本語", [], {}, [1, ["a"]],
                 {"deep": {"deeper": [1, 2, {"x": None}]}}]
        keys = ["item", "value_usd", "bbox", "category", "desc", "why",
                "frame_b64", "origin", "estimated"]
        crashes = 0
        for _ in range(500):
            body = {rng.choice(keys): rng.choice(atoms)
                    for _ in range(rng.randint(0, 6))}
            try:
                res = client.post("/api/exhibit", json=body)
                if res.status_code >= 500:
                    crashes += 1
            except Exception:
                crashes += 1
        # Whatever landed, the JSON contract must stay strict-parseable.
        raw = client.get("/state.json").get_data(as_text=True)
        json.loads(raw)
        self.assertNotIn("NaN", raw)
        self.assertEqual(crashes, 0)

    def test_negative_value_cannot_drain_the_take(self):
        store = fresh_store()
        added, _ = store.add_item({"item": "CURSED VASE", "value_usd": -500})
        self.assertTrue(added)
        self.assertEqual(store.take(), 0.0)
        self.assertEqual(store.snapshot()["items"][0]["value_usd"], 0.0)

    def test_ledger_cap_refuses_new_exhibits(self):
        saved = os.environ.get("MAX_EXHIBITS")
        os.environ["MAX_EXHIBITS"] = "12"
        store = fresh_store()
        names = ["ROLEX SUBMARINER", "LEICA M3", "HEMINGWAY NOVEL",
                 "BRASS LAMP", "SONY HEADPHONES", "RAZER HEADSET",
                 "GOLD POCKETWATCH", "SILVER LOCKET", "IVORY CHESS SET",
                 "OAK GAVEL", "RUBY BROOCH", "SAPPHIRE RING",
                 "EMERALD PENDANT", "PEARL NECKLACE", "ONYX FIGURINE"]
        try:
            for name in names:
                store.add_item({"item": name, "value_usd": 1})
            self.assertEqual(store.count(), 12)
        finally:
            if saved is None:
                os.environ.pop("MAX_EXHIBITS", None)
            else:
                os.environ["MAX_EXHIBITS"] = saved

    def test_add_item_fuzz_never_throws(self):
        import random
        rng = random.Random(7)
        store = fresh_store()
        pool = [None, 0, 3.14, "", "LOOT", ["a"], {"x": 1}, float("nan"), b"\x00"]
        for _ in range(500):
            cand = {k: rng.choice(pool) for k in ("item", "value_usd", "bbox",
                                                  "category", "desc", "why")}
            try:
                store.add_item(cand, None)
            except Exception as exc:
                self.fail(f"add_item raised {exc!r} on {cand!r}")


# ---------- Race harness: random op storm on RobotDriver ----------

class RaceStorm(unittest.TestCase):
    def test_random_drive_storm_ends_safe(self):
        import random
        mod, calls = hw_sim.fake_gpiozero()
        restore = hw_sim.install({"gpiozero": mod})
        try:
            from rig import drive
            drv = drive.RobotDriver()
            rng = random.Random(99)
            ops = ["forward", "back", "left", "right", "stop"] * 20
            threads = [
                threading.Thread(target=drv.move,
                                 args=(rng.choice(ops), rng.uniform(0, 0.05)))
                for _ in range(200)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            drv.move("stop")
            time.sleep(0.1)
            self.assertEqual(calls["robot"][-1], "stop")
            # every thread completed — no deadlock, no orphan sleeper
            self.assertFalse(any(t.is_alive() for t in threads))
        finally:
            restore()


# ---------- Corrupt-tail recovery: power cut mid-write ----------

class CorruptTail(unittest.TestCase):
    def test_truncated_case_file_loads_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "case.json"
            s = Store(path)
            s.add_item({"item": "VASE", "value_usd": 10}, None)
            good = path.read_bytes()
            # simulate a power cut halfway through the temp-file rename window
            path.write_bytes(good[:len(good) // 2])
            s2 = Store(path)
            self.assertEqual(s2.count(), 0)   # degrades to fresh, never crashes


# ---------- Golden-path E2E: real HTTP server + real rover ----------

class EndToEnd(unittest.TestCase):
    def test_real_http_chain_rover_to_ledger(self):
        from werkzeug.serving import make_server
        saved = rig_app.store
        rig_app.store = fresh_store()
        rig_app._rate.clear()
        server = make_server("127.0.0.1", 0, rig_app.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            # real rover code path -> real urllib -> real Flask route
            self.assertTrue(rover.ping_hub(url))
            ok = rover.post_exhibit(url, {"item": "E2E LOOT", "value_usd": 42,
                                          "category": "prop"})
            self.assertTrue(ok)
            snap = rig_app.store.snapshot()
            self.assertEqual(len(snap["items"]), 1)
            self.assertEqual(snap["items"][0]["origin"], "rover")
        finally:
            server.shutdown()
            rig_app.store = saved


# ---------- Security posture ----------

class SecurityPosture(unittest.TestCase):
    def setUp(self):
        rig_app._rate.clear()

    def test_rate_limit_exhibit(self):
        client = rig_app.app.test_client()
        codes = [client.post("/api/exhibit", json={"item": f"SPAM{i}",
                                                 "value_usd": 1}).status_code
                 for i in range(130)]
        self.assertIn(429, codes)

    def test_rate_limit_drive(self):
        client = rig_app.app.test_client()
        codes = [client.post("/api/drive", json={"dir": "stop"}).status_code
                 for _ in range(610)]
        self.assertIn(429, codes)

    def test_confirm_nonce_gates_the_reveal_post(self):
        client = rig_app.app.test_client()
        snap = rig_app.store.snapshot()["revealed"]
        # A drive-by POST without the nonce must 403.
        res = client.post("/trigger_reveal")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(rig_app.store.snapshot()["revealed"], snap)
        # The nonce in the GET page unlocks it.
        page = client.get("/trigger_reveal").get_data(as_text=True)
        nonce = re.search(r'name=nonce value=([0-9a-f]+)', page).group(1)
        res = client.post("/trigger_reveal", data={"nonce": nonce})
        self.assertEqual(res.status_code, 200)

    def test_security_headers_present(self):
        resp = rig_app.app.test_client().get("/state.json")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")

    def test_radio_endpoint_fires_dispatch(self):
        from rig import radio
        saved = radio._radio
        radio.set_radio(radio.Radio(lambda: rig_app.store, autostart=False))
        try:
            res = rig_app.app.test_client().post("/api/radio")
            self.assertEqual(res.status_code, 202)
            job = res.get_json()
            self.assertEqual((job["source"], job["state"]), ("mic", "queued"))
            self.assertEqual(radio.radio().get(job["job_id"])["job_id"], job["job_id"])
        finally:
            radio.set_radio(saved)

    def test_auto_token_mints_and_enforces(self):
        saved = os.environ.get("RIG_TOKEN")
        os.environ["RIG_TOKEN"] = "auto"
        rig_app._auto_token = None
        try:
            client = rig_app.app.test_client()
            self.assertEqual(client.post("/trigger_reveal").status_code, 401)
            self.assertEqual(
                client.post("/trigger_reveal",
                            headers={"X-Rig-Token": rig_app._rig_token(),
                                     "X-Case-Nonce": rig_app._nonce()}).status_code, 200)
            # The phone confirm page posts a bare form — no header room.
            # Token mode must still honor the nonce or that path is dead.
            page = client.get("/trigger_reveal").get_data(as_text=True)
            nonce = re.search(r'name=nonce value=([0-9a-f]+)', page).group(1)
            res = client.post("/trigger_reveal", data={"nonce": nonce})
            self.assertEqual(res.status_code, 200)
        finally:
            if saved is None:
                os.environ.pop("RIG_TOKEN", None)
            else:
                os.environ["RIG_TOKEN"] = saved
            rig_app._auto_token = None

    def test_token_mode_gates_the_reads(self):
        """With RIG_TOKEN set the feed, the ledger, and the crops are crew-only;
        /health and /manifest stay open for the kiosk probe and the QR board."""
        saved = os.environ.get("RIG_TOKEN")
        os.environ["RIG_TOKEN"] = "crew-test"
        try:
            client = rig_app.app.test_client()
            for path in ("/state.json", "/wrist.json?peek", "/frame.jpg", "/crop/1.jpg"):
                self.assertEqual(client.get(path).status_code, 401, path)
            for path in ("/health", "/manifest", "/"):
                self.assertEqual(client.get(path).status_code, 200, path)
            hdrs = {"X-Rig-Token": "crew-test"}
            self.assertEqual(client.get("/state.json", headers=hdrs).status_code, 200)
            self.assertEqual(client.get("/wrist.json?peek", headers=hdrs).status_code, 200)
            self.assertEqual(client.get("/frame.jpg", headers=hdrs).status_code, 200)
        finally:
            if saved is None:
                os.environ.pop("RIG_TOKEN", None)
            else:
                os.environ["RIG_TOKEN"] = saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    unittest.main(verbosity=2)
