"""DeskQueue's standard-library command line interface."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def default_db() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "DeskQueue" / "tasks.sqlite3"


def calendar_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("use a valid date in YYYY-MM-DD format") from None


def week_bounds(now: datetime, zone=None) -> tuple[datetime, datetime]:
    """Convert each local Monday midnight separately (including DST changes)."""
    local_day = now.astimezone(zone).date()
    monday = local_day - timedelta(days=local_day.weekday())
    start = datetime.combine(monday, time.min, tzinfo=zone).astimezone()
    end = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone).astimezone()
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Personal tasks in local SQLite storage")
    p.add_argument("--db", type=Path, default=default_db(), help="SQLite file path")
    p.add_argument("--timezone", help="IANA calendar timezone; default: system local")
    commands = p.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="capture a task")
    add.add_argument("title")
    add.add_argument("--deadline", type=calendar_day)
    add.add_argument("--priority", type=int, choices=(1, 2, 3), default=2)
    add.add_argument("--tag", action="append", default=[], help="repeat for multiple tags")
    listing = commands.add_parser("list", help="list open tasks")
    listing.add_argument("--tag")
    today = commands.add_parser("today", help="list today's tasks, or select IDs for today")
    today.add_argument("ids", nargs="*")
    complete = commands.add_parser("complete", help="complete a task")
    complete.add_argument("id")
    commands.add_parser("overdue", help="list open tasks with past deadlines")
    commands.add_parser("summary", help="count completions this Monday–Sunday week")
    for command in ("export", "import"):
        cmd = commands.add_parser(command, help=f"{command} JSON")
        cmd.add_argument("file", type=Path)
    return p


def show(tasks) -> None:
    if not tasks:
        print("No tasks.")
    for task in tasks:
        deadline = task.deadline.isoformat() if task.deadline else "-"
        print(f"{task.id}  P{task.priority}  due:{deadline}  {task.title}"
              + ("  #" + " #".join(task.tags) if task.tags else ""))


def main(argv=None, *, now: datetime | None = None) -> int:
    args = parser().parse_args(argv)
    from .models import NotFoundError, ValidationError
    from .storage import Store

    store = None
    try:
        zone = ZoneInfo(args.timezone) if args.timezone else None
        instant = now if now is not None else datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")
        today = instant.astimezone(zone).date()
        args.db.parent.mkdir(parents=True, exist_ok=True)
        store = Store(args.db)
        if args.command == "add":
            task = store.add_task(args.title, deadline=args.deadline, priority=args.priority,
                                  tags=args.tag, now=instant)
            print(f"Added {task.id}")
        elif args.command == "list":
            show(store.list_open(tag=args.tag))
        elif args.command == "today":
            # Validate all IDs before planning, so a typo doesn't partially select tasks.
            for task_id in args.ids:
                if store.get_task(task_id).completed_at is not None:
                    raise ValueError("completed tasks cannot be selected for today")
            for task_id in args.ids:
                store.plan_task(task_id, today)
            show(store.list_planned(today))
        elif args.command == "complete":
            task = store.complete_task(args.id, now=instant)
            print(f"Completed {task.id}")
        elif args.command == "overdue":
            show(store.list_overdue(today))
        elif args.command == "summary":
            start, end = week_bounds(instant, zone)
            count = store.completion_summary(start, end)
            print(f"Completed this week: {count}")
        elif args.command == "export":
            # Refuse accidental replacement of an existing export or database.
            payload = store.export_json()
            with args.file.open("x", encoding="utf-8") as output:
                output.write(payload)
                output.write("\n")
            print(f"Exported to {args.file}")
        elif args.command == "import":
            count = store.import_json(args.file.read_text(encoding="utf-8"))
            print(f"Imported {count} task(s)")
        return 0
    except (NotFoundError, ValidationError, ValueError, OSError, sqlite3.Error,
            ZoneInfoNotFoundError) as exc:
        print(f"deskqueue: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()
