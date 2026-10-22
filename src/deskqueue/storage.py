"""Local SQLite persistence and atomic JSON interchange."""
import json
import re
import sqlite3
from dataclasses import asdict, fields, replace
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from .models import Task, ValidationError, NotFoundError, valid_id, valid_date, utc, tag as normalize_tag


def _record(task):
    result = asdict(task)
    for key in ('deadline', 'planned_for', 'created_at', 'completed_at'):
        value = result[key]
        result[key] = value.isoformat() if value is not None else None
    result['tags'] = list(task.tags)
    return result


def _parse(record):
    if not isinstance(record, dict) or set(record) != {f.name for f in fields(Task)}:
        raise ValidationError('Invalid task fields')
    record = record.copy()
    try:
        for key in ('deadline', 'planned_for'):
            value = record[key]
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError
                record[key] = date.fromisoformat(value)
        for key in ('created_at', 'completed_at'):
            value = record[key]
            if value is not None:
                if not isinstance(value, str) or 'T' not in value:
                    raise ValueError
                record[key] = datetime.fromisoformat(value)
        return Task(**record)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError('Invalid task record: ' + str(exc)) from None


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        version = self._db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise ValidationError('Unsupported database schema version')
        with self._db:
            self._db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            self._db.execute('PRAGMA user_version=1')

    def _insert(self, task):
        self._db.execute('INSERT INTO tasks VALUES (?, ?)', (task.id, json.dumps(_record(task))))

    def _save(self, task):
        self._db.execute('UPDATE tasks SET payload=? WHERE id=?', (json.dumps(_record(task)), task.id))

    def _all(self):
        return [_parse(json.loads(row[0])) for row in self._db.execute('SELECT payload FROM tasks')]

    @staticmethod
    def _sort(tasks):
        return sorted(tasks, key=lambda t: (t.priority, t.deadline is None, t.deadline or date.max, t.created_at, t.id))

    def add_task(self, title, *, deadline=None, priority=2, tags=(), now):
        # Materialize general Sequence inputs while rejecting a single string.
        if isinstance(tags, (str, bytes)):
            raise ValidationError('Tags must be a sequence of strings')
        try:
            tags = tuple(tags)
        except TypeError:
            raise ValidationError('Tags must be a sequence of strings') from None
        task = Task(str(uuid4()), title, deadline, priority, tags, now)
        with self._db:
            self._insert(task)
        return task

    def get_task(self, task_id):
        task_id = valid_id(task_id)
        row = self._db.execute('SELECT payload FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(task_id)
        return _parse(json.loads(row[0]))

    def list_open(self, *, tag=None):
        wanted = normalize_tag(tag) if tag is not None else None
        return self._sort(t for t in self._all() if t.completed_at is None and (wanted is None or wanted in t.tags))

    def plan_task(self, task_id, planned_for):
        valid_date(planned_for)
        with self._db:
            task = replace(self.get_task(task_id), planned_for=planned_for)
            self._save(task)
        return task

    def list_planned(self, day):
        valid_date(day)
        return [t for t in self.list_open() if t.planned_for == day]

    def complete_task(self, task_id, *, now):
        now = utc(now)
        with self._db:
            task = self.get_task(task_id)
            if task.completed_at is None:
                task = replace(task, completed_at=now)
                self._save(task)
        return task

    def list_overdue(self, today):
        valid_date(today)
        return [t for t in self.list_open() if t.deadline is not None and t.deadline < today]

    def completion_summary(self, start, end):
        start, end = utc(start), utc(end)
        if end < start:
            raise ValidationError('End must not precede start')
        return sum(t.completed_at is not None and start <= t.completed_at < end for t in self._all())

    def export_json(self):
        return json.dumps({'schema_version': 1, 'tasks': [_record(t) for t in self._sort(self._all())]}, indent=2)

    def import_json(self, payload):
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValidationError('Duplicate JSON object key')
                result[key] = value
            return result
        try:
            document = json.loads(payload, object_pairs_hook=unique_keys)
        except (ValueError, TypeError) as exc:
            raise ValidationError('Invalid JSON: ' + str(exc)) from None
        if (not isinstance(document, dict) or set(document) != {'schema_version', 'tasks'}
                or type(document['schema_version']) is not int or document['schema_version'] != 1
                or not isinstance(document['tasks'], list)):
            raise ValidationError('Expected schema_version 1 and tasks array')
        incoming = {}
        for record in document['tasks']:
            task = _parse(record)
            if task.id in incoming and incoming[task.id] != task:
                raise ValidationError('Conflicting duplicate task ID')
            incoming[task.id] = task
        # Lock before checking conflicts so concurrent writers cannot invalidate checks.
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            existing = {t.id: t for t in self._all()}
            for task in incoming.values():
                if task.id in existing and existing[task.id] != task:
                    raise ValidationError('Conflicting existing task ID')
            new = [t for t in incoming.values() if t.id not in existing]
            for task in new:
                self._insert(task)
        return len(new)

    def close(self):
        self._db.close()
