from datetime import datetime, timedelta, timezone


def get_week_key(dt: datetime) -> str:
    """Return 'YY_WW' for a given datetime, e.g. '26_08'."""
    iso = dt.isocalendar()
    return f"{iso.year % 100:02d}_{iso.week:02d}"


def parse_week_key(key: str) -> tuple[int, int]:
    """Parse 'YY_WW' -> (full_year, week_number)."""
    yy, ww = key.split("_")
    return 2000 + int(yy), int(ww)


def week_bounds(year: int, week: int) -> tuple[datetime, datetime]:
    """Return (Monday 00:00:00 UTC, Sunday 23:59:59 UTC) for an ISO year/week."""
    # Jan 4 is always in ISO week 1
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    monday = week1_monday + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def max_week_in_year(year: int) -> int:
    """Return 52 or 53 depending on whether the ISO year has a week 53."""
    dec28 = datetime(year, 12, 28, tzinfo=timezone.utc)
    return dec28.isocalendar().week


def weeks_in_year(year: int) -> list[str]:
    """All 'YY_WW' keys for a given ISO year."""
    return [f"{year % 100:02d}_{w:02d}" for w in range(1, max_week_in_year(year) + 1)]


def current_week_key() -> str:
    return get_week_key(datetime.now(timezone.utc))
