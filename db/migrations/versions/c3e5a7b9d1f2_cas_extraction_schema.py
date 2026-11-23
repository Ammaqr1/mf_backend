"""cas extraction schema

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: PAN unique per account instead of globally
    op.drop_constraint('user_pan_key', 'user', type_='unique')
    op.create_index(op.f('ix_user_pan'), 'user', ['pan'], unique=False)
    op.create_unique_constraint('uq_user_credential_pan', 'user', ['credentials_id', 'pan'])

    # documents <-> users many-to-many (one statement can hold several PANs)
    op.create_table(
        'document_users',
        sa.Column('document_id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('document_id', 'user_id'),
    )
    op.execute(
        "INSERT INTO document_users (document_id, user_id) "
        "SELECT id, user_id FROM documents WHERE user_id IS NOT NULL"
    )
    op.drop_index(op.f('ix_documents_user_id'), table_name='documents')
    op.drop_constraint('documents_user_id_fkey', 'documents', type_='foreignkey')
    op.drop_column('documents', 'user_id')

    # holdings: extra statement fields
    op.add_column('mutual_fund_holdings', sa.Column('opening_units', sa.Float(), nullable=True))
    op.add_column('mutual_fund_holdings', sa.Column('total_cost', sa.Float(), nullable=True))
    op.add_column('mutual_fund_holdings', sa.Column('market_value', sa.Float(), nullable=True))
    op.add_column('mutual_fund_holdings', sa.Column('rta', sa.String(length=50), nullable=True))
    op.add_column('mutual_fund_holdings', sa.Column('rta_code', sa.String(length=50), nullable=True))
    op.add_column('mutual_fund_holdings', sa.Column('advisor', sa.String(length=100), nullable=True))

    # transactions: gift_folio is a folio string, not a number
    op.alter_column(
        'mutual_fund_transactions', 'gift_folio',
        existing_type=sa.Float(), type_=sa.String(length=100),
        existing_nullable=True, postgresql_using='gift_folio::text',
    )


def downgrade() -> None:
    op.alter_column(
        'mutual_fund_transactions', 'gift_folio',
        existing_type=sa.String(length=100), type_=sa.Float(),
        existing_nullable=True, postgresql_using='NULL',
    )
    for col in ('advisor', 'rta_code', 'rta', 'market_value', 'total_cost', 'opening_units'):
        op.drop_column('mutual_fund_holdings', col)

    op.add_column('documents', sa.Column('user_id', sa.String(length=32), nullable=True))
    op.create_foreign_key('documents_user_id_fkey', 'documents', 'user', ['user_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_documents_user_id'), 'documents', ['user_id'], unique=False)
    op.drop_table('document_users')

    op.drop_constraint('uq_user_credential_pan', 'user', type_='unique')
    op.drop_index(op.f('ix_user_pan'), table_name='user')
    op.create_unique_constraint('user_pan_key', 'user', ['pan'])
