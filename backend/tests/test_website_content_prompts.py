# -*- coding: utf-8 -*-
"""Proves every website-content prompt is still byte-identical to the n8n node.

The prompts in app/agents/website_content/prompts/ were lifted out of
"Website Content Generation (V7).json" mechanically, not by hand. This test
reverses that transform -- unescape the doubled braces, put each n8n expression
back where its ChatPromptTemplate field is -- and diffs the result against the
node's own text in the workflow JSON.

It exists because the whole port rests on the prompts being unchanged. They are
tuned, and this module deliberately reproduces their quirks (`accreditiations`,
"Sinage and Shoplifting", the plural "Services Page"), so a well-meaning tidy-up
is exactly the kind of edit that would pass review and silently change output.
This turns that into a failing test.

Needs WORKFLOW_JSON to point at the export; skips cleanly when it is absent, so
a checkout without the JSON does not fail the suite.

Run: backend/venv/Scripts/python.exe tests/test_website_content_prompts.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.website_content.prompts import (  # noqa: E402
    analyst_prompt,
    blog_prompts,
    home_page_prompt,
    about_us_prompt,
    industry_prompt,
    knowledge_base_prompts,
    other_page_prompt,
    refine_prompts,
    service_area_prompt,
    service_page_prompt,
    sitemap_prompt,
)

#: Where the n8n export lives. The JSON is not in the repo -- it is the source
#: artefact the prompts were lifted from, kept alongside it -- so both the repo
#: root and its parent are checked before giving up. WORKFLOW_JSON overrides.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FILENAME = "Website Content Generation (V7).json"
_CANDIDATES = [
    os.path.join(_REPO, _FILENAME),
    os.path.join(os.path.dirname(_REPO), _FILENAME),
]

WORKFLOW_JSON = os.environ.get("WORKFLOW_JSON") or next(
    (path for path in _CANDIDATES if os.path.exists(path)), _CANDIDATES[0]
)


# --------------------------------------------------------------------------
# The reverse transform
# --------------------------------------------------------------------------


def unconvert(text, reverse):
    """`{{` -> `{`, `}}` -> `}`, and `{field}` -> the n8n expression it came from.

    Walked character by character rather than by regex: after escaping, a literal
    brace and a template field differ only by doubling, and no regex reads that
    unambiguously in a prompt containing sixty lines of example JSON.
    """
    out = []
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair == "{{":
            out.append("{")
            i += 2
        elif pair == "}}":
            out.append("}")
            i += 2
        elif text[i] == "{":
            end = text.index("}", i)
            name = text[i + 1 : end]
            if name not in reverse:
                raise AssertionError("unknown template field {%s}" % name)
            out.append("{{ %s }}" % reverse[name])
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def node_text(nodes, name, path):
    """The raw text of one node parameter, minus n8n's leading `=` marker."""
    value = nodes[name]["parameters"]
    for key in path.split("."):
        value = value[int(key)] if key.isdigit() else value[key]
    return value[1:] if value.startswith("=") else value


# --------------------------------------------------------------------------
# The placeholder maps, as gen used them
# --------------------------------------------------------------------------

BRIEF = {
    "$json.business_name": "business_name",
    "$json.phone_number": "phone_number",
    "$json.email": "email",
    "$json.address": "address",
    "$json.country": "country",
    "$json['state-province-region']": "state_province_region",
    "$json['zip-postal-code']": "zip_postal_code",
    "$json['unique-selling-points']": "unique_selling_points",
    "$json.unique_selling_points": "unique_selling_points",
    "$json.services": "services",
    "$json.areas": "areas",
    "$json.sitemap": "sitemap",
    "$json.pricing": "pricing",
    "$json.accreditiations": "accreditiations",
    "$json.industries": "industries",
    "$json.complete_meeting_insights": "complete_meeting_insights",
    "$json.other_pages": "other_pages",
    "$('Form Data').first().json.description_for_other_pages": "description_for_other_pages",
}

