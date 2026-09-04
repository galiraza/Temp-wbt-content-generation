"""Request and response models for the content hub, v2.

EVERY class here is prefixed `Hub`, without exception. `app.schemas` is a flat
namespace, so an unprefixed `SectionOut` silently replaces the one
`website_content` exports and the older routers keep importing. That failure
does not show up as an import error, it shows up as a 500 with a Pydantic
validation error naming fields from the wrong model, a long way from the cause.
It has happened once already.

The vocabulary is the schema's, which inverted between v1 and v2:
`content_type` is now the top level tab (website, social, blog, logo, ads) and
`section` is the sub type inside it (pages, posts, reels, stories, reviews,
blogs, scratch, revamp, ads). In v1 `section` meant the tab. Nothing here uses
the old sense of the word.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Enums. Mirrors of cg_content_type and cg_section.
#
# Declared here as well as in the database so an unknown value is rejected at
# the edge as a 422 naming the field. Without them psycopg raises
# InvalidTextRepresentation at commit time, which surfaces as a 500 and takes
# the whole transaction with it.
# --------------------------------------------------------------------------


class HubContentType(str, Enum):
    website = "website"
    social = "social"
    blog = "blog"
    logo = "logo"
    ads = "ads"


class HubSection(str, Enum):
    pages = "pages"
    posts = "posts"
    reels = "reels"
    stories = "stories"
    reviews = "reviews"
    blogs = "blogs"
    scratch = "scratch"
    revamp = "revamp"
    ads = "ads"



# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------


class HubClientOut(BaseModel):
    """A client in the switcher, as Command HQ describes it.

    `client_id` is HQ's uuid, typed as a string rather than a UUID because the
    export is the source and one badly formed id there should return a row the
    UI can ignore, not fail the whole list of 361. Path parameters are the
    opposite case and are typed `uuid.UUID`, so a malformed id is a 422.

    There is no local id, because most HQ clients have no row in this database
    at all. `asset_count` is the only thing this app contributes.
    """

    model_config = ConfigDict(from_attributes=True)

    client_id: str
    #: Named to match cg_clients, not the export's own `name`/`organizationId`.
    #: The database column names are the contract the whole stack reads from.
    client_name: str
    client_organization: Optional[str] = None
    asset_count: int = 0
    #: When this client last had a run, or null if never. Drives the Recent tab
    #: in the picker, which is why it is on the list response rather than on a
    #: separate route: Recent and All are two views of one list.
    last_run_at: Optional[datetime] = None
    meta: str = ""


# --------------------------------------------------------------------------
# Overview: the five content types, their sections, and the run history
# --------------------------------------------------------------------------


class HubSectionOut(BaseModel):
    """One sub tab under a content type.

    `id` is a plain string rather than HubSection because blog's sub tabs are
    the periods that exist for the client ('2026-09'), not sections.
    """

    id: str
    label: str
    count: int


class HubContentTypeOut(BaseModel):
    """One of the five tabs, with its badge count and the prototype's UI flags.

    The flags travel with the tab so the client does not carry a second copy of
    which content type renders as a table, which is monthly and which shows a
    single card. They are layout, not data, but they change with the content
    type and nothing else, so this is where they belong.
    """

    id: HubContentType
    label: str
    count: int
    unit: str
    single: bool = False
    table: bool = False
    monthly: bool = False
    logo: bool = False
    sections: List[HubSectionOut] = []


class HubRunOut(BaseModel):
    """One line of the run history.

    `source`, the frozen brief, is deliberately not here. It is the largest
    thing in the schema and the history is twenty of these; the brief belongs
    on a run detail route, if one is ever needed.
    """

    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    content_type: HubContentType
    version: int
    status: str
    period: Optional[str] = None
    summary: Optional[str] = None
    requested_by: Optional[str] = None
    client_name: Optional[str] = None
    asset_count: int = 0
    approved_count: int = 0
    approved_label: str = ""
    created_at: Optional[datetime] = None


class HubOverviewOut(BaseModel):
    """Everything one client's panel needs, in a single response.

    One call rather than one per tab: the badges all have to be right before
    the panel first paints, and switching tabs should not wait on the network.
    """

    client: HubClientOut
    content_types: List[HubContentTypeOut] = []
    runs: List[HubRunOut] = []


# --------------------------------------------------------------------------
# Assets, versions and chat
# --------------------------------------------------------------------------


class HubVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    body: Optional[str] = None
    file_path: Optional[str] = None
    created_at: Optional[datetime] = None
    #: True for the version that ships, which is not necessarily the one the
    #: card is showing. Restore is what moves this.
    is_active: bool = False


class HubAssetOut(BaseModel):
    """One card.

    `body` and `file_path` are the active version's, not the asset's: an asset
    row holds no content of its own, so every route that returns one folds in
    the content of `active_version`. Previewing an older version is UI state and
    is never stored, so there is nothing here to resolve.

    `content_type` comes off the run rather than the asset, and is null only
    when a caller built this without the run to hand.
    """

    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    run_id: UUID
    client_id: UUID
    content_type: Optional[HubContentType] = None
    section: HubSection
    type: str
    position: int
    title: Optional[str] = None
    #: The URL segment, unique per (client, section). See the /sg routes.
    slug: Optional[str] = None
    status: str

    active_version: int
    body: Optional[str] = None
    file_path: Optional[str] = None

    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HubAssetDetailOut(BaseModel):
    """One asset with its whole history.

    `active_version` is repeated here even though it also sits on `asset`,
    because the version list is what the panel renders and every row in it needs
    comparing against the active number. Making the caller reach into `asset` for
    the value it is about to use on every row buys nothing.
    """

    asset: HubAssetOut
    versions: List[HubVersionOut] = []
    active_version: int


class HubChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    asset_id: UUID
    version: int
    body: str
    created_at: Optional[datetime] = None


class HubChatMessageCreate(BaseModel):
    """A message being appended.

    The version it belongs to is a query parameter, not a field, because it is
    part of the thread's address and the route has to check it exists before
    the insert either way.
    """

    body: str = Field(min_length=1)


# --------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------


class HubSyncOut(BaseModel):
    """The sync's own tally, passed straight through.

    `extra="allow"` because the sync decides what it counts. Adding a counter
    there should not need an edit here, and pinning the shape would quietly
    drop the new key from the response instead of failing loudly.
    """

    model_config = ConfigDict(extra="allow")

    clients: int = 0
    runs: int = 0
    assets: int = 0


# --------------------------------------------------------------------------
# Per-section item counts
# --------------------------------------------------------------------------


class HubSectionDefaultOut(BaseModel):
    """One row of the settings panel.

    `source` is what lets the panel show an inherited value differently from an
    overridden one, and offer Reset only where there is something to reset,
    without a second call to work out which is which:

        house    inherited from the house default
        client   this client overrides it
        derived  not settable, and `note` says what decides it instead

    `house_count` travels alongside `item_count` so an overridden row can show
    what it would fall back to.
    """

    content_type: HubContentType
    section: HubSection
    label: str
    item_count: int
    house_count: int
    source: str
    editable: bool = True
    note: str = ""


class HubSectionDefaultIn(BaseModel):
    """A count being set.

    Bounded here as well as by the check constraint, so a bad number is a 422
    naming the field rather than a 500 out of Postgres.
    """

    item_count: int = Field(ge=1, le=50)


# --------------------------------------------------------------------------
# Runs and generation
# --------------------------------------------------------------------------


class HubRunCreate(BaseModel):
    """A generation request: which content type, and the whole brief.

    `source` is the form, passed through as it was filled in. It is not
    validated field by field here on purpose: the required fields differ per
    content type, the planner is what knows them, and it returns a sentence
    saying which one is missing. Validating twice would mean two lists of
    required fields disagreeing with each other.
    """

    content_type: HubContentType
    source: dict = Field(default_factory=dict)
    period: Optional[str] = None
    requested_by: Optional[str] = None


class HubDraftOut(BaseModel):
    """What a form should open with for this client and content type.

    The merged `source` of the most recent run, so re-opening a form shows what
    was used last time rather than an empty sheet. `run_id` and `version` say
    which run it came from, and are null when the client has never had one, in
    which case `source` is empty and the form is blank.

    Nothing here comes from the Command HQ export. That was asked for
    explicitly: the client picker says who the run is for, the form says what to
    generate, and prefilling the second from the first put stale answers in
    front of someone who was there to type fresh ones.
    """

    content_type: HubContentType
    source: dict = Field(default_factory=dict)
    run_id: Optional[UUID] = None
    version: Optional[int] = None
    created_at: Optional[datetime] = None
