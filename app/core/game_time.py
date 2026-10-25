"""Game clock helpers for the 8:1 calendar.

4 game years ≈ 6 real months → 1 game year ≈ 45.625 real days.
Activity durations are scaled separately (short real waits, full age gain).
"""

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

# Real seconds in one game day at 8:1 (approx):
# 365.25 game days / year, 4 years = 6 months = 182.625 real days
# → 1 game day ≈ 3.0 real hours
SECONDS_PER_GAME_DAY = 3 * 60 * 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def real_duration_for_game_days(game_days: float) -> timedelta:
    """Convert game-time days to wall-clock duration at the configured ratio."""
    settings = get_settings()
    # Base 8:1 mapping; ratio scales relative to 8
    scale = 8 / max(settings.game_time_ratio, 1)
    return timedelta(seconds=SECONDS_PER_GAME_DAY * game_days * scale)


def age_years_from_game_days(game_days: float) -> float:
    return game_days / 365.25
