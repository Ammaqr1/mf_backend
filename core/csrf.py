from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def csrf_protection(request: Request, call_next):

    # print("I am in the middleware")

    if request.method in SAFE_METHODS:
        return await call_next(request)

    origin = request.headers.get("origin")

    if not origin:
        return JSONResponse(
            status_code=403,
            content={"detail": "Missing request origin"},
        )

    allowed_origins = set(
        request.app.state.allowed_origins
    )

    # Allow requests originating from the API itself,
    # including Swagger UI during development.
    allowed_origins.add(get_origin(str(request.base_url)))

    # print("this is the allowed origin", allowed_origins)

    if origin not in allowed_origins:
        return JSONResponse(
            status_code=403,
            content={"detail": "Invalid request origin"},
        )

    return await call_next(request)