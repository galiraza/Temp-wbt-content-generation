"""The blog keyword row, looked up by industry.

n8n read this from a data table called "WBT-Blogs-Keywords" (two columns,
`Industry` and `Keywords`) via a `dataTable` node, aggregated every row into one
item, and then a Code node did a case-insensitive match of the "Get Industry"
answer against the `Industry` column:

    const match = keywordData.find(item =>
      item.Industry.toLowerCase() === selectedIndustry.toLowerCase()
    );
    if (match && match.Keywords) matchedKeywords = match.Keywords;

`lookup` below is that, exactly -- including the part that matters most: **a
miss returns an empty string, and the blogs are written anyway**. The Blogs
prompt reads the keyword row as "(Use three keywords from these that best fit in
the blog if available.)", so an empty row means the agent writes without forced
keywords rather than the run failing.

The rows themselves are hardcoded here rather than kept in a table, so changing
them is a code change and a redeploy -- the same trade app.rag.industries makes.

  NOTE: the keyword strings are the one thing that could not be lifted from the
  workflow JSON. n8n data tables live in the n8n database, not in the exported
  workflow, so `KEYWORDS_BY_INDUSTRY` below carries the industry list from the
  "Get Industry" prompt with empty rows. Paste the exported Keywords column in
  and nothing else needs touching. Until then every industry misses, which is
  the same path n8n already took for any industry with no row.
"""

import logging
from typing import Dict

logger = logging.getLogger("app")

#: Industry -> the comma-separated keyword row for its blogs.
#:
#: The keys are the exact 28 options the "Get Industry" prompt constrains the
#: model to, in its own order and its own spelling ("Sinage and Shoplifting",
#: "wood Burning Stove"). Do not tidy the spellings: the match is against what
#: that prompt returns, and correcting one here turns a hit into a miss.
KEYWORDS_BY_INDUSTRY: Dict[str, str] = {
    "Air Conditioner": "",
    "ASHP": "",
    "Bathroom Installation": "",
    "Boiler": "",
    "Building Construction": "",
    "Canopy Verandas": "",
    "Damp Proofing": "",
    "Doors and Windows": "",
    "Driveway and Patio": "",
    "ECO4": "",
    "Electrical": "",
    "EV Charger": "",
    "Fire Protection": "",
    "Garden Rooms": "",
    "Insulation": "",
    "Insurance Claim": "",
    "Networking Service": "",
    "Painting and Decorating": "",
    "Property Maintenance": "",
    "Roofing": "",
    "Security Installer": "",
    "Sinage and Shoplifting": "",
    "Skin Booster": "",
    "Solar": "",
    "Stairlifts and Homelifts": "",
    "Swimming pool": "",
    "Television": "",
    "wood Burning Stove": "",
}

#: Built once. Matching is case-insensitive because the n8n Code node compared
#: `.toLowerCase()` on both sides, and the model does not always echo the
#: prompt's exact capitalisation back.
_BY_LOWER = {name.lower(): keywords for name, keywords in KEYWORDS_BY_INDUSTRY.items()}


def lookup(industry: str) -> str:
    """The keyword row for an industry, or "" when there is no row for it."""
    key = (industry or "").strip().lower()
    if not key:
        return ""
    keywords = _BY_LOWER.get(key, "")
    if not keywords:
        # Not an error -- see the module docstring -- but worth a line, because
        # "the blogs came back with no keywords" is otherwise silent.
        logger.info("website_blog_keywords_missing industry=%s", industry)
    return keywords
