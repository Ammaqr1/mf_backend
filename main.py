from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.csrf import csrf_protection
from app.api.v1.router import api_router
import os
from dotenv import load_dotenv

load_dotenv()

origin = os.getenv("FRONTEND_ORIGINS").strip()




app = FastAPI(
    title="Mutual Funds API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origin,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.state.allowed_origins = origin

app.middleware("http")(csrf_protection)

app.include_router(api_router, prefix="/api/v1")