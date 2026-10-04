"""Dedup, the running take, and the snapshot /state.json is built from.

One lock covers the list. Flask reads it, the scan thread writes it.
The ledger is mirrored to a JSON file on every change, so a crash or a
restart reopens the same case instead of losing the take. Exhibits keep
their still as JPEG bytes, not raw frames, so a long walk cannot eat the Pi.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from rapidfuzz import fuzz

from rig import config
from rig.planner import clean_weight

log = logging.getLogger("rig.store")

CASE_START = 1138


def jpeg_quality() -> int:
    """Exhibit still quality. JPEG_QUALITY trades size for legibility."""
    return config.env_int("JPEG_QUALITY", 85, lo=30, hi=100)


def default_state_path() -> Path:
    env = config.env_str("RIG_STATE_FILE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "state" / "case.json"


def _clean_value(raw) -> float:
    """One gate for every value_usd: write path AND reload path. NaN/inf
    would poison every JSON response and re-persist into case.json."""
    try:
        v = round(float(raw or 0), 2)
    except (TypeError, ValueError):
        return 0.0
    # NaN/inf poison JSON; a negative "price" just drains the take.
    return max(0.0, v) if math.isfinite(v) else 0.0


def max_exhibits() -> int:
    """Ledger cap: every exhibit holds its JPEG still in memory, so a hostile
    LAN spamming /api/exhibit must not eat the Pi. MAX_EXHIBITS tunes it."""
    return config.env_int("MAX_EXHIBITS", 500, lo=10)


# A digit run long enough to be a card number, printed packed or grouped.
_DIGIT_RUN = re.compile(r"\d(?:[ .-]?\d){12,}")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def _is_payment_number(d: str) -> bool:
    """A real payment-card number: network prefix, its length, and a Luhn pass.

    School and employee IDs carry long numbers too (library barcodes, campus
    card numbers); those are public and must file, so length alone is not enough."""
    n = len(d)
    if not 13 <= n <= 19 or not _luhn(d):
        return False
    if d[0] == "4":                                               # Visa
        return n in (13, 16, 19)
    if d[:2] in ("34", "37"):                                     # Amex
        return n == 15
    if 51 <= int(d[:2]) <= 55 or 2221 <= int(d[:4]) <= 2720:      # Mastercard
        return n == 16
    return n >= 16 and (d.startswith(("6011", "65"))              # Discover
                        or 644 <= int(d[:3]) <= 649
                        or 622126 <= int(d[:6]) <= 622925)


def _payment_span(digits: str) -> tuple[int, int] | None:
    """(start, length) of a payment-card number inside a digit run, if any."""
    if len(digits) <= 19:
        return (0, len(digits)) if _is_payment_number(digits) else None
    for size in range(13, 20):   # a card number run into other digits
        for i in range(len(digits) - size + 1):
            if _is_payment_number(digits[i:i + size]):
                return i, size
    return None


def has_pan(text) -> bool:
    """True if the text carries a payment-card number."""
    return isinstance(text, str) and any(
        _payment_span(re.sub(r"\D", "", m.group())) for m in _DIGIT_RUN.finditer(text))


def scrub_pan(text: str) -> str:
    """Mask a payment-card number down to its last four; every other number stays."""
    def mask(m):
        run = m.group()
        where = [i for i, ch in enumerate(run) if ch.isdigit()]
        span = _payment_span("".join(run[i] for i in where))
        if not span:
            return run
        first, last = where[span[0]], where[span[0] + span[1] - 1]
        tail = "".join(run[i] for i in where[span[0] + span[1] - 4:span[0] + span[1]])
        return run[:first] + "****" + tail + run[last + 1:]
    return _DIGIT_RUN.sub(mask, text) if isinstance(text, str) else text


# What a badge or school ID prints. A UT Dallas Comet Card puts name, role,
# and "UTD ID#" on the front, and a card number plus issue date on the back.
CARD_FIELDS = ("name", "id", "org", "role", "card_no", "issued", "expires")
# Numbers that pin one physical card: a match on either is the same card.
CARD_KEYS = ("id", "card_no")


def clean_card(raw) -> dict | None:
    """Card text: known fields only, 60 chars each, payment numbers masked.

    One gate for the model's answer, rover POSTs, and the reload path. A
    numeric ID (the model sometimes drops the quotes) is kept as text."""
    if not isinstance(raw, dict):
        return None
    card = {}
    for key in CARD_FIELDS:
        val = raw.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            val = str(int(val)) if float(val).is_integer() else str(val)
        if isinstance(val, str) and val.strip():
            card[key] = scrub_pan(val.strip())[:60]
    return card or None


# An exhibit's place in a Mastermind job: the plan decides "available" ones;
# "collected" are in the bag for real; "excluded" the crew ruled out.
STATUSES = ("available", "collected", "excluded")


def _tag(raw, default: str = "unknown") -> str:
    """Provenance tags (who identified it, what priced it): short slugs only,
    so a hostile POST can't smuggle markup or paths into a report."""
    tag = str(raw or "").strip().lower()[:24]
    return tag if re.fullmatch(r"[a-z0-9_-]+", tag) else default


