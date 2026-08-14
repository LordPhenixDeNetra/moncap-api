from fastapi import APIRouter

from app.api.v1.routes import adhesions
from app.api.v1.routes import admin
from app.api.v1.routes import articles
from app.api.v1.routes import auth
from app.api.v1.routes import geo
from app.api.v1.routes import health
from app.api.v1.routes import militants
from app.api.v1.routes import users
from app.api.v1.routes import validations

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(auth.router, tags=["auth"])
api_v1_router.include_router(geo.router, tags=["geo"])
api_v1_router.include_router(adhesions.router, tags=["adhesions"])
api_v1_router.include_router(militants.router, tags=["militants"])
api_v1_router.include_router(militants.public_router, tags=["militants"])
api_v1_router.include_router(articles.public_router, tags=["articles"])
api_v1_router.include_router(articles.protected_router, tags=["articles"])
api_v1_router.include_router(admin.read_router, tags=["admin"])
api_v1_router.include_router(admin.write_router, tags=["admin"])
api_v1_router.include_router(validations.accueil_router, tags=["validations"])
api_v1_router.include_router(validations.directoire_router, tags=["validations"])
api_v1_router.include_router(validations.rejection_router, tags=["validations"])
api_v1_router.include_router(users.router, tags=["users"])
