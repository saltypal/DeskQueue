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

    def test_explicit_timezone_not_system_timezone(self):
        zone = timezone(timedelta(hours=-7))
        start, end = week_bounds(datetime(2026, 10, 26, 2, tzinfo=timezone.utc), zone)
        self.assertEqual(start, datetime(2026, 10, 19, 7, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 10, 26, 7, tzinfo=timezone.utc))

    def test_dst_week_boundary(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            zone = ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            self.skipTest("IANA timezone database unavailable")
        start, end = week_bounds(datetime(2026, 3, 8, 18, tzinfo=timezone.utc), zone)
        self.assertEqual(start, datetime(2026, 3, 2, 5, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 3, 9, 4, tzinfo=timezone.utc))


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

    def test_week_summary_and_overdue_at_calendar_boundaries(self):
        import contextlib
        import io
        from deskqueue.cli import main
        from deskqueue.storage import Store

        monday = datetime(2026, 10, 19, tzinfo=timezone.utc)
        store = Store(self.db)
        try:
            for offset in (-1, 0, 6 * 86400, 7 * 86400):
                instant = monday + timedelta(seconds=offset)
                task = store.add_task(str(offset), now=instant)
                store.complete_task(task.id, now=instant)
            store.add_task("Due today", deadline=monday.date(), now=monday)
            store.add_task("Due yesterday", deadline=(monday - timedelta(days=1)).date(), now=monday)
        finally:
            store.close()
        def invoke(command):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--db", str(self.db), "--timezone", "UTC", command], now=monday)
            self.assertEqual(result, 0)
            return output.getvalue()
        self.assertIn("Completed this week: 2", invoke("summary"))
        overdue = invoke("overdue")
        self.assertIn("Due yesterday", overdue)
        self.assertNotIn("Due today", overdue)

    def test_today_bad_id_does_not_partially_plan(self):
        task_id = self.add("Leave unplanned")
        self.run_cli("today", task_id, "missing", expected=1)
        self.assertEqual(self.run_cli("today"), "No tasks.\n")


if __name__ == "__main__":
    unittest.main()
