from datetime import datetime, timezone

MORNING_END_HOUR = 11
NOON_HOUR = 12
AFTERNOON_END_HOUR = 17


def get_greeting() -> str:
    """Determine the greeting based on the current hour (UTC)."""
    hour = datetime.now(timezone.utc).hour
    if hour <= MORNING_END_HOUR:
        return 'Good morning!'
    elif hour == NOON_HOUR:
        return 'Good noon!'
    elif hour <= AFTERNOON_END_HOUR:
        return 'Good afternoon!'
    else:
        return 'Good evening!'
