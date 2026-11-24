from sqlalchemy import func, select
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


async def list_documents_page(
    db: AsyncSession,
    credential_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Document], int]:
    """credential_id=None lists every user's documents (admin view)."""
    conds = [Document.deleted_at.is_(None)]
    if credential_id is not None:
        conds.append(Document.credential_id == credential_id)

    total = (
        await db.execute(select(func.count()).select_from(Document).where(*conds))
    ).scalar_one()
    rows = await db.execute(
        select(Document)
        .where(*conds)
        .order_by(Document.created_at.desc(), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars().all()), total


async def get_document_owner_id(db: AsyncSession, document_id: str) -> str | None:
    result = await db.execute(
        select(Document.credential_id).where(
            Document.id == document_id, Document.deleted_at.is_(None)
        )
    )
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
