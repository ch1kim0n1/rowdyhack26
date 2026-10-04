"""The radio's ears: mic press -> a few seconds of audio -> Whisper -> text.

The mic button (GPIO27, the dashboard's R, or Enter here) opens a radio call
(rig/radio.py), which records through record_wav(), transcribes through
transcribe(), deletes the recording, and answers from the live plan. No
model invents the answer; Whisper only turns speech into text.

No key, no ears: with no OPENAI_API_KEY the call fails visibly and dispatch
says the radio's dead.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

from rig import config

log = logging.getLogger("rig.listen")

WHISPER_MODEL = "whisper-1"
LLM_TIMEOUT = 20

_openai = None


def listen_secs() -> float:
    """Mic press records this long. LISTEN_SECS tunes it on site."""
    return config.env_float("LISTEN_SECS", 4.0, lo=1.0, hi=15.0)


def _openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI(timeout=LLM_TIMEOUT)
    return _openai


def _record_wav(seconds: float) -> str | None:
    """A few seconds of mic audio as a wav. arecord on the Pi, sox elsewhere."""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="rig-mic-")
    os.close(fd)
    cmds = [
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(int(seconds)), path],
        ["rec", "-q", "-r", "16000", "-c", "1", path, "trim", "0", str(seconds)],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, timeout=seconds + 5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.getsize(path) > 100:
                return path
        except (OSError, subprocess.SubprocessError):
            continue
    try:
        os.unlink(path)
    except OSError:
        pass
    return None


def _transcribe(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            resp = _openai_client().audio.transcriptions.create(
                model=config.env_str("WHISPER_MODEL", WHISPER_MODEL), file=fh)
        return (resp.text or "").strip() or None
    except Exception:
        log.warning("mic transcription failed", exc_info=True)
        return None


def record_wav(seconds: float) -> str | None:
    return _record_wav(seconds)


def transcribe(path: str) -> str | None:
    return _transcribe(path)


def discard(path: str) -> None:
    """Recordings live only as long as their transcription."""
    try:
        os.unlink(path)
    except OSError:
        pass


def ask_evac(store, started: float | None = None) -> None:
    """The mic button, GPIO27 or the dashboard's R: a radio call. Fire and
    forget; the call's progress shows on the desk."""
    from rig import radio
    radio.radio(lambda: store).submit("mic")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from rig.store import Store
    print("press Enter to radio dispatch (Ctrl+C to quit)")
    try:
        while True:
            input()
            ask_evac(Store())
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
