"""The bring-up journal: rotating file, env level, transition-only HW events."""
from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path

for _var in ("RIG_LOG_LEVEL", "RIG_LOG_JSON", "RIG_LOG_DIR"):
    os.environ.pop(_var, None)

from rig import journal


class JournalSetupTests(unittest.TestCase):
    def setUp(self):
        # setup() is a process-global; reset it per test.
        journal.setup._done = False
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["RIG_LOG_DIR"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("RIG_LOG_DIR", None)
        os.environ.pop("RIG_LOG_LEVEL", None)
        root = logging.getLogger()
        for h in root.handlers[:]:
            h.close()
            root.removeHandler(h)
        journal.setup._done = False
        self.tmp.cleanup()

    def test_setup_writes_a_rotating_file(self):
        path = journal.setup()
        self.assertTrue(str(path).endswith("rig.log"))
        logging.getLogger("rig.test").info("hello journal")
        for h in logging.getLogger().handlers:
            h.flush()
        self.assertIn("hello journal", Path(path).read_text())

    def test_setup_is_idempotent(self):
        journal.setup()
        n = len(logging.getLogger().handlers)
        journal.setup()
        self.assertEqual(len(logging.getLogger().handlers), n)

    def test_level_comes_from_env(self):
        os.environ["RIG_LOG_LEVEL"] = "DEBUG"
        journal.setup()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)


class HardwareEventTests(unittest.TestCase):
    def setUp(self):
        journal._reset_for_tests()
        self.records = []
        h = logging.Handler()
        h.emit = self.records.append
        logging.getLogger("rig.hw").addHandler(h)
        logging.getLogger("rig.hw").setLevel(logging.DEBUG)
        self.handler = h

    def tearDown(self):
        logging.getLogger("rig.hw").removeHandler(self.handler)

    def test_first_observation_logs(self):
        journal.event("camera", True)
        self.assertEqual(len(self.records), 1)
        self.assertIn("camera up", self.records[0].getMessage())

    def test_steady_state_is_silent(self):
        journal.event("wrist", True)
        journal.event("wrist", True)
        journal.event("wrist", True)
        self.assertEqual(len(self.records), 1)

    def test_transition_logs_down_with_detail(self):
        journal.event("rover", True)
        journal.event("rover", False, "last seen 42s ago")
        self.assertEqual(len(self.records), 2)
        rec = self.records[1]
        self.assertEqual(rec.levelno, logging.WARNING)
        self.assertIn("42s", rec.getMessage())

    def test_recovery_logs_up(self):
        journal.event("camera", True)
        journal.event("camera", False)
        journal.event("camera", True)
        self.assertEqual(len(self.records), 3)
        self.assertEqual(self.records[2].levelno, logging.INFO)

    def test_state_lookup(self):
        self.assertIsNone(journal.state("nothing"))
        journal.event("motor", False)
        self.assertFalse(journal.state("motor"))


if __name__ == "__main__":
    unittest.main()


class JsonFormatterTests(unittest.TestCase):
    def test_traceback_survives_json_mode(self):
        import sys
        rec = logging.LogRecord("rig.x", logging.ERROR, __file__, 1, "boom", (), None)
        try:
            raise ZeroDivisionError("boom")
        except ZeroDivisionError:
            rec.exc_info = sys.exc_info()
        out = journal._JsonFormatter().format(rec)
        self.assertIn('"exc"', out)
        self.assertIn("ZeroDivisionError", out)

    def test_clean_record_has_no_exc_key(self):
        rec = logging.LogRecord("rig.x", logging.INFO, __file__, 1, "fine", (), None)
        self.assertNotIn("exc", journal._JsonFormatter().format(rec))
