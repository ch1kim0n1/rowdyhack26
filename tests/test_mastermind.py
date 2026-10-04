"""Mastermind mode (#28): the weight/clock/job-size planner, the live plan, and its API.

No camera, no keys, no network. Each test gets its own store.
"""
from __future__ import annotations

import itertools
import os
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["PYTHON_DOTENV_DISABLED"] = "1"   # importing rig.app must not load a real .env over this setup
# ...nor bind its store to the rig's live case file: run before test_contract, that module's
# blank(rig_app.store) would then delete rig/state/case.json.
os.environ.setdefault("RIG_STATE_FILE", str(Path(tempfile.mkdtemp(prefix="heist-test-")) / "case.json"))
os.environ.setdefault("RIG_VOICE", "0")   # the suite never talks out loud

for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SERPAPI_API_KEY", "RIG_TOKEN", "RIG_REPORTS_DIR"):
    os.environ.pop(var, None)

from rig import app as rig_app
from rig import capture, mastermind, planner, report, script, vision
from rig.store import Store

rig_app.voice.announce = lambda *a, **k: None
rig_app.voice.announce_top5 = lambda *a, **k: None
rig_app.printer.receipt = lambda *a, **k: None

# The scripted walk's four exhibits plus a TV, with spec-sheet weights.
LOOT = [
    {"n": 1, "item": "VINTAGE ROLEX", "category": "watch", "value_usd": 4200, "weight_lb": 0.34},
    {"n": 2, "item": "LEICA M3", "category": "camera", "value_usd": 1850, "weight_lb": 1.29},
    {"n": 3, "item": "FIRST-ED. HEMINGWAY", "category": "book", "value_usd": 950, "weight_lb": 1.6},
    {"n": 4, "item": "BRASS DESK LAMP", "category": "lamp", "value_usd": 180, "weight_lb": 5.5},
    {"n": 5, "item": "65-INCH OLED TV", "category": "tv", "value_usd": 900, "weight_lb": 30},
]


def rows(specs=LOOT):
    return mastermind.exhibits_from([dict(s) for s in specs])


def fresh_store() -> Store:
    return Store(Path(tempfile.mkdtemp(prefix="mastermind-store-")) / "case.json")


# ---------- the planner ----------

