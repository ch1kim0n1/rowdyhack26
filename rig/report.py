"""Defender Report: the revealed case, preserved, with modeled exposure.

The reveal freezes the ledger; finalize() copies that frozen case into its own
folder (report.json plus one evidence crop per exhibit) before reset_case()
can clear the live ledger and its stills. A report never reads live state
again, so it renders the same after the next case starts or the Pi restarts.

Everything past the evidence is computed at render time from the stored
exhibits and stored assumptions with the deterministic planner: no model
call, no network, the same totals every time. Owner what-ifs ("secured",
"moved") are query parameters on the page, so they produce a comparison and
never touch the stored case.

Layout under the reports root (RIG_REPORTS_DIR, default <state dir>/reports):
    <report_id>/report.json        the finalized case, or an expiry tombstone
    <report_id>/evidence-<n>.jpg   evidence crops (deleted on expiry)
    .tmp-<report_id>/              a finalize in progress; renamed into place
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from rig import capture, planner

log = logging.getLogger("rig.report")

SCHEMA = 1
_RID = re.compile(r"[A-Za-z0-9_-]{16}")
FIXTURE_SOURCES = {"offline", "script"}
MAX_TOMBSTONES = 200

SOURCE_LABELS = {
    "openai": "OpenAI vision model",
    "anthropic": "Anthropic vision model",
    "offline": "FIXTURE: offline demo catalog, not a real observation",
    "script": "FIXTURE: scripted demo walk, not a real observation",
}
PRICE_LABELS = {
    "ebay": "eBay sold-listing comps (the listings themselves were not kept)",
    "ebayapi": "eBay listings via the official Browse API (listings were not kept)",
    "serpapi": "eBay sold-listing comps (the listings themselves were not kept)",
    "model_quote": "model price quote (estimate)",
    "vision": "vision-model estimate only",
    "fixture": "fixture value from the demo script",
    "exit": "not priced: an exit, not loot",
}
UNKNOWNS = (
    "Whether any exhibit is anchored, locked, or alarmed. A camera seeing an object "
    "does not show how hard it is to take.",
    "Actual access to the room and any entry path. Nothing here models getting in.",
    "Objects the camera never saw. This is the observed inventory, not a room audit.",
    "Real removal times and weights. Time, carry, and risk figures are fixed modeling "
    "assumptions, not measurements.",
)

_lock = threading.Lock()
STATUS: dict = {"last_error": None, "last_error_at": None, "last_report": None}


class ReportError(RuntimeError):
    """Finalization failed; the live case must not be cleared."""


def enabled() -> bool:
    return os.environ.get("RIG_REPORTS", "1").strip().lower() not in {"0", "false", "no", "off"}


def keep_count() -> int:
    """RIG_REPORT_KEEP: newest finalized reports kept with their evidence."""
    try:
        return max(1, int(os.environ.get("RIG_REPORT_KEEP", "20") or 20))
    except ValueError:
        return 20


def keep_days() -> float:
    """RIG_REPORT_DAYS: a report expires this long after finalizing. 0 = no age limit."""
    try:
        return max(0.0, float(os.environ.get("RIG_REPORT_DAYS", "7") or 7))
    except ValueError:
        return 7.0


def root_for(store) -> Path:
    env = os.environ.get("RIG_REPORTS_DIR", "").strip()
    return Path(env) if env else store.state_path().parent / "reports"


def valid_id(report_id: str) -> bool:
    return isinstance(report_id, str) and bool(_RID.fullmatch(report_id))


# ---------- finalize ----------

def finalize(store, now: float | None = None) -> dict | None:
    """Preserve the revealed case. Idempotent: the case's report is pinned in
    the store, so a second call returns it. None when there is nothing to
    finalize (no reveal, or reports disabled). Raises ReportError on a failed
    write; nothing partial is left behind and the next call retries."""
    if not enabled():
        return None
    root = root_for(store)
    now = time.time() if now is None else now
    with _lock:
        sealed = store.sealed_case()
        if sealed is None:
            return None
        pinned = sealed.get("report_id")
        if pinned and valid_id(pinned):
            existing = _read(root, pinned)
            if existing is not None:
                return existing
        try:
            doc = _write(root, sealed, now)
        except Exception as exc:
            STATUS.update(last_error=f"{type(exc).__name__}: {exc}", last_error_at=now)
            log.exception("Defender Report for case %s could not be filed", sealed["case_no"])
            raise ReportError(str(exc)) from exc
        if not store.set_report_id(sealed["case_no"], doc["report_id"]):
            log.warning("case moved on while its report was filed; report %s kept", doc["report_id"])
        STATUS.update(last_error=None, last_error_at=None, last_report=doc["report_id"])
        log.info("Defender Report %s filed for case %s", doc["report_id"], sealed["case_no"])
        try:
            prune(root, now)
        except OSError:
            log.warning("report retention pass failed", exc_info=True)
        return doc


def _write(root: Path, sealed: dict, now: float) -> dict:
    report_id = secrets.token_urlsafe(12)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp-{report_id}"
    tmp.mkdir()
    try:
        items = []
        for it in sealed["items"]:
            evidence = False
            jpeg = it.get("frame_jpeg")
            if jpeg:
                arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if arr is not None:
                    (tmp / f"evidence-{int(it['n'])}.jpg").write_bytes(capture.crop_jpeg(arr, it.get("bbox")))
                    evidence = True
            items.append({
                "n": int(it["n"]),
                "item": it["item"],
                "desc": it.get("desc") or "",
                "category": it.get("category") or "",
                "value_usd": float(it["value_usd"]),
                "estimated": bool(it.get("estimated")),
                "why": it.get("why") or "",
                "origin": it.get("origin") or "hat",
                "source": it.get("source") or "unknown",
                "price_source": it.get("price_source") or "unknown",
                "evidence": evidence,
                **planner.attributes(it.get("category") or "", it.get("weight_lb")),
            })
        doc = {
            "schema": SCHEMA,
            "state": "final",
            "report_id": report_id,
            "share_key": secrets.token_urlsafe(16),
            "case_no": int(sealed["case_no"]),
            "finalized_at": now,
            "take": round(sum(i["value_usd"] for i in items), 2),
            "provenance": {
                "sources": sorted({i["source"] for i in items}),
                "price_sources": sorted({i["price_source"] for i in items}),
                "fixture": any(i["source"] in FIXTURE_SOURCES for i in items),
            },
            "assumptions": {
                "scenario_seconds": list(planner.SCENARIO_SECONDS),
                "bag_lb": planner.DEFAULT_BAG_LB,
                "risk_points": planner.DEFAULT_RISK_POINTS,
                "objective": planner.OBJECTIVE,
            },
            # The job the crew ran: appraisal (no plan) or mastermind (its own bag/clock/size).
            "mode": sealed.get("mode") or "appraisal",
            "plan_settings": sealed.get("plan_settings") if sealed.get("mode") == "mastermind" else None,
            "items": items,
        }
        (tmp / "report.json").write_text(json.dumps(doc))
        tmp.rename(root / report_id)
        return doc
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ---------- read, expire, prune ----------

def load(root: Path, report_id: str, now: float | None = None) -> dict | None:
    """The report, or its expiry tombstone. Expires on read once past its age."""
    if not valid_id(report_id):
        return None
    with _lock:
        doc = _read(root, report_id)
        if doc is None:
            return None
        days = keep_days()
        now = time.time() if now is None else now
        if doc.get("state") == "final" and days and now - doc["finalized_at"] > days * 86400:
            doc = _expire(root, doc, f"older than the {days:g}-day retention window", now)
        return doc


def _read(root: Path, report_id: str) -> dict | None:
    try:
        doc = json.loads((root / report_id / "report.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("report_id") != report_id:
        return None
    return doc


def _expire(root: Path, doc: dict, reason: str, now: float) -> dict:
    tomb = {
        "schema": SCHEMA,
        "state": "expired",
        "report_id": doc["report_id"],
        "share_key": doc.get("share_key"),   # an old QR still lands on the expiry page
        "case_no": doc.get("case_no"),
        "finalized_at": doc.get("finalized_at"),
        "expired_at": now,
        "reason": reason,
    }
    folder = root / doc["report_id"]
    fd, tmp = tempfile.mkstemp(dir=str(folder), suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(tomb, fh)
    os.replace(tmp, folder / "report.json")
    for still in folder.glob("evidence-*.jpg"):
        still.unlink(missing_ok=True)
    log.info("report %s expired: %s", doc["report_id"], reason)
    return tomb


def prune(root: Path, now: float | None = None) -> None:
    """Retention: keep the newest RIG_REPORT_KEEP reports, expire anything past
    RIG_REPORT_DAYS, cap the tombstones, and sweep abandoned temp folders.
    Call with _lock held."""
    now = time.time() if now is None else now
    if not root.is_dir():
        return
    docs = []
    for folder in root.iterdir():
        if folder.name.startswith(".tmp-"):
            shutil.rmtree(folder, ignore_errors=True)   # a finalize that died mid-write
        elif folder.is_dir() and valid_id(folder.name):
            doc = _read(root, folder.name)
            if doc is not None:
                docs.append(doc)
    finals = sorted((d for d in docs if d.get("state") == "final"),
                    key=lambda d: d["finalized_at"], reverse=True)
    days = keep_days()
    keep = keep_count()
    tombs = [d for d in docs if d.get("state") == "expired"]
    for i, doc in enumerate(finals):
        if i >= keep:
            tombs.append(_expire(root, doc, f"only the newest {keep} reports are kept", now))
        elif days and now - doc["finalized_at"] > days * 86400:
            tombs.append(_expire(root, doc, f"older than the {days:g}-day retention window", now))
    tombs.sort(key=lambda d: d.get("expired_at") or 0, reverse=True)
    for doc in tombs[MAX_TOMBSTONES:]:
        shutil.rmtree(root / doc["report_id"], ignore_errors=True)


def listing(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    rows = []
    for folder in root.iterdir():
        if folder.is_dir() and valid_id(folder.name):
            doc = _read(root, folder.name)
            if doc is not None:
                rows.append(doc)
    return sorted(rows, key=lambda d: d.get("finalized_at") or 0, reverse=True)


def evidence_path(root: Path, report_id: str, n: int) -> Path | None:
    """The evidence crop, only if it really sits inside this report's folder."""
    if not valid_id(report_id):
        return None
    base = root.resolve()
    path = (root / report_id / f"evidence-{int(n)}.jpg").resolve()
    if not path.is_relative_to(base) or not path.is_file():
        return None
    return path


