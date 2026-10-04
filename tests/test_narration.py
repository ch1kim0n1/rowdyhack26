"""The narrator (#34): line catalog, selection rules, and the one bounded speech queue.

Fake clock, fake player, fake TTS, seeded variants: every rule here is
deterministic. No sound is made.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("RIG_VOICE", "0")   # the suite never talks out loud
for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "RIG_TOKEN", "NARRATOR_MILESTONES"):
    os.environ.pop(var, None)

from rig import app as rig_app
from rig import capture, mastermind, narration, script, voice
from rig.store import Store


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, s):
        self.t += s


def fresh_store() -> Store:
    return Store(Path(tempfile.mkdtemp(prefix="narration-store-")) / "case.json")


class Audio:
    """A fake speaker system: records what would have played or been spoken."""
    def __init__(self, play_ok=True, tts_ok=True):
        self.played, self.spoken = [], []
        self.play_ok, self.tts_ok = play_ok, tts_ok

    def play(self, path):
        self.played.append(Path(path).name)
        return self.play_ok

    def tts(self, text):
        self.spoken.append(text)
        return self.tts_ok


def speaker(clock=None, audio=None, maxlen=6):
    audio = audio or Audio()
    return voice.Speaker(clock=clock or Clock(), player=audio.play, tts=audio.tts, maxlen=maxlen,
                         autostart=False), audio


def utt(event, priority=30, case_no=1, text=None, **kw):
    return voice.Utterance(event, [("say", text or event)], [text or event], priority=priority,
                           case_no=case_no, **kw)


class Voiced(unittest.TestCase):
    """Runs with sound 'on' so the ladder is exercised (the fakes make no noise)."""

    def setUp(self):
        self._env = os.environ.get("RIG_VOICE")
        os.environ["RIG_VOICE"] = "1"

    def tearDown(self):
        if self._env is None:
            os.environ.pop("RIG_VOICE", None)
        else:
            os.environ["RIG_VOICE"] = self._env


# ---------- the catalog and its audio ----------

class Catalog(unittest.TestCase):
    def test_catalog_is_valid_and_every_line_has_a_playable_clip(self):
        data = narration.load_catalog()
        self.assertEqual(narration.check_assets(data), [])
        for event, spec in data["events"].items():
            for v in spec["variants"]:
                path = narration.asset_path(event, v)
                with wave.open(str(path), "rb") as w:
                    self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050), path.name)
                    self.assertLess(w.getnframes() / w.getframerate(), 6.0, f"{path.name} runs long")
                self.assertTrue(v.get("provenance"), f"{event}/{v['id']} has no provenance")

    def test_issue_events_are_all_covered(self):
        events = set(narration.load_catalog()["events"])
        for needed in ("case_started", "first_exhibit", "top5_entry", "value_milestone", "rover_confirmed",
                       "camera_lost", "camera_restored", "radio_busy", "radio_unavailable", "plan_revised",
                       "no_feasible_plan", "scenario_time_low", "reveal", "empty_reveal", "case_closed"):
            self.assertIn(needed, events)

    def test_validation_names_each_problem(self):
        bad = {"version": 2, "events": {"x": {"priority": 500, "scope": "forever", "kind": "song",
                                               "cooldown_s": -1, "expire_s": 5, "requires": "magic",
                                               "variants": [{"id": "a", "text": " ", "asset": "../../etc/passwd"}]}}}
        problems = " | ".join(narration.validate_catalog(bad))
        for word in ("version", "priority", "scope", "kind", "cooldown_s", "unknown dependency", "transcript", "escapes"):
            self.assertIn(word, problems)

    def test_lines_never_claim_collection_risk_or_a_countdown(self):
        for event, spec in narration.load_catalog()["events"].items():
            for v in spec["variants"]:
                text = v["text"].lower()
                for banned in ("we took", "we've taken", "secured it", "alarm", "detected", "seconds left",
                               "minutes left"):
                    self.assertNotIn(banned, text, f"{event}/{v['id']}")


# ---------- the speaker queue ----------

class Queue(Voiced):
    def test_reveal_jumps_a_backlog_of_flavor(self):
        sp, audio = speaker()
        for i in range(5):
            sp.submit(utt(f"flavor{i}", priority=20))
        sp.submit(utt("reveal", priority=90))
        sp.drain()
        self.assertEqual(audio.spoken[0], "reveal")

    def test_bounded_queue_drops_the_least_important(self):
        sp, audio = speaker(maxlen=3)
        for i in range(3):
            self.assertTrue(sp.submit(utt(f"low{i}", priority=20)))
        self.assertFalse(sp.submit(utt("also_low", priority=20)))       # not more important: refused
        self.assertTrue(sp.submit(utt("radio", priority=80)))           # more important: bumps the newest low
        self.assertEqual(sp.depth(), 3)
        sp.drain()
        self.assertEqual(audio.spoken, ["radio", "low0", "low1"])
        states = {line["event"]: line["state"] for line in sp.transcript}
        self.assertEqual((states["also_low"], states["low2"]), ("dropped", "dropped"))

    def test_expired_and_old_case_lines_never_play(self):
        clock = Clock()
        sp, audio = speaker(clock)
        sp.submit(utt("stale", case_no=2, expires_at=clock() + 5))
        sp.submit(utt("old_case", case_no=1))
        sp.submit(utt("this_case", case_no=2))
        clock.tick(10)
        sp.drop_case_before(2)
        self.assertFalse(sp.submit(utt("late_old_case", case_no=1)))
        sp.drain()
        self.assertEqual(audio.spoken, ["this_case"])
        states = {line["event"]: line["state"] for line in sp.transcript}
        self.assertEqual(states["stale"], "expired")
        self.assertEqual(states["old_case"], "cancelled")
        self.assertEqual(states["late_old_case"], "cancelled")

    def test_a_lines_time_to_live_runs_on_the_speakers_clock(self):
        # The narrator's clock may sit anywhere relative to the speaker's (a
        # CI box minutes after boot has a small monotonic): expiry must not care.
        for elsewhere in (0.0, 1e6):
            clock = Clock()
            sp, _ = speaker(clock)
            n = narration.Narrator(speaker=sp, clock=lambda t=elsewhere: t, seed=1)
            ttl = n.catalog["events"]["case_started"]["expire_s"]
            n.emit("case_started", case_no=1)
            sp.drain()
            n.emit("case_started", case_no=2)
            clock.tick(ttl + 1)
            sp.drain()
            states = [line["state"] for line in reversed(sp.transcript)]
            self.assertEqual(states, ["played", "expired"])

    def test_coalesced_lines_keep_only_the_newest(self):
        sp, audio = speaker()
        sp.submit(utt("plan", text="revision 2", coalesce="plan"))
        sp.submit(utt("plan", text="revision 3", coalesce="plan"))
        sp.drain()
        self.assertEqual(audio.spoken, ["revision 3"])

    def test_a_played_clip_is_not_spoken_again(self):
        clip = str(narration.asset_path("top5_entry", {"id": "a"}))
        sp, audio = speaker()
        sp.submit(voice.Utterance("top5_entry", [("clip", clip), ("say", "ROLEX. Top five.")],
                                  ["That's worth a second look.", "ROLEX. Top five."]))
        sp.drain()
        self.assertEqual(audio.played, ["top5_entry-a.wav"])
        self.assertEqual(audio.spoken, ["ROLEX. Top five."])           # only the dynamic part
        self.assertEqual(sp.transcript[0]["state"], "played")

    def test_missing_or_corrupt_clips_fall_back_to_their_transcript(self):
        bad = Path(tempfile.mkdtemp()) / "corrupt.wav"
        bad.write_bytes(b"RIFF not a wav")
        sp, audio = speaker()
        sp.submit(voice.Utterance("x", [("clip", str(bad))], ["Lost the picture."]))
        sp.submit(voice.Utterance("y", [("clip", "/no/such.wav")], ["Picture's back."]))
        sp.drain()
        self.assertEqual(audio.played, [])
        self.assertEqual(audio.spoken, ["Lost the picture.", "Picture's back."])

    def test_failures_down_the_ladder_end_as_text(self):
        sp, audio = speaker(audio=Audio(play_ok=False, tts_ok=False))
        sp.submit(utt("anything", text="Scan complete."))
        sp.drain()
        self.assertEqual(sp.transcript[0]["state"], "text-only")
        self.assertEqual(sp.transcript[0]["text"], "Scan complete.")

    def test_a_crashing_player_does_not_kill_the_queue(self):
        def boom(_path):
            raise OSError("speaker unplugged")
        clip = str(narration.asset_path("reveal", {"id": "a"}))
        sp = voice.Speaker(clock=Clock(), player=boom, tts=lambda t: True, autostart=False)
        sp.submit(voice.Utterance("reveal", [("clip", clip)], ["Scan complete."]))
        sp.submit(utt("after"))
        self.assertEqual(sp.drain(), 2)

    def test_muted_is_silent_but_still_written_down(self):
        os.environ["RIG_VOICE"] = "0"
        sp, audio = speaker()
        sp.submit(utt("reveal", text="Scan complete. Here's the take."))
        sp.drain()
        self.assertEqual((audio.played, audio.spoken), ([], []))
        self.assertEqual(sp.transcript[0]["state"], "muted")
        self.assertEqual(sp.transcript[0]["text"], "Scan complete. Here's the take.")

    def test_volume_zero_is_mute(self):
        os.environ["NARRATOR_VOLUME"] = "0"
        try:
            self.assertFalse(voice.enabled())
        finally:
            os.environ.pop("NARRATOR_VOLUME", None)

    def test_latency_is_recorded(self):
        clock = Clock()
        sp, _ = speaker(clock)
        sp.submit(utt("reveal"))
        clock.tick(0.25)
        sp.drain()
        self.assertEqual(sp.transcript[0]["latency_ms"], 250)

    def test_soak_keeps_one_thread_and_a_bounded_queue(self):
        sp, _ = speaker(maxlen=6)
        before = threading.active_count()
        for i in range(2000):
            sp.submit(utt(f"e{i % 7}", priority=10 + i % 50))
            self.assertLessEqual(sp.depth(), 6)
            if i % 100 == 0:
                sp.drain()
        self.assertEqual(threading.active_count(), before)
        self.assertLessEqual(len(sp.transcript), voice.TRANSCRIPT_MAX)


# ---------- the narrator: events from transitions ----------

class Narration(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sp, self.audio = speaker(self.clock)
        self.n = narration.Narrator(speaker=self.sp, clock=self.clock, seed=7)
        self.store = fresh_store()
        mastermind.reset_cache()
        self.n.prime(self.store)

    def look(self):
        return self.n.observe(self.store)

    def add(self, item, value, category="watch", **kw):
        self.store.add_item({"item": item, "value_usd": value, "category": category, **kw})

    def test_polling_the_same_state_says_nothing_twice(self):
        self.add("ROLEX", 4200)
        self.assertEqual(self.look(), ["first_exhibit", "value_milestone"])
        for _ in range(5):
            self.assertEqual(self.look(), [])

    def test_first_find_then_top_five_with_the_item_and_price(self):
        self.add("ROLEX", 400)
        self.look()
        self.clock.tick(5)
        self.add("LEICA", 350, "camera")
        self.assertEqual(self.look(), ["top5_entry"])
        self.sp.drain()
        lines = [line["text"] for line in self.sp.transcript]
        self.assertTrue(any(t.endswith("LEICA. Top five. 350 dollars.") for t in lines))
        self.assertTrue(any(t.endswith("ROLEX. 400 dollars.") for t in lines))

    def test_top_five_has_a_cooldown_and_exits_are_never_called(self):
        self.add("ROLEX", 100)
        self.look()
        self.clock.tick(5)
        self.add("FIRE DOOR", 0, "exit")
        self.add("LEICA", 90, "camera")
        self.add("BOOK", 80, "book")
        self.assertEqual(self.look(), ["top5_entry"])            # the book waits out the cooldown
        self.assertEqual([e["key"] for e in self.n.events if e["event"] == "top5_entry"], [3])

    def test_milestones_fire_on_crossing_once(self):
        self.add("A", 900)
        self.look()
        self.add("B", 200, "camera")
        self.assertIn("value_milestone", self.look())            # crossed 1,000
        self.clock.tick(10)                                      # past the milestone cooldown
        self.add("C", 9500, "art")
        self.look()                                              # 5,000 and 10,000 in one jump: one line
        keys = [e["key"] for e in self.n.events if e["event"] == "value_milestone"]
        self.assertEqual(keys, [1000.0, 10000.0])

    def test_camera_loss_is_debounced_and_restore_follows_only_a_spoken_loss(self):
        self.store.set_camera(False)
        self.assertEqual(self.look(), [])
        self.clock.tick(0.5)
        self.store.set_camera(True)
        self.assertEqual(self.look(), [])                        # a flap: nothing
        self.store.set_camera(False)
        self.look()
        self.clock.tick(2.5)
        self.assertEqual(self.look(), ["camera_lost"])
        self.assertEqual(self.look(), [])
        self.store.set_camera(True)
        self.assertEqual(self.look(), ["camera_restored"])

    def test_reveal_and_close(self):
        self.add("ROLEX", 4200)
        self.look()
        self.store.mark_revealed()
        self.assertEqual(self.look(), ["reveal"])
        self.store.reset_case()
        self.assertEqual(self.look(), ["case_closed"])
        empty = fresh_store()
        n2 = narration.Narrator(speaker=speaker(self.clock)[0], clock=self.clock, seed=1)
        n2.prime(empty)
        empty.mark_revealed()
        self.assertEqual(n2.observe(empty), ["empty_reveal"])

    def test_a_reset_cancels_the_old_cases_queue(self):
        self.add("ROLEX", 4200)
        self.look()                                              # two lines queued for case 1138
        self.store.mark_revealed()
        self.look()
        self.store.reset_case()
        self.look()
        self.sp.drain()
        states = {line["event"]: line["state"] for line in self.sp.transcript}
        self.assertEqual(states["first_exhibit"], "cancelled")
        self.assertEqual(states["reveal"], "cancelled")
        self.assertEqual(states["case_closed"], "muted")          # the new case's line still plays

    def test_variants_rotate_without_repeating(self):
        picks = []
        for case in range(6):
            self.n.emit("case_started", case_no=case)
            picks.append(self.n.events[-1]["variant"])
        self.assertTrue(all(a != b for a, b in zip(picks, picks[1:], strict=False)))

    def test_case_scope_fires_once_per_case(self):
        self.assertTrue(self.n.emit("case_started", case_no=5))
        self.assertFalse(self.n.emit("case_started", case_no=5))
        self.assertTrue(self.n.emit("case_started", case_no=6))

    def test_unshipped_dependencies_stay_silent(self):
        self.assertFalse(self.n.emit("rover_confirmed", case_no=1, key=3))

    def test_restart_mid_case_reannounces_nothing(self):
        self.add("ROLEX", 4200)
        self.add("LEICA", 1850, "camera")
        fresh = narration.Narrator(speaker=self.sp, clock=self.clock, seed=1)
        fresh.prime(Store(self.store.state_path()))
        self.assertEqual(fresh.observe(self.store), [])

    def test_plan_lines_follow_real_revisions(self):
        self.store.set_job("mastermind", {"bag_lb": 2, "time_s": 60, "level": "small"})
        self.n.prime(self.store)
        self.add("ROLEX", 4200, weight_lb=0.34)
        self.add("BOOK", 950, "book", weight_lb=1.6)
        self.look()
        self.clock.tick(5)
        self.add("LEICA", 1850, "camera", weight_lb=1.29)       # swaps the book out
        self.assertIn("plan_revised", self.look())
        self.store.set_job("mastermind", {"bag_lb": 2, "time_s": 4, "level": "small"})
        fired = self.look()
        self.assertIn("no_feasible_plan", fired)                 # nothing grabs in 4 seconds
        self.assertEqual(self.look(), [])

    def test_time_low_on_crossing(self):
        self.store.set_job("mastermind", {"bag_lb": 25, "time_s": 12, "level": "small"})
        self.n.prime(self.store)
        self.add("ROLEX", 4200, weight_lb=0.34)                  # 5 of 12 seconds
        self.look()
        self.add("BOOK", 950, "book", weight_lb=1.6)             # 11 of 12: over 80 percent
        self.assertIn("scenario_time_low", self.look())


class OfflineDemo(unittest.TestCase):
    """The scripted walk, start to finish, with no network: fixed lines are clips."""

    def test_scripted_case_narrates_from_clips_with_no_cloud_call(self):
        audio = Audio()
        clock = Clock()
        sp = voice.Speaker(clock=clock, player=audio.play, tts=audio.tts, autostart=False)
        n = narration.Narrator(speaker=sp, seed=3)
        store = fresh_store()
        n.prime(store)
        narration.set_narrator(n)
        saved_env = os.environ.get("RIG_VOICE")
        os.environ["RIG_VOICE"] = "1"
        os.environ["NARRATOR_CAMERA_DEBOUNCE"] = "0"
        try:
            narration.emit("case_started", case_no=store.case_no())
            script._walk(store, sleep=lambda _s: sp.drain())
            sp.drain()
        finally:
            narration.set_narrator(None)
            os.environ.pop("NARRATOR_CAMERA_DEBOUNCE", None)
            if saved_env is None:
                os.environ.pop("RIG_VOICE", None)
            else:
                os.environ["RIG_VOICE"] = saved_env
        events = [line["event"] for line in reversed(sp.transcript)]
        for needed in ("case_started", "first_exhibit", "top5_entry", "camera_lost", "camera_restored",
                       "reveal", "case_closed"):
            self.assertIn(needed, events)
        fixed = {line["text"] for line in sp.transcript}
        self.assertFalse(set(audio.spoken) & fixed)              # no fixed sentence went to TTS
        self.assertTrue(all(name.endswith(".wav") for name in audio.played))
        self.assertTrue(all("dollars" in s for s in audio.spoken))   # TTS only for item/price


class AppWiring(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        self.sp, _ = speaker()
        self.n = narration.Narrator(speaker=self.sp, seed=1)
        narration.set_narrator(self.n)
        self.n.prime(rig_app.store)
        rig_app._rate.clear()
        self.client = rig_app.app.test_client()
        voice.set_speaker(self.sp)

    def tearDown(self):
        rig_app.store = self.saved
        narration.set_narrator(None)
        voice.set_speaker(None)

    def test_scan_reveal_and_reset_narrate_once_each(self):
        frame = capture.paint_still([0.2, 0.2, 0.3, 0.3])
        rig_app._examine(frame, identify=lambda _b: {"item": "ROLEX", "category": "watch", "value_usd": 4200})
        rig_app._examine(frame, identify=lambda _b: {"item": "ROLEX", "category": "watch", "value_usd": 4200})
        for _ in range(3):
            self.client.get("/state.json")                       # polls never narrate
        rig_app.on_button()
        rig_app.on_button()
        events = [e["event"] for e in self.n.events]
        self.assertEqual(events, ["first_exhibit", "value_milestone", "reveal", "case_closed"])

    def test_picking_the_job_starts_the_case_once(self):
        hdr = {"X-Case-Nonce": rig_app._nonce()}
        self.client.post("/api/plan", json={"mode": "appraisal"}, headers=hdr)
        self.client.post("/api/plan", json={"mode": "appraisal"}, headers=hdr)
        self.assertEqual([e["event"] for e in self.n.events], ["case_started"])

    def test_narrator_json_shows_the_transcript(self):
        self.n.emit("case_started", case_no=rig_app.store.case_no())
        self.sp.drain()
        body = self.client.get("/narrator.json").get_json()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["lines"][0]["event"], "case_started")
        self.assertEqual(body["lines"][0]["state"], "muted")
        self.assertIn("narrator", self.client.get("/health").get_json())


@unittest.skipUnless(os.environ.get("NARRATOR_PLAYBACK_TEST") == "1", "set NARRATOR_PLAYBACK_TEST=1 to hear a clip")
class RealPlayback(unittest.TestCase):
    def test_a_bundled_clip_plays_on_this_machine(self):
        import time
        os.environ["RIG_VOICE"] = "1"
        clip = str(narration.asset_path("reveal", {"id": "a"}))
        start = time.monotonic()
        self.assertTrue(voice.play_wav(clip))
        print(f"\nreveal clip played end to end in {time.monotonic() - start:.2f}s")


if __name__ == "__main__":
    unittest.main()
