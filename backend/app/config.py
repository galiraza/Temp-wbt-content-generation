"""Centralized environment configuration for the app."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]  # always Supabase Postgres — no local fallback

# Shared secret the frontend must send as the X-API-Key header on every request.
# See app.main for enforcement — every route is protected unless explicitly exempted.
API_KEY = os.environ["API_KEY"]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Anthropic — the post/review generation agents. The n8n workflows these were
# ported from ran on Claude Sonnet 4.6, but the module now defaults to Sonnet 5;
# override ANTHROPIC_MODEL to move the whole post module to another model at once.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

# Firecrawl — scrapes the client's public reviews page so the review agent has
# real customer reviews to work from (see app.agents.post_generation.firecrawl).
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
# The ad-angle example index. Website content reads two different indexes of its
# own -- see below -- so this is no longer the only one in play.
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME")

# Website content generation reads two more Pinecone indexes, both on the same
# PINECONE_API_KEY. The five industry knowledge bases are namespaces inside the
# first; the blogs agent has its own index and namespace. These are the index
# and namespace names the n8n workflow's vector-store nodes point at, so the
# defaults are the live ones and only need overriding to point at a copy.
WEBSITE_CONTENT_PINECONE_INDEX = os.environ.get(
    "WEBSITE_CONTENT_PINECONE_INDEX", "wbt-kb-website-content-generation"
)
BLOGS_PINECONE_INDEX = os.environ.get("BLOGS_PINECONE_INDEX", "wbt-blogs-kb")
BLOGS_PINECONE_NAMESPACE = os.environ.get("BLOGS_PINECONE_NAMESPACE", "blogs_services")

# The one node in the website-content workflow that is not on Claude. "Generate
# Titles" opens with "Always use web search in UK to gather the latest
# information", so it needs a model that actually searches, not just a good one.
#
# n8n pointed at gpt-4o-search-preview, which OpenAI has since retired — the API
# now answers 404 "has been deprecated" and the whole Blogs branch dies with it,
# in n8n exactly as it did here. gpt-5-search-api is its successor and the only
# non-deprecated search model on the account; gpt-4o-mini-search-preview is
# retired too, and the plain gpt-4.1/gpt-5 chat models do not search at all.
#
# It rejects the `temperature` and `n` parameters, which is why langchain-openai
# must stay >= 0.3.28 — older versions always send both and get a 400.
WEBSITE_CONTENT_TITLE_MODEL = os.environ.get(
    "WEBSITE_CONTENT_TITLE_MODEL", "gpt-5-search-api"
)

# Supabase Storage — used for all uploaded/generated image files (see app.storage).
# SUPABASE_URL: e.g. https://<project-ref>.supabase.co
# SUPABASE_SERVICE_ROLE_KEY: the service_role key (needed to upload/delete via the
# Storage REST API) — never the anon/public key.
# SUPABASE_STORAGE_BUCKET: the public bucket name images are stored in.
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "ad-angle-images")

# WBT Command HQ's Client Data Export API — used to prefill the ad-angle form
# from an existing client's onboarding questionnaire. Server-side only: the
# frontend never sees this key, it calls our own /api/client-export routes,
# which proxy to HQ using this key (see app.routers.client_export).
CLIENT_EXPORT_API_URL = os.environ.get(
    "CLIENT_EXPORT_API_URL", "https://hq.webuildtrades.com/api/client-management/export"
)
CLIENT_EXPORT_API_KEY = os.environ.get("CLIENT_EXPORT_API_KEY")

# n8n workflow that takes a Fathom meeting URL and returns its transcript —
# used to pull meeting context into logo generation before the images are
# generated (see app.services.fathom_service). No authentication.
FATHOM_TRANSCRIPT_WEBHOOK_URL = os.environ.get(
    "FATHOM_TRANSCRIPT_WEBHOOK_URL", "https://n8nserver.webuildtrades.com/webhook/fathom-meeting-lookup"
)

# Allowed CORS origins come from the environment only — add a new frontend domain
# by editing CORS_ALLOW_ORIGINS in the deploy env, never this file. The value is a
# comma-separated list of origins (scheme + host + optional port, no trailing path),
# e.g. "https://aistudio.webuildtrades.com,https://staging.example.com".
#
# Each entry must be the origin of the *browser page* calling the API, not the API's
# own domain. Wildcards are not usable here: app.main sets allow_credentials=True,
# which the CORS spec forbids combining with "*".
#
# Left unset or empty, this falls back to the local dev servers below so `npm run dev`
# and docker compose work without any env setup. That fallback is dev-only — every
# deployed environment must set CORS_ALLOW_ORIGINS explicitly.
_LOCAL_DEV_CORS_ORIGINS = [
    "http://localhost:3000",  # `npm run dev`
    "http://localhost:3001",  # `npm run dev` when 3000 is taken
    "http://localhost:4000",  # frontend published by docker compose
]

# dict.fromkeys de-duplicates while preserving order.
CORS_ALLOW_ORIGINS = list(
    dict.fromkeys(
        origin.strip()
        for origin in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",")
        if origin.strip()
    )
) or _LOCAL_DEV_CORS_ORIGINS


def has_openai_key() -> bool:
    return bool(OPENAI_API_KEY)


def has_anthropic_key() -> bool:
    return bool(ANTHROPIC_API_KEY)


def has_firecrawl_key() -> bool:
    return bool(FIRECRAWL_API_KEY)
