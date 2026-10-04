"""Demo-readiness smoke check. Run it the morning of the hackathon.

    python smoke_demo.py             # offline self-check, no camera or keys
    python smoke_demo.py --tests     # also run the unit-test suite first
    python smoke_demo.py --live http://127.0.0.1:5000   # check a running rig

Offline mode exercises the whole dashboard contract with a fake camera:
state schema, /health, crops, the manifest, reveal/reset, the persistence
round-trip, offline-fallback determinism, and the flicker gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FAILURES: list[str] = []


def _open(url: str):
    """GET with the crew token attached when RIG_TOKEN is set — read endpoints
    are open in demo mode but 401 once the LAN is locked."""
    req = urllib.request.Request(url)
    token = os.environ.get("RIG_TOKEN", "").strip()
    if token:
        req.add_header("X-Rig-Token", token)
    return urllib.request.urlopen(req, timeout=5)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}" + (f", {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def check_offline() -> None:
    import os

    case_path = Path(tempfile.gettempdir()) / "heist-smoke-case.json"
    case_path.unlink(missing_ok=True)   # stale file would dedup the exhibit
    os.environ["RIG_STATE_FILE"] = str(case_path)
    for mod in list(sys.modules):
        if mod == "rig" or mod.startswith("rig."):
            del sys.modules[mod]

    from rig import app as rig_app
    from rig import capture, vision
    from rig.pricing import WHY
    from rig.store import Store

    client = rig_app.app.test_client()

    state = client.get("/state.json")
    body = state.get_json() or {}
    check("state.json responds with the full schema",
          state.status_code == 200
          and all(k in body for k in ("frame_id", "camera_ok", "pending", "revealed", "take", "case_no", "items")),
          f"keys={sorted(body)}")

    health = client.get("/health")
    hb = health.get_json() or {}
    check("health reports every subsystem",
          health.status_code == 200
          and all(k in hb for k in ("ok", "camera_ok", "vision_provider", "serpapi", "voice", "oled_mode", "persistence")),
          f"provider={hb.get('vision_provider')}, serpapi={hb.get('serpapi')}")

    still = capture.paint_still([0.12, 0.20, 0.26, 0.36], 210)
    rig_app.store.set_frame(capture.frame_jpeg(still))
    added, hot = rig_app.store.add_item(
        {"item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200,
         "bbox": [0.12, 0.20, 0.26, 0.36], "why": WHY["serpapi"]},
        still,
    )
    check("exhibit lands in the ledger and hits the top 5", added and hot)
    check("crop endpoint serves a jpeg",
          client.get("/crop/1.jpg").data[:2] == b"\xff\xd8")

    manifest = client.get("/manifest").get_data(as_text=True)
    check("manifest lists the exhibit with its why line",
          "VINTAGE ROLEX" in manifest and "sold-listing" in manifest)

    nonce = {"X-Case-Nonce": rig_app._nonce()}
    revealed = client.post("/trigger_reveal", headers=nonce).get_json() or {}
    check("reveal fires and reset closes the case",
          revealed.get("revealed") is True
          and (client.post("/trigger_reveal", headers=nonce).get_json() or {}).get("case_no") == revealed.get("case_no", 0) + 1)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.json"
        first = Store(path)
        first.add_item({"item": "ROUND-TRIP PROP", "category": "test", "value_usd": 12.5,
                        "why": "persistence check"})
        reopened = Store(path)
        rows = reopened.manifest_rows()
        check("case file survives a restart",
              len(rows) == 1 and rows[0]["item"] == "ROUND-TRIP PROP" and rows[0]["why"] == "persistence check")

    still_a = capture.frame_b64(capture.paint_still([0.1, 0.1, 0.4, 0.4], 200))
    one = vision.offline_fallback(still_a)
    two = vision.offline_fallback(still_a)
    check("offline fallback is deterministic per frame",
          one["item"] == two["item"] and one.get("source") == "offline",
          f"item={one['item']}")

    base = capture.paint_still(None, 40)
    flicker = capture.paint_still([0.3, 0.3, 0.3, 0.3], 220)
    gate = [capture.scene_changed(f) for f in (base, base.copy(), flicker, base.copy())]
    check("a one-frame flicker does not open the gate", not any(gate[1:]), f"gate={gate}")

    os.environ.pop("RIG_STATE_FILE", None)


def check_live(base: str) -> None:
    base = base.rstrip("/")
    for path, keys in (
        ("/health", ("ok", "camera_ok", "vision_provider", "serpapi", "voice", "persistence")),
        ("/state.json", ("frame_id", "camera_ok", "pending", "revealed", "take", "case_no", "items")),
        ("/wrist.json", ("case_no", "take", "count", "pending", "revealed", "top")),
    ):
        try:
            with _open(base + path) as resp:
                body = json.load(resp)
            missing = [k for k in keys if k not in body]
            check(f"{path} schema", not missing, f"missing={missing}" if missing else "")
        except Exception as exc:
            check(f"{path} reachable", False, str(exc))
    try:
        with _open(base + "/frame.jpg") as resp:
            check("/frame.jpg serves a jpeg", resp.read(2) == b"\xff\xd8")
    except Exception as exc:
        check("/frame.jpg reachable", False, str(exc))

    for path, needle in (
        ("/manifest", b"Loot Manifest"),
        ("/kit", None),
        ("/demo.html", None),
        ("/qr.png", b"\x89PNG"),
    ):
        try:
            with _open(base + path) as resp:
                body = resp.read()
            check(f"{path} serves", resp.status == 200 and (needle is None or needle in body))
        except Exception as exc:
            check(f"{path} reachable", False, str(exc))

    try:
        with _open(base + "/state.json") as resp:
            items = json.load(resp).get("items") or []
        if items:
            with _open(base + "/crop/1.jpg") as resp:
                check("/crop/1.jpg serves a jpeg", resp.read(2) == b"\xff\xd8")
        else:
            check("/crop/1.jpg serves a jpeg", True, "skipped: no exhibits yet")
    except Exception as exc:
        check("/crop/1.jpg reachable", False, str(exc))

    # Teleop relay must answer with a real status — 401 locked, 503 no rover
    # registered, 200 wired. Anything else means the drive chain broke.
    try:
        req = urllib.request.Request(
            base + "/api/drive", data=b'{"dir":"forward","secs":0.1}',
            headers={"Content-Type": "application/json",
                     **({"X-Rig-Token": os.environ["RIG_TOKEN"].strip()}
                        if os.environ.get("RIG_TOKEN", "").strip() else {})},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                drive_status = resp.status
        except urllib.error.HTTPError as exc:
            drive_status = exc.code
        check("/api/drive teleop chain answers", drive_status in (200, 401, 503),
              f"status={drive_status}")
    except Exception as exc:
        check("/api/drive reachable", False, str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Heist rig demo-readiness check")
    parser.add_argument("--tests", action="store_true", help="run the unit-test suite first")
    parser.add_argument("--live", metavar="URL", help="check a running rig instead of the offline contract")
    args = parser.parse_args()

    print("========================================")
    print("  Heist Loot Scanner, demo smoke check")
    print("========================================")

    if args.tests:
        res = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
        check("unit tests", res.returncode == 0)

    if args.live:
        check_live(args.live)
    else:
        check_offline()

    print("\n----------------------------------------")
    if FAILURES:
        print(f"SMOKE FAILED, {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SMOKE PASSED, the rig is ready to walk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