# ---------- the view: scenarios, what-ifs, ranking, recommendations ----------

def parse_whatif(values: list[str], known: set[int]) -> set[int]:
    """'3,5' / repeated params -> exhibit numbers. Raises ValueError on junk or
    a number that is not in this report."""
    out: set[int] = set()
    for raw in values:
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit() or int(part) not in known:
                raise ValueError(f"not an exhibit in this report: {part!r}")
            out.add(int(part))
    return out


def view(doc: dict, secured: set[int] | None = None, moved: set[int] | None = None) -> dict:
    """Everything the page and the JSON route show, from the stored case alone."""
    secured, moved = set(secured or ()), set(moved or ()) - set(secured or ())
    items = doc["items"]
    by_n = {it["n"]: it for it in items}
    a = doc["assumptions"]
    unavailable = {n: "secured" for n in secured} | {n: "moved" for n in moved}

    def scenario(c: planner.Constraints, label: str, kind: str) -> dict:
        base = planner.plan(items, c)
        alt = planner.plan(items, c, unavailable) if unavailable else None
        return {
            "kind": kind,
            "label": label,
            "seconds": c.time_s,
            "constraints": c.as_dict(),
            "base": _decorate(base, by_n, c),
            "whatif": _decorate(alt, by_n, c) if alt else None,
            "delta_usd": round(alt["totals"]["value_usd"] - base["totals"]["value_usd"], 2) if alt else None,
        }

    scenarios = []
    crew = doc.get("plan_settings") if doc.get("mode") == "mastermind" else None
    if crew:
        level = planner.LEVELS.get(crew.get("level"), planner.LEVELS["small"])
        c = planner.for_level(crew.get("level") if crew.get("level") in planner.LEVELS else "small",
                              crew["bag_lb"], crew["time_s"])
        scenarios.append(scenario(c, f"The crew's plan: {level['label']}", "crew"))
    first_taken: dict[int, int] = {}
    for secs in a["scenario_seconds"]:
        s = scenario(planner.Constraints(secs, a["bag_lb"], a["risk_points"]), f"{secs} seconds", "standard")
        for n in s["base"]["selected"]:
            first_taken.setdefault(n, secs)
        scenarios.append(s)

    exposed = sorted(first_taken, key=lambda n: (-by_n[n]["value_usd"], n))[:5]
    ranking = [{**by_n[n], "first_seconds": first_taken[n],
                "scenarios": sum(n in s["base"]["selected"] for s in scenarios if s["kind"] == "standard")}
               for n in exposed]

    recs = []
    for row in ranking[:3]:
        name = row["item"]
        if row["first_seconds"] == a["scenario_seconds"][0]:
            where = f"it is in the modeled haul even in the {row['first_seconds']}-second scenario."
        else:
            where = f"it enters the modeled haul at {row['first_seconds']} seconds."
        lines = [f"Review where {name} is displayed: {where}"]
        if row["estimated"] or row["price_source"] in {"vision", "unknown"}:
            lines.append(f"Document {name}'s identity (make, model, serial, photos). "
                         "Its value here is an estimate.")
        lines.append(f"Verify whether {name} is physically secured. The camera saw it; "
                     "that says nothing about anchoring, locks, or reach.")
        recs.append({"n": row["n"], "item": name, "lines": lines})

    facts = ([{"n": n, "item": by_n[n]["item"], "fact": "marked secured"} for n in sorted(secured)]
             + [{"n": n, "item": by_n[n]["item"], "fact": "moved out of the display area"}
                for n in sorted(moved)])
    return {
        "items": items,
        "scenarios": scenarios,
        "ranking": ranking,
        "recommendations": recs,
        "unknowns": list(UNKNOWNS),
        "owner_whatif": facts,
        "secured": sorted(secured),
        "moved": sorted(moved),
        "fixture": doc["provenance"]["fixture"],
        "mode": doc.get("mode") or "appraisal",
        "algorithm": sorted({s["base"]["algorithm"] for s in scenarios}),
    }


def _decorate(result: dict, by_n: dict, c: planner.Constraints) -> dict:
    """Planner output plus a sentence for every exclusion, rendered from its code."""
    out = dict(result)
    out["excluded"] = sorted(
        ({**ex, "text": reason_text(ex["reason"], by_n[ex["n"]], c)} for ex in result["excluded"]),
        key=lambda ex: (-by_n[ex["n"]]["value_usd"], ex["n"]),
    )
    return out


def reason_text(reason: str, item: dict, c: planner.Constraints) -> str:
    return planner.reason_text(reason, item, c)


def source_label(tag: str) -> str:
    return SOURCE_LABELS.get(tag, "unknown" if tag == "unknown" else f"unknown ({tag})")


def price_label(tag: str) -> str:
    return PRICE_LABELS.get(tag, "unknown" if tag == "unknown" else f"unknown ({tag})")
