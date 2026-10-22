import json
import subprocess
import sys
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4

import pytest
from deskqueue.models import ValidationError, NotFoundError
from deskqueue.storage import Store

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / 'tasks.db')
    yield value
    value.close()


def test_persistence_other_process_and_isolation(tmp_path):
    path = tmp_path / 'nested' / 'tasks.db'
    store = Store(path)
    task = store.add_task('Persist', now=NOW)
    store.close()
    result = subprocess.run([sys.executable, '-c',
        'from deskqueue.storage import Store; import sys; from pathlib import Path; s=Store(Path(sys.argv[1])); print(s.get_task(sys.argv[2]).title); s.close()',
        str(path), task.id], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'Persist'
    other = Store(tmp_path / 'other.db')
    assert other.list_open() == []
    other.close()


def test_filters_order_and_calendar(store):
    low = store.add_task('low', priority=3, now=NOW)
    no_date = store.add_task('no date', now=NOW)
    due = store.add_task('due today', deadline=date(2026, 10, 22), tags=[' Work '], now=NOW)
    past = store.add_task('past', deadline=date(2026, 10, 21), tags=['work'], now=NOW)
    urgent = store.add_task('urgent', priority=1, now=NOW)
    assert [t.id for t in store.list_open()] == [urgent.id, past.id, due.id, no_date.id, low.id]
    assert [t.id for t in store.list_open(tag=' WORK ')] == [past.id, due.id]
    assert store.list_overdue(date(2026, 10, 22)) == [past]
    planned = store.plan_task(past.id, date(2026, 10, 22))
    assert store.list_planned(date(2026, 10, 22)) == [planned]
    done = store.complete_task(past.id, now=NOW)
    assert store.complete_task(past.id, now=NOW + timedelta(days=1)) == done
    assert store.list_planned(date(2026, 10, 22)) == []
    assert store.list_overdue(date(2026, 10, 22)) == []


def test_summary_half_open_and_offsets(store):
    start = datetime(2026, 10, 19, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    end = start + timedelta(days=7)
    for i, instant in enumerate([start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end]):
        t = store.add_task(str(i), now=NOW)
        store.complete_task(t.id, now=instant)
    assert store.completion_summary(start, end) == 2
    assert store.completion_summary(start, start) == 0
    with pytest.raises(ValidationError):
        store.completion_summary(end, start)


def test_roundtrip_and_duplicates(store, tmp_path):
    first = store.add_task('one', tags=['a'], deadline=date(2026, 10, 21), now=NOW)
    store.plan_task(first.id, date(2026, 10, 22))
    store.complete_task(first.id, now=NOW)
    store.add_task('two', now=NOW)
    data = json.loads(store.export_json())
    data['tasks'].append(data['tasks'][0])
    other = Store(tmp_path / 'copy.db')
    assert other.import_json(json.dumps(data)) == 2
    assert other.export_json() == store.export_json()
    assert other.import_json(store.export_json()) == 0
    other.close()


@pytest.mark.parametrize('corruption', ['title', 'date', 'timestamp', 'priority', 'fields', 'duplicate', 'existing'])
def test_invalid_import_is_atomic(store, corruption):
    existing = store.add_task('original', now=NOW)
    before = store.export_json()
    original = json.loads(before)['tasks'][0]
    fresh = dict(original, id=str(uuid4()), title='new')
    bad = dict(original, id=str(uuid4()))
    if corruption == 'title': bad['title'] = ' '
    if corruption == 'date': bad['deadline'] = '20261022'
    if corruption == 'timestamp': bad['created_at'] = '2026-10-22T00:00:00'
    if corruption == 'priority': bad['priority'] = True
    if corruption == 'fields': bad['extra'] = 'unknown'
    if corruption == 'duplicate': bad.update(id=fresh['id'], title='conflict')
    if corruption == 'existing': bad.update(id=existing.id, title='conflict')
    with pytest.raises(ValidationError):
        store.import_json(json.dumps({'schema_version': 1, 'tasks': [fresh, bad]}))
    assert store.export_json() == before


@pytest.mark.parametrize('payload', ['{}', '[]', '{', '{"schema_version":true,"tasks":[]}', '{"schema_version":1,"tasks":[],"tasks":[]}'])
def test_invalid_documents(store, payload):
    with pytest.raises(ValidationError):
        store.import_json(payload)


def test_missing_and_invalid_queries(store):
    with pytest.raises(NotFoundError): store.get_task(str(uuid4()))
    with pytest.raises(ValidationError): store.get_task('nope')
    with pytest.raises(ValidationError): store.list_open(tag=' ')
    with pytest.raises(ValidationError): store.list_overdue(datetime.now())


def test_null_deadline_last_and_stable_ties(store):
    undated = store.add_task('undated', now=NOW - timedelta(days=1))
    last_date = store.add_task('dated', deadline=date.max, now=NOW)
    tied = [store.add_task(str(i), deadline=date.max, now=NOW) for i in range(3)]
    assert [t.id for t in store.list_open()] == sorted(t.id for t in [last_date, *tied]) + [undated.id]


def test_import_offset_equivalence(store):
    value = store.add_task('offset', now=NOW)
    doc = json.loads(store.export_json())
    doc['tasks'][0]['created_at'] = '2026-10-22T17:30:00+05:30'
    assert store.import_json(json.dumps(doc)) == 0
    assert store.get_task(value.id).created_at.tzinfo == timezone.utc
