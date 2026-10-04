"""The narrator's mouth: one bounded queue, one speaker, one playback ladder.

Every line the rig says goes through a single Speaker: a priority queue with
one worker thread, so two lines never talk over each other and a burst of
flavor lines can't pile up threads. The highest priority goes first (the
reveal and radio answers outrank commentary); a full queue drops its least
important line, not the reveal; a line past its expiry, or from a case that
has since closed, is dropped before it plays; a newer line with the same
coalesce key replaces the older one still waiting (only the newest plan
revision is worth hearing).

An utterance is a list of parts. A "clip" part is a bundled WAV with its
exact transcript; a "say" part is dynamic text (an item name, a price, a
radio answer). Playback ladder, per part:
    clip: the WAV -> if missing/corrupt/unplayable, speak its transcript
    say:  cached TTS for this exact text and voice -> OpenAI TTS (cached)
          -> the local voice (macOS `say`, else pyttsx3) -> transcript only
A clip that played is never spoken again through TTS, and nothing plays
twice. RIG_VOICE=0 or NARRATOR_VOLUME=0 keeps the queue and the transcript
but makes no sound, so the desk still shows every line.

The hub's speaker is the only narrator output: browsers show transcripts,
they don't play narration, so ten open tabs can't make ten narrators.
"""
from __future__ import annotations

import hashlib
import heapq
import itertools
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from rig import config

log = logging.getLogger("rig.voice")

CLIPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice")
QUEUE_MAX = 6
TRANSCRIPT_MAX = 40
CACHE_MAX = 64


def enabled() -> bool:
    return config.env_flag("RIG_VOICE", True) and volume() > 0


def volume() -> int:
    """NARRATOR_VOLUME, 0-100. 0 is mute."""
    return config.env_int("NARRATOR_VOLUME", 100, lo=0, hi=100)


@dataclass
class Utterance:
    event: str
    parts: list[tuple[str, str]]          # ("clip", path) or ("say", text), with transcripts below
    transcripts: list[str]
    priority: int = 30
    case_no: int | None = None
    expires_at: float | None = None       # on the speaker's clock; prefer ttl_s
    ttl_s: float | None = None            # seconds it stays worth saying, from submit()
    coalesce: str | None = None
    on_done: object = None                # callable(state) once it is spoken, muted, or dropped
    created: float = 0.0
    seq: int = 0
    state: str = "queued"
    detail: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(t for t in self.transcripts if t).strip()


