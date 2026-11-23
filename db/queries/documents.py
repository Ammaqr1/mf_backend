from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import Document


async def create_document(
    db: AsyncSession,
    document_id: str,
    credential_id: str,
    s3_key: str,
    original_filename: str | None,
    password: str | None = None,
) -> Document:
    document = Document(
        id=document_id,
        credential_id=credential_id,
        s3_key=s3_key,
        original_filename=original_filename,
        password=password,
        status="pending",
    )
    db.add(document)
    await db.flush()
    return document


async def get_document_by_key(
    db: AsyncSession,
    credential_id: str,
    s3_key: str,
) -> Document | None:
    stmt = select(Document).where(
        Document.credential_id == credential_id,
        Document.s3_key == s3_key,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_document_by_id(
    db: AsyncSession,
    credential_id: str,
    document_id: str,
) -> Document | None:
    stmt = select(Document).where(
        Document.credential_id == credential_id,
        Document.id == document_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_documents(
    db: AsyncSession,
    credential_id: str,
) -> list[Document]:
    stmt = (
        select(Document)
        .where(
            Document.credential_id == credential_id,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