ANALYST = {
    "$json.business_name": "business_name",
    "$json.phone_number": "phone_number",
    "$json.email": "email",
    "$json.address": "address",
    "$json.country": "country",
    "$json['state-province-region']": "state_province_region",
    "$json['zip-postal-code']": "zip_postal_code",
    "$json['unique-selling-points']": "unique_selling_points",
    "$json.fathom_meeting1_summary": "fathom_meeting1_summary",
    "$json.fathom_meeting1_transcript": "fathom_meeting1_transcript",
    "$json.fathom_meeting2_summary": "fathom_meeting2_summary",
    "$json.fathom_meeting2_transcript": "fathom_meeting2_transcript",
    "$json.fathom_meeting3_summary": "fathom_meeting3_summary",
    "$json.fathom_meeting3_transcript": "fathom_meeting3_transcript",
    "$json.loom1_summary": "loom1_summary",
    "$json.loom1_transcript": "loom1_transcript",
    "$json.loom2_summary": "loom2_summary",
    "$json.loom2_transcript": "loom2_transcript",
    "$json.loom3_summary": "loom3_summary",
    "$json.loom3_transcript": "loom3_transcript",
    "$json.sitemap_text": "sitemap_text",
    "$json.pricing_info": "pricing_info",
    "$json.services_offered": "services_offered",
    "$json.areas_covered": "areas_covered",
}

BLOGS = {
    "$('Generate Titles').item.json.text": "blog_titles",
    "$json.keywords": "keywords",
    "$('Content Data').first().json.areas": "areas",
    "$('Form Data').first().json.business_name": "business_name",
    "$('Content Data').first().json.sitemap": "sitemap",
    "$('Content Data').first().json.pricing": "pricing",
    "$('Content Data').first().json.services": "services",
    "$('Content Data').first().json.unique_selling_points": "unique_selling_points",
    "$('Content Data').first().json.complete_meeting_insights": "complete_meeting_insights",
}

SYSTEM = "options.systemMessage"
CHAIN_SYSTEM = "messages.messageValues.0.message"

