"""UTC upload clocks and six-calendar-month retention boundaries."""
from calendar import monthrange
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Retention timestamps require an explicit timezone')
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Retention timestamps require an explicit timezone')
    return parsed.astimezone(timezone.utc)


def expires_at(uploaded_at: str) -> datetime:
    uploaded = parse_time(uploaded_at)
    month_index = uploaded.year * 12 + uploaded.month - 1 + 6
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return uploaded.replace(year=year, month=month,
                            day=min(uploaded.day, monthrange(year, month)[1]))
