from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix='/hello', tags=['hello'])


class HelloResponse(BaseModel):
    message: str = Field(example="Good morning!")


def get_greeting() -> str:
    """Determine the greeting based on the current hour."""
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour <= 11:  # noqa: PLR2004
        return 'Good morning!'
    elif hour == 12:  # noqa: PLR2004
        return 'Good noon!'
    elif 13 <= hour <= 17:  # noqa: PLR2004
        return 'Good afternoon!'
    else:
        return 'Good evening!'


@router.get('', response_model=HelloResponse)
async def hello() -> HelloResponse:
    """Return a greeting based on the time of day (UTC)."""
    return HelloResponse(message=get_greeting())
