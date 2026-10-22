"""Validated, immutable DeskQueue task values."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID


class ValidationError(ValueError):
    """Input does not satisfy the task contract."""


class NotFoundError(LookupError):
    """No task has the requested identifier."""


def valid_id(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('Invalid task UUID') from None


def valid_date(value):
    if type(value) is not date:
        raise ValidationError('Expected a calendar date')
    return value


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError('Expected an aware timestamp')
    return value.astimezone(timezone.utc)


def tag(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError('Tags must be nonempty strings')
    return value.strip().lower()


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    deadline: date | None = None
    priority: int = 2
    tags: tuple[str, ...] = ()
    created_at: datetime = None
    completed_at: datetime | None = None
    planned_for: date | None = None

    def __post_init__(self):
        object.__setattr__(self, 'id', valid_id(self.id))
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError('Title must be nonempty')
        object.__setattr__(self, 'title', self.title.strip())
        if type(self.priority) is not int or self.priority not in (1, 2, 3):
            raise ValidationError('Priority must be 1, 2 or 3')
        if not isinstance(self.tags, (list, tuple)):
            raise ValidationError('Tags must be a sequence of strings')
        object.__setattr__(self, 'tags', tuple(sorted({tag(t) for t in self.tags})))
        for field in ('deadline', 'planned_for'):
            if getattr(self, field) is not None:
                valid_date(getattr(self, field))
        object.__setattr__(self, 'created_at', utc(self.created_at))
        if self.completed_at is not None:
            object.__setattr__(self, 'completed_at', utc(self.completed_at))
