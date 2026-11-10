"""UTC-aware SQLAlchemy timestamps, including SQLite's offset-free storage."""

from datetime import UTC

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp writes must include a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # Existing application-generated SQLite values have always been written in UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
