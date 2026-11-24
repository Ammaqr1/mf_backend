from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependecies import get_current_user
from app.db.db import get_db
from app.db.queries.documents import get_document_owner_id, list_documents_page
from app.schemas.common import Page, PageParams, make_page
from app.schemas.s3 import (
    DocumentResponse,
    UploadUrlRequest,
    UpdatePasswordRequest,
    UploadUrlResponse,
    VerifyUploadRequest,
)
from app.services.document_service import (
    process_by_id,
    start_upload,
    update_password,
    verify_upload as verify_upload_service,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


async def _owner_id(db: AsyncSession, current_user, document_id: str) -> str:
    """Admins may act on any document; others only on their own."""
    if current_user.is_admin:
        owner = await get_document_owner_id(db, document_id)
        if owner:
            return owner
    return str(current_user.id)


@router.get("", response_model=Page[DocumentResponse])
async def list_my_documents(
    params: PageParams = Depends(),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner = None if current_user.is_admin else str(current_user.id)
    items, total = await list_documents_page(db, owner, params.per_page, params.offset)
    return make_page(items, params, total)


@router.post("/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    payload: UploadUrlRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await start_upload(db, str(current_user.id), payload.filename, payload.password)


@router.post("/verify", response_model=DocumentResponse)
async def verify_upload(
    payload: VerifyUploadRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await verify_upload_service(db, str(current_user.id), payload.key)
    except ValueError as exc:
        msg = str(exc)
        if msg == "Invalid document ownership":
            code = status.HTTP_403_FORBIDDEN
        elif msg == "Uploaded document not found":
            code = status.HTTP_404_NOT_FOUND
        else:
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg)


@router.patch("/{document_id}/password", response_model=DocumentResponse)
async def change_document_password(
    document_id: str,
    payload: UpdatePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_password(
            db, await _owner_id(db, current_user, document_id), document_id, payload.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{document_id}/process", response_model=DocumentResponse)
async def process_document_endpoint(
    document_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await process_by_id(
            db, await _owner_id(db, current_user, document_id), document_id
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if msg == "Uploaded document not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=msg)