#: (constant, node name, parameter path, placeholder map)
CASES = [
    (sitemap_prompt.SITEMAP_EXTRACTION_PROMPT, "Sitemap Data Extractor", "text",
     {"$('On form submission').item.json['Sitemap Text']": "sitemap_text"}),
    (analyst_prompt.ANALYST_PROMPT, "Analyst Node", "text", ANALYST),
    (analyst_prompt.JSON_CORRECTION_PROMPT, "Json Correction Agent", "text",
     {"$('Analyst Node').item.json.text": "raw_output", "$json.error": "error_message"}),
    (industry_prompt.SELECT_INDUSTRY_SYSTEM_PROMPT, "Select Industry", CHAIN_SYSTEM, {}),
    (industry_prompt.SELECT_INDUSTRY_USER_PROMPT, "Select Industry", "text",
     {"$('Form Data').item.json.other_industries": "other_industries"}),
    (home_page_prompt.HOME_PAGE_SYSTEM_PROMPT, "Home Page", SYSTEM, {}),
    (home_page_prompt.HOME_PAGE_USER_PROMPT, "Home Page", "text", BRIEF),
    (about_us_prompt.ABOUT_US_SYSTEM_PROMPT, "About Us Page", SYSTEM, {}),
    (about_us_prompt.ABOUT_US_USER_PROMPT, "About Us Page", "text", BRIEF),
    (service_page_prompt.SERVICE_PAGE_SYSTEM_PROMPT, "Service Page", SYSTEM, {}),
    (service_page_prompt.SERVICE_PAGE_USER_PROMPT, "Service Page", "text", BRIEF),
    (service_area_prompt.SERVICE_AREA_SYSTEM_PROMPT, "Service Area", SYSTEM, {}),
    (service_area_prompt.SERVICE_AREA_USER_PROMPT, "Service Area", "text", BRIEF),
    (other_page_prompt.OTHER_PAGE_SYSTEM_PROMPT, "Other Page", SYSTEM, {}),
    (other_page_prompt.OTHER_PAGE_USER_PROMPT, "Other Page", "text", BRIEF),
    (blog_prompts.GET_INDUSTRY_PROMPT, "Get Industry", "text",
     {"$json.complete_meeting_insights": "complete_meeting_insights"}),
    (blog_prompts.GET_SERVICE_PROMPT, "Get Service ", "text",
     {"$('Content Data').item.json.complete_meeting_insights": "complete_meeting_insights"}),
    (blog_prompts.GENERATE_TITLES_PROMPT, "Generate Titles", "text", {"$json.text": "service"}),
    (blog_prompts.BLOGS_SYSTEM_PROMPT, "Blogs", SYSTEM, {}),
    (blog_prompts.BLOGS_USER_PROMPT, "Blogs", "text", BLOGS),
    (refine_prompts.CRITIC_SYSTEM_PROMPT, "Critic Agent", CHAIN_SYSTEM, {}),
    (refine_prompts.CRITIC_USER_PROMPT, "Critic Agent", "text",
     {"$json.output": "draft", "$json.remaining_issues": "remaining_issues"}),
    (refine_prompts.REFINER_SYSTEM_PROMPT, "Refiner Agent", CHAIN_SYSTEM, {}),
    (refine_prompts.REFINER_USER_PROMPT, "Refiner Agent", "text",
     {"$('loop_input').item.json.output": "draft", "$json.text": "critic_report"}),
    (refine_prompts.EVALUATOR_SYSTEM_PROMPT, "Evaluator Agent ", CHAIN_SYSTEM, {}),
    (refine_prompts.EVALUATOR_USER_PROMPT, "Evaluator Agent ", "text",
     {"$json.text": "refined_page", "$('loop_input').item.json.output": "draft",
      "$('Critic Agent').item.json.text": "critic_report"}),
]

#: The five knowledge-base tool descriptions, per page agent. Each page had its
#: own five nodes in n8n, differing only in their worked examples, which is why
#: the descriptions are stored per page rather than shared.
KB_SUFFIX = {"home": "", "about_us": "1", "service": "2", "service_area": "3", "other": "4"}
KB_BASES = [
    ("Energy and Heating Systems Knowledge Base", "energy_heating_systems"),
    ("Construction and Property Services Knowledge Base", "construction_property_services"),
    ("Home Improvement and Interiors Knowledge Base", "home_improvement_interiors"),
    ("Electrical and Security Systems Knowledge Base", "electrical_security_systems"),
    ("Health and Aesthetics Knowledge Base", "health_aesthetics"),
]


