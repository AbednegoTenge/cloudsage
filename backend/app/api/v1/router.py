from fastapi import APIRouter

from app.api.v1.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
# Phase 2+: investigations, connections, resources routers are mounted here.
