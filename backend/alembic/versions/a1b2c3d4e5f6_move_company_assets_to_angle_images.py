"""move company_assets into per-angle columns on angle_images

Revision ID: a1b2c3d4e5f6
Revises: eb05a60f3542
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'eb05a60f3542'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # angle_images: each generated image now carries its own snapshot of the
    # logo + company photos used, instead of pulling from the shared,
    # request-level company_assets table. company_image_paths is a
    # JSON-encoded array (mirrors ad_angle_requests.offers/industry).
    with op.batch_alter_table('angle_images') as batch_op:
        batch_op.add_column(sa.Column('logo_path', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('company_image_paths', sa.Text(), nullable=True))

    # Backfill: company_assets was shared across every angle in a request, so
    # there's no historical record of which angle used which logo/photos.
    # Best-effort snapshot — copy the request's current assets onto every
    # existing angle_images row for that request (identical values across
    # angles at migration time; they diverge going forward as angles are
    # individually regenerated under the new per-angle model).
    op.execute(
        """
        UPDATE angle_images
        SET logo_path = (
            SELECT ca.file_path FROM company_assets ca
            JOIN ad_angles a ON a.request_id = ca.request_id
            WHERE a.id = angle_images.angle_id AND ca.asset_type = 'logo'
            ORDER BY ca.created_at DESC
            LIMIT 1
        )
        """
    )
    op.execute(
        """
        UPDATE angle_images
        SET company_image_paths = (
            SELECT json_agg(ca.file_path ORDER BY ca.created_at)::text
            FROM company_assets ca
            JOIN ad_angles a ON a.request_id = ca.request_id
            WHERE a.id = angle_images.angle_id AND ca.asset_type = 'company_image'
        )
        """
    )

    op.drop_index(op.f('ix_company_assets_id'), table_name='company_assets')
    op.drop_index(op.f('ix_company_assets_request_id'), table_name='company_assets')
    op.drop_table('company_assets')


def downgrade() -> None:
    op.create_table(
        'company_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('asset_type', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['ad_angle_requests.id'], name='fk_company_assets_request_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_assets_id'), 'company_assets', ['id'])
    op.create_index(op.f('ix_company_assets_request_id'), 'company_assets', ['request_id'])

    # Best-effort reverse backfill: recreate one logo + N company_image rows
    # per request from whichever angle_images row happens to have them (the
    # most recent one), since the per-angle columns had no single canonical
    # request-level source once angles started diverging.
    op.execute(
        """
        INSERT INTO company_assets (request_id, asset_type, file_path, created_at)
        SELECT DISTINCT ON (a.request_id) a.request_id, 'logo', ai.logo_path, ai.created_at
        FROM angle_images ai
        JOIN ad_angles a ON a.id = ai.angle_id
        WHERE ai.logo_path IS NOT NULL
        ORDER BY a.request_id, ai.created_at DESC
        """
    )
    op.execute(
        """
        INSERT INTO company_assets (request_id, asset_type, file_path, created_at)
        SELECT DISTINCT a.request_id, 'company_image', photo.value, ai.created_at
        FROM angle_images ai
        JOIN ad_angles a ON a.id = ai.angle_id
        CROSS JOIN LATERAL json_array_elements_text(ai.company_image_paths::json) AS photo(value)
        WHERE ai.company_image_paths IS NOT NULL
        """
    )

    with op.batch_alter_table('angle_images') as batch_op:
        batch_op.drop_column('company_image_paths')
        batch_op.drop_column('logo_path')
