"""flatten company into ad_angle_request

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ad_angle_requests: replace company_id FK with a flat company_name column,
    # backfilled from the linked company_profiles row before company_id is dropped.
    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.add_column(sa.Column('company_name', sa.String(), nullable=True))

    op.execute(
        """
        UPDATE ad_angle_requests
        SET company_name = (
            SELECT company_name FROM company_profiles
            WHERE company_profiles.id = ad_angle_requests.company_id
        )
        """
    )
    op.execute("UPDATE ad_angle_requests SET company_name = '' WHERE company_name IS NULL")

    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.alter_column('company_name', nullable=False)
        batch_op.drop_constraint('fk_ad_angle_requests_company_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_ad_angle_requests_company_id'))
        batch_op.drop_column('company_id')

    # company_assets: re-parent from company_id -> request_id. Since a company's
    # assets used to be shared across all of that company's ad-angle requests but
    # are now scoped to a single request, each asset is attached to that
    # company's MOST RECENT request (best-effort — old shared assets can't be
    # duplicated across every request without inventing new rows).
    with op.batch_alter_table('company_assets') as batch_op:
        batch_op.add_column(sa.Column('request_id', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE company_assets
        SET request_id = (
            SELECT r.id FROM ad_angle_requests r
            JOIN company_profiles c ON c.id = company_assets.company_id
            WHERE r.company_name = c.company_name
            ORDER BY r.id DESC
            LIMIT 1
        )
        """
    )
    op.execute("DELETE FROM company_assets WHERE request_id IS NULL")

    # The company_id FK's actual constraint name depends on how it was created
    # (a hand-named migration vs. Postgres's own default naming), so look it
    # up from the catalog instead of assuming a fixed name.
    conn = op.get_bind()
    fk_name = conn.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'company_assets'::regclass
              AND contype = 'f'
              AND conname != 'fk_company_assets_request_id'
            """
        )
    ).scalar()

    with op.batch_alter_table('company_assets') as batch_op:
        batch_op.alter_column('request_id', nullable=False)
        if fk_name:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.drop_index(op.f('ix_company_assets_company_id'))
        batch_op.drop_column('company_id')
        batch_op.create_index(op.f('ix_company_assets_request_id'), ['request_id'])
        batch_op.create_foreign_key(
            'fk_company_assets_request_id', 'ad_angle_requests', ['request_id'], ['id']
        )

    op.drop_index(op.f('ix_company_profiles_id'), table_name='company_profiles')
    op.drop_index(op.f('ix_company_profiles_company_name'), table_name='company_profiles')
    op.drop_table('company_profiles')


def downgrade() -> None:
    op.create_table(
        'company_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('website_url', sa.String(), nullable=False),
        sa.Column('areas_covered', sa.Text(), nullable=False),
        sa.Column('usps', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_profiles_company_name'), 'company_profiles', ['company_name'], unique=True)
    op.create_index(op.f('ix_company_profiles_id'), 'company_profiles', ['id'], unique=False)

    # Recreate one company_profiles row per distinct company_name seen in
    # ad_angle_requests (phone/email/website_url/areas_covered/usps are gone
    # for good — these columns come back empty).
    op.execute(
        """
        INSERT INTO company_profiles (company_name, phone, email, website_url, areas_covered)
        SELECT DISTINCT company_name, '', '', '', ''
        FROM ad_angle_requests
        """
    )

    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE ad_angle_requests
        SET company_id = (
            SELECT id FROM company_profiles
            WHERE company_profiles.company_name = ad_angle_requests.company_name
        )
        """
    )

    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.alter_column('company_id', nullable=False)
        batch_op.create_index(op.f('ix_ad_angle_requests_company_id'), ['company_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_ad_angle_requests_company_id', 'company_profiles', ['company_id'], ['id']
        )
        batch_op.drop_column('company_name')

    with op.batch_alter_table('company_assets') as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE company_assets
        SET company_id = (
            SELECT r.company_id FROM ad_angle_requests r
            WHERE r.id = company_assets.request_id
        )
        """
    )

    with op.batch_alter_table('company_assets') as batch_op:
        batch_op.alter_column('company_id', nullable=False)
        batch_op.drop_constraint('fk_company_assets_request_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_company_assets_request_id'))
        batch_op.drop_column('request_id')
        batch_op.create_index(op.f('ix_company_assets_company_id'), ['company_id'])
        batch_op.create_foreign_key(
            'fk_company_assets_company_id', 'company_profiles', ['company_id'], ['id']
        )
