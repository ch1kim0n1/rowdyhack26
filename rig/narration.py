"""The narrator's script: which line, when, and how often.

The catalog is rig/voice/lines.json: stable event ids, each with its
variants (exact transcript + bundled WAV), a priority, a repeat scope, a
cooldown, an expiry, and whether the line is a complete sentence or an intro
to dynamic speech (the item and price after "That's worth a second look").

Events come from state transitions, never from polls. Narrator.observe()
diffs the case against what it last saw: the first exhibit, a new top-five
entry, a take crossing a milestone, the camera dropping (debounced) and
coming back, the reveal, the case closing, and in Mastermind a real plan
revision. Calling observe() twice on the same state says nothing the second
time. Explicit events (the job picked, radio failures) go through emit().

Selection is deterministic given a seed: variants rotate without repeating
back to back, cooldowns and scopes use an injectable clock, and everything
lands in the one Speaker queue (rig/voice.py).

    python -m rig.narration check            # catalog + every asset, before the demo
    python -m rig.narration build            # (re)generate WAVs: OpenAI TTS if keyed, else macOS say
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from pathlib import Path

from rig import config, voice

log = logging.getLogger("rig.narration")

LINES = Path(__file__).resolve().parent / "voice" / "lines.json"
SCOPES = {"case", "exhibit", "threshold", "global"}
KINDS = {"sentence", "intro"}
# Dependencies an event can wait on. Sensor fusion (#29) has not shipped.
AVAILABLE = {"planner": True, "fusion": False}
TIME_LOW = 0.8


def milestones() -> list[float]:
    raw = config.env_str("NARRATOR_MILESTONES", "1000,5000,10000,25000")
    try:
        return sorted({float(x) for x in raw.split(",") if x.strip() and float(x) > 0})
    except ValueError:
        return [1000.0, 5000.0, 10000.0, 25000.0]


def camera_debounce() -> float:
    return config.env_float("NARRATOR_CAMERA_DEBOUNCE", 2.0, lo=0.0, hi=30.0)


# ---------- the catalog ----------

def asset_path(event: str, variant: dict) -> Path:
    return LINES.parent / (variant.get("asset") or f"lines/{event}-{variant['id']}.wav")


def load_catalog(path: Path = LINES) -> dict:
    data = json.loads(Path(path).read_text())
    problems = validate_catalog(data)
    if problems:
        raise ValueError("narrator catalog: " + "; ".join(problems))
    return data


def validate_catalog(data: dict) -> list[str]:
    problems = []
    if data.get("version") != 1:
        problems.append("version must be 1")
    events = data.get("events")
    if not isinstance(events, dict) or not events:
        return problems + ["no events"]
    for event, spec in events.items():
        where = f"{event}:"
        if not isinstance(spec.get("priority"), int) or not 0 <= spec["priority"] <= 100:
            problems.append(f"{where} priority must be 0-100")
        if spec.get("scope") not in SCOPES:
            problems.append(f"{where} scope must be one of {sorted(SCOPES)}")
        if spec.get("kind") not in KINDS:
            problems.append(f"{where} kind must be sentence or intro")
        for key in ("cooldown_s", "expire_s"):
            if not isinstance(spec.get(key), (int, float)) or spec[key] < 0:
                problems.append(f"{where} {key} must be a non-negative number")
        if spec.get("requires") and spec["requires"] not in AVAILABLE:
            problems.append(f"{where} requires an unknown dependency {spec['requires']!r}")
        variants = spec.get("variants")
        if not isinstance(variants, list) or not variants:
            problems.append(f"{where} needs at least one variant")
            continue
        ids = set()
        for v in variants:
            if not isinstance(v.get("text"), str) or not v["text"].strip():
                problems.append(f"{where} a variant has no transcript")
            if not v.get("id") or v["id"] in ids:
                problems.append(f"{where} variant ids must be present and unique")
            ids.add(v.get("id"))
            rel = asset_path(event, v).resolve()
            if not rel.is_relative_to(LINES.parent.resolve()):
                problems.append(f"{where} asset escapes rig/voice/")
    return problems


def check_assets(data: dict) -> list[str]:
    """Missing or unplayable WAVs, as readable lines. Empty means demo-ready."""
    out = []
    for event, spec in data["events"].items():
        for v in spec["variants"]:
            path = asset_path(event, v)
            if not path.exists():
                out.append(f"{event}/{v['id']}: missing {path.name}")
            elif not voice.valid_clip(str(path)):
                out.append(f"{event}/{v['id']}: {path.name} is not a playable wav")
    return out


# ---------- the narrator ----------

class Narrator:
    def __init__(self, catalog: dict | None = None, speaker=None, clock=time.monotonic,
                 seed: int | None = None):
        self.catalog = catalog or load_catalog()
        self._speaker = speaker
        self._clock = clock
        self._rng = random.Random(seed)
        self._lock = threading.RLock()
        self._last_variant: dict[str, str] = {}
        self._last_fired: dict[str, float] = {}
        self._fired: set[tuple] = set()
        self.events: list[dict] = []
        self._seen: dict | None = None

    @property
    def speaker(self):
        return self._speaker or voice.speaker()

    # ---------- explicit events ----------

    def emit(self, event: str, case_no: int | None = None, key=None, dynamic: str = "",
             tag: str | None = None, on_done=None) -> bool:
        """Queue the line for an event if its rules allow it. True if queued."""
        spec = self.catalog["events"].get(event)
        if spec is None:
            log.warning("narrator: no line for event %r", event)
            return False
        if spec.get("requires") and not AVAILABLE.get(spec["requires"]):
            return False
        with self._lock:
            now = self._clock()
            scope = spec["scope"]
            once = {"case": (event, case_no), "exhibit": (event, case_no, key),
                    "threshold": (event, case_no, key)}.get(scope)
            if once is not None and once in self._fired:
                return False
            last = self._last_fired.get(event)
            if spec["cooldown_s"] and last is not None and now - last < spec["cooldown_s"]:
                return False
            variants = [v for v in spec["variants"] if tag is None or v.get("tag") == tag] or spec["variants"]
            choices = [v for v in variants if v["id"] != self._last_variant.get(event)] or variants
            pick = self._rng.choice(choices)
            if once is not None:
                self._fired.add(once)
            self._last_fired[event] = now
            self._last_variant[event] = pick["id"]
            self.events.append({"event": event, "variant": pick["id"], "case_no": case_no,
                                "key": key, "at": now})
            del self.events[:-50]
        parts = [("clip", str(asset_path(event, pick)))]
        words = [pick["text"]]
        if spec["kind"] == "intro" and dynamic:
            parts.append(("say", dynamic))
            words.append(dynamic)
        return self.speaker.submit(voice.Utterance(
            event, parts, words, priority=spec["priority"], case_no=case_no,
            ttl_s=spec["expire_s"], coalesce=spec.get("coalesce"),
            on_done=on_done))

    # ---------- transitions from the case ----------

    def prime(self, store) -> None:
        """Learn the room as it stands, saying nothing: a restart mid-case
        must not re-announce what was filed before it."""
        snap = store.snapshot()
        plan = None
        if snap.get("mode") == "mastermind":
            from rig import mastermind
            plan = mastermind.current(store, snap)
        with self._lock:
            self._seen = self._state(snap, plan, lost_since=None, lost_said=False)

    def observe(self, store, plan: dict | None = None) -> list[str]:
        """Diff the case against the last look and narrate what changed.
        Returns the events emitted (for tests and logs)."""
        snap = store.snapshot()
        if plan is None and snap.get("mode") == "mastermind":
            from rig import mastermind
            plan = mastermind.current(store, snap)
        with self._lock:
            return self._observe(snap, plan)

    def _observe(self, snap: dict, plan: dict | None) -> list[str]:
        fired: list[str] = []
        case_no = snap["case_no"]
        items = snap["items"]
        loot = [it for it in items if (it.get("category") or "").lower() != "exit"]
        prev = self._seen
        if prev is None:
            # First look: learn the room, say nothing. A restart mid-case must
            # not re-announce exhibits that were filed before it.
            self._seen = self._state(snap, plan, lost_since=None, lost_said=False)
            return fired

        def say(event, **kw):
            if self.emit(event, case_no=case_no, **kw):
                fired.append(event)

        if case_no != prev["case_no"]:
            self.speaker.drop_case_before(case_no)
            if prev["revealed"]:
                say("case_closed")
            prev = self._state({**snap, "items": [], "take": 0, "revealed": False}, None,
                               lost_since=prev["lost_since"], lost_said=prev["lost_said"])

        if snap["revealed"] and not prev["revealed"]:
            say("reveal" if loot else "empty_reveal")
        elif not snap["revealed"]:
            known = prev["ns"]
            fresh = [it for it in items if it["n"] not in known]
            top5 = {it["n"] for it in sorted(loot, key=lambda it: (-it["value_usd"], it["n"]))[:5]}
            for it in fresh:
                if (it.get("category") or "").lower() == "exit":
                    continue
                line = f"{it['item']}. {it['value_usd']:,.0f} dollars."
                if not prev["loot_count"] and it is next((x for x in fresh if x in loot), None):
                    say("first_exhibit", dynamic=line)
                elif it["n"] in top5:
                    say("top5_entry", key=it["n"], dynamic=f"{it['item']}. Top five. {it['value_usd']:,.0f} dollars.")
            crossed = [m for m in milestones() if prev["take"] < m <= snap["take"]]
            if crossed:
                say("value_milestone", key=crossed[-1])

        # the camera: announce a loss only once it has held, and a return only after that
        now = self._clock()
        lost_since, lost_said = prev["lost_since"], prev["lost_said"]
        if not snap["camera_ok"]:
            lost_since = now if lost_since is None else lost_since
            if not lost_said and now - lost_since >= camera_debounce():
                say("camera_lost")
                lost_said = True
        else:
            if lost_said:
                say("camera_restored")
            lost_since, lost_said = None, False

        # the plan: a real revision, not a poll
        if plan and not snap["revealed"]:
            change = plan.get("change")
            # A swap, or new settings that actually moved the bag. Retuning the
            # clock without changing what's in the bag is not news.
            moved = change and (change["dropped"] or (change["settings_changed"] and change["added"]))
            if plan["revision"] != prev["plan_rev"] and moved:
                say("plan_revised", key=plan["revision"])
            stuck = bool(loot) and not plan["selected"]
            if stuck and not prev["plan_stuck"]:
                say("no_feasible_plan")
            clock = plan["constraints"]["time_s"]
            low = clock > 0 and plan["totals"]["grab_seconds"] >= TIME_LOW * clock
            if low and not prev["plan_low"]:
                say("scenario_time_low", key=plan["revision"])

        self._seen = self._state(snap, plan, lost_since=lost_since, lost_said=lost_said)
        return fired

    @staticmethod
    def _state(snap, plan, lost_since, lost_said) -> dict:
        loot = [it for it in snap["items"] if (it.get("category") or "").lower() != "exit"]
        clock = plan["constraints"]["time_s"] if plan else 0
        return {
            "case_no": snap["case_no"], "revealed": snap["revealed"], "take": snap["take"],
            "ns": {it["n"] for it in snap["items"]}, "loot_count": len(loot),
            "lost_since": lost_since, "lost_said": lost_said,
            "plan_rev": plan["revision"] if plan else None,
            "plan_stuck": bool(plan) and bool(loot) and not plan["selected"],
            "plan_low": bool(plan) and clock > 0 and plan["totals"]["grab_seconds"] >= TIME_LOW * clock,
        }


_narrator: Narrator | None = None
_narrator_lock = threading.Lock()


def narrator() -> Narrator:
    global _narrator
    with _narrator_lock:
        if _narrator is None:
            _narrator = Narrator()
        return _narrator


def set_narrator(n: Narrator | None) -> None:
    global _narrator
    with _narrator_lock:
        _narrator = n


def observe(store) -> None:
    """Call after any accepted change. Never raises into the scan loop."""
    try:
        narrator().observe(store)
    except Exception:
        log.warning("narrator observe failed", exc_info=True)


def emit(event: str, **kw) -> bool:
    try:
        return narrator().emit(event, **kw)
    except Exception:
        log.warning("narrator emit failed", exc_info=True)
        return False


# ---------- building the bundled audio ----------

TARGET_RATE = 22050


def _finish_wav(src: Path, dest: Path) -> float:
    """Mono 16-bit 22.05 kHz, silence trimmed, -20 dBFS RMS with a -1 dBFS peak. Returns seconds."""
    import subprocess
    import wave

    import numpy as np
    tmp = dest.with_suffix(".tmp.wav")
    # afconvert (macOS) resamples cleanly; any other source is assumed to be the target format.
    if src.suffix.lower() != ".wav" or _rate(src) != TARGET_RATE:
        subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{TARGET_RATE}", "-c", "1", str(src), str(tmp)],
                       check=True)
        src = tmp
    with wave.open(str(src), "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1)
    loud = np.flatnonzero(np.abs(pcm) > 0.01)
    if loud.size:
        pad = int(0.06 * TARGET_RATE)
        pcm = pcm[max(0, loud[0] - pad): loud[-1] + pad]
    rms = float(np.sqrt(np.mean(pcm ** 2))) or 1e-9
    pcm = pcm * (10 ** (-20 / 20) / rms)
    peak = float(np.max(np.abs(pcm))) or 1e-9
    ceiling = 10 ** (-1 / 20)
    if peak > ceiling:
        pcm = pcm * (ceiling / peak)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(TARGET_RATE)
        out.writeframes((pcm * 32767).astype(np.int16).tobytes())
    tmp.unlink(missing_ok=True)
    return len(pcm) / TARGET_RATE


def _rate(path: Path) -> int:
    import wave
    try:
        with wave.open(str(path), "rb") as w:
            return w.getframerate()
    except Exception:
        return 0


def build(provider: str = "auto", only: str | None = None, local_voice: str = "Daniel") -> list[str]:
    """Generate every catalog line's WAV and record its provenance. Not run at startup."""
    import subprocess
    import tempfile
    from datetime import date
    data = json.loads(LINES.read_text())
    if provider == "auto":
        provider = "openai" if config.env_str("OPENAI_API_KEY") else "say"
    made = []
    for event, spec in data["events"].items():
        if only and event != only:
            continue
        for v in spec["variants"]:
            dest = asset_path(event, v)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                raw = Path(tmpdir) / "raw.aiff"
                if provider == "openai":
                    from openai import OpenAI
                    model, voice_name = config.env_str("TTS_MODEL", "tts-1"), config.env_str("TTS_VOICE", "onyx")
                    raw = raw.with_suffix(".wav")
                    raw.write_bytes(OpenAI(timeout=30).audio.speech.create(
                        model=model, voice=voice_name, input=v["text"], response_format="wav").read())
                    source = f"OpenAI TTS {model}, voice {voice_name}"
                else:
                    subprocess.run(["say", "-v", local_voice, "-r", "165", "-o", str(raw), v["text"]], check=True)
                    source = f"macOS say, voice {local_voice}, rate 165"
                secs = _finish_wav(raw, dest)
            v["provenance"] = f"{source}; generated {date.today().isoformat()}; {secs:.2f}s"
            made.append(f"{event}/{v['id']}: {secs:.2f}s")
    LINES.write_text(json.dumps(data, indent=2) + "\n")
    return made


def _main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.WARNING)
    cmd = argv[0] if argv else "check"
    if cmd == "build":
        provider = argv[1] if len(argv) > 1 else "auto"
        for line in build(provider):
            print(line)
        return 0
    data = load_catalog()
    missing = check_assets(data)
    for event, spec in data["events"].items():
        gate = f"  [needs {spec['requires']}: {'on' if AVAILABLE.get(spec['requires']) else 'off'}]" if spec.get("requires") else ""
        print(f"{event:18} p{spec['priority']:<3} {spec['scope']:9} {len(spec['variants'])} line(s){gate}")
    for problem in missing:
        print("PROBLEM", problem)
    print("narrator catalog OK" if not missing else f"{len(missing)} asset problem(s)")
    return 1 if missing else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