class Planner(unittest.TestCase):
    def reasons(self, result):
        return {e["n"]: e["reason"] for e in result["excluded"]}

    def test_small_job_leaves_the_conspicuous(self):
        p = planner.plan(rows(), planner.for_level("small", 25, 60))
        self.assertEqual(p["selected"], [1, 2, 3, 4])
        self.assertEqual(self.reasons(p), {5: "too_conspicuous"})
        self.assertEqual(p["totals"], {"value_usd": 7180.0, "weight_lb": 8.8,
                                       "grab_seconds": 34, "risk_points": 6})

    def test_big_score_is_still_bound_by_the_bag(self):
        p = planner.plan(rows(), planner.for_level("big", 25, 60))
        self.assertEqual(self.reasons(p), {5: "exceeds_weight"})
        roomy = planner.plan(rows(), planner.for_level("big", 40, 120))
        self.assertIn(5, roomy["selected"])

    def test_a_small_bag_swaps_for_value(self):
        p = planner.plan(rows(), planner.for_level("small", 2, 60))
        self.assertEqual(p["selected"], [1, 2])               # $6,050 beats rolex + book at $5,150
        self.assertEqual(self.reasons(p)[3], "outranked")
        self.assertEqual(self.reasons(p)[4], "exceeds_weight")

    def test_the_clock_binds(self):
        p = planner.plan(rows(), planner.for_level("big", 50, 12))
        self.assertEqual(p["selected"], [1, 3])               # 5s + 6s; the camera needs 8s
        self.assertLessEqual(p["totals"]["grab_seconds"], 12)

    def test_nothing_fits_is_an_explained_empty_plan(self):
        p = planner.plan(rows(), planner.for_level("small", 1, 10))
        self.assertEqual(p["selected"], [1])
        empty = planner.plan(rows(LOOT[3:]), planner.for_level("small", 1, 10))
        self.assertEqual(empty["selected"], [])
        self.assertEqual(empty["totals"]["value_usd"], 0.0)
        self.assertEqual(self.reasons(empty), {4: "exceeds_weight", 5: "too_conspicuous"})

    def test_weight_rounds_against_the_crew(self):
        exact = [{"n": 1, "category": "watch", "value_usd": 10, **planner.attributes("watch", 2.5)}]
        over = [{"n": 1, "category": "watch", "value_usd": 10, **planner.attributes("watch", 2.51)}]
        self.assertEqual(planner.plan(exact, planner.Constraints(60, 2.5))["selected"], [1])
        self.assertEqual(planner.plan(over, planner.Constraints(60, 2.5))["selected"], [])

    def test_model_weight_wins_over_the_category_default(self):
        self.assertEqual(planner.attributes("camera", 3.2)["weight_lb"], 3.2)
        self.assertEqual(planner.attributes("camera", 3.2)["weight_source"], "vision-model estimate")
        self.assertEqual(planner.attributes("camera")["weight_lb"], 1.8)
        for junk in ("heavy", -1, 0, float("inf"), float("nan"), 900, None, True):
            self.assertIn("default", planner.attributes("camera", junk)["weight_source"], junk)
        self.assertEqual(planner.attributes("mystery")["weight_lb"], planner.UNKNOWN_DEFAULT[0])

    def test_matches_exhaustive_enumeration(self):
        rng = random.Random(28)
        cats = ["watch", "camera", "lamp", "book", "laptop", "tv", "art", "mystery", "exit", "phone"]
        for _ in range(400):
            specs = [{"n": i, "category": rng.choice(cats),
                      "value_usd": rng.choice([0, 50, 180, 950, 1850, 4200, rng.randint(1, 5000)]),
                      "weight_lb": rng.choice([None, round(rng.uniform(0.1, 20), 2)])}
                     for i in range(1, rng.randint(0, 9) + 1)]
            ex = [{"n": s["n"], "category": s["category"], "value_usd": s["value_usd"],
                   **planner.attributes(s["category"], s["weight_lb"])} for s in specs]
            c = rng.choice([
                planner.Constraints(rng.choice([10, 30, 60, 120]), rng.choice([2, 5, 25]),
                                    rng.choice([3, 8, 20]), rng.choice([None, 1, 2])),
                planner.for_level(rng.choice(["small", "big"]), rng.choice([5, 25]), rng.choice([30, 60])),
            ])
            got = planner.plan(ex, c)
            self.assertEqual(got["algorithm"], "exact")
            self.assertEqual(tuple(got["selected"]), _brute(ex, c))

    def test_twenty_exhibits_well_under_budget(self):
        rng = random.Random(7)
        ex = [{"n": i, "category": c, "value_usd": rng.randint(10, 5000),
               **planner.attributes(c, round(rng.uniform(0.2, 8), 1))}
              for i, c in enumerate(rng.choices(["watch", "camera", "lamp", "laptop", "book"], k=20), 1)]
        start = time.perf_counter()
        for level, bag, secs in (("small", 25, 60), ("big", 50, 300), ("big", 10, 30)):
            planner.plan(ex, planner.for_level(level, bag, secs))
        self.assertLess(time.perf_counter() - start, 0.2)

    def test_a_huge_ledger_is_labeled_bounded(self):
        ex = [{"n": i, "category": "watch", "value_usd": 100 + i, **planner.attributes("watch")}
              for i in range(1, 61)]
        p = planner.plan(ex, planner.for_level("big", 100, 600))
        self.assertEqual(p["algorithm"], "bounded")
        self.assertIn("not_considered", {e["reason"] for e in p["excluded"]})

    def test_reasons_read_as_sentences(self):
        c = planner.for_level("small", 25, 60)
        tv = rows()[4]
        self.assertEqual(planner.reason_text("too_conspicuous", tv, c),
                         "too conspicuous for a small job (5 risk; the limit is 2 per item)")
        self.assertEqual(planner.reason_text("exceeds_weight", tv, c), "30 lb on its own; the bag holds 25 lb")


