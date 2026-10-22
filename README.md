# DeskQueue

Python-only personal task manager with a local SQLite database. V1 is under development.

Scope: capture tasks, date deadlines, priority, tags, open/tag queries, today planning,
completion, overdue queries, weekly completion count, JSON import/export.
No web UI, cloud sync, AI, or notifications.

Runtime: Python 3.11 or newer, standard library only.

## Development

Install: `python -m pip install -e .`

Test: `python -m unittest discover -s tests -v`

See `CONTRACT.md` for the agreed integration interface.
