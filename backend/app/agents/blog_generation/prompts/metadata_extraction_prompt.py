# -*- coding: utf-8 -*-
"""Verbatim from the n8n workflow "Blogs Content Generation (V2)", node "Blog Metadata Extractor".

Re-extracted from the workflow JSON, which is never modified. n8n
expression placeholders became ChatPromptTemplate fields; literal JSON
braces are escaped as {{ }} because that is what the template engine
requires.

ONE deliberate difference from the JSON, and nothing else: the hardcoded count
of 12 is gone. The n8n prompt said "exactly 12 blogs" in four places and
"Output must always contain exactly 12 objects", so a plan with three blogs came
back as three real ones plus nine "<UNKNOWN>" placeholders — the model padding to
satisfy the instruction. The count now comes from the input, and the prompt
forbids padding. The form's "Cluster #" is what the extracted count is checked
against, in blog_generation_service.run_metadata_extraction.

Everything else is unchanged. Do not reword the rest: the output format is what
the BlogMetadataList schema in app.agents.blog_generation.parsers validates.
"""

#: Placeholders: blog_schema
METADATA_EXTRACTION_USER_PROMPT = """\nExtract the blog metadata from the following raw input. Identify every blog present in the input, in the order they appear, and return the structured JSON with blog_title, funnel_stage, service_areas, and keywords for each.

Raw Input:
{blog_schema}"""

#: Placeholders: none
METADATA_EXTRACTION_SYSTEM_PROMPT = """\nYou are a blog metadata extraction agent. You will receive a raw, unstructured text string from a previous node that contains metadata for one or more blogs packed together without clear delimiters.

Your job is to carefully read through the entire input from start to finish and sequentially identify each blog one by one (Blog 1 through the last one present) by recognizing these four elements in order:

1. blog_title — The full descriptive title of the blog post
2. funnel_stage — One of: Informational, Commercial, Transactional, Navigational, or combinations like "Info → Commercial" or "Commercial → Transactional". This always appears immediately after the blog title.
3. service_areas — Extract any location/city/region names found in the blog title or keywords (e.g. "Worthing"). Return as an array. If none found, return [].
4. keywords — All keyword phrases that appear after the funnel stage and before the next blog title. Split by comma. Trim whitespace. Return as an array.

The pattern repeats for every blog present:
[Blog Title][Funnel Stage][keywords], [keywords]...[Next Blog Title][Funnel Stage]...

Output ONLY this exact JSON structure with no explanation, no preamble, no markdown, no code fences:

{{
  "blogs": [
    {{
      "blog_number": 1,
      "blog_title": "...",
      "funnel_stage": "...",
      "service_areas": ["..."],
      "keywords": ["...", "..."]
    }},
    {{
      "blog_number": 2,
      "blog_title": "...",
      "funnel_stage": "...",
      "service_areas": ["..."],
      "keywords": ["...", "..."]
    }}
  ]
}}

Critical rules:
- Process blogs strictly in order: 1, 2, 3 ... N. Never skip or merge any blog.
- Do NOT use TOFU, MOFU, BOFU — use only the exact funnel stage text from the input.
- Do NOT invent or modify any blog title, keyword, or funnel stage — extract them exactly as they appear.
- Output exactly one object per blog that is actually present in the input.
- Never pad the array to reach a target count. Do NOT invent placeholder blogs,
  and never emit a title such as "<UNKNOWN>" or "N/A" to fill a gap. If the input
  holds three blogs, return three objects.
- Return only raw JSON. Nothing else."""
