from typing import List, Optional

from pydantic import BaseModel


class ClientPrefill(BaseModel):
    """The subset of a client's exported onboarding data the forms prefill from.

    Deliberately narrow: the HQ export returns the client's entire record —
    billing, Stripe ids, logins, sales process, growth reports — and none of
    that belongs in the browser. Every field here is one a form actually fills.

    Four consumers with different needs: the ad-angle and logo forms want
    `industry` (one value, in app.rag.industries spelling), the blog form wants
    `website_url`, and the website-content form wants the contact block, the
    sitemap and `industries` (many values, in app.schemas.website_content
    spelling). The two industry vocabularies are genuinely different lists, so
    they are two fields rather than one reused one.
    """

    company_name: str
    industry: Optional[str] = None
    usps: Optional[str] = None
    #: The client's own site, for the blog form's required Website Homepage URL.
    #: Often absent — most clients have not answered the domain question — so the
    #: form treats it as a convenience, never a dependency.
    website_url: Optional[str] = None

    # --- the contact block, from companyInfo ---
    # HQ keeps these separately from the questionnaire, and they are the closest
    # thing to a verified address the export has.
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    postcode: Optional[str] = None

    # --- website content ---
    #: The agreed sitemap as tab-separated text, ready for the form's Sitemap
    #: box. None whenever HQ has no AGREED sitemap for this client — see
    #: `sitemap_status`. Never built from a crawl of the client's existing site.
    sitemap_text: Optional[str] = None
    #: Why `sitemap_text` is or isn't there, so the form can say so rather than
    #: leaving the user guessing at an empty box:
    #:   agreed     -> filled from the sitemap WBT agreed with the client
    #:   crawl_only -> HQ only has pages crawled off their existing site
    #:   none       -> HQ has no sitemap at all for this client
    sitemap_status: str = "none"
    #: How many pages the agreed sitemap held, for the form's confirmation line.
    sitemap_page_count: int = 0

    #: The client's services, matched onto the website-content industry options.
    industries: List[str] = []
    #: Services that matched none of them, comma-joined for the Other industry
    #: box. Nothing is lost by failing to match: that box is itself classified
    #: by the Select Industry agent at generation time.
    other_industries: Optional[str] = None