#: Prompts we have deliberately moved away from the n8n original, and why.
#:
#: The point of this test is to catch UNINTENDED drift, not to freeze the prompts
#: forever. Once a prompt is knowingly rewritten, holding it to byte parity would
#: mean either a permanently red suite or deleting the check for all 52, and both
#: of those lose the guard on the prompts nobody has touched.
#:
#: So a rewritten prompt moves here with its reason. It is still compared, but a
#: difference is reported as EXPECTED rather than counted as a failure, and a
#: prompt in this list that has gone BACK to matching n8n is itself reported, so
#: stale entries cannot pile up unnoticed.
#:
#: All of these come from the 28 Aug 2026 client review: pages were text heavy,
#: repeated copy across services and sold the service to a reader who had already
#: chosen it. See prompts/direct_response.py for the shared method.
DIVERGED = {
    ("Home Page", SYSTEM):
        "reader-first opening; trade-neutral vocabulary guidance",
    ("About Us Page", SYSTEM):
        "reader-awareness block, two worked examples from unrelated trades, "
        "reader-first structure, accreditations no longer hardcoded to heating",
    ("Service Page", SYSTEM):
        "reader-awareness block, landing-page structure, cross-page uniqueness, "
        "examples spread across trades instead of all boiler",
    ("Service Page", "text"):
        "shorter page target (450-650 words)",
    ("Service Area", SYSTEM):
        "shorter target and density rules; the 22 boiler/West-London example "
        "lines replaced with trade-neutral placeholders",
    ("Service Area", "text"):
        "shorter page target (350-550 words per area)",
    ("Other Page", SYSTEM):
        "YOUR ROLE no longer points at the knowledge-base style; page-type list "
        "and vocabulary guidance no longer heating-specific",

    # The prompts were themselves written full of em dashes while instructing the
    # model never to output one. The Refiner's own system message contained 24 of
    # them, and it was the agent observed adding em dashes to a clean draft. Every
    # em dash used as prose punctuation is now a comma; the only ones left are the
    # two that QUOTE the character as the thing being banned.
    ("Sitemap Data Extractor", "text"): "prose em dashes replaced with commas",
    ("Blogs", SYSTEM): "prose em dashes replaced with commas",
    ("Critic Agent", CHAIN_SYSTEM): "prose em dashes replaced with commas (29 of them)",
    ("Refiner Agent", CHAIN_SYSTEM): "prose em dashes replaced with commas (24 of them)",
    ("Evaluator Agent ", CHAIN_SYSTEM): "prose em dashes replaced with commas (11 of them)",
}


def main():
    if not os.path.exists(WORKFLOW_JSON):
        print("SKIP  workflow JSON not found at %s" % WORKFLOW_JSON)
        print("      set WORKFLOW_JSON to run this check")
        return 0

    workflow = json.load(open(WORKFLOW_JSON, encoding="utf-8"))
    nodes = {n["name"]: n for n in workflow["nodes"]}
    failures = 0
    expected = 0
    reconverged = []

    for generated, name, path, mapping in CASES:
        want = node_text(nodes, name, path)
        got = unconvert(generated, {v: k for k, v in mapping.items()})
        reason = DIVERGED.get((name, path))
        if got == want:
            if reason is not None:
                reconverged.append((name, path))
            continue
        if reason is not None:
            expected += 1
            print("OK    %s / %s diverged as intended: %s" % (name, path, reason))
            continue
        failures += 1
        print("DIFF  %s / %s" % (name, path))
        for index, (a, b) in enumerate(zip(got, want)):
            if a != b:
                print("      first difference at char %d" % index)
                print("      ours: %r" % got[index : index + 70])
                print("      n8n : %r" % want[index : index + 70])
                break
        else:
            print("      length differs: %d vs %d" % (len(got), len(want)))

    for page, suffix in KB_SUFFIX.items():
        for base, namespace in KB_BASES:
            want = node_text(nodes, base + suffix, "toolDescription")
            got = knowledge_base_prompts.KB_TOOL_DESCRIPTIONS[page][namespace]
            if got != want:
                failures += 1
                print("DIFF  knowledge-base tool %s / %s" % (page, namespace))

    want = node_text(nodes, "Blogs Knowledge Base", "toolDescription")
    if knowledge_base_prompts.BLOGS_KB_TOOL_DESCRIPTION != want:
        failures += 1
        print("DIFF  Blogs Knowledge Base tool description")

    checked = len(CASES) + len(KB_SUFFIX) * len(KB_BASES) + 1

    # A prompt listed as diverged that now matches n8n again means the rewrite was
    # reverted, or the entry was never right. Either way the list is lying about
    # the state of the prompts, so say so rather than quietly passing.
    for name, path in reconverged:
        failures += 1
        print("STALE %s / %s is listed in DIVERGED but matches n8n again" % (name, path))

    if failures:
        print("\nFAIL  %d of %d prompts differ from the n8n workflow" % (failures, checked))
        return 1
    print(
        "OK    %d of %d prompts match the n8n workflow byte for byte, "
        "%d deliberately diverged" % (checked - expected, checked, expected)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
