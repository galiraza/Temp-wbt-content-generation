// Generation-form field specs, one per section.
//
// Ported field-for-field from Paid_Ads_Generation/frontend:
//   website  <- components/website-content/WebsiteContentForm.tsx
//   posts    <- components/post-generation/PostGenerationForm.tsx
//   blog     <- components/blog-generation/BlogGenerationForm.tsx
//   logo     <- components/logos/FromScratchForm.tsx + FromPreviousLogoForm.tsx
//   meta     <- components/ad-angles/AdAngleForm.tsx
//
// Labels, placeholders, hints, required flags, field types and section
// headings all match the source. What is NOT ported is their Tailwind: these
// render through the design's own modal chrome and type scale.
//
// Field types:
//   text | url | email | number   single-line input
//   textarea                      multi-line, `rows`
//   industries                    the multi-select chip grid
//   industry                      the same grid, single choice
//   file                          drop zone
//
// `full: true` makes a field span the section's grid.

export const FORM_SPECS = {
  website: {
    submit: 'Generate Website Content',
    meta: 'Website content · 6 page groups per run',
    footnote: 'Six page groups per run, each with its own version history.',
    sections: [
      {
        heading: 'Business details',
        subtext: 'Who the site is for. These drive the copy throughout.',
        icon: 'business',
        min: 240,
        fields: [
          { key: 'business_name', label: 'Business name', type: 'text', required: true, placeholder: 'Green Touch Services LTD' },
          { key: 'phone', label: 'Phone', type: 'text', required: true, placeholder: '7708910551' },
          { key: 'email', label: 'Email', type: 'email', required: true, placeholder: 'info@green-touch.co.uk' },
          { key: 'address', label: 'Address', type: 'text', required: true, placeholder: '0/1 37 Coxton Place' },
          { key: 'country', label: 'Country', type: 'text', required: true, placeholder: 'United Kingdom' },
          { key: 'region', label: 'State / province / region', type: 'text', required: true, placeholder: 'North Lanarkshire' },
          { key: 'zip', label: 'Zip / postal code', type: 'text', required: true, placeholder: 'G33 5EL' },
          {
            key: 'unique_selling_points', label: 'Unique selling points', type: 'textarea', rows: 3, full: true,
            placeholder: 'Reason: Quality of service. Description: We proactively ensure satisfaction at every step…',
            hint: 'What makes them different. Reason plus description works well.',
          },
        ],
      },
      {
        heading: 'Content context',
        subtext: 'The sitemap has the highest authority. Every page, service and area comes from it, and nothing outside it is written about.',
        icon: 'doc',
        fields: [
          {
            key: 'sitemap_text', label: 'Sitemap', type: 'textarea', rows: 4, required: true, full: true, mono: true,
            placeholder: 'HOME | www.example.co.uk/ | keep intro short\nABOUT US | www.example.co.uk/about/ | mention team size',
            hint: 'Tab-separated page list (PAGE NAME → FINAL PAGE URL → INSTRUCTIONS). Paste straight from the agreed sheet.',
          },
          {
            key: 'industries', label: 'Industries', type: 'industries', full: true,
            hint: 'Pick every one that applies. This chooses which knowledge bases the writers read for tone and structure, so a business spanning three categories should tick all three.',
          },
          {
            key: 'other_industry', label: 'Other industry', type: 'text', full: true,
            placeholder: 'e.g. Tree surgery',
            hint: 'Free text for anything not in the list above.',
          },
        ],
      },
      {
        heading: 'Meeting context',
        subtext: 'Add a Fathom URL and/or a Loom summary + transcript for more tailored content. Without one, the copy is written blind and the run comes back with a warning.',
        icon: 'video',
        optional: true,
        collapsible: true,
        note: 'Fathom is fetched from the URL — do not paste its transcript. Loom is the other way round.',
        min: 260,
        fields: [
          { key: 'fathom_meeting_1_url', label: 'Fathom meeting 1 URL', type: 'text', mono: true, placeholder: 'https://fathom.video/share/…' },
          { key: 'fathom_meeting_2_url', label: 'Fathom meeting 2 URL', type: 'text', mono: true, placeholder: 'https://fathom.video/share/…' },
          { key: 'fathom_meeting_3_url', label: 'Fathom meeting 3 URL', type: 'text', mono: true, placeholder: 'https://fathom.video/share/…' },
          { key: 'loom_1_summary', label: 'Loom 1: summary', type: 'textarea', rows: 3, placeholder: 'Account-manager kickoff summary…' },
          { key: 'loom_1_transcript', label: 'Loom 1: transcript', type: 'textarea', rows: 3, mono: true, placeholder: '0:00 Hi team…' },
          { key: 'loom_2_summary', label: 'Loom 2: summary', type: 'textarea', rows: 3, placeholder: 'Account-manager kickoff summary…' },
          { key: 'loom_2_transcript', label: 'Loom 2: transcript', type: 'textarea', rows: 3, mono: true, placeholder: '0:00 Hi team…' },
          { key: 'loom_3_summary', label: 'Loom 3: summary', type: 'textarea', rows: 3, placeholder: 'Account-manager kickoff summary…' },
          { key: 'loom_3_transcript', label: 'Loom 3: transcript', type: 'textarea', rows: 3, mono: true, placeholder: '0:00 Hi team…' },
        ],
      },
    ],
  },

  posts: {
    submit: 'Generate Posts',
    meta: 'Social content · posts, reels, reviews and stories',
    footnote: 'One run produces the whole social package for the month.',
    sections: [
      {
        heading: 'Business details',
        subtext: 'Who this post is for, and how to reach them.',
        icon: 'business',
        min: 240,
        fields: [
          { key: 'company_name', label: 'Company Name', type: 'text', required: true, placeholder: 'e.g. Acme HVAC' },
          { key: 'phone', label: 'Phone', type: 'text', placeholder: 'e.g. 07700 900123' },
          { key: 'email', label: 'Email', type: 'email', placeholder: 'e.g. hello@example.co.uk' },
          { key: 'website_url', label: 'Website URL', type: 'url', placeholder: 'e.g. www.example.co.uk' },
          { key: 'company_reviews_page_url', label: 'Company Reviews Page URL', type: 'url', placeholder: 'e.g. g.page/r/…' },
          { key: 'industry', label: 'Industry', type: 'text', placeholder: 'e.g. Air Conditioning and Heat Pumps' },
          { key: 'month', label: 'Month', type: 'text', placeholder: 'e.g. August 2026' },
        ],
      },
      {
        heading: 'Content direction',
        subtext: 'What the post should cover and any rules to follow.',
        icon: 'doc',
        fields: [
          { key: 'fixed_rules', label: 'Fixed Rules', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. never promise same-day unless the diary is open' },
          { key: 'main_topic', label: 'Main Topic', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. pre-winter boiler servicing' },
          { key: 'promotion', label: 'Promotion', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. £89 fixed-price service through September' },
          { key: 'additional_resources', label: 'Additional Resources', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. links to case studies or product pages' },
          { key: 'additional_notes', label: 'Additional Notes', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. avoid mentioning the old branding' },
          { key: 'areas_covered', label: 'Areas Covered', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. Kingston, Surbiton, New Malden' },
          { key: 'unique_selling_points', label: 'Unique Selling Points', type: 'textarea', rows: 2, full: true, placeholder: 'e.g. two hour response, fixed pricing, family run since 2009' },
        ],
      },
      {
        heading: 'Assets',
        subtext: 'Logo to use when generating the post.',
        icon: 'image',
        fields: [
          { key: 'logo', label: 'Logo', type: 'file', full: true, accept: 'SVG, PNG or JPG · up to 20 MB' },
        ],
      },
    ],
  },

  blog: {
    submit: 'Generate Blogs',
    meta: 'Blog · one cluster per run',
    footnote: 'The homepage is scraped once, then used as context for every blog in the cluster.',
    sections: [
      {
        heading: 'Client',
        subtext: 'The homepage is scraped and summarised once, then used as context for every blog in the cluster.',
        icon: 'business',
        min: 240,
        fields: [
          { key: 'client_name', label: 'Client Name', type: 'text', required: true, placeholder: 'e.g. Acme Heating' },
          { key: 'website_url', label: 'Website Homepage URL', type: 'text', required: true, placeholder: 'e.g. acmeheating.co.uk' },
        ],
      },
      {
        heading: 'Cluster themes',
        subtext: 'The themes this month’s blogs sit under. Only the first is required.',
        icon: 'doc',
        min: 240,
        fields: [
          { key: 'cluster_theme_1', label: 'Cluster Theme 1', type: 'text', required: true, placeholder: 'e.g. Boiler installation costs' },
          { key: 'cluster_theme_2', label: 'Cluster Theme 2', type: 'text', placeholder: 'e.g. Radiator upgrades' },
          { key: 'cluster_theme_3', label: 'Cluster Theme 3', type: 'text', placeholder: 'e.g. Landlord compliance' },
          {
            key: 'cluster_number', label: 'Cluster #', type: 'number', min: 1, max: 100, placeholder: 'e.g. 12',
            hint: 'How many blogs the plan below should contain. Checked against what gets extracted.',
          },
        ],
      },
      {
        heading: 'Blog schema',
        subtext: 'Paste the content plan. Each blog needs a title, a funnel stage, its service areas and its keywords — the extractor reads them back into one brief per blog, which you review before any writing happens.',
        icon: 'doc',
        fields: [
          {
            key: 'blog_schema_raw', label: 'Blog Schema', type: 'textarea', rows: 14, required: true, full: true, mono: true,
            placeholder: '1 | How Much Does a New Boiler Cost in Glasgow? | Commercial | Glasgow | boiler installation glasgow, new boiler cost glasgow\n2 | ...',
          },
        ],
      },
    ],
  },

  logo: {
    submit: 'Generate Logo',
    meta: 'Logo studio · 4 concepts per run',
    footnote: 'Four concepts per run, each with its own version history.',
    // The approach toggle picks which spec applies; it maps to the section's
    // own sub-tabs (scratch / revamp).
    modes: {
      scratch: [
        {
          heading: 'Business details',
          subtext: 'Who this logo is for.',
          icon: 'business',
          min: 240,
          fields: [
            { key: 'company_name', label: 'Company Name', type: 'text', required: true, placeholder: 'e.g. Acme HVAC' },
            { key: 'industry', label: 'Industry', type: 'text', required: true, placeholder: 'e.g. Home Services' },
          ],
        },
        {
          heading: 'Content direction',
          subtext: 'What makes them different, and any reference material.',
          icon: 'doc',
          fields: [
            { key: 'usps', label: "USP's", type: 'textarea', rows: 3, full: true, hint: 'What makes this business stand out', placeholder: 'e.g. 24/7 support, lifetime warranty...' },
            { key: 'fathom_url', label: 'Fathom URL', type: 'text', full: true, mono: true, placeholder: 'https://fathom.video/...' },
          ],
        },
        {
          heading: 'Any Suggestions',
          subtext: 'If you have a suggestion, add it below — otherwise we’ll generate the logo from the details above.',
          icon: 'doc',
          fields: [
            { key: 'suggestion', label: 'Suggestion', type: 'textarea', rows: 3, full: true, placeholder: 'Keep the flame mark, drop the italic wordmark.' },
          ],
        },
      ],
      revamp: [
        {
          heading: 'Logo details',
          subtext: 'The existing logo and a reference link, if any.',
          icon: 'business',
          min: 240,
          fields: [
            { key: 'company_name', label: 'Company Name', type: 'text', required: true, placeholder: 'e.g. Acme HVAC' },
            { key: 'logo', label: 'Logo', type: 'file', full: true, accept: 'SVG, PNG or PDF · up to 20 MB' },
            { key: 'fathom_url', label: 'Fathom URL', type: 'text', full: true, mono: true, placeholder: 'https://fathom.video/...' },
          ],
        },
        {
          heading: 'Any Suggestions',
          subtext: 'If you have a suggestion, add it below — otherwise we’ll generate the logo from the details above.',
          icon: 'doc',
          fields: [
            { key: 'suggestion', label: 'Suggestion', type: 'textarea', rows: 3, full: true, placeholder: 'Keep the flame mark, drop the italic wordmark.' },
          ],
        },
      ],
    },
  },

  meta: {
    submit: 'Generate Meta Ads',
    meta: 'Meta Ads · one angle set per run',
    footnote: 'Each run returns a set of ad angles you can review before any creative is made.',
    sections: [
      {
        heading: 'Business details',
        subtext: 'Who this ad is for, and what it’s promoting.',
        icon: 'business',
        min: 240,
        fields: [
          { key: 'company_name', label: 'Company Name', type: 'text', required: true, placeholder: 'e.g. Acme HVAC' },
          { key: 'service_name', label: 'Service name', type: 'text', required: true, placeholder: 'e.g. AC Installation' },
          { key: 'offers', label: 'Offers', type: 'text', placeholder: 'e.g. Free Thermostat', hint: 'e.g. "Free Thermostat, $0 Down Financing"' },
        ],
      },
      {
        heading: 'Industries',
        subtext: 'Pick the industry that best matches this business.',
        icon: 'doc',
        requiredMark: true,
        fields: [
          { key: 'industry', label: 'Industry', type: 'industry', full: true, hideLabel: true },
        ],
      },
      {
        heading: 'Content direction',
        subtext: 'What makes them different, and what the ad should cover.',
        icon: 'doc',
        fields: [
          {
            key: 'service_content', label: 'Service content', type: 'textarea', rows: 3, required: true, full: true,
            hint: 'Description of the service being advertised',
            placeholder: "What the service includes, who it's for, why it matters...",
          },
        ],
      },
    ],
  },
};

/** The sections that apply to a given section id, honouring logo's two modes. */
export function formSections(sectionId, sub) {
  const spec = FORM_SPECS[sectionId];
  if (!spec) return [];
  if (spec.modes) return spec.modes[sub] || spec.modes[Object.keys(spec.modes)[0]];
  return spec.sections;
}

/** Every field key across a spec, used to seed and read back values. */
export function formFieldKeys(sectionId, sub) {
  return formSections(sectionId, sub).flatMap(s => s.fields.map(f => f.key));
}
