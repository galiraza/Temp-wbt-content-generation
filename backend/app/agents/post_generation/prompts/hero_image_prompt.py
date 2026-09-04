"""Prompt for the hero-image prompt builder: writes the 12 image-generation
prompts that the hero images (the background photos composed into each post's
graphic) are generated from.

No matching file existed in this module before this was ported - unlike the
other prompts here, this n8n node has only a user message, no system message,
so there is no *_SYSTEM_PROMPT constant. n8n expression placeholders became
str.format fields; field names match the ones already established elsewhere
in this module (usps -> unique_selling_points, notes -> additional_notes).

Do not reword this prompt: the phrasing and the strict JSON-array output
format are load-bearing for whatever parses the 12 prompts back out.
"""

HERO_IMAGE_PROMPT_USER_PROMPT = """\
You are a professional visual content strategist specialising in commercial photography for social media.
A company has provided the following details:

- Company Name: {company_name}
- Industry: {industry}
- Areas Covered: {areas_covered}

**FIXED RULES — These rules define how every image must be generated. Apply all of them strictly to every prompt:**
{fixed_rules}
PRIORITY: Fixed Rules are non-negotiable hard constraints. Every prompt MUST satisfy all Fixed Rules first, then incorporate the Main Topic within those constraints. If there is any conflict between Fixed Rules and Main Topic, Fixed Rules always win.

**MAIN TOPIC — All images must be related to this topic:**
{main_topic}

**WHAT MAKES THIS COMPANY DIFFERENT — use these as concrete inspiration for specific, believable scenes, not generic stock-photo ideas:**
{unique_selling_points}

**ADDITIONAL CONTEXT ABOUT THE COMPANY:**
{additional_notes}

**POST TITLES — Use these titles as additional context and inspiration for generating prompts. Each prompt should visually represent the theme and message behind these titles:**

{image_video_titles}

Each generated prompt must feel like it could serve as a fitting background image for one of these post titles. Aim to give roughly one prompt a distinctly matching scene for each title above, plus a few extra prompts covering different angles or moments of the same topic for variety.

Generate exactly 12 different hyper-realistic image generation prompts for social media post backgrounds. Every prompt must be directly related to the Main Topic above and must strictly follow all Fixed Rules above. Each prompt must depict a genuinely different scene, angle, or moment — no two prompts should feel interchangeable.

Each prompt MUST follow ALL of these rules:

REALISM RULES:
- The image must look like a real, unedited photograph taken on location with a phone or DSLR camera — not a render, illustration, CGI, or an obviously "AI-generated" image
- The image must directly and obviously represent the Main Topic — a viewer should immediately understand what is being shown
- Show the subject clearly — noticeably professional, modern, and well-maintained
- Be specific: reference the actual materials, tools, techniques, and finishes involved (drawing on the company's differentiators and services above) instead of generic descriptions — specificity is what makes an image feel real rather than AI-generated

AVOID THE "AI LOOK" — every prompt must explicitly include realistic imperfections so it reads as a genuine candid photo, not a polished render:
- Natural, slightly imperfect composition — not perfectly centred or symmetric, like a real photographer's candid shot
- Ordinary environmental clutter appropriate to the scene (parked cars, tool bags, dust sheets, scaffolding, weathered brickwork, an untidy work area) — real job sites are never pristine
- Natural UK daylight — often overcast or soft, never studio-perfect lighting
- Slight natural imperfections consistent with a real photo: natural grain, realistic depth-of-field falloff, minor lens vignetting — never airbrushed or artificially smooth surfaces

HUMAN INVOLVEMENT RULES — most prompts must show a real person genuinely engaged, not just the product or an empty scene:
- For most prompts, include either (a) a tradesperson actively performing a specific, industry-accurate action with their tools/equipment (installing, repairing, adjusting, applying, servicing — whatever this exact industry's technicians actually do), or (b) the customer/homeowner genuinely experiencing the benefit of the service (adjusting a thermostat or control, feeling warm/cool/comfortable at home, admiring finished work) — pick whichever fits each specific post title best
- Ground every human action in the specific industry and services described above — a heating engineer, a renderer/insulation installer, and an AC fitter all physically do different things; describe the exact real action for THIS company's trade, not a generic "person working"
- LOGO PLACEMENT: a company logo image is supplied as a reference. When a prompt shows a technician who is genuinely representing the company while performing the work, explicitly state that their workwear (jacket, polo shirt, or hi-vis) displays the company logo, matching the supplied reference exactly — never redraw, invent, or alter it. When a prompt shows a company van or vehicle, explicitly state that the van displays the company logo too. Do NOT put the logo on a customer/homeowner or on any bystander who is not a company representative — only genuine company workwear or company vehicles carry it. Prompts with no technician or van present (e.g. a customer-only comfort scene, or a finished-work-only shot) do not need to mention the logo at all. The supplied company logo must NEVER appear on any equipment, appliance, or product itself (never printed on a boiler, outdoor unit, or any product casing) — it belongs only on workwear and vehicles, nowhere else.
- NATURAL POSTURE: match each person's pose to how they would realistically be doing that activity — for example, someone using a desktop computer should normally be seated in an ordinary chair, not standing at a standing desk, unless the scene specifically calls for standing (e.g. actively installing something on a wall). An unnatural or unusual pose is a giveaway that an image is AI-generated.
- Prefer framing people from behind, the side, three-quarter angle, or focused on their hands/tools in action rather than a straight-on posed portrait — this reads as a genuine candid work photo and avoids the uncanny look AI models give front-on faces
- Hands performing simple, clear, unambiguous actions (holding a tool, adjusting a dial, pointing at something) — avoid complex hand poses that are prone to looking distorted
- A small number of prompts (roughly 2-3 of the 12) may reasonably feature only the finished work or equipment with no person, for variety — but this must be the exception, not the norm

COMPOSITION RULES:
- Professional commercial photography style with natural lighting
- Wide shot showing full context in its real environment
- No invented or fabricated text, watermarks, or stamped-on overlays added to the photo itself. This does NOT apply to authentic branding that would genuinely be printed on real equipment: if the Fixed Rules specify particular product/equipment brands (e.g. specific boiler, AC, or appliance manufacturers), any matching equipment shown in the scene must be exactly those brands, with that manufacturer's real name/nameplate/logo authentically visible on the unit's casing exactly as it appears on genuine equipment — a plain, unbranded unit is not realistic and must be avoided whenever Fixed Rules name a brand for that equipment type
- STRICT BRAND ACCURACY: only use an equipment/product brand name if it is explicitly written in the Fixed Rules text above — never substitute, guess, or default to a well-known brand that is not named there (for example, never show Mitsubishi or Daikin unless one of those exact names appears in the Fixed Rules). If the Fixed Rules do not name any brand for a given piece of equipment, show it unbranded/generic rather than inventing one. The company's own logo must never be used as the equipment's brand — the equipment's brand and the company's own logo are always two different things
- Photorealistic DSLR/smartphone camera quality, sharp focus where it matters, natural depth of field
- Surrounding environment should match the topic being shown

INDUSTRY & CULTURE RULES:
- Interpret every concept strictly according to the Industry named above — the same word can mean a different scene in a different trade. For example: "comfort" for an Air Conditioning/cooling company means a cool room in warm weather and a person by a wall-mounted indoor unit or using a remote/app; "comfort" for a boiler/heating company means warmth, hot water, and a cosy heated home in cold weather, with radiators or a boiler visible, not an AC unit; "comfort" for an insulation/rendering company means a well-insulated, weatherproofed home exterior. Never reuse a scene, prop, or piece of equipment from a different industry than the one named above.
- The setting, environment, and props must match the Main Topic and the company's services described above
- The image must feel authentic and local to the UK culture and environment — reference the specific towns/areas covered above where it naturally fits (typical local house styles, streets, weather) rather than a generic anywhere-in-the-world setting
- Realistic atmosphere — natural lighting, real locations, no studio setups

Return ONLY a JSON array like this:
["prompt 1 here",
"prompt 2 here",
"prompt 3 here",
"prompt 4 here",
"prompt 5 here",
"prompt 6 here",
"prompt 7 here",
"prompt 8 here",
"prompt 9 here",
"prompt 10 here",
"prompt 11 here",
"prompt 12 here"]
No explanation, no markdown, only the JSON array."""
