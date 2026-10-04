"""Bring-up journal: one log that tracks integration progress and records
every hardware/software issue while the rig is glued together.

What it does, all stdlib:

* **File + console.** `setup()` attaches a `RotatingFileHandler` next to the
  case file (`rig/state/logs/rig.log`, 5 MB x 3) alongside the usual console
  output, so systemd/journald keeps working and a persistent file survives
  restarts for after-the-fact triage.
* **Levels from env.** `RIG_LOG_LEVEL=DEBUG` gets the chatter; default INFO.
* **Hardware events.** `event(component, ok, detail)` logs a state transition
  once per change — `HW camera up`, `HW wrist down (last seen 42s ago)` —
  instead of spamming every poll. This is the progress trail: a boot that
  comes up clean prints a short ordered list of `up`s; anything that flaps
  shows up as alternating transitions with timestamps.
* **Machine-readable option.** `RIG_LOG_JSON=1` writes one JSON object per
  line for grepping/feeding elsewhere.

CLI: `python -m rig.journal [-n 50] [-f] [--errors]` tails the current log,
like `journalctl -f` but local.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
import time
from pathlib import Path

from rig import config

_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 3


def _log_dir() -> Path:
    env = config.env_str("RIG_LOG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "state" / "logs"


def _log_file() -> Path:
    return _log_dir() / "rig.log"

_hw = logging.getLogger("rig.hw")
_states: dict[str, bool] = {}
_states_lock = threading.Lock()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            out["exc"] = record.exc_text
        return json.dumps(out)


def setup(level: str | None = None) -> Path:
    """Attach console + rotating file handlers to the root logger. Idempotent —
    safe to call from main() and from tests/diag tools. Returns the log path."""
    log_file = _log_file()
    root = logging.getLogger()
    if getattr(setup, "_done", False):
        return log_file
    setup._done = True

    level_name = (level or config.env_str("RIG_LOG_LEVEL", "INFO")).upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    if config.env_flag("RIG_LOG_JSON", False):
        fmt: logging.Formatter = _JsonFormatter()
    else:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        _log_dir().mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUPS)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        # Read-only/deployed FS: console-only still logs fine.
        root.warning("journal: %s not writable; logging to console only", _log_dir())
    return log_file


def event(component: str, ok: bool, detail: str = "") -> None:
    """Record a hardware/software component going up or down. Logs only on a
    state CHANGE (first observation counts), so a healthy heartbeat is silent
    and a flapping device is loud. `ok=None`-style detail-only notes use
    `note()` instead."""
    with _states_lock:
        prev = _states.get(component)
        if prev is not None and prev == ok:
            return
        _states[component] = ok
    tag = f" ({detail})" if detail else ""
    if ok:
        _hw.info("%s up%s", component, tag)
    else:
        _hw.warning("%s down%s", component, tag)


def note(component: str, detail: str) -> None:
    """One-off hardware/software observation that isn't an up/down transition —
    a diag result, a retry count, a quirk worth remembering at triage time."""
    _hw.info("%s: %s", component, detail)


def state(component: str) -> bool | None:
    """Last recorded up/down for a component, None if never observed."""
    with _states_lock:
        return _states.get(component)


def _reset_for_tests() -> None:
    with _states_lock:
        _states.clear()


# ---------- CLI: tail the journal ----------


def _iter_lines(n: int):
    try:
        lines = _log_file().read_text(errors="replace").splitlines()
    except OSError:
        print(f"no journal yet ({_log_file()})")
        return
    yield from lines[-n:] if n else lines


def main(argv: list[str] | None = None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="rig.journal", description="Tail the bring-up log")
    p.add_argument("-n", type=int, default=50, help="lines to show (0 = all)")
    p.add_argument("-f", "--follow", action="store_true")
    p.add_argument("--errors", action="store_true", help="WARNING and above only")
    p.add_argument("--hw", action="store_true", help="hardware events only")
    args = p.parse_args(argv)

    err_marks = ("WARNING", "ERROR", "CRITICAL",
                 '"level": "WARNING"', '"level": "ERROR"', '"level": "CRITICAL"')

    def want(line: str) -> bool:
        if args.errors and not any(m in line for m in err_marks):
            return False
        if args.hw and "rig.hw" not in line:
            return False
        return True

    for line in _iter_lines(args.n):
        if want(line):
            print(line)
    if args.follow:
        try:
            with _log_file().open(errors="replace") as fh:
                fh.seek(0, 2)
                while True:
                    line = fh.readline()
                    if line:
                        if want(line.rstrip()):
                            print(line, end="")
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main(sys.argv[1:])
