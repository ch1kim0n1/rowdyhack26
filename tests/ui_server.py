"""Deterministic local UI fixture: no camera, GPIO, speech or API keys."""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["RIG_STATE_FILE"] = str(Path(tempfile.mkdtemp(prefix="heist-ui-")) / "case.json")
os.environ["RIG_OFFLINE"] = "1"
os.environ["RIG_VOICE"] = "0"

from flask import jsonify, request

from rig import app as hub
from rig import capture
from rig.store import Store

hub.voice.announce = lambda *args, **kwargs: None
hub.voice.announce_top5 = lambda *args, **kwargs: None
hub.printer.receipt = lambda *args, **kwargs: None


@hub.app.post("/__fixture")
def fixture():
    data = request.get_json()
    hub.store = Store(Path(tempfile.mkdtemp(prefix="heist-ui-case-")) / "case.json")
    with hub.store._lock:
        hub.store._case_no = data.get("case_no", 42)
    frame = capture.paint_still([0.12, 0.2, 0.26, 0.36])
    hub.store.set_camera(data.get("camera_ok", True))
    hub.store.set_pending(bool(data.get("pending", False)))
    hub.store.set_frame(capture.frame_jpeg(frame))
    for i in range(data.get("count", 5)):
        names = [
            "VINTAGE LEICA M3 RANGEFINDER CAMERA", "ROLEX SUBMARINER WRISTWATCH",
            "FIRST EDITION HEMINGWAY NOVEL", "SILK SMOKING JACKET", "BRASS DESK LAMP",
            "HANDMADE PERSIAN WOOL RUG", "STERLING SILVER TEA SERVICE", "ANTIQUE OAK WRITING DESK",
            "DIAMOND RIVIERE NECKLACE", "SIGNED ABSTRACT OIL PAINTING", "PORCELAIN MING STYLE VASE",
            "MARSHALL TUBE GUITAR AMPLIFIER", "TURNTABLE WITH WALNUT PLINTH", "BESPOKE LEATHER TRAVEL TRUNK",
            "ART DECO CRYSTAL CHANDELIER",
        ]
        hub.store.add_item({
            "item": names[i] if i < len(names) else hashlib.sha256(str(i).encode()).hexdigest()[:40],
            "category": f"category-{i}",
            "value_usd": 999999 if data.get("huge") else 100 + i * 25,
            "estimated": i % 2 == 0,
            "bbox": [0.12 + i % 4 * .15, 0.2, 0.13, 0.36],
            "why": data.get("why", "sold-listing comps; median of three comparable sales"),
        }, frame)
    if data.get("revealed"):
        hub.store.mark_revealed()
    hub._rover_addr = None
    return jsonify(hub.store.snapshot())


if __name__ == "__main__":
    hub.app.run(host="127.0.0.1", port=int(os.environ.get("UI_TEST_PORT", "5127")), use_reloader=False)
