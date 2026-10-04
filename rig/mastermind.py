"""Mastermind mode: the crew's bag, clock, and job size, and the live plan.

Appraisal mode is the sandbox: scan anything, the take is everything seen.
Mastermind mode asks for a bag (pounds), a clock (seconds), and a job size,
then keeps one plan current as exhibits come in: what goes in the bag, what
stays, and why. The planner itself is pure (rig/planner.py); this module owns
the settings, validation, caching, and revisions.

A revision is a change in what the plan says, never a poll: the plan is
cached on its inputs (case, settings, and every exhibit's value, category,
and weight), so a dashboard polling at 12 Hz sees the same revision until a
find or a settings change actually moves it. A plan computed against a case
that has since closed is thrown away, never published.
"""
from __future__ import annotations

import math
import threading

from rig import planner

MODES = ("appraisal", "mastermind")
DEFAULTS = {"bag_lb": 25.0, "time_s": 60, "level": "small"}
LIMITS = {"bag_lb": (1.0, 200.0), "time_s": (10, 1800)}

_lock = threading.Lock()
_cache: dict = {"key": None, "doc": None, "case_no": None, "revision": 0}


def validate(payload) -> tuple[str, dict | None]:
    """(mode, settings) from a POST body. Raises ValueError with a reason a
    person can act on: nothing non-finite, negative, or out of range lands."""
    if not isinstance(payload, dict):
        raise ValueError("send a JSON object")
    mode = payload.get("mode")
    if mode not in MODES:
        raise ValueError("mode must be 'appraisal' or 'mastermind'")
    if mode == "appraisal":
        return mode, None
    settings = {}
    for key, (low, high) in LIMITS.items():
        raw = payload.get(key, DEFAULTS[key])
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be a number")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number") from None
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low:g} and {high:g}")
        settings[key] = round(value, 1) if key == "bag_lb" else int(round(value))
    level = payload.get("level", DEFAULTS["level"])
    if level not in planner.LEVELS:
        raise ValueError("level must be 'small' or 'big'")
    settings["level"] = level
    return mode, settings


def settings_for(store) -> dict:
    return {**DEFAULTS, **(store.plan_settings() or {})}


def constraints(settings: dict) -> planner.Constraints:
    return planner.for_level(settings["level"], settings["bag_lb"], settings["time_s"])


def exhibits_from(items: list[dict]) -> list[dict]:
    """Planner rows for ledger rows: value and category as filed, weight as
    the model estimated it or the category default."""
    rows = []
    for it in items:
        attrs = planner.attributes(it.get("category") or "", it.get("weight_lb"))
        rows.append({"n": it["n"], "item": it["item"], "value_usd": it["value_usd"],
                     "category": it.get("category") or "", "status": it.get("status") or "available",
                     **attrs})
    return rows


def current(store, snap: dict | None = None) -> dict | None:
    """The live plan for the open case, or None in appraisal mode."""
    snap = snap or store.snapshot()
    if snap.get("mode") != "mastermind":
        return None
    settings = settings_for(store)
    rows = exhibits_from(snap["items"])
    key = (snap["case_no"], tuple(sorted(settings.items())),
           tuple((r["n"], r["value_usd"], r["category"], r["weight_lb"], r["status"]) for r in rows))
    with _lock:
        if _cache["key"] == key:
            return _cache["doc"]
        c = constraints(settings)
        result = _plan_rows(rows, c)
        if store.case_no() != snap["case_no"]:
            return None                      # the case closed under us; never publish it
        prev = _cache["doc"] if _cache["case_no"] == snap["case_no"] else None
        revision = (_cache["revision"] if prev else 0) + 1
        doc = _document(result, rows, settings, c, snap["case_no"], revision, prev)
        _cache.update(key=key, doc=doc, case_no=snap["case_no"], revision=revision)
        return doc


def _plan_rows(rows: list[dict], c: planner.Constraints) -> dict:
    """The one place a crew status reaches the planner: excluded exhibits
    are off the table, collected ones are already in the bag."""
    return planner.plan(
        rows, c,
        unavailable={r["n"]: "excluded" for r in rows if r["status"] == "excluded"},
        collected={r["n"] for r in rows if r["status"] == "collected"},
    )


