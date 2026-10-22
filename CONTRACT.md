# Frozen V1 agreement

Host owns CLI, packaging, README, tests/test_cli.py and final integration.
Storage teammate owns src/deskqueue/models.py, src/deskqueue/storage.py,
tests/test_models.py and tests/test_storage.py. No overlapping edits without handover.
Branches: host/cli and friend/storage from the shared baseline. Host reviews before
integration; no force pushes. Each side consolidates its own subagent results.

## Data and calendar

models.py exports frozen Task dataclass, ValidationError and NotFoundError.
Task fields: id (UUID str), title (stripped nonempty str), deadline (date or None),
priority (int 1 high, 2 normal default, 3 low; reject bool), tags (tuple[str,...]),
created_at (aware datetime), completed_at (aware datetime or None),
planned_for (date or None). Strip/lowercase/sort/deduplicate tags; reject empty tags.
Accept aware timestamp offsets and normalize to UTC. Reject naive timestamps.

Deadlines are calendar dates, YYYY-MM-DD. Local calendar today drives planning and
overdue: open and deadline < today. Week is local Monday midnight through next
Monday midnight, converted to aware UTC half-open query boundaries. Inject clocks,
dates and timezone in tests. Completed tasks are excluded from open/today/overdue.

## Store API

Store(path: pathlib.Path) in storage.py initializes/migrates the SQLite database.
No connection state is shared between users. Caller closes the Store explicitly.

```python
add_task(title, *, deadline: date | None = None, priority: int = 2,
         tags: Sequence[str] = (), now: datetime) -> Task
get_task(task_id: str) -> Task
list_open(*, tag: str | None = None) -> list[Task]
plan_task(task_id: str, planned_for: date) -> Task
list_planned(day: date) -> list[Task]
complete_task(task_id: str, *, now: datetime) -> Task
list_overdue(today: date) -> list[Task]
completion_summary(start: datetime, end: datetime) -> int
export_json() -> str
import_json(payload: str) -> int
close() -> None
```

Completion is idempotent (preserve original timestamp). Lists sort by priority,
deadline (None last), created_at, id. Missing IDs raise NotFoundError. Invalid
values raise ValidationError.

JSON has schema_version=1 and tasks array. Dates use YYYY-MM-DD, timestamps ISO8601
UTC. Preserve IDs and timestamps. Validate entire document before writes. Within
payload and against existing rows, identical duplicate IDs are skipped; conflicting
duplicates fail atomically. Return inserted count. Export/import roundtrip retains
all Task fields.

## CLI and acceptance

Commands: add, list [--tag], today [IDs...], complete ID, overdue, summary,
export FILE, import FILE; global --db PATH. today without IDs lists planned open
tasks; with IDs selects them for today. Default DB is in the user's local data dir.

Meaningful checks: installed commands across processes, DB isolation, title/date/
priority/tag validation, persistence, filter/order, idempotent completion, correct
today/overdue/week boundaries, JSON roundtrip and atomic invalid/conflict rejection.