def _brute(ex, c):
    best = None
    for k in range(len(ex) + 1):
        for combo in itertools.combinations(ex, k):
            if any(not planner.is_loot(e["category"]) or planner._cents(e) <= 0 for e in combo):
                continue
            if c.max_item_risk is not None and any(e["risk_points"] > c.max_item_risk for e in combo):
                continue
            w = sum(planner._tenths(e["weight_lb"]) for e in combo)
            t = sum(e["grab_seconds"] for e in combo)
            r = sum(e["risk_points"] for e in combo)
            if w > planner._tenths(c.bag_lb) or t > c.time_s or r > c.risk_points:
                continue
            key = (-sum(planner._cents(e) for e in combo), r, t, w, tuple(sorted(e["n"] for e in combo)))
            best = key if best is None or key < best else best
    return best[4]


# ---------- settings, live plan, API ----------

class Validation(unittest.TestCase):
    def test_good_settings(self):
        self.assertEqual(mastermind.validate({"mode": "appraisal"}), ("appraisal", None))
        mode, settings = mastermind.validate({"mode": "mastermind", "bag_lb": "12.5", "time_s": 90.4, "level": "big"})
        self.assertEqual((mode, settings), ("mastermind", {"bag_lb": 12.5, "time_s": 90, "level": "big"}))

    def test_bad_settings_are_refused(self):
        bad = [None, [], {}, {"mode": "heist"},
               {"mode": "mastermind", "bag_lb": "nan"}, {"mode": "mastermind", "bag_lb": float("inf")},
               {"mode": "mastermind", "bag_lb": -5}, {"mode": "mastermind", "bag_lb": 0},
               {"mode": "mastermind", "bag_lb": 500}, {"mode": "mastermind", "time_s": 5},
               {"mode": "mastermind", "time_s": "soon"}, {"mode": "mastermind", "time_s": True},
               {"mode": "mastermind", "level": "medium"}]
        for body in bad:
            with self.assertRaises(ValueError, msg=body):
                mastermind.validate(body)