def set_status(store, n, status: str, case_no: int | None = None) -> tuple[bool, int, str]:
    """Mark one exhibit available / collected / excluded. Returns (ok, http
    status, message). Shared by the desk buttons and the radio, so both get
    the same rules: Mastermind only, a real exhibit that is loot, no double
    collect, and no collect that would overflow the bag, clock, or risk."""
    from rig.store import STATUSES
    if status not in STATUSES:
        return False, 400, "status must be available, collected, or excluded"
    if isinstance(n, bool) or not isinstance(n, int):
        return False, 400, "n must be an exhibit number"
    snap = store.snapshot()
    if case_no is not None and case_no != snap["case_no"]:
        return False, 409, f"case {case_no} is closed; this is case {snap['case_no']}"
    if snap["revealed"]:
        return False, 409, "the lineup is up; the next case can change the plan"
    if snap["mode"] != "mastermind":
        return False, 409, "switch to Mastermind first: an appraisal job has no plan"
    item = next((it for it in snap["items"] if it["n"] == n), None)
    if item is None:
        return False, 404, f"no exhibit {n:02d} in case {snap['case_no']}"
    if not planner.is_loot(item.get("category") or ""):
        return False, 409, f"exhibit {n:02d} is an exit, not loot"
    current_status = item.get("status") or "available"
    if current_status == status:
        return False, 409, f"exhibit {n:02d} is already {status}"
    if status == "collected":
        rows = exhibits_from(snap["items"])
        trial = [{**r, "status": "collected" if r["n"] == n else r["status"]} for r in rows]
        c = constraints(settings_for(store))
        result = _plan_rows(trial, c)
        if result["conflict"]:
            return False, 409, (f"{item['item']} won't fit beside what's already collected: "
                                f"over the {' and '.join(result['conflict'])}")
    if not store.set_status(n, status, snap["case_no"]):
        return False, 409, "the case moved on; try again"
    return True, 200, f"exhibit {n:02d} {item['item']} marked {status}"


def _document(result, rows, settings, c, case_no, revision, prev) -> dict:
    by_n = {r["n"]: r for r in rows}
    selected = result["selected"]
    left = [{"n": ex["n"], "reason": ex["reason"], "short": planner.SHORT_REASONS.get(ex["reason"], ex["reason"]),
             "text": planner.reason_text(ex["reason"], by_n[ex["n"]], c)}
            for ex in result["excluded"] if ex["reason"] not in {"not_loot"}]
    collected = set(result.get("collected") or ())
    nxt = max((n for n in selected if n not in collected),
              key=lambda n: (by_n[n]["value_usd"], -n), default=None)
    change = None
    if prev is not None:
        added = [n for n in selected if n not in prev["selected"]]
        dropped = [n for n in prev["selected"] if n not in selected]
        delta = round(result["totals"]["value_usd"] - prev["totals"]["value_usd"], 2)
        if added or dropped or delta or prev["settings"] != settings:
            change = {"added": [{"n": n, "item": by_n[n]["item"]} for n in added],
                      "dropped": [{"n": n, "item": by_n[n]["item"]} for n in dropped if n in by_n],
                      "delta_usd": delta,
                      "settings_changed": prev["settings"] != settings}
    level = planner.LEVELS[settings["level"]]
    return {
        "case_no": case_no,
        "revision": revision,
        "settings": dict(settings),
        "level": {"key": settings["level"], "label": level["label"], "blurb": level["blurb"]},
        "constraints": c.as_dict(),
        "objective": result["objective"],
        "algorithm": result["algorithm"],
        "selected": selected,
        "collected": sorted(collected),
        "excluded": sorted(r["n"] for r in rows if r["status"] == "excluded"),
        "conflict": result.get("conflict") or [],
        "left": left,
        "totals": result["totals"],
        "next": {"n": nxt, "item": by_n[nxt]["item"], "value_usd": by_n[nxt]["value_usd"]} if nxt else None,
        "change": change,
    }


def reset_cache() -> None:
    with _lock:
        _cache.update(key=None, doc=None, case_no=None, revision=0)
