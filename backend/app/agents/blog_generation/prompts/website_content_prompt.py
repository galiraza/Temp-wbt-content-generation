# -*- coding: utf-8 -*-
"""Verbatim from the n8n workflow "Blogs Content Generation (V2)", node "Website Content".

Re-extracted from the workflow JSON, which is never modified. n8n
expression placeholders became ChatPromptTemplate fields; literal JSON
braces are escaped as {{ }} because that is what the template engine
requires. Do not reword: the output format is what the parsers in
app.agents.blog_generation.parsers read back.
"""

#: Placeholders: scraped_markdown
WEBSITE_CONTENT_USER_PROMPT = """\n# Website Content Structuring Prompt

You are an expert content parser. You will receive raw, unstructured data scraped from a website. Your job is to analyze it, identify every piece of meaningful content, and output it in a clean, well-organized, readable markdown format.

---

## Rules

1. **Extract everything.** Do not skip, summarize, or omit any content. Every detail matters.
2. **Auto-detect sections.** There is no fixed template — identify the natural sections and content types present in the data and organize accordingly.
3. **Use clean markdown.** Use headings, subheadings, bullet points, tables, and blockquotes where appropriate for readability.
4. **Preserve exact wording** for: testimonials/reviews, FAQs, pricing, terms & conditions, legal text, and quotes.
5. **Deduplicate.** If the same content appears multiple times (common in scraped data), include it only once.
6. **Ignore junk.** Skip raw HTML/SVG code, base64 data, broken formatting artifacts, and meaningless markup. Focus only on human-readable content.
7. **Extract from image alt text.** If image alt text contains meaningful information (brand names, descriptions, context), treat it as content.
8. **Organize logically.** Group related items together even if they were scattered in the raw data.

---

## Content Types to Look For

Detect and structure whichever of these are present (skip any that don't exist in the data):

- **Company / Brand Info** — name, tagline, description, location, contact details, social links
- **Navigation & Page Structure** — main menu items, section hierarchy
- **Services / Products** — names, descriptions, features, specifications
- **Pricing / Packages** — plans, tiers, costs, payment terms, what's included
- **Testimonials / Reviews** — reviewer name, platform, rating, full review text
- **Case Studies / Portfolio** — project details, results, metrics
- **Team / People** — names, roles, bios
- **FAQs** — questions and answers
- **Blog Posts / Articles** — titles, summaries, dates, authors
- **Promotions / Offers** — details, terms, eligibility, dates
- **Accreditations / Certifications / Trust Signals** — badges, partner logos, certifications
- **CTAs (Calls to Action)** — button text and destination URLs
- **Media Assets** — image URLs with descriptions, video references
- **Legal / Policy Content** — terms, privacy policy, disclaimers
- **SEO / Keyword Content** — keyword lists, meta descriptions, tags
- **Footer Content** — address, copyright, secondary links
- **Any other meaningful content** — if it doesn't fit the above, create an appropriate section for it

---

## Output Format

```
# [Website Name or Title]

> One-line summary of what this website/business is about.

## [Section Name]
(organized content here)

## [Section Name]
(organized content here)

...
```

Use tables for pricing/comparison data. Use blockquotes for testimonials. Use bullet lists for features and specs. Use numbered lists for steps or processes.

---

## Raw Scraped Data

```
{scraped_markdown}
```

---

Now parse the above raw data and produce a fully structured, readable markdown document."""
