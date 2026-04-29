from fastapi import APIRouter

from questr.domains.hello.api import router as hello_router
from questr.domains.users.api import router as users_router

api_router = APIRouter(prefix='/api')
api_router.include_router(hello_router)
api_router.include_router(users_router)
