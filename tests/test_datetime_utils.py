from datetime import timezone

from nextinai.core.datetime_utils import parse_datetime


def test_parse_datetime_supports_trailing_z() -> None:
    parsed = parse_datetime("2026-04-29T21:58:15Z")

    assert parsed.tzinfo == timezone.utc
    assert parsed.year == 2026
    assert parsed.month == 4
    assert parsed.day == 29