def _clean_bbox(raw):
    """bbox is [x,y,w,h] of finite floats or nothing, never persisted junk."""
    try:
        bbox = [float(v) for v in raw] if raw else None
    except (TypeError, ValueError):
        return None
    if not (bbox and len(bbox) == 4 and all(math.isfinite(v) for v in bbox)):
        return None
    return bbox


def _encode_still(frame) -> bytes | None:
    """JPEG bytes for a still. Frames arrive as numpy; crops arrive as bytes."""
    if frame is None:
        return None
    if isinstance(frame, (bytes, bytearray)):
        return bytes(frame)
    try:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality()])
        return buf.tobytes() if ok else None
    except Exception:
        log.warning("could not encode exhibit still", exc_info=True)
        return None


class Store:
    def __init__(self, path: Path | None = None):
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._jpeg: bytes | None = None
        self._frame_id = 0
        self._camera_ok = True
        self._pending = False
        self._revealed = False
        self._case_no = CASE_START
        self._report_id: str | None = None
        # The job: "appraisal" (scan anything) or "mastermind" (plan a haul).
        # Survives a reset: the crew sets it up once, not every case.
        self._mode = "appraisal"
        self._plan_settings: dict | None = None
        self._path = Path(path) if path is not None else default_state_path()
        self._last_saved: float | None = None
        # The ledger lock never wraps disk: writers build a payload under
        # _lock, then queue the actual write on _save_lock, ordered by seq so
        # a slow older payload can never overwrite a newer one.
        self._save_lock = threading.Lock()
        self._save_seq = 0
        self._written_seq = 0
        self._load()

    def state_path(self) -> Path:
        return self._path

    def last_saved(self) -> float | None:
        return self._last_saved

    def _still_path(self, n: int) -> Path:
        return self._path.parent / f"{self._path.stem}-stills" / f"still-{n}.jpg"

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            log.warning("case file %s is unreadable; starting fresh", self._path, exc_info=True)
            return
        self._case_no = int(data.get("case_no") or CASE_START)
        self._revealed = bool(data.get("revealed"))
        self._report_id = data.get("report_id") if isinstance(data.get("report_id"), str) else None
        if data.get("mode") in {"appraisal", "mastermind"}:
            self._mode = data["mode"]
        if isinstance(data.get("plan_settings"), dict):
            self._plan_settings = dict(data["plan_settings"])
        for row in data.get("items") or []:
            try:
                n = int(row["n"])
                try:
                    still = self._still_path(n).read_bytes()
                except OSError:
                    still = None
                self._items.append({
                    "n": n,
                    "item": scrub_pan(str(row["item"])),
                    "desc": scrub_pan(str(row.get("desc") or "")),
                    "category": str(row.get("category") or ""),
                    "value_usd": _clean_value(row.get("value_usd")),
                    "estimated": bool(row.get("estimated")),
                    "bbox": _clean_bbox(row.get("bbox")),
                    "why": scrub_pan(str(row.get("why") or "")),
                    "origin": str(row.get("origin") or "hat"),
                    "card": clean_card(row.get("card")),
                    "source": _tag(row.get("source")),
                    "price_source": _tag(row.get("price_source")),
                    "weight_lb": clean_weight(row.get("weight_lb")),
                    "status": row.get("status") if row.get("status") in STATUSES else "available",
                    "frame_jpeg": still,
                })
            except (KeyError, TypeError, ValueError):
                log.warning("skipped a malformed saved exhibit: %r", row)
        if self._items:
            log.info("reopened case %s with %s exhibit(s) from %s",
                     self._case_no, len(self._items), self._path)

    def _payload_locked(self) -> tuple[dict, int]:
        """Serialize the case under _lock; the write happens after release."""
        rows = [{
            "n": it["n"],
            "item": it["item"],
            "desc": it["desc"],
            "category": it["category"],
            "value_usd": it["value_usd"],
            "estimated": it["estimated"],
            "bbox": it["bbox"],
            "why": it.get("why") or "",
            "origin": it.get("origin") or "hat",
            "card": it.get("card"),
            "source": it.get("source") or "unknown",
            "price_source": it.get("price_source") or "unknown",
            "weight_lb": it.get("weight_lb"),
            "status": it.get("status") or "available",
        } for it in self._items]
        self._save_seq += 1
        data = {"case_no": self._case_no, "revealed": self._revealed,
                "report_id": self._report_id, "mode": self._mode,
                "plan_settings": self._plan_settings, "items": rows}
        return data, self._save_seq

    def _write_state(self, data: dict, seq: int) -> None:
        """mkstemp+replace off the ledger lock: a slow SD card stalls this
        writer, never /state.json. A payload superseded before its write
        lands is dropped rather than let stale state win the rename race."""
        with self._save_lock:
            if seq <= self._written_seq:
                return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
                with os.fdopen(fd, "w") as fh:
                    json.dump(data, fh)
                os.replace(tmp, self._path)
                self._written_seq = seq
                self._last_saved = time.time()
            except OSError:
                log.warning("could not save the case to %s", self._path, exc_info=True)

    def _write_still(self, n: int, jpeg: bytes) -> None:
        try:
            path = self._still_path(n)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg)
        except OSError:
            log.warning("could not save the exhibit still", exc_info=True)

    def snapshot(self, marker_ttl: float | None = None) -> dict:
        """The case for the consoles. `marker_ttl` is how many seconds a fresh
        sighting keeps its bbox (the on-screen box); older exhibits stay in the
        tally and the ledger but lose the box. None keeps every box."""
        now = time.monotonic()
        with self._lock:
            items = []
            for it in self._items:
                row = {
                    "n": it["n"],
                    "item": it["item"],
                    "category": it.get("category") or "",
                    "weight_lb": it.get("weight_lb"),
                    "value_usd": it["value_usd"],
                    "estimated": it["estimated"],
                    "why": it.get("why") or "",
                    "origin": it.get("origin") or "hat",
                    "status": it.get("status") or "available",
                }
                fresh = marker_ttl is None or now - it.get("seen", float("-inf")) <= marker_ttl
                # With a marker lifetime, the box is where it was last sighted;
                # the filed bbox stays paired with the filed still for crops.
                box = (it.get("live_bbox") if marker_ttl is not None else None) or it.get("bbox")
                if box and fresh:
                    row["bbox"] = list(box)
                if it.get("card"):
                    row["card"] = dict(it["card"])
                items.append(row)
            return {
                "mode": self._mode,
                "frame_id": self._frame_id,
                "camera_ok": self._camera_ok,
                "pending": self._pending,
                "revealed": self._revealed,
                "take": round(sum(i["value_usd"] for i in self._items), 2),
                "case_no": self._case_no,
                "items": items,
            }

    def set_frame(self, jpeg: bytes) -> int:
        with self._lock:
            self._jpeg = jpeg
            self._frame_id += 1
            return self._frame_id

    def frame_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def camera_ok(self) -> bool:
        with self._lock:
            return self._camera_ok

    def set_camera(self, ok: bool) -> None:
        with self._lock:
            self._camera_ok = ok

    def set_pending(self, pending: bool) -> None:
        with self._lock:
            self._pending = pending

    @property
    def revealed(self) -> bool:
        with self._lock:
            return self._revealed

    def case_no(self) -> int:
        with self._lock:
            return self._case_no

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def take(self) -> float:
        with self._lock:
            return round(sum(i["value_usd"] for i in self._items), 2)

    def _rejects_locked(self, name: str, category: str, card: dict | None = None,
                        bbox: list | None = None) -> tuple[bool, tuple | None]:
        """Dedup + gates, with _lock held. Same object twice is not a new
        exhibit: fuzzy name, tighter when the category matches, so "laptop"
        and "MacBook" don't both count. Badges with a legible number dedup on
        it: same number is the same card — the other side's scan merges its
        fields in — and two numbers are two cards even off one issuer.

        Returns (rejected, save) where save is a (payload, seq) to write once
        _lock drops — a card merge mutates the ledger without adding a row."""
        if self._revealed or not name or len(self._items) >= max_exhibits():
            return True, None
        for existing in self._items:
            old_card = existing.get("card") or {}
            shared = [k for k in CARD_KEYS if (card or {}).get(k) and old_card.get(k)]
            if shared:
                if any(card[k].lower() == old_card[k].lower() for k in shared):
                    save = self._payload_locked() if self._merge_card_locked(existing, card) else None
                    return True, save
                continue
            score = fuzz.ratio(existing["item"].lower(), name.lower())
            # Exits dedup on name alone: "BACK DOOR" and "SIDE DOOR" are
            # different exits, but a tightened same-category rule would
            # collapse them at score > 55.
            same_cat = (existing.get("category") == category
                        and category not in {"", "exit"})
            if score > 85 or (same_cat and score > 55):
                if bbox:
                    # Seen again: not a new exhibit, but its box goes back up
                    # where it is now, so the crew can tell the camera knows it.
                    existing["live_bbox"] = bbox
                    existing["seen"] = time.monotonic()
                save = None
                if category == "badge" and self._merge_card_locked(existing, card):
                    save = self._payload_locked()
                return True, save
        return False, None

    def add_item(self, candidate: dict, frame=None) -> tuple[bool, bool]:
        """Append a new exhibit. Returns (added, now_in_top_five).

        Two passes: the cheap reject runs under the lock, the JPEG encode
        runs outside it (imencode is the slow part), then a re-check under
        the lock catches a reveal/reset that landed mid-encode.

        A payment-card number in any text field is masked to its last four,
        whoever sent it, so none reaches case.json or /state.json.
        """
        name = scrub_pan(str(candidate.get("item") or "").strip())
        category = candidate.get("category") or ""
        card = clean_card(candidate.get("card")) if category == "badge" else None
        with self._lock:
            rejected, save = self._rejects_locked(
                name, category, card, _clean_bbox(candidate.get("bbox")))
        if rejected:
            if save:
                self._write_state(*save)
            return False, False
        still = _encode_still(frame)
        with self._lock:
            rejected, save = self._rejects_locked(name, category, card)
            if not rejected:
                item = {
                    "n": len(self._items) + 1,
                    "item": name[:120],
                    "desc": scrub_pan(str(candidate.get("desc") or ""))[:300],
                    "category": str(category)[:60],
                    "value_usd": _clean_value(candidate.get("value_usd")),
                    "estimated": bool(candidate.get("estimated")),
                    "bbox": _clean_bbox(candidate.get("bbox")),
                    "why": scrub_pan(str(candidate.get("why") or ""))[:300],
                    "origin": str(candidate.get("origin") or "hat"),
                    "card": card,
                    "source": _tag(candidate.get("source")),
                    "price_source": _tag(candidate.get("price_source")),
                    "weight_lb": clean_weight(candidate.get("weight_lb")),
                    "status": "available",
                    "frame_jpeg": still,
                    # When it was sighted, for the live marker's lifetime. Not
                    # saved: a reopened case starts with no markers on screen.
                    "seen": time.monotonic(),
                }
                self._items.append(item)
                payload, seq = self._payload_locked()
                hot = any(top["n"] == item["n"] for top in self._top_locked())
        if rejected:
            if save:
                self._write_state(*save)
            return False, False
        if still:
            self._write_still(item["n"], still)
        self._write_state(payload, seq)
        return True, hot

    def _merge_card_locked(self, existing: dict, card: dict | None) -> bool:
        """Fill the filed card's blanks from another look at it. The longer
        name wins: the front prints the full name, the back a short one.
        True when the ledger actually changed (the caller persists it)."""
        if not card:
            return False
        merged = dict(existing.get("card") or {})
        for key, val in card.items():
            if not merged.get(key) or (key == "name" and len(val) > len(merged[key])):
                merged[key] = val
        if merged == existing.get("card"):
            return False
        existing["card"] = merged
        return True

    def _top_locked(self) -> list[dict]:
        return sorted(self._items, key=lambda it: it["value_usd"], reverse=True)[:5]

    def top_five(self) -> list[dict]:
        with self._lock:
            return [dict(it) for it in self._top_locked()]

    def item_frame(self, n: int):
        """The still an exhibit was found in, decoded, plus its bbox (maybe None)."""
        with self._lock:
            jpeg = next((it.get("frame_jpeg") for it in self._items if it["n"] == n), None)
            bbox = next((it.get("bbox") for it in self._items if it["n"] == n), None)
        if jpeg is None:
            return None, bbox
        arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        return (None if arr is None else arr), bbox

    def manifest_rows(self) -> list[dict]:
        with self._lock:
            rows = sorted(self._items, key=lambda it: it["value_usd"], reverse=True)
            return [
                {
                    "n": it["n"],
                    "item": it["item"],
                    "category": it.get("category") or "",
                    "value_usd": it["value_usd"],
                    "estimated": it["estimated"],
                    "why": it.get("why") or "",
                    "origin": it.get("origin") or "hat",
                }
                for it in rows
            ]

    def sealed_case(self) -> dict | None:
        """The revealed case, frozen for a report: every exhibit with its still
        bytes. None until the reveal (the ledger is still moving before it)."""
        with self._lock:
            if not self._revealed:
                return None
            return {
                "case_no": self._case_no,
                "report_id": self._report_id,
                "mode": self._mode,
                "plan_settings": dict(self._plan_settings) if self._plan_settings else None,
                "items": [dict(it) for it in self._items],
            }

    def mode(self) -> str:
        with self._lock:
            return self._mode

    def plan_settings(self) -> dict | None:
        with self._lock:
            return dict(self._plan_settings) if self._plan_settings else None

    def set_job(self, mode: str, settings: dict | None) -> bool:
        """Pick the job for this case. Refused once the lineup is up: the
        revealed case and its report are already filed under the old job."""
        with self._lock:
            if self._revealed:
                return False
            self._mode = mode
            if settings is not None:
                self._plan_settings = dict(settings)
            payload, seq = self._payload_locked()
        self._write_state(payload, seq)
        return True

    def set_status(self, n: int, status: str, case_no: int | None = None) -> bool:
        """Crew's call on one exhibit: available, collected, or excluded.
        Validation (mode, capacity, double-collect) lives in mastermind; this
        only refuses a revealed or moved-on case and an unknown exhibit."""
        if status not in STATUSES:
            return False
        with self._lock:
            if self._revealed or (case_no is not None and case_no != self._case_no):
                return False
            item = next((it for it in self._items if it["n"] == n), None)
            if item is None:
                return False
            item["status"] = status
            payload, seq = self._payload_locked()
        self._write_state(payload, seq)
        return True

    def report_id(self) -> str | None:
        with self._lock:
            return self._report_id if self._revealed else None

    def set_report_id(self, case_no: int, report_id: str) -> bool:
        """Pin the case's finalized report. Refused if the case moved on."""
        with self._lock:
            if not self._revealed or self._case_no != case_no:
                return False
            self._report_id = report_id
            payload, seq = self._payload_locked()
        self._write_state(payload, seq)
        return True

    def mark_revealed(self) -> bool:
        """First press. False if the lineup is already up."""
        with self._lock:
            if self._revealed:
                return False
            self._revealed = True
            self._pending = False
            payload, seq = self._payload_locked()
        self._write_state(payload, seq)
        return True

    def reset_case(self) -> bool:
        """Second press. Clears the ledger and drops the flag so the client plays THE END."""
        with self._lock:
            if not self._revealed:
                return False
            self._items.clear()
            self._revealed = False
            self._report_id = None
            self._pending = False
            self._case_no += 1
            stills = self._still_path(0).parent
            payload, seq = self._payload_locked()
        # Unlinks off the lock: an add_item still-write that lands here after
        # the clear can leave one orphan file; the next reset cleans it up.
        if stills.is_dir():
            try:
                for still in stills.glob("still-*.jpg"):
                    still.unlink(missing_ok=True)
                stills.rmdir()
            except OSError:
                log.warning("could not clear exhibit stills in %s", stills, exc_info=True)
        self._write_state(payload, seq)
        return True
