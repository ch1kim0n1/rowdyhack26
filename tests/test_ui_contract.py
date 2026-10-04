"""Device status and printed-case contracts used by the UI."""
import time
import unittest
from unittest.mock import patch

from test_contract import blank, fresh_store

from rig import app as hub


class UIContracts(unittest.TestCase):
    def setUp(self):
        self.old_store = hub.store
        hub.store = fresh_store()
        blank(hub.store)
        self.client = hub.app.test_client()

    def tearDown(self):
        hub.store = self.old_store

    def test_rover_timeout_status_does_not_kill_camera(self):
        for age, expected in [(0, True), (hub.ROVER_TTL + 1, False)]:
            with patch.object(hub._rover, "addr", "127.0.0.1"), patch.object(hub._rover, "seen", time.monotonic() - age):
                state = self.client.get("/state.json").get_json()
            self.assertEqual(state["rover_ok"], expected)
            self.assertTrue(state["camera_ok"])

    def test_case_format_and_untrusted_exhibit_names(self):
        with hub.store._lock:
            hub.store._case_no = 42
        hub.store.add_item({"item": '<img src=x onerror="alert(1)">', "value_usd": 400})
        manifest = self.client.get("/manifest").get_data(as_text=True)
        dashboard = self.client.get("/").get_data(as_text=True)
        self.assertIn("CASE NO. 0042", manifest)
        self.assertIn("0042</span>", dashboard)
        self.assertNotIn('<img src=x', manifest)
        self.assertIn("&lt;img", manifest)

    def test_wrist_rec_phase_has_two_second_period(self):
        with patch.object(hub.time, "time", return_value=100.75):
            self.assertEqual(self.client.get("/wrist.json").get_json()["rec_phase_ms"], 750)

    def test_premiere_portal_and_title_assets_and_seekable_film_are_served(self):
        """The premiere's camera move and particle title load through Flask; the film must seek."""
        with self.client.get("/premiere") as response:
            page = response.get_data(as_text=True)
        for name in ("premiere-portal.js", "premiere-portal.css",
                     "premiere-title-particles.js", "premiere-title-particles.css",
                     "scroll-cinema.js", "motion-presets.js", "webgl-scenes.js",
                     "cinematic-motion.css", "anime.min.js"):
            self.assertIn(name, page)
            with self.client.get("/" + name) as response:
                self.assertEqual(response.status_code, 200, name)
                self.assertGreater(len(response.get_data()), 100)
        with self.client.get("/media/film-960.mp4", headers={"Range": "bytes=0-255"}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertTrue(response.headers["Content-Range"].startswith("bytes 0-255/"))
            self.assertEqual(len(response.get_data()), 256)
