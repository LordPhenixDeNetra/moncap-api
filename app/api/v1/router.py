from fastapi import APIRouter

from app.api.v1.routes import adhesions
from app.api.v1.routes import admin
from app.api.v1.routes import auth
from app.api.v1.routes import geo
from app.api.v1.routes import health

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(auth.router, tags=["auth"])
api_v1_router.include_router(geo.router, tags=["geo"])
api_v1_router.include_router(adhesions.router, tags=["adhesions"])
api_v1_router.include_router(admin.router, tags=["admin"])
