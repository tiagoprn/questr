from fastapi import APIRouter

from questr.hello.schemas import HelloResponse
from questr.hello.service import HelloService

router = APIRouter(prefix='/hello', tags=['hello'])


@router.get('', response_model=HelloResponse)
async def hello() -> HelloResponse:
    service = HelloService()
    return HelloResponse(message=service.get_greeting())
