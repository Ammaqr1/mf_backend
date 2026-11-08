from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
import os
from app.db.db import get_db
from app.schemas.auth import SignupRequest, UserResponse, LoginRequest
from app.services.auth_service import signup as signup_service, login as login_service, refresh_session, logout as logout_service
from app.core.security import create_access_token
from app.core.dependecies import get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup_endpoint(
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        credential = await signup_service(
            db=db,
            name=payload.name.strip(),
            email=str(payload.email),
            password=payload.password,
        )

        return credential

    except ValueError as exc:
        if str(exc) == "Email already registered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        raise

@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
async def login_endpoint(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await login_service(
        db=db,
        email=str(payload.email),
        password=payload.password,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    credential, refresh_token = result

    cookie_secure = os.getenv("COOKIE_SECURE").lower() == "true"

    access_token = create_access_token(credential.id)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=15 * 60,
        path="/",
    )


    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE").lower() == "true",
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/api/v1/auth",
    )

    return credential

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user = Depends(get_current_user),
):
    return current_user


@router.post("/refresh", response_model=UserResponse)
async def refresh_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_refresh_token = request.cookies.get("refresh_token")

    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    result = await refresh_session(
        db=db,
        raw_refresh_token=raw_refresh_token,
    )

    if not result:
        response.delete_cookie("access_token", path="/")
        response.delete_cookie(
            "refresh_token",
            path="/api/v1/auth",
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    credential, new_refresh_token = result

    new_access_token = create_access_token(credential.id)

    cookie_secure = (
        os.getenv("COOKIE_SECURE").lower() == "true"
    )

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=15 * 60,
        path="/",
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/api/v1/auth",
    )

    return credential

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")

    await logout_service(
        db=db,
        raw_refresh_token=refresh_token,
    )

    response.delete_cookie(
        key="access_token",
        path="/",
    )

    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
    )

    response.status_code = status.HTTP_204_NO_CONTENT

    return response