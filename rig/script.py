"""A scripted walk through the dashboard contract. No camera, no API keys.

RIG_SCRIPT=1 plays it on a loop: pending, four exhibits (one with no box),
a camera drop, the reveal, then a reset so the client can play THE END.
"""
from __future__ import annotations

import logging
import time

from rig import capture, display, narration, report
from rig.store import Store

log = logging.getLogger("rig.script")

# Four exhibits. The book has no bbox, so the ledger keeps it and the feed does not mark it.
# The boxes sit apart so each exhibit's tag and caption have room on the projector.
LOOT = [
    {"item": "VINTAGE ROLEX", "weight_lb": 0.34, "desc": "steel sports watch", "category": "watch",
     "value_usd": 4200, "estimated": False, "bbox": [0.07, 0.15, 0.24, 0.32], "shade": 210,
     "why": "priced from live eBay sold-listing comps"},
    {"item": "LEICA M3 RANGEFINDER", "weight_lb": 1.29, "desc": "chrome camera body", "category": "camera",
     "value_usd": 1850, "estimated": False, "bbox": [0.60, 0.22, 0.22, 0.30], "shade": 170,
     "why": "priced from live eBay sold-listing comps"},
    {"item": "FIRST-ED. HEMINGWAY", "weight_lb": 1.6, "desc": "clothbound novel", "category": "book",
     "value_usd": 950, "estimated": True, "bbox": None, "shade": 140,
     "why": "no sold comps; priced by model quote"},
    {"item": "BRASS DESK LAMP", "weight_lb": 5.5, "desc": "adjustable desk lamp", "category": "lamp",
     "value_usd": 180, "estimated": False, "bbox": [0.34, 0.62, 0.20, 0.22], "shade": 120,
     "why": "priced from live eBay sold-listing comps"},
]


def run(store: Store, sleep=time.sleep) -> None:
    first = True
    while True:
        # Let the reel finish before the first poll has something to type,
        # and let THE END finish before the next case starts.
        sleep(6.5 if first else 8)
        first = False
        _walk(store, sleep)


def _walk(store: Store, sleep) -> None:
    store.set_camera(True)
    display.show_lost(False)
    seen = []
    _push_frame(store, seen)
    for spec in LOOT:
        store.set_pending(True)
        sleep(1.4)
        seen.append(spec)
        frame = _push_frame(store, seen)
        # Fixture data, and labeled so: the Defender Report marks it as demo.
        added, hot = store.add_item({**spec, "source": "script", "price_source": "fixture"}, frame)
        store.set_pending(False)
        if added:
            display.show_take(store.take(), store.count(), store.case_no())
            log.info("exhibit %s $%s", spec["item"], spec["value_usd"])
            narration.observe(store)
        sleep(1.2)

    store.set_camera(False)
    display.show_lost(True)
    narration.observe(store)
    sleep(2.5)
    narration.observe(store)            # the loss has held: "Lost the picture."
    store.set_camera(True)
    display.show_lost(False)
    narration.observe(store)
    _push_frame(store, seen)
    sleep(1.5)

    if store.mark_revealed():
        display.show_reveal(store.case_no())
        narration.observe(store)
        _file_report(store)
    sleep(12)
    _file_report(store)   # retry before the reset clears the evidence
    if store.reset_case():
        display.show_take(0, 0, store.case_no())
        narration.observe(store)


def _file_report(store: Store) -> None:
    """The scripted walk keeps looping either way; a failure is logged and on /health."""
    try:
        report.finalize(store)
    except report.ReportError:
        pass


def _push_frame(store: Store, specs: list):
    """One still with every exhibit found so far, so older markers stay on their objects."""
    still = capture.paint_still(None)
    for spec in specs:
        block = spec.get("bbox")
        if not block:
            continue
        x, y, w, h = block
        x0, y0 = int(x * 640), int(y * 480)
        x1, y1 = int((x + w) * 640), int((y + h) * 480)
        still[y0:y1, x0:x1] = spec.get("shade", 180)
    store.set_frame(capture.frame_jpeg(still))
    return still