class LivePlan(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        mastermind.reset_cache()
        rig_app._rate.clear()
        self.client = rig_app.app.test_client()
        self.nonce = {"X-Case-Nonce": rig_app._nonce()}
        os.environ.pop("RIG_TOKEN", None)

    def tearDown(self):
        rig_app.store = self.saved
        os.environ.pop("RIG_TOKEN", None)

    def job(self, **body):
        return self.client.post("/api/plan", json=body, headers=self.nonce)

    def file(self, *specs):
        for spec in specs:
            rig_app.store.add_item({k: v for k, v in spec.items() if k != "n"})

    def test_appraisal_is_the_default_sandbox(self):
        self.file(*LOOT)
        state = self.client.get("/state.json").get_json()
        self.assertEqual(state["mode"], "appraisal")
        self.assertIsNone(state["plan"])
        self.assertEqual(state["take"], 8080.0)            # everything seen counts, no limits

    def test_mastermind_plan_rides_state_json(self):
        self.assertEqual(self.job(mode="mastermind", bag_lb=25, time_s=60, level="small").status_code, 200)
        self.file(*LOOT)
        state = self.client.get("/state.json").get_json()
        plan = state["plan"]
        self.assertEqual(state["mode"], "mastermind")
        self.assertEqual(plan["selected"], [1, 2, 3, 4])
        self.assertEqual(plan["next"]["item"], "VINTAGE ROLEX")
        self.assertEqual(plan["level"]["label"], "Small job")
        tv = next(row for row in plan["left"] if row["n"] == 5)
        self.assertEqual((tv["reason"], tv["short"]), ("too_conspicuous", "too loud"))
        self.assertEqual(state["take"], 8080.0)            # the room's appraisal is unchanged
        full = self.client.get("/plan.json")
        self.assertIn("no-store", full.headers["Cache-Control"])
        self.assertEqual(set(full.get_json()["levels"]), {"small", "big"})

    def test_polling_never_bumps_the_revision(self):
        self.job(mode="mastermind", bag_lb=25, time_s=60, level="small")
        self.file(LOOT[0])
        revs = {self.client.get("/state.json").get_json()["plan"]["revision"] for _ in range(6)}
        self.assertEqual(len(revs), 1)
        self.file(LOOT[1])
        self.assertEqual(self.client.get("/state.json").get_json()["plan"]["revision"], revs.pop() + 1)

    def test_a_better_find_swaps_and_reports_the_gain(self):
        self.job(mode="mastermind", bag_lb=2, time_s=60, level="small")
        self.file(LOOT[0], LOOT[2])                         # rolex + book: $5,150
        first = self.client.get("/state.json").get_json()["plan"]
        self.assertEqual(first["selected"], [1, 2])
        self.file(LOOT[1])                                  # the camera beats the book
        plan = self.client.get("/state.json").get_json()["plan"]
        self.assertEqual(plan["selected"], [1, 3])
        self.assertEqual(plan["change"]["added"], [{"n": 3, "item": "LEICA M3"}])
        self.assertEqual(plan["change"]["dropped"], [{"n": 2, "item": "FIRST-ED. HEMINGWAY"}])
        self.assertEqual(plan["change"]["delta_usd"], 900.0)
        self.assertFalse(plan["change"]["settings_changed"])

    def test_tightening_the_clock_revises_the_plan(self):
        self.job(mode="mastermind", bag_lb=25, time_s=60, level="big")
        self.file(*LOOT[:4])
        before = self.client.get("/state.json").get_json()["plan"]
        self.job(mode="mastermind", bag_lb=25, time_s=20, level="big")
        after = self.client.get("/state.json").get_json()["plan"]
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertTrue(after["change"]["settings_changed"])
        self.assertLessEqual(after["totals"]["grab_seconds"], 20)
        self.assertLess(after["totals"]["value_usd"], before["totals"]["value_usd"])

    def test_the_job_survives_restart_and_reset(self):
        self.job(mode="mastermind", bag_lb=10, time_s=120, level="big")
        rig_app.store = Store(rig_app.store.state_path())
        self.assertEqual(rig_app.store.mode(), "mastermind")
        self.assertEqual(rig_app.store.plan_settings(), {"bag_lb": 10.0, "time_s": 120, "level": "big"})
        self.file(LOOT[0])
        rig_app.on_button()
        rig_app.on_button()                                 # reset: next case, same job
        self.assertEqual(rig_app.store.mode(), "mastermind")
        plan = self.client.get("/state.json").get_json()["plan"]
        self.assertEqual((plan["case_no"], plan["revision"], plan["change"]), (1139, 1, None))

    def test_the_job_is_locked_once_the_lineup_is_up(self):
        self.file(LOOT[0])
        rig_app.on_button()
        resp = self.job(mode="mastermind", bag_lb=10, time_s=60, level="small")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(rig_app.store.mode(), "appraisal")

    def test_api_guard_and_validation(self):
        self.assertEqual(self.client.post("/api/plan", json={"mode": "appraisal"}).status_code, 403)
        bad = self.job(mode="mastermind", bag_lb=-1)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("bag_lb", bad.get_json()["error"])
        os.environ["RIG_TOKEN"] = "tok"
        self.assertEqual(self.client.post("/api/plan", json={"mode": "appraisal"}).status_code, 401)
        self.assertEqual(self.client.post("/api/plan", json={"mode": "appraisal"},
                                          headers={"X-Rig-Token": "tok"}).status_code, 200)
        # Token set = hosted: pages are public, so the nonce alone no longer mutates.
        os.environ["RIG_TOKEN"] = "tok"
        self.assertEqual(self.job(mode="appraisal").status_code, 401)   # nonce only
        os.environ.pop("RIG_TOKEN", None)
        self.assertEqual(self.job(mode="appraisal").status_code, 200)   # open LAN: nonce ok

    def test_manifest_shows_the_haul(self):
        self.job(mode="mastermind", bag_lb=25, time_s=60, level="small")
        self.file(*LOOT)
        page = self.client.get("/manifest").get_data(as_text=True)
        self.assertIn("MASTERMIND HAUL", page)
        self.assertIn("$7,180.00", page)
        self.assertIn("in the bag", page)
        self.assertIn(">left<", page)

    def test_vision_reads_weight(self):
        parsed = vision.parse_response('{"item": "Sony WH-1000XM6", "value_usd": 400, "weight_lb": 0.56}')
        self.assertEqual(parsed["weight_lb"], 0.56)
        self.assertIsNone(vision.parse_response('{"item": "Lamp", "value_usd": 4, "weight_lb": "heavy"}')["weight_lb"])
        self.assertIn("weight_lb", vision.PROMPT)
        self.assertTrue(all(spec.get("weight_lb") for spec in vision.OFFLINE_CATALOG))


class ReportsInBothModes(unittest.TestCase):
    def setUp(self):
        self.saved = rig_app.store
        rig_app.store = fresh_store()
        mastermind.reset_cache()
        rig_app._rate.clear()
        self.client = rig_app.app.test_client()

    def tearDown(self):
        rig_app.store = self.saved

    def walk(self):
        for spec in LOOT:
            rig_app.store.add_item({k: v for k, v in spec.items() if k != "n"},
                                   capture.paint_still([0.2, 0.2, 0.3, 0.3]))
        rig_app.on_button()
        return rig_app.store.report_id()

    def test_mastermind_report_leads_with_the_crews_plan(self):
        self.client.post("/api/plan", json={"mode": "mastermind", "bag_lb": 2, "time_s": 60, "level": "small"},
                         headers={"X-Case-Nonce": rig_app._nonce()})
        rid = self.walk()
        live = self.client.get("/state.json").get_json()["plan"]
        body = self.client.get(f"/report/{rid}.json").get_json()
        self.assertEqual(body["mode"], "mastermind")
        crew = body["scenarios"][0]
        self.assertEqual(crew["kind"], "crew")
        self.assertEqual(crew["base"]["selected"], live["selected"])          # same planner, same answer
        self.assertEqual(crew["base"]["totals"], live["totals"])
        self.assertEqual([s["kind"] for s in body["scenarios"][1:]], ["standard"] * 3)
        page = self.client.get(f"/report/{rid}").get_data(as_text=True)
        self.assertIn("The crew&#39;s plan: Small job", page)
        self.assertIn("Mastermind mode: 2.0 lb bag", page)

    def test_appraisal_report_has_no_crew_plan(self):
        rid = self.walk()
        body = self.client.get(f"/report/{rid}.json").get_json()
        self.assertEqual(body["mode"], "appraisal")
        self.assertNotIn("crew", [s["kind"] for s in body["scenarios"]])
        weights = {i["item"]: (i["weight_lb"], i["weight_source"]) for i in body["items"]}
        self.assertEqual(weights["65-INCH OLED TV"], (30.0, "vision-model estimate"))

    def test_scripted_walk_in_mastermind_mode(self):
        rig_app.store.set_job("mastermind", {"bag_lb": 5, "time_s": 60, "level": "small"})
        script._walk(rig_app.store, sleep=lambda _s: None)
        doc = report.listing(report.root_for(rig_app.store))[0]
        self.assertEqual(doc["mode"], "mastermind")
        self.assertEqual(doc["plan_settings"]["bag_lb"], 5)


class Dashboard(unittest.TestCase):
    def test_both_doors_and_the_job_sheet_are_on_the_page(self):
        page = rig_app.app.test_client().get("/reveal").get_data(as_text=True)
        for needle in ('data-job="appraisal"', 'data-job="mastermind"', 'id="job-sheet"',
                       'name="bag_lb"', 'name="time_s"', 'name="level" value="small"', 'value="big"',
                       'id="plan-panel"', 'id="mode-chip"', 'id="plan-take"'):
            self.assertIn(needle, page)
        js = (Path(rig_app.KIT) / "noir.js").read_text()
        for needle in ("function applyJob", "function jobSheet", "'/api/plan'", "dataset.plan", "markLog("):
            self.assertIn(needle, js)
        css = (Path(rig_app.KIT) / "noir.css").read_text()
        for needle in (".job-pick", ".job-sheet", ".plan-panel", ".photo[data-plan]::after"):
            self.assertIn(needle, css)


if __name__ == "__main__":
    unittest.main()
