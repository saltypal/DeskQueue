# DeskQueue

Python-only personal task manager with a local SQLite database.

Scope: capture tasks, date deadlines, priority, tags, open/tag queries, today planning,
completion, overdue queries, weekly completion count, JSON import/export.
No web UI, cloud sync, AI, or notifications.

Runtime: Python 3.11 or newer, standard library only.

## Development

Install development tools: `python -m pip install -e ".[dev]"`

Run all tests: `python -m pytest -q`

See `CONTRACT.md` for the agreed integration interface.

## Daily use

```sh
python -m pip install .
deskqueue add "Finish assignment" --deadline 2026-10-25 --priority 1 --tag college
deskqueue list
deskqueue list --tag college
deskqueue today TASK_UUID
deskqueue today
deskqueue complete TASK_UUID
deskqueue overdue
deskqueue summary
deskqueue export backup.json
deskqueue import backup.json
```

Replace TASK_UUID with the complete ID printed by `add` or `list`. Repeat `--tag`
to supply more tags. Priority: 1 high, 2 normal (default), 3 low. Completed tasks
disappear from open, today, and overdue lists; repeated completion keeps its timestamp.

Each person has a separate database: `%LOCALAPPDATA%/DeskQueue/tasks.sqlite3` on
Windows, `~/Library/Application Support/DeskQueue/tasks.sqlite3` on macOS, and
`$XDG_DATA_HOME/DeskQueue/tasks.sqlite3` (default `~/.local/share`) on Linux.
Use `deskqueue --db PATH list` to select another SQLite file. Global options go
before the command. `python -m deskqueue` also works if the command isn't on PATH.

Deadlines are dates (YYYY-MM-DD). A task is overdue only after its deadline day.
`today` selects tasks for the local calendar day; completed selections are hidden.
`summary` counts completions in the local Monday–Sunday calendar week.
The system local timezone is the default; `--timezone Asia/Kolkata` selects an IANA
timezone explicitly. This option needs OS timezone data (or optional `tzdata` on
systems without it: `python -m pip install tzdata`); the default and explicit UTC
need no extra package. UTC timestamps are stored
internally. Date deadlines do not shift when timezone changes.

Exports contain all task data and no credentials. Use a new export filename:
existing files are never overwritten. Imports preserve IDs, skip identical tasks,
and reject conflicting or malformed data without partial imports. JSON is a manual
backup/interchange feature, not cloud sync. Keep backups private as needed.