class Speaker:
    """The single narrator output. Tests build one with autostart=False and a
    fake clock and call drain(); the hub runs one daemon worker."""

    def __init__(self, clock=time.monotonic, player=None, tts=None, maxlen: int = QUEUE_MAX,
                 autostart: bool = True):
        self._clock = clock
        self._play = player or play_wav
        self._tts = tts or speak_text
        self._maxlen = maxlen
        self._heap: list[tuple[int, int, Utterance]] = []
        self._cond = threading.Condition()
        self._seq = itertools.count(1)
        self._current: Utterance | None = None
        self._min_case = 0
        self.transcript: deque[dict] = deque(maxlen=TRANSCRIPT_MAX)
        self._thread = None
        if autostart:
            self._thread = threading.Thread(target=self._loop, name="narrator", daemon=True)
            self._thread.start()

    # ---------- queueing ----------

    def submit(self, utt: Utterance) -> bool:
        """Queue a line. False if it was refused (stale case, or a full queue
        of more important lines)."""
        with self._cond:
            utt.created = self._clock()
            utt.seq = next(self._seq)
            if utt.ttl_s is not None and utt.expires_at is None:
                # Stamped here, on the clock _next() checks it against: a
                # caller's clock (another monotonic, a test's) can't skew it.
                utt.expires_at = utt.created + utt.ttl_s
            if utt.case_no is not None and utt.case_no < self._min_case:
                self._finish(utt, "cancelled")
                return False
            if utt.coalesce:
                for _, _, old in list(self._heap):
                    if old.coalesce == utt.coalesce:
                        self._remove(old, "superseded")
            if len(self._heap) >= self._maxlen:
                weakest = max(self._heap, key=lambda e: (-e[2].priority, e[2].seq))[2]
                if weakest.priority >= utt.priority:
                    self._finish(utt, "dropped")
                    return False
                self._remove(weakest, "dropped")
            heapq.heappush(self._heap, (-utt.priority, utt.seq, utt))
            self._cond.notify()
            return True

    def drop_case_before(self, case_no: int) -> None:
        """A new case opened: nothing queued for an older one may play."""
        with self._cond:
            self._min_case = max(self._min_case, case_no)
            for _, _, old in list(self._heap):
                if old.case_no is not None and old.case_no < case_no:
                    self._remove(old, "cancelled")

    def depth(self) -> int:
        with self._cond:
            return len(self._heap)

    def busy(self) -> bool:
        with self._cond:
            return self._current is not None or bool(self._heap)

    def _remove(self, utt: Utterance, state: str) -> None:
        self._heap = [e for e in self._heap if e[2] is not utt]
        heapq.heapify(self._heap)
        self._finish(utt, state)

    # ---------- playing ----------

    def _next(self) -> Utterance | None:
        """Pop the best line still worth saying. Caller holds the lock."""
        while self._heap:
            _, _, utt = heapq.heappop(self._heap)
            if utt.expires_at is not None and self._clock() > utt.expires_at:
                self._finish(utt, "expired")
                continue
            if utt.case_no is not None and utt.case_no < self._min_case:
                self._finish(utt, "cancelled")
                continue
            return utt
        return None

    def drain(self) -> int:
        """Say everything queued, in order, on this thread. Returns lines handled."""
        handled = 0
        while True:
            with self._cond:
                utt = self._next()
                self._current = utt
            if utt is None:
                return handled
            self._say(utt)
            handled += 1

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._heap:
                    self._cond.wait()
                utt = self._next()
                self._current = utt
            if utt is not None:
                self._say(utt)

    def _say(self, utt: Utterance) -> None:
        started = self._clock()
        utt.detail["latency_ms"] = round((started - utt.created) * 1000)
        if not enabled():
            state = "muted"
        else:
            audible = 0
            for (kind, value), words in zip(utt.parts, utt.transcripts, strict=True):
                try:
                    if kind == "clip" and valid_clip(value) and self._play(value):
                        audible += 1
                    elif words and self._tts(words):
                        audible += 1
                except Exception:
                    log.warning("narrator part failed; moving on", exc_info=True)
            state = "played" if audible == len(utt.parts) else ("partial" if audible else "text-only")
        with self._cond:
            self._current = None
            self._finish(utt, state)

    def _finish(self, utt: Utterance, state: str) -> None:
        utt.state = state
        self.transcript.appendleft({
            "event": utt.event, "text": utt.text, "state": state, "case_no": utt.case_no,
            "priority": utt.priority, "at": time.time(), **utt.detail,
        })
        log.info("narrator [%s] %s: %s", state, utt.event, utt.text)
        if callable(utt.on_done):
            try:
                utt.on_done(state)
            except Exception:
                log.warning("narrator callback failed", exc_info=True)


# ---------- the process-wide speaker ----------

_speaker: Speaker | None = None
_speaker_lock = threading.Lock()


def speaker() -> Speaker:
    global _speaker
    with _speaker_lock:
        if _speaker is None:
            _speaker = Speaker()
        return _speaker


def set_speaker(sp: Speaker) -> None:
    """Tests swap in a fake-clock speaker."""
    global _speaker
    with _speaker_lock:
        _speaker = sp


def announce(text: str, clip: str | None = None, clip_text: str = "", priority: int = 60,
             case_no: int | None = None) -> None:
    """Old call shape, same queue: an optional clip by name, then text."""
    parts, words = [], []
    if clip:
        parts.append(("clip", os.path.join(CLIPS, clip + ".wav")))
        words.append(clip_text)
    elif clip_text:
        text = f"{clip_text} {text}".strip()
    if text:
        parts.append(("say", text))
        words.append(text)
    if parts:
        speaker().submit(Utterance("announce", parts, words, priority=priority, case_no=case_no))


def announce_top5(item_name: str, price: float) -> None:
    announce(f"{item_name}. Top five. {price:,.0f} dollars.", clip_text="Alert.", priority=30)


# ---------- clips and playback ----------

_valid: dict[str, tuple[float, bool]] = {}


