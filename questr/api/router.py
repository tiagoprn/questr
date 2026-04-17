from fastapi import APIRouter

from questr.hello.router import router as hello_router
from questr.users.router import router as users_router

api_router = APIRouter(prefix='/api')
api_router.include_router(hello_router)
api_router.include_router(users_router)
