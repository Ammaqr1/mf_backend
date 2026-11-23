from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries.documents import (
    create_document,
    get_document_by_id,
    get_document_by_key,
    list_documents,
)
from app.services.cas_service import process_document
from app.services.s3_service import (
    check_pdf_password,
    generate_upload_url,
    verify_uploaded_pdf,
)


async def start_upload(
    db: AsyncSession,
    credential_id: str,
    filename: str | None,
    password: str | None = None,
):
    # boto3 is synchronous; keep it off the event loop
    upload = await run_in_threadpool(generate_upload_url, credential_id)

    await create_document(
        db=db,
        document_id=upload["document_id"],
        credential_id=credential_id,
        s3_key=upload["key"],
        original_filename=(filename or None) and filename[:255],
        password=password or None,
    )
    await db.commit()

    return upload


async def verify_upload(db: AsyncSession, credential_id: str, key: str):
    document = await get_document_by_key(db, credential_id, key)
    if document is None:
        raise ValueError("Uploaded document not found")

    try:
        info = await run_in_threadpool(verify_uploaded_pdf, credential_id, key)
    except ValueError as exc:
        if str(exc) != "Uploaded document not found":
            document.status = "failed"
            document.error_message = str(exc)[:500]
            await db.commit()
        raise

    # a wrong password never blocks the upload; it only flags the document
    document.password_valid = await run_in_threadpool(
        check_pdf_password, document.s3_key, document.password
    )
    document.status = "verified"
    document.size_bytes = info["size"]
    document.content_type = info["content_type"]
    document.verified_at = datetime.now()
    document.error_message = None
    await db.commit()

    # extract data right away unless the password is known to be wrong
    if document.password_valid is not False:
        await process_document(db, document)
    await db.refresh(document)

    return document


async def update_password(
    db: AsyncSession, credential_id: str, document_id: str, password: str
):
    document = await get_document_by_id(db, credential_id, document_id)
    if document is None:
        raise ValueError("Uploaded document not found")

    document.password = password or None
    document.password_valid = await run_in_threadpool(
        check_pdf_password, document.s3_key, document.password
    )
    await db.commit()

    # a corrected password unlocks extraction
    if document.password_valid is not False and document.status != "processed":
        await process_document(db, document)
    await db.refresh(document)
    return document


async def process_by_id(db: AsyncSession, credential_id: str, document_id: str):
    document = await get_document_by_id(db, credential_id, document_id)
    if document is None:
        raise ValueError("Uploaded document not found")
    if document.password_valid is False:
        raise ValueError("Fix the PDF password before processing")
    if document.status in ("pending", "processing"):
        raise ValueError("Document is not ready to process")

    await process_document(db, document)
    await db.refresh(document)
    return document


async def get_documents(db: AsyncSession, credential_id: str):
    return await list_documents(db, credential_id)