def valid_clip(path: str) -> bool:
    """A readable PCM WAV with frames in it. Cached per file version."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False
    hit = _valid.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with wave.open(path, "rb") as w:
            ok = w.getnframes() > 0 and w.getsampwidth() in (1, 2) and w.getnchannels() in (1, 2)
    except (wave.Error, EOFError, OSError):
        ok = False
    if not ok:
        log.warning("narrator clip %s is not a playable wav", path)
    _valid[path] = (mtime, ok)
    return ok


def _scaled(path: str, vol: int) -> str:
    """A copy of the wav at vol percent, for players with no volume flag."""
    import numpy as np
    with wave.open(path, "rb") as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    if params.sampwidth != 2:
        return path
    pcm = (np.frombuffer(frames, np.int16).astype(np.float32) * (vol / 100)).astype(np.int16)
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="rig-vol-")
    os.close(fd)
    with wave.open(tmp, "wb") as out:
        out.setparams(params)
        out.writeframes(pcm.tobytes())
    return tmp


def play_wav(path: str) -> bool:
    """Play a wav on the hub's speaker and block until it ends. False on any failure."""
    vol = volume()
    try:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return True
        if sys.platform == "darwin" and shutil.which("afplay"):
            cmd = ["afplay", "-v", f"{vol / 100:.2f}", path]
            return subprocess.run(cmd, check=False, timeout=30).returncode == 0
        player = shutil.which("aplay") or shutil.which("paplay")
        if not player:
            return False
        src = _scaled(path, vol) if vol < 100 else path
        try:
            args = [player, "-q", src] if player.endswith("aplay") else [player, src]
            res = subprocess.run(args, check=False, timeout=30)
            if res.returncode != 0:
                log.warning("%s exited %s on %s", player, res.returncode, path)
            return res.returncode == 0
        finally:
            if src != path:
                try:
                    os.unlink(src)
                except OSError:
                    pass
    except Exception:
        log.warning("could not play %s", path, exc_info=True)
        return False


# ---------- dynamic speech ----------

_tts = None
_tts_failed = False


def cache_dir() -> Path:
    env = config.env_str("NARRATOR_CACHE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "state" / "tts-cache"


def _cache_path(text: str) -> Path:
    model, voice = config.env_str("TTS_MODEL", "tts-1"), config.env_str("TTS_VOICE", "onyx")
    digest = hashlib.sha256(f"openai|{model}|{voice}|{text}".encode()).hexdigest()[:24]
    return cache_dir() / f"{digest}.wav"


def _prune_cache() -> None:
    try:
        files = sorted(cache_dir().glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in files[CACHE_MAX:]:
        old.unlink(missing_ok=True)


def _openai_speak(text: str) -> bool:
    """Dispatch's radio voice: OpenAI TTS, cached by exact text + model + voice."""
    cached = _cache_path(text)
    if cached.exists() and valid_clip(str(cached)):
        os.utime(cached)
        return play_wav(str(cached))
    if not config.env_str("OPENAI_API_KEY"):
        return False
    try:
        from openai import OpenAI
        wav = OpenAI(timeout=15).audio.speech.create(
            model=config.env_str("TTS_MODEL", "tts-1"),
            voice=config.env_str("TTS_VOICE", "onyx"),
            input=text,
            response_format="wav",
        ).read()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(wav)
        _prune_cache()
        return play_wav(str(cached))
    except Exception:
        log.warning("openai tts failed; falling back to local", exc_info=True)
        return False


def _local_speak(text: str) -> bool:
    global _tts, _tts_failed
    if sys.platform == "darwin" and shutil.which("say"):
        voice = config.env_str("NARRATOR_LOCAL_VOICE", "Daniel")
        try:
            return subprocess.run(["say", "-v", voice, "-r", "170", text], check=False,
                                  timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    if _tts_failed:
        return False
    try:
        if _tts is None:
            import pyttsx3
            _tts = pyttsx3.init()
            _tts.setProperty("rate", 145)
        _tts.say(text)
        _tts.runAndWait()
        return True
    except Exception:
        _tts_failed = True
        _tts = None
        return False


def speak_text(text: str) -> bool:
    """Dynamic speech down the ladder. False means it stayed text-only."""
    return _openai_speak(text) or _local_speak(text)
