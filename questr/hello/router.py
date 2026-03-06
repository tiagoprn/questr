from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix='/hello', tags=['hello'])


def get_greeting() -> str:
    """Determine the greeting based on the current hour."""
    hour = datetime.now().hour
    if 0 <= hour <= 11:  # noqa: PLR2004
        return 'Good morning!'
    elif hour == 12:  # noqa: PLR2004
        return 'Good noon!'
    elif 13 <= hour <= 17:  # noqa: PLR2004
        return 'Good afternoon!'
    else:
        return 'Good evening!'


@router.get('')
async def hello() -> dict:
    """Return a greeting based on the time of day."""
    return {'message': get_greeting()}
