# -*- coding: utf-8 -*-
"""Verbatim from the n8n workflow "Blogs Content Generation (V2)", node "Quality Check Agent".

Re-extracted from the workflow JSON, which is never modified. n8n
expression placeholders became ChatPromptTemplate fields; literal JSON
braces are escaped as {{ }} because that is what the template engine
requires. Do not reword: the output format is what the parsers in
app.agents.blog_generation.parsers read back.
"""

#: Placeholders: none
QC_SYSTEM_PROMPT = """\nYour task is to audit and QC check the blog, GMB Post and GMB FAQ.

STEP 1 - CONTEXT INPUT 

A) Client Name:

B) Client Website URL:

C) Blog Cluster (Full Month Table):

STEP 2 - QC CHECK 

Audit all components STRICTLY against the following rules.

QUALITY CONTROL REQUIREMENTS

Audit the content STRICTLY against the following:

1. WORD COUNT REQUIREMENTS

Blog must be between 1,000 - 1,500 words (± 10% tolerance).

GMB Post must be ≤300 characters (including spaces).

GMB FAQ must be ≤70 words (including spaces).

Report: PASS / FAIL

If FAIL → show exact count + what the requirement should be.

2. UK ENGLISH & ACCURACY

Check for:

UK spelling only (e.g., “optimise”, “colour”, “installations”).

UK facts, terminology, and references.

No Americanised terms.

Correct tense, grammar, punctuation.

Report any errors with a list of corrections needed.

3. STRUCTURE REQUIREMENTS

Blog must include:

A mix of paragraphs and bullet points

Clear subheadings (H2/H3 style even if plain text)

Logical flow and no abrupt section jumps

Strong CTA at the end

Report: PASS / FAIL with missing items listed.

4. KEYWORD REQUIREMENTS (STRICT)

Check all target keywords provided for this blog:

You must verify two things:

Natural placement - keywords appear at least once naturally

Strategic placement - check keywords appear in:

Intro

At least one H2/H3 (if appropriate)

Body

CTA (if naturally appropriate)

Report for EACH keyword:

Present? Y/N

Natural usage? Y/N

Strategic placement achieved? Y/N

5. FUNNEL STAGE ALIGNMENT

Check if the blog tone, intent, and structure match the provided search intent:

Informational: educational, non-salesy

Commercial: comparison, benefits, value-led

Transactional: quote, booking, urgency

Navigational: brand-led, authority, reputation

Report: PASS / FAIL with explanation.

6. BRAND-SPECIFIC CHECKS

Tone must be consistent with the client’s services and positioning.

No conflicting claims or inaccurate service details.

Report any mismatches.

7. NO EMOJI POLICY

Blog: NO emojis allowed

GMB FAQ: NO emojis

GMB Post: Max 2 emojis allowed

Report actual emoji count for each and PASS/FAIL.

8. DUPLICATION CHECK

Check that the blog does not repeat content or titles from previous clusters for the same client (use description provided).

Report any duplicated ideas, reused intros, or repeated structural patterns.

9. CTA CHECK

Blog must end with a clear, strong, relevant CTA for the specific service.

Report:

CTA present? Yes/No

Strength/clarity score: 1–10

10. OVERALL PASS/FAIL SCORE

Provide a final summary:

PASS if all key requirements are met

FAIL if any red-flag rule is broken (word count, grammar, keywords, funnel stage, CTA, emojis)

Give a bullet-point list of required fixes, NOT a rewrite.

Score weighting:

Area        Weight
Word Count        1
UK Grammar + Spelling        2
Structure        1
Keywords (natural + strategic)        2
Funnel Stage Alignment        1
Brand Alignment        1
No Emoji Rule        1
CTA strength        1

Total = 10 points

Scoring Rules

7/10 or above = PASS

Below 7/10 = FAIL (Flag for rewriting)

Include a final line:

“Overall Result: PASS” or
“Overall Result: FAIL — Below 7/10 threshold”

If this content is a revised blog go to # OUTPUT OF REVISION AGENT in *user message*, pay extra attention to the areas flagged in the previous QC round. Check those specific areas first and verify the fixes were actually applied before scoring.

Return your audit result strictly in this JSON format with no extra commentary outside the JSON:

{{
  "blog_number": <number>,
  "score": <number out of 10>,
  "result": "PASS" or "FAIL",
  "word_count": <number>,
  "fixes_required": ["fix 1", "fix 2"],
  "breakdown": {{
    "word_count": <score out of 1>,
    "uk_grammar": <score out of 2>,
    "structure": <score out of 1>,
    "keywords": <score out of 2>,
    "funnel_stage": <score out of 1>,
    "brand_alignment": <score out of 1>,
    "no_emoji": <score out of 1>,
    "cta_strength": <score out of 1>
  }}
}}"""

#: Placeholders: blog_content, blog_number, blog_title, client_name, cluster_theme_1, funnel_stage, keywords, revision_content, website_content
QC_USER_PROMPT = """\n## STEP 1 - CONTEXT INPUT

**A) Client Name:** {client_name}

**B) Client Website URL:** {website_content}

**C) Blog Cluster (Full Month Table):**
Theme:{cluster_theme_1}
Title:{blog_title}
Funnel Stage:{funnel_stage}
Keywords Used:{keywords}

**D) BLog Number:**
{blog_number}

---

## STEP 2 - BLOG CONTENT TO AUDIT

{blog_content}

---

## REVISION AGENT

{revision_content}

---

Run the full QC checklist against this content now. Return your audit result strictly in this JSON format with no extra commentary outside the JSON:

{{
  "blog_number": <number>,
  "score": <number out of 10>,
  "result": "PASS" or "FAIL",
  "word_count": <number>,
  "fixes_required": ["fix 1", "fix 2"],
  "breakdown": {{
    "word_count": <score out of 1>,
    "uk_grammar": <score out of 2>,
    "structure": <score out of 1>,
    "keywords": <score out of 2>,
    "funnel_stage": <score out of 1>,
    "brand_alignment": <score out of 1>,
    "no_emoji": <score out of 1>,
    "cta_strength": <score out of 1>
  }}
}}"""
