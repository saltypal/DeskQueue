from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4

import pytest
from deskqueue.models import Task, ValidationError


def task(**changes):
    values = dict(id=str(uuid4()), title=' task ', created_at=datetime(2026, 10, 22, tzinfo=timezone.utc))
    values.update(changes)
    return Task(**values)


def test_normalization_and_immutability():
    value = task(tags=[' Work ', 'work', 'HOME'], created_at=datetime(2026, 10, 22, 6, tzinfo=timezone(timedelta(hours=6))))
    assert value.title == 'task'
    assert value.tags == ('home', 'work')
    assert value.created_at == datetime(2026, 10, 22, tzinfo=timezone.utc)
    with pytest.raises(FrozenInstanceError):
        value.title = 'changed'


@pytest.mark.parametrize('changes', [
    {'id': 'bad'}, {'id': 1}, {'title': ' '}, {'title': None},
    {'priority': True}, {'priority': 0}, {'priority': 2.0},
    {'tags': [' ']}, {'tags': 'work'}, {'tags': [1]},
    {'created_at': datetime(2026, 10, 22)}, {'created_at': None},
    {'deadline': '2026-10-22'}, {'deadline': datetime(2026, 10, 22)},
    {'completed_at': datetime(2026, 10, 22)}, {'planned_for': 'bad'},
])
def test_invalid_values(changes):
    with pytest.raises(ValidationError):
        task(**changes)
