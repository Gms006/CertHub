from fastapi import APIRouter

from app.api.v1.endpoints import admin, certificados, install_jobs

api_router = APIRouter()
api_router.include_router(admin.router)
api_router.include_router(certificados.router)
api_router.include_router(install_jobs.router)
