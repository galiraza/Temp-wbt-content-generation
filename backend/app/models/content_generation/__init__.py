"""The content hub, v2: clients, runs, assets, versions and chat.

Client-first, keyed on Command HQ's own uuids. This replaces the first cut of
the cg_* tables outright rather than migrating it, because the column types all
changed (uuid, enum, jsonb, timestamptz) and the old rows are cheaper to
re-derive from the source tables, which are untouched and remain the record.

    cg_clients          one row per client, HQ's clientId as the key
    cg_runs             one request, with the whole brief frozen in jsonb
    cg_assets           one generated item, with approval and version state
    cg_asset_versions   the content itself, one row per version, kept forever
    cg_asset_chats      the refinement thread, per version, not per asset

app/models/content_generation/schema.sql is authoritative for the tables, the
enums, the indexes and the updated_at trigger, and is already applied to the
database. It was applied directly rather than through Alembic because this
database sits on a revision that does not exist in the repo and the migration
graph has two open heads. These classes map that schema, they do not define it:
no model here is allowed to create, alter or drop anything, which is why the
enums are declared with create_type=False.
"""

from app.models.content_generation.asset import ContentAsset, ContentAssetVersion
from app.models.content_generation.chat import ContentAssetChat
from app.models.content_generation.client import ContentClient
from app.models.content_generation.run import ContentRun
from app.models.content_generation.settings import (
    FALLBACK_ITEM_COUNTS,
    ContentSectionDefault,
)

__all__ = [
    "ContentClient",
    "ContentRun",
    "ContentAsset",
    "ContentAssetVersion",
    "ContentAssetChat",
    "ContentSectionDefault",
    "FALLBACK_ITEM_COUNTS",
]
