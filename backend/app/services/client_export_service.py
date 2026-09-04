"""Client Data Export API (WBT Command HQ) — used to prefill the ad-angle and
logo forms from the list of existing clients.
"""

import re
from typing import Any, List, Optional

import requests
from fastapi import HTTPException

from app.config import CLIENT_EXPORT_API_KEY, CLIENT_EXPORT_API_URL
from app.rag.industries import INDUSTRIES
from app.schemas.client_export import ClientPrefill
from app.schemas.website_content import INDUSTRY_OPTIONS

_TIMEOUT = 15

# Maps a loosely-written industry (the export answers them as slugs like
# "ev-charger") onto our canonical INDUSTRIES spelling, by stripping everything
# that isn't a letter or digit: "EV Charger" and "ev-charger" both key to
# "evcharger".
_INDUSTRY_BY_KEY = {re.sub(r"[^a-z0-9]", "", name.lower()): name for name in INDUSTRIES}


def _headers() -> dict:
    return {"Authorization": f"Bearer {CLIENT_EXPORT_API_KEY}"}


def _get(params: dict) -> dict:
    if not CLIENT_EXPORT_API_KEY:
        raise HTTPException(status_code=503, detail="Client export is not configured")
    try:
        response = requests.get(
            CLIENT_EXPORT_API_URL, headers=_headers(), params=params, timeout=_TIMEOUT
        )
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Could not reach the client data service")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Client data service returned an error")
    return response.json()


def list_clients() -> List[dict]:
    return _get({"list": 1}).get("clients", [])


def _canonical_industry(value: Any) -> Optional[str]:
    """Normalise the questionnaire's industry answer (a list of slugs) to one of
    INDUSTRIES, falling back to a prettified slug for industries we don't list."""
    raw = value[0] if isinstance(value, list) and value else value
    if not isinstance(raw, str) or not raw.strip():
        return None
    canonical = _INDUSTRY_BY_KEY.get(re.sub(r"[^a-z0-9]", "", raw.lower()))
    return canonical or raw.replace("-", " ").replace("_", " ").strip().title()


def _clean(value: Any) -> Optional[str]:
    return value.strip() or None if isinstance(value, str) else None


# A domain has a dot, no whitespace, and a plausible TLD. The questionnaire's
# domain fields are free text, so they also hold answers that are not domains at
# all — "Checkatrade" and "n/a" have both been seen — and pasting one of those
# into the blog form's URL field would fail at the scrape with a confusing error.
_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.I)


def _website_url(answers: dict) -> Optional[str]:
    """The client's own site as an absolute URL, or None.

    Prefers the domain they gave for their current site, falling back to an
    affiliated one. Case is normalised because the answers arrive as typed
    ("Www.absolute-elec.co.uk"), and a scheme is added because Firecrawl needs an
    absolute URL.
    """
    for key in ("current_website_domain", "affiliated_website_url", "other_affiliated_domain"):
        raw = _clean(answers.get(key))
        if not raw:
            continue
        candidate = raw.strip().strip("/")
        # Tolerate a full URL as well as a bare domain.
        for prefix in ("https://", "http://"):
            if candidate.lower().startswith(prefix):
                candidate = candidate[len(prefix):]
                break
        host = candidate.split("/")[0].strip().lower()
        if _DOMAIN_RE.match(host):
            return f"https://{host}"
    return None


# --------------------------------------------------------------------------
# The contact block
# --------------------------------------------------------------------------


def _address(company_info: dict, answers: dict) -> Optional[str]:
    """Street address, falling back to the questionnaire's own address answer.

    Street only, not the whole postal address: the website-content form has
    separate country, region and postcode fields, and repeating them inside the
    address line makes the generated copy read the town twice.
    """
    street = _clean(company_info.get("street"))
    if street:
        return street
    postal = answers.get("company_address")
    if isinstance(postal, dict):
        return _clean(postal.get("street") or postal.get("address_line_1"))
    return None


def _contact(payload: dict, answers: dict) -> dict:
    """The seven business-detail fields, preferring companyInfo over answers.

    companyInfo is HQ's own maintained record; the questionnaire is whatever the
    client typed months ago. Where both exist companyInfo wins, and each field
    falls back independently rather than choosing one source for all of them --
    plenty of clients have a companyInfo with holes in it.
    """
    info = payload.get("companyInfo") or {}
    account = payload.get("account") or {}
    details = answers.get("company_details") if isinstance(answers.get("company_details"), dict) else {}
    postal = answers.get("company_address") if isinstance(answers.get("company_address"), dict) else {}

    return {
        "phone": _clean(info.get("phone")) or _clean(details.get("phone_number")),
        "email": (
            _clean(info.get("email"))
            or _clean(answers.get("display_email"))
            or _clean(details.get("email"))
        ),
        "address": _address(info, answers),
        "country": (
            _clean(info.get("country"))
            or _clean(postal.get("country"))
            or _clean(account.get("country"))
        ),
        "region": (
            _clean(info.get("region"))
            or _clean(postal.get("state_region"))
            or _clean(account.get("region"))
        ),
        "postcode": _clean(info.get("postcode")) or _clean(postal.get("postal_code")),
    }


