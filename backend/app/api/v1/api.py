from fastapi import APIRouter

from app.api.v1.endpoints import admin

api_router = APIRouter()
api_router.include_router(admin.router)
