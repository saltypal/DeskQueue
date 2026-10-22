"""Exercise actual CLI processes and calendar boundaries against real SQLite."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from deskqueue.cli import calendar_day, week_bounds


class CalendarTests(unittest.TestCase):
    def test_week_uses_local_calendar(self):
        zone = timezone(timedelta(hours=5, minutes=30))
        start, end = week_bounds(datetime(2026, 10, 25, 20, tzinfo=timezone.utc), zone)
        self.assertEqual(start, datetime(2026, 10, 25, 18, 30, tzinfo=timezone.utc))
        self.assertEqual(end - start, timedelta(days=7))

    def test_strict_date(self):
        import argparse
        for value in ("20261022", "2026-02-30", "2026-W43-4"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                calendar_day(value)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = self.root / "tasks.sqlite3"

    def run_cli(self, *args, db=None, expected=0):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        result = subprocess.run([sys.executable, "-m", "deskqueue", "--db",
                                 str(db or self.db), *args], text=True,
                                capture_output=True, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout if expected == 0 else result.stderr

    def add(self, title="Example", *args):
        return self.run_cli("add", title, *args).strip().split()[-1]

    def test_capture_filter_plan_complete_and_isolation(self):
        task_id = self.add("Write draft", "--tag", " Work ", "--priority", "1")
        self.assertIn("Write draft", self.run_cli("list", "--tag", "work"))
        self.assertNotIn("Write draft", self.run_cli("list", "--tag", "home"))
        self.assertIn(task_id, self.run_cli("today", task_id))
        self.assertIn(task_id, self.run_cli("today"))
        self.assertEqual(self.run_cli("list", db=self.root / "other.sqlite3"), "No tasks.\n")
        self.run_cli("complete", task_id)
        self.run_cli("complete", task_id)
        self.assertEqual(self.run_cli("list"), "No tasks.\n")
        self.assertEqual(self.run_cli("today"), "No tasks.\n")
        self.assertIn("Completed this week: 1", self.run_cli("summary"))

    def test_overdue_and_roundtrip(self):
        task_id = self.add("Past task", "--deadline", "2000-01-01")
        self.assertIn(task_id, self.run_cli("overdue"))
        export = self.root / "backup.json"
        self.run_cli("export", str(export))
        other = self.root / "restored.sqlite3"
        self.assertIn("Imported 1", self.run_cli("import", str(export), db=other))
        self.assertIn("Imported 0", self.run_cli("import", str(export), db=other))
        self.assertIn(task_id, self.run_cli("list", db=other))
        self.run_cli("export", str(export), expected=1)
        self.assertIn("schema_version", export.read_text(encoding="utf-8"))

    def test_invalid_input_and_import_leave_data_intact(self):
        self.add("Keep me")
        self.run_cli("add", "   ", expected=1)
        self.run_cli("add", "Bad priority", "--priority", "4", expected=2)
        self.run_cli("add", "Bad date", "--deadline", "2026-02-30", expected=2)
        self.run_cli("complete", "missing", expected=1)
        bad = self.root / "bad.json"
        bad.write_text('{"schema_version":1,"tasks":[{}]}', encoding="utf-8")
        self.run_cli("import", str(bad), expected=1)
        self.assertIn("Keep me", self.run_cli("list"))


if __name__ == "__main__":
    unittest.main()