# --------------------------------------------------------------------------
# Industries
# --------------------------------------------------------------------------

#: The questionnaire answers `website_services` and `industry` as slugs, and its
#: vocabulary does not match the website-content option list one for one. These
#: are the slugs seen in the live export that need an explicit mapping; anything
#: else falls through to the normalised match below, and anything that still
#: misses becomes free text in the Other industry box.
_SERVICE_SLUG_ALIASES = {
    "boiler-heating-services": "Boiler",
    "boilers": "Boiler",
    "cooling-hvac-services": "Air Conditioner",
    "air-conditioning": "Air Conditioner",
    "heat-pump-services": "ASHP",
    # ASHP is an initialism, so nothing normalises onto it — every way of
    # writing it out in full needs saying here.
    "air-source-heat-pumps": "ASHP",
    "air-source-heat-pump": "ASHP",
    "ground-source-heat-pumps": "ASHP",
    "solar-energy-services": "Solar",
    # Battery storage is sold as part of a solar installation and the option
    # list has no separate entry for it.
    "solar-and-battery": "Solar",
    "solar-battery": "Solar",
    "battery-storage": "Solar",
    "ev-charger-services": "EV Charger",
    "ev-chargers": "EV Charger",
    "bathrooms": "Bathroom Installation",
    "electrical": "Electrical",
}

#: Trailing words that describe the offering rather than the trade. Dropped
#: before matching so "eco4-services" finds "ECO4"; without this the whole slug
#: is compared and misses.
_SLUG_SUFFIXES = ("services", "service", "installation", "installations")

#: Slugs that carry no information and must not reach the Other industry box.
_MEANINGLESS_SLUGS = {"other", "none", "n-a", "na"}

#: The option list keyed for loose comparison, so "swimming-pools" finds
#: "Swimming pool": lowercase, alphanumerics only, trailing "s" dropped.
def _industry_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", str(value).lower())
    return key[:-1] if key.endswith("s") else key


_OPTION_BY_KEY = {_industry_key(name): name for name in INDUSTRY_OPTIONS}


def _match_option(slug: str) -> Optional[str]:
    """The option this slug names, or None.

    Tries the slug whole first, then again with a describing suffix removed, so
    "eco4-services" reaches "ECO4" without "-services" being stripped from
    anything it actually belongs to.
    """
    option = _OPTION_BY_KEY.get(_industry_key(slug))
    if option:
        return option

    words = re.split(r"[^a-z0-9]+", slug.lower())
    while len(words) > 1 and words[-1] in _SLUG_SUFFIXES:
        words = words[:-1]
        option = _OPTION_BY_KEY.get(_industry_key("".join(words)))
        if option:
            return option
    return None


def _prettify_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _industries(answers: dict) -> tuple:
    """(matched options, unmatched free text) from the client's service answers.

    Reads both `website_services` and `industry`: they are separate questions
    answered with overlapping vocabularies, and either can hold something the
    other missed. Order is preserved and duplicates dropped, so the ticked boxes
    read the way the client listed their services.
    """
    slugs = []
    for key in ("website_services", "industry"):
        value = answers.get(key)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and item.strip():
                slugs.append(item.strip())

    matched, unmatched = [], []
    for slug in dict.fromkeys(slugs):
        if slug.lower() in _MEANINGLESS_SLUGS:
            continue
        option = _SERVICE_SLUG_ALIASES.get(slug.lower()) or _match_option(slug)
        if option:
            matched.append(option)
        else:
            unmatched.append(_prettify_slug(slug))

    return list(dict.fromkeys(matched)), ", ".join(dict.fromkeys(unmatched)) or None


# --------------------------------------------------------------------------
# Sitemap
# --------------------------------------------------------------------------

#: Pages whose whole job is to be the site's front door or identity, which the
#: extractor prompt treats as main pages and never as "Other Pages".
_IDENTITY_TITLES = {"home", "about us", "about", "why us", "why us?", "why choose us", "why choose us?"}

#: Structural rows that are not pages at all, and legal boilerplate nobody
#: generates marketing copy for. Left out so the extractor is not asked to
#: classify "Privacy Policy" as a service.
_SKIP_TITLES = {
    "privacy policy", "terms conditions", "terms and conditions", "terms of service",
    "cookie policy", "cookie policy uk", "sitemap", "services", "service areas",
}

#: `source` values that mean "WBT agreed this page with the client", as opposed
#: to `site-crawl`, which is just what their existing site happens to contain.
_AGREED_SOURCES = {"baseline", "admin", "service-area", "kickoff"}

