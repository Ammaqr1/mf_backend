from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.s3 import router as s3_router


api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(s3_router)