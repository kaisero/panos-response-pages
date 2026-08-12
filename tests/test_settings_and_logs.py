"""Settings precedence, and that logging obeys it.

The rule these pin down: a CLI flag always beats the settings file. A -q in a
shell script that a stale settings file could override would be a nasty way to
lose the output you were relying on.
"""

import logging
import pathlib
import tempfile
import unittest

import pytest

from panos_response_pages import logs, settings

pytestmark = pytest.mark.unit


def write(text: str) -> pathlib.Path:
    path = pathlib.Path(tempfile.mkdtemp()) / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestSettings(unittest.TestCase):
    def test_absent_file_yields_defaults(self):
        s = settings.load(pathlib.Path(tempfile.mkdtemp()) / "nothing.yaml")
        self.assertEqual(s.log.level, "warning")
        self.assertFalse(s.log.file)
        self.assertIsNone(s.source)

    def test_empty_file_yields_defaults(self):
        s = settings.load(write(""))
        self.assertEqual(s.log.level, "warning")

    def test_partial_file_keeps_the_other_defaults(self):
        s = settings.load(write("log:\n  level: debug\n"))
        self.assertEqual(s.log.level, "debug")
        self.assertFalse(s.log.file, "an unset key must not change")
        self.assertEqual(s.log.backups, 5)

    def test_rotation_settings_are_read(self):
        s = settings.load(write("log:\n  file: true\n  rotate:\n    max_bytes: 42\n    backups: 2\n"))
        self.assertTrue(s.log.file)
        self.assertEqual(s.log.max_bytes, 42)
        self.assertEqual(s.log.backups, 2)

    def test_a_typo_is_an_error_not_a_silent_no_op(self):
        """Believing file logging is on when it is not is exactly the class of
        quiet failure this project refuses everywhere else."""
        with self.assertRaises(ValueError) as caught:
            settings.load(write("log:\n  levl: info\n"))
        self.assertIn("levl", str(caught.exception))

    def test_a_non_mapping_document_is_rejected(self):
        with self.assertRaises(ValueError):
            settings.load(write("- a\n- b\n"))

    def test_log_must_be_a_mapping(self):
        with self.assertRaises(ValueError):
            settings.load(write("log: nonsense\n"))

    def test_tilde_in_the_log_dir_is_expanded(self):
        s = settings.load(write("log:\n  dir: ~/somewhere\n"))
        self.assertTrue(s.log.dir.is_absolute())
        self.assertNotIn("~", str(s.log.dir))

    def test_explicit_null_yields_defaults(self):
        # A present key with value None is not the same as an absent key --
        # dict.get(key, default) only supplies the default in the latter case.
        # A settings file rendered from a template with an unset variable
        # produces exactly this shape.
        s = settings.load(write("log:\n  level: null\n  rotate:\n    max_bytes: null\n    backups: null\n"))
        self.assertEqual(s.log.level, "warning")
        self.assertEqual(s.log.max_bytes, 1_048_576)
        self.assertEqual(s.log.backups, 5)


class TestLevelPrecedence(unittest.TestCase):
    def _with(self, level):
        return settings.load(write(f"log:\n  level: {level}\n"))

    def test_cli_quiet_beats_the_settings_file(self):
        self.assertEqual(logs.resolve_level(self._with("debug"), verbose=0, quiet=True), logging.ERROR)

    def test_cli_verbose_beats_the_settings_file(self):
        self.assertEqual(logs.resolve_level(self._with("error"), verbose=1, quiet=False), logging.INFO)
        self.assertEqual(logs.resolve_level(self._with("error"), verbose=2, quiet=False), logging.DEBUG)

    def test_the_settings_file_applies_when_no_flag_is_given(self):
        self.assertEqual(logs.resolve_level(self._with("info"), verbose=0, quiet=False), logging.INFO)

    def test_an_unrecognised_level_falls_back_rather_than_crashing(self):
        self.assertEqual(logs.resolve_level(self._with("chatty"), verbose=0, quiet=False), logging.WARNING)


class TestLogHandlers(unittest.TestCase):
    def tearDown(self):
        logs.get().handlers.clear()

    def test_file_logging_is_off_unless_asked_for(self):
        logger = logs.configure(settings.Settings())
        self.assertEqual([h for h in logger.handlers if hasattr(h, "baseFilename")], [])

    def test_file_logging_writes_where_the_settings_say(self):
        target = pathlib.Path(tempfile.mkdtemp()) / "logs"
        cfg = settings.Settings()
        cfg.log.file = True
        cfg.log.dir = target
        logger = logs.configure(cfg, verbose=1)
        logger.info("hello")
        for handler in logger.handlers:
            handler.flush()
        self.assertTrue((target / "panos-response-pages.log").is_file())

    def test_the_logger_does_not_hijack_the_root_logger(self):
        """A library that reconfigures the root logger surprises whatever
        imports it."""
        logger = logs.configure(settings.Settings())
        self.assertFalse(logger.propagate)

    def test_json_formatter_emits_one_object_per_record(self):
        import json

        record = logging.LogRecord("x", logging.INFO, "f", 1, "built %d pages", (48,), None)
        payload = json.loads(logs.JsonFormatter().format(record))
        self.assertEqual(payload["level"], "info")
        self.assertEqual(payload["event"], "built 48 pages")

    def test_json_formatter_carries_extra_fields(self):
        import json

        record = logging.LogRecord("x", logging.INFO, "f", 1, "sized", None, None)
        record.page = "url-block-page"
        payload = json.loads(logs.JsonFormatter().format(record))
        self.assertEqual(payload["page"], "url-block-page")
