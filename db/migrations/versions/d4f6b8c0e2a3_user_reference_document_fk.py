"""user.reference -> documents.id, drop document_users

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-11-23 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f6b8c0e2a3'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # keep existing links: point each user at one of its documents
    op.execute(
        'UPDATE "user" u SET reference = du.document_id '
        'FROM (SELECT DISTINCT ON (user_id) user_id, document_id '
        '      FROM document_users ORDER BY user_id, document_id) du '
        'WHERE u.id = du.user_id'
    )
    op.drop_table('document_users')

    # free-text values can't become a foreign key
    op.execute('UPDATE "user" SET reference = NULL WHERE reference NOT IN (SELECT id FROM documents)')
    op.alter_column(
        'user', 'reference',
        existing_type=sa.String(length=455), type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.create_foreign_key(
        'user_reference_fkey', 'user', 'documents', ['reference'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('user_reference_fkey', 'user', type_='foreignkey')
    op.alter_column(
        'user', 'reference',
        existing_type=sa.String(length=32), type_=sa.String(length=455),
        existing_nullable=True,
    )
    op.create_table(
        'document_users',
        sa.Column('document_id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('document_id', 'user_id'),
    )
    op.execute(
        'INSERT INTO document_users (document_id, user_id) '
        'SELECT reference, id FROM "user" WHERE reference IS NOT NULL'
    )
