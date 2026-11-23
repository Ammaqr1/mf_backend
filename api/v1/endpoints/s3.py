from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependecies import get_current_user
from app.db.db import get_db
from app.schemas.s3 import (
    DocumentResponse,
    UploadUrlRequest,
    UpdatePasswordRequest,
    UploadUrlResponse,
    VerifyUploadRequest,
)
from app.services.document_service import (
    get_documents,
    start_upload,
    update_password,
    verify_upload as verify_upload_service,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.get("", response_model=list[DocumentResponse])
async def list_my_documents(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_documents(db, str(current_user.id))


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
            db, str(current_user.id), document_id, payload.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