#: Parents that mean a page has been FILED INTO the agreed tree, whatever its
#: source. This matters more than `source` does: a crawled page someone has
#: since parented under `services` has been curated into the agreed structure,
#: while a crawled page still sitting at `parent: None` has not been looked at.
#: Without this, a client whose services were all discovered by crawl and then
#: filed correctly would come back with no services at all.
_AGREED_PARENTS = {"services", "service-areas", "why-choose-us"}


def _is_agreed(page: dict) -> bool:
    return page.get("source") in _AGREED_SOURCES or (page.get("parent") or "") in _AGREED_PARENTS


def _sitemap(payload: dict) -> dict:
    """Builds the Sitemap box's text from the AGREED sitemap only.

    Returns {text, status, page_count}. `status` is agreed | crawl_only | none.

    Crawl pages are deliberately excluded rather than merged in. The prompts
    call the sitemap the highest authority and forbid naming any page, service
    or area that is not on it, so handing them a crawl of the client's OLD site
    would generate the wrong site with full confidence. A crawl also arrives
    flat -- no services/areas grouping, and carrying Privacy Policy and Terms --
    so there is nothing reliable to section it by.

    The output shape is the tab-separated one the Sitemap Data Extractor prompt
    was written against: PAGE NAME, FINAL PAGE URL, INSTRUCTIONS FOR PAGE, with
    FUNNEL in the middle column where HQ marks a page as one.
    """
    pages = (payload.get("sitemap") or {}).get("pages") or []
    if not pages:
        return {"text": None, "status": "none", "page_count": 0}

    agreed = [p for p in pages if isinstance(p, dict) and _is_agreed(p)]
    if not agreed:
        return {"text": None, "status": "crawl_only", "page_count": 0}

    identity, other, services, areas = [], [], [], []
    for page in agreed:
        title = _clean(page.get("title"))
        if not title or title.lower() in _SKIP_TITLES:
            continue
        page_type = page.get("type")
        parent = page.get("parent") or ""
        if page_type == "blog":
            # The extractor is told not to put blogs in the other-pages
            # descriptions, and blog topics come from the Blogs branch instead.
            continue
        if not parent and title.lower() in _IDENTITY_TITLES:
            identity.append((title, page_type))
        elif page_type in ("service", "funnel") or parent == "services":
            services.append((title, page_type))
        elif page_type == "area" or parent == "service-areas":
            areas.append((title, page_type))
        else:
            other.append((title, page_type))

    # A handful of stray pages is worse than nothing here. Some clients have two
    # area pages parented correctly and everything else still an unsorted crawl;
    # emitting that as the agreed sitemap would tell the prompts the business has
    # two locations and no services, and they would write exactly that. Require a
    # front door and at least one service or area before calling it usable.
    if not identity or not (services or areas):
        return {"text": None, "status": "crawl_only", "page_count": 0}

    def row(title: str, page_type: Optional[str] = None) -> str:
        # FUNNEL goes in the URL column because that is where the agreed
        # sitemaps put it, and the extractor keys off it there.
        return "%s\t%s\t" % (title, "FUNNEL" if page_type == "funnel" else "")

    lines = ["PAGE NAME\tFINAL PAGE URL\tINSTRUCTIONS FOR PAGE"]
    lines += [row(t.upper(), k) for t, k in identity]
    lines += [row(t, k) for t, k in other]
    if services:
        lines.append(row("SERVICES"))
        lines += [row(t, k) for t, k in services]
    if areas:
        lines.append(row("AREAS COVERED"))
        lines += [row(t, k) for t, k in areas]

    count = len(identity) + len(other) + len(services) + len(areas)
    return {"text": "\n".join(lines), "status": "agreed", "page_count": count}


def get_client_prefill(client_id: str) -> ClientPrefill:
    payload = _get({"clientId": client_id})
    account = payload.get("account") or {}
    answers = (payload.get("questionnaire") or {}).get("answers") or {}
    company_details = answers.get("company_details") or {}

    # The questionnaire holds the trading name the client typed; account.name is
    # the CRM label, which is the only name we have for clients who haven't
    # filled the questionnaire in yet.
    company_name = (
        _clean(company_details.get("company_name") if isinstance(company_details, dict) else None)
        or _clean(account.get("name"))
        or ""
    )

    contact = _contact(payload, answers)
    sitemap = _sitemap(payload)
    matched_industries, other_industries = _industries(answers)

    return ClientPrefill(
        company_name=company_name,
        industry=_canonical_industry(answers.get("industry")),
        # There is no dedicated USP question — accreditations is what the
        # onboarding actually captures about what sets the business apart.
        usps=_clean(answers.get("accreditations")),
        website_url=_website_url(answers if isinstance(answers, dict) else {}),
        sitemap_text=sitemap["text"],
        sitemap_status=sitemap["status"],
        sitemap_page_count=sitemap["page_count"],
        industries=matched_industries,
        other_industries=other_industries,
        **contact,
    )
