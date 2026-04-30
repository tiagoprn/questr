from fastapi import APIRouter
from pydantic import BaseModel

from questr.domains.hello.service import get_greeting

router = APIRouter(prefix='/hello', tags=['hello'])


class HelloResponse(BaseModel):
    message: str

    model_config = {'from_attributes': True}


@router.get('', response_model=HelloResponse)
async def hello() -> HelloResponse:
    return HelloResponse(message=get_greeting())
