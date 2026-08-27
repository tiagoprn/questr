from fastapi import APIRouter

from questr.domains.users.api import router as users_router

api_router = APIRouter(prefix='/api')
api_router.include_router(users_router)
