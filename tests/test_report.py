"""Defender Report (#30): the planner core, finalized snapshots, and the report routes.

No camera, no keys, no network. Each test gets its own store, so its reports
root (<state dir>/reports) is its own temp folder.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("RIG_VOICE", "0")   # the suite never talks out loud

for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SERPAPI_API_KEY", "RIG_TOKEN", "RIG_REPORTS_DIR"):
    os.environ.pop(var, None)

from rig import app as rig_app
from rig import capture, planner, report, script
from rig.store import Store

rig_app.voice.announce = lambda *a, **k: None
rig_app.voice.announce_top5 = lambda *a, **k: None
rig_app.printer.receipt = lambda *a, **k: None


def fresh_store() -> Store:
    return Store(Path(tempfile.mkdtemp(prefix="report-store-")) / "case.json")


# ---------- finalized reports through the app ----------

class ReportCase(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        self.client = rig_app.app.test_client()
        report.STATUS.update(last_error=None, last_error_at=None, last_report=None)
        for var in ("RIG_TOKEN", "RIG_REPORTS", "RIG_REPORT_KEEP", "RIG_REPORT_DAYS"):
            os.environ.pop(var, None)
        rig_app._rate.clear()

    def tearDown(self):
        rig_app.store = self.saved
        for var in ("RIG_TOKEN", "RIG_REPORTS", "RIG_REPORT_KEEP", "RIG_REPORT_DAYS"):
            os.environ.pop(var, None)

    def walk(self, specs=None):
        """File exhibits with stills, then press the button once (reveal)."""
        specs = specs if specs is not None else [
            {"item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200,
             "bbox": [0.12, 0.2, 0.26, 0.36], "source": "openai", "price_source": "serpapi"},
            {"item": "LEICA M3", "category": "camera", "value_usd": 1850,
             "bbox": [0.5, 0.3, 0.2, 0.3], "source": "offline", "price_source": "model_quote",
             "estimated": True},
            {"item": "FLAT SCREEN TV", "category": "tv", "value_usd": 900, "source": "anthropic",
             "price_source": "vision"},
            {"item": "MYSTERY BOX", "category": "", "value_usd": 300},
        ]
        for spec in specs:
            frame = capture.paint_still(spec.get("bbox"), 200) if spec.get("bbox") else None
            rig_app.store.add_item(spec, frame)
        rig_app.on_button()
        return rig_app.store.report_id()

    def test_report_outlives_reset_and_restart(self):
        rid = self.walk()
        self.assertIsNotNone(rid)
        before = self.client.get(f"/report/{rid}.json").get_json()
        rig_app.on_button()                       # reset: live ledger and stills cleared
        self.assertEqual(rig_app.store.count(), 0)
        self.assertIsNone(self.client.get("/state.json").get_json()["report"])
        rig_app.store = Store(rig_app.store.state_path())   # process restart
        after = self.client.get(f"/report/{rid}.json").get_json()
        self.assertEqual(after["items"], before["items"])
        self.assertEqual(after["take"], 7250.0)
        self.assertEqual(after["case_no"], 1138)
        resp = self.client.get(f"/report/{rid}/evidence/1.jpg")
        self.assertEqual(resp.data[:2], b"\xff\xd8")
        resp.close()

    def test_finalize_is_idempotent_and_pinned_to_the_case(self):
        rid = self.walk()
        self.assertEqual(report.finalize(rig_app.store)["report_id"], rid)
        self.assertEqual(len(report.listing(report.root_for(rig_app.store))), 1)
        rig_app.on_button()   # reset re-checks, files nothing new
        self.assertEqual(len(report.listing(report.root_for(rig_app.store))), 1)
        self.assertIsNone(report.finalize(rig_app.store))   # nothing revealed now

    def test_state_json_links_the_report_without_its_key(self):
        rid = self.walk()
        doc = report.load(report.root_for(rig_app.store), rid)
        body = self.client.get("/state.json").get_data(as_text=True)
        self.assertIn(f"/report/{rid}", body)
        self.assertNotIn(doc["share_key"], body)
        page = self.client.get("/manifest").get_data(as_text=True)
        self.assertIn(f"/report/{rid}", page)

    def test_scenarios_agree_with_the_planner_and_show_assumptions(self):
        rid = self.walk()
        doc = report.load(report.root_for(rig_app.store), rid)
        body = self.client.get(f"/report/{rid}.json").get_json()
        self.assertEqual([s["kind"] for s in body["scenarios"]], ["standard"] * 3)   # appraisal mode
        for s in body["scenarios"]:
            direct = planner.plan(doc["items"], planner.Constraints(
                s["seconds"], doc["assumptions"]["bag_lb"], doc["assumptions"]["risk_points"]))
            self.assertEqual(s["base"]["selected"], direct["selected"])
            self.assertEqual(s["base"]["totals"], direct["totals"])
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertIn("Simulation, not a loss prediction", page)
        self.assertIn(f"{planner.DEFAULT_BAG_LB:g} lb bag", page)
        self.assertIn("Appraisal mode", page)
        self.assertIn("30 lb on its own; the bag holds 25 lb", page)   # the TV, explained

    def test_provenance_fixture_and_unknown_stay_labeled(self):
        rid = self.walk()
        body = self.client.get(f"/report/{rid}.json").get_json()
        self.assertTrue(body["provenance"]["fixture"])
        mystery = next(i for i in body["items"] if i["item"] == "MYSTERY BOX")
        self.assertEqual((mystery["source"], mystery["price_source"]), ("unknown", "unknown"))
        self.assertIn("unknown", mystery["attr_source"])
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertIn("Demo data.", page)
        self.assertIn("FIXTURE: offline demo catalog", page)
        self.assertIn("comps (the listings themselves were not kept)", page)

    def test_live_only_case_is_not_marked_fixture(self):
        rid = self.walk([{"item": "ROLEX", "category": "watch", "value_usd": 4200,
                          "source": "openai", "price_source": "serpapi"}])
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertNotIn("Demo data.", page)

    def test_whatif_compares_without_editing_the_case(self):
        rid = self.walk()
        stored = (report.root_for(rig_app.store) / rid / "report.json").read_bytes()
        body = self.client.get(f"/report/{rid}.json?secure=1&move=2").get_json()
        s30 = body["scenarios"][0]
        self.assertEqual(s30["base"]["selected"], [1, 2])
        self.assertNotIn(1, s30["whatif"]["selected"])
        self.assertNotIn(2, s30["whatif"]["selected"])
        self.assertEqual(s30["delta_usd"],
                         round(s30["whatif"]["totals"]["value_usd"] - s30["base"]["totals"]["value_usd"], 2))
        self.assertLess(s30["delta_usd"], 0)
        self.assertEqual((report.root_for(rig_app.store) / rid / "report.json").read_bytes(), stored)
        page = self.client.get(f"/report/{rid}?secure=1").get_data(as_text=True)
        self.assertIn("Owner-stated (what-if, not verified)", page)
        self.assertEqual(self.client.get(f"/report/{rid}?secure=99").status_code, 400)
        self.assertEqual(self.client.get(f"/report/{rid}?move=x").status_code, 400)

    def test_missing_evidence_has_a_visible_state(self):
        rid = self.walk()
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertIn("No still on file", page)              # the TV and the box had no frame
        self.assertEqual(self.client.get(f"/report/{rid}/evidence/3.jpg").status_code, 404)

    def test_expired_report_says_so(self):
        rid = self.walk()
        os.environ["RIG_REPORT_DAYS"] = "1"
        root = report.root_for(rig_app.store)
        doc = report.load(root, rid, now=time.time() + 2 * 86400)
        self.assertEqual(doc["state"], "expired")
        self.assertFalse(list((root / rid).glob("evidence-*.jpg")))
        page = self.client.get(f"/report/{rid}")
        self.assertEqual(page.status_code, 410)
        self.assertIn("Expired", page.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/report/{rid}/evidence/1.jpg").status_code, 410)
        self.assertEqual(self.client.get(f"/report/{rid}.json").status_code, 410)

    def test_retention_keeps_the_newest_n(self):
        os.environ["RIG_REPORT_KEEP"] = "2"
        ids = []
        for i in range(3):
            ids.append(self.walk([{"item": f"WATCH {i}", "category": "watch", "value_usd": 100 + i}]))
            rig_app.on_button()
        states = {d["report_id"]: d["state"] for d in report.listing(report.root_for(rig_app.store))}
        self.assertEqual(states[ids[0]], "expired")
        self.assertEqual((states[ids[1]], states[ids[2]]), ("final", "final"))

    def test_failed_finalize_blocks_the_reset_until_it_succeeds(self):
        saved = report._write

        def broken(*_a, **_k):
            raise OSError("disk full")

        report._write = broken
        try:
            rig_app.store.add_item({"item": "ROLEX", "category": "watch", "value_usd": 4200},
                                   capture.paint_still([0.1, 0.1, 0.3, 0.3]))
            rig_app.on_button()                   # reveal still happens
            self.assertTrue(rig_app.store.revealed)
            rig_app.on_button()                   # reset refused: evidence would be lost
            self.assertTrue(rig_app.store.revealed)
            self.assertEqual(rig_app.store.count(), 1)
            self.assertIn("disk full", self.client.get("/health").get_json()["reports"]["last_error"])
            self.assertIn("not filed", self.client.get("/manifest").get_data(as_text=True))
            root = report.root_for(rig_app.store)
            self.assertFalse(root.exists() and any(root.iterdir()))   # nothing half-written
        finally:
            report._write = saved
        rig_app.on_button()                       # retry succeeds, then resets
        self.assertFalse(rig_app.store.revealed)
        self.assertEqual(len(report.listing(report.root_for(rig_app.store))), 1)
        self.assertIsNone(self.client.get("/health").get_json()["reports"]["last_error"])

    def test_reports_can_be_switched_off(self):
        os.environ["RIG_REPORTS"] = "0"
        rig_app.store.add_item({"item": "ROLEX", "category": "watch", "value_usd": 4200})
        rig_app.on_button()
        rig_app.on_button()
        self.assertFalse(rig_app.store.revealed)
        self.assertFalse(report.root_for(rig_app.store).exists())

    def test_exhibit_text_is_escaped(self):
        rid = self.walk([{"item": "<script>alert(1)</script>", "category": "watch", "value_usd": 10,
                          "desc": "<img src=x onerror=alert(2)>"}])
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<img src=x", page)

    def test_scripted_walk_files_a_fixture_report(self):
        script._walk(rig_app.store, sleep=lambda _s: None)
        rows = report.listing(report.root_for(rig_app.store))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["provenance"]["fixture"])
        self.assertEqual({i["price_source"] for i in rows[0]["items"]}, {"fixture"})


class ReportAccess(unittest.TestCase):
    TOKEN = "op-secret-123"

    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        rig_app._rate.clear()
        self.client = rig_app.app.test_client()
        rig_app.store.add_item({"item": "ROLEX", "category": "watch", "value_usd": 4200},
                               capture.paint_still([0.1, 0.1, 0.3, 0.3]))
        rig_app.on_button()
        self.rid = rig_app.store.report_id()
        self.key = report.load(report.root_for(rig_app.store), self.rid)["share_key"]
        os.environ["RIG_TOKEN"] = self.TOKEN

    def tearDown(self):
        os.environ.pop("RIG_TOKEN", None)
        rig_app.store = self.saved

    def test_token_mode_needs_the_operator_or_the_share_key(self):
        rid, key = self.rid, self.key
        locked = self.client.get(f"/report/{rid}")
        self.assertEqual(locked.status_code, 401)
        self.assertIn("Operator token", locked.get_data(as_text=True))
        self.assertNotIn("ROLEX", locked.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/report/{rid}?k=wrong").status_code, 401)
        self.assertEqual(self.client.get(f"/report/{rid}.json").status_code, 401)
        self.assertEqual(self.client.get(f"/report/{rid}/evidence/1.jpg").status_code, 401)
        self.assertEqual(self.client.get(f"/report/{rid}/qr.png").status_code, 401)
        self.assertEqual(self.client.get("/api/reports").status_code, 401)
        ok = self.client.get(f"/report/{rid}?k={key}")
        self.assertEqual(ok.status_code, 200)
        self.assertIn(f"/report/{rid}/evidence/1.jpg?k={key}", ok.get_data(as_text=True))
        with self.client.get(f"/report/{rid}/evidence/1.jpg?k={key}") as still:
            self.assertEqual(still.status_code, 200)
        self.assertEqual(self.client.get(f"/report/{rid}/qr.png?k={key}").status_code, 200)
        hdr = {"X-Rig-Token": self.TOKEN}
        self.assertEqual(self.client.get(f"/report/{rid}.json", headers=hdr).status_code, 200)
        listing = self.client.get("/api/reports", headers=hdr).get_json()
        self.assertEqual(listing["reports"][0]["url"], f"/report/{rid}?k={key}")

    def test_unlock_trades_the_token_for_the_share_link(self):
        bad = self.client.post(f"/report/{self.rid}/unlock", data={"token": "nope"})
        self.assertEqual(bad.status_code, 401)
        self.assertIn("did not match", bad.get_data(as_text=True))
        good = self.client.post(f"/report/{self.rid}/unlock", data={"token": self.TOKEN})
        self.assertEqual(good.status_code, 303)
        self.assertTrue(good.headers["Location"].endswith(f"/report/{self.rid}?k={self.key}"))
        self.assertNotIn(self.TOKEN, good.headers["Location"])

    def test_no_secret_leaks_into_pages_or_json(self):
        hdr = {"X-Rig-Token": self.TOKEN}
        for url in (f"/report/{self.rid}?k={self.key}", f"/report/{self.rid}.json?k={self.key}",
                    "/state.json", "/manifest", "/health"):
            body = self.client.get(url, headers=hdr).get_data(as_text=True)
            self.assertNotIn(self.TOKEN, body, url)
        body = self.client.get(f"/report/{self.rid}.json", headers=hdr).get_json()
        self.assertNotIn("share_key", body)

    def test_ids_and_paths_cannot_escape_the_reports_root(self):
        root = report.root_for(rig_app.store)
        for rid in ("..", "../..", "%2e%2e", "x" * 16 + "/..", "short"):
            self.assertIn(self.client.get(f"/report/{rid}/evidence/1.jpg?k={self.key}").status_code,
                          {401, 404})
        self.assertIsNone(report.evidence_path(root, "../" + self.rid, 1))
        self.assertIsNone(report.load(root, "../../etc/passwd"))
        outside = Path(tempfile.mkdtemp()) / "secret.jpg"
        outside.write_bytes(b"\xff\xd8 not yours")
        (root / self.rid / "evidence-9.jpg").symlink_to(outside)
        self.assertIsNone(report.evidence_path(root, self.rid, 9))
        self.assertEqual(self.client.get(f"/report/{self.rid}/evidence/9.jpg?k={self.key}").status_code, 404)

    def test_a_forged_share_key_is_not_echoed_into_links(self):
        os.environ.pop("RIG_TOKEN", None)   # open mode: the page renders for anyone
        body = self.client.get(f'/report/{self.rid}?k="><script>x</script>').get_data(as_text=True)
        self.assertNotIn("<script>x", body)
        self.assertNotIn("?k=", body.split("Re-run scenarios")[0])


if __name__ == "__main__":
    unittest.main()
