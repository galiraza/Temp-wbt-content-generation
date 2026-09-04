# -*- coding: utf-8 -*-
"""Verbatim from the n8n workflow "Website Content Generation (V7)", the Pinecone vector-store nodes.

Re-extracted from the workflow JSON, which is never modified. n8n expression
placeholders became ChatPromptTemplate fields; every other brace is escaped as
{{ }} because that is what the template engine requires. Do not reword: these
prompts are tuned, and app.agents.website_content reads their output formats back.
"""

#: {page key: {namespace: tool description}}, keyed exactly as the
#: five tools were wired to each page agent in n8n.
KB_TOOL_DESCRIPTIONS = {
    "home": {
        "energy_heating_systems": """\
**Tool Name:** Energy and Heating Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for energy and heating-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Air Conditioner
- ASHP (Air Source Heat Pump)
- Boilers
- ECO4
- Insulation
- Solar
- EV Charger
- Wood Burning Stove

**HOW TO USE:**
1. Query with the specific service type (e.g., "homepage content for boiler services" or "solar panel website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "construction_property_services": """\
**Tool Name:** Construction and Property Services Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for construction and property-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Building Constructions
- Property Maintenance
- Roofing
- Damp Proofing
- Driveway and Patio
- Canopy and Verandas
- Garden Rooms
- Swimming Pools
- Insurance Claims

**HOW TO USE:**
1. Query with the specific service type (e.g., "homepage content for roofing company" or "driveway installation website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "home_improvement_interiors": """\
**Tool Name:** Home Improvement and Interiors Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for home improvement and interior services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Bathroom Installations
- Doors and Windows
- Doors
- Painting Decorating
- Stairlifts and Home lifts

**HOW TO USE:**
1. Query with the specific service type (e.g., "homepage content for bathroom installation company" or "doors and windows website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "electrical_security_systems": """\
**Tool Name:** Electrical and Security Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for electrical and security-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Electrical
- Networking Service
- Security Installers
- Fire Protection
- Signage and Shopfitting

**HOW TO USE:**
1. Query with the specific service type (e.g., "homepage content for electrical contractor" or "security systems website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "health_aesthetics": """\
**Tool Name:** Health and Aesthetics Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for health and aesthetics services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Skin Boosters
- PRP (Platelet-Rich Plasma)
- Aesthetics services
- Beauty treatments

**HOW TO USE:**
1. Query with the specific service type (e.g., "homepage content for aesthetics clinic" or "skin booster treatment website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
    },
    "about_us": {
        "energy_heating_systems": """\
**Tool Name:** Energy and Heating Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for energy and heating-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Air Conditioner
- ASHP (Air Source Heat Pump)
- Boilers
- ECO4
- Insulation
- Solar
- EV Charger
- Wood Burning Stove

**HOW TO USE:**
1. Query with the specific service type (e.g., "about us page content for boiler services" or "solar panel website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "construction_property_services": """\
**Tool Name:** Construction and Property Services Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for construction and property-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Building Constructions
- Property Maintenance
- Roofing
- Damp Proofing
- Driveway and Patio
- Canopy and Verandas
- Garden Rooms
- Swimming Pools
- Insurance Claims

**HOW TO USE:**
1. Query with the specific service type (e.g., "about us page content for roofing company" or "driveway installation website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "home_improvement_interiors": """\
**Tool Name:** Home Improvement and Interiors Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for home improvement and interior services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Bathroom Installations
- Doors and Windows
- Doors
- Painting Decorating
- Stairlifts and Home lifts

**HOW TO USE:**
1. Query with the specific service type (e.g., "about us page content for bathroom installation company" or "doors and windows website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "electrical_security_systems": """\
**Tool Name:** Electrical and Security Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for electrical and security-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Electrical
- Networking Service
- Security Installers
- Fire Protection
- Signage and Shopfitting

**HOW TO USE:**
1. Query with the specific service type (e.g., "about us page content for electrical contractor" or "security systems website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "health_aesthetics": """\
**Tool Name:** Health and Aesthetics Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for health and aesthetics services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Skin Boosters
- PRP (Platelet-Rich Plasma)
- Aesthetics services
- Beauty treatments

**HOW TO USE:**
1. Query with the specific service type (e.g., "about us page content for aesthetics clinic" or "skin booster treatment website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
    },
    "service": {
        "energy_heating_systems": """\
**Tool Name:** Energy and Heating Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for energy and heating-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Air Conditioner
- ASHP (Air Source Heat Pump)
- Boilers
- ECO4
- Insulation
- Solar
- EV Charger
- Wood Burning Stove

**HOW TO USE:**
1. Query with the specific service type (e.g., "services page content for boiler services" or "solar panel website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "construction_property_services": """\
**Tool Name:** Construction and Property Services Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for construction and property-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Building Constructions
- Property Maintenance
- Roofing
- Damp Proofing
- Driveway and Patio
- Canopy and Verandas
- Garden Rooms
- Swimming Pools
- Insurance Claims

**HOW TO USE:**
1. Query with the specific service type (e.g., "services page content for roofing company" or "driveway installation website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "home_improvement_interiors": """\
**Tool Name:** Home Improvement and Interiors Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for home improvement and interior services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Bathroom Installations
- Doors and Windows
- Doors
- Painting Decorating
- Stairlifts and Home lifts

**HOW TO USE:**
1. Query with the specific service type (e.g., "services page content for bathroom installation company" or "doors and windows website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "electrical_security_systems": """\
**Tool Name:** Electrical and Security Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for electrical and security-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Electrical
- Networking Service
- Security Installers
- Fire Protection
- Signage and Shopfitting

**HOW TO USE:**
1. Query with the specific service type (e.g., "services page content for electrical contractor" or "security systems website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "health_aesthetics": """\
**Tool Name:** Health and Aesthetics Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for health and aesthetics services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Skin Boosters
- PRP (Platelet-Rich Plasma)
- Aesthetics services
- Beauty treatments

**HOW TO USE:**
1. Query with the specific service type (e.g., "services page content for aesthetics clinic" or "skin booster treatment website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
    },
    "service_area": {
        "energy_heating_systems": """\
**Tool Name:** Energy and Heating Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for energy and heating-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Air Conditioner
- ASHP (Air Source Heat Pump)
- Boilers
- ECO4
- Insulation
- Solar
- EV Charger
- Wood Burning Stove

**HOW TO USE:**
1. Query with the specific service type (e.g., "service areas page content for boiler services" or "solar panel website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "construction_property_services": """\
**Tool Name:** Construction and Property Services Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for construction and property-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Building Constructions
- Property Maintenance
- Roofing
- Damp Proofing
- Driveway and Patio
- Canopy and Verandas
- Garden Rooms
- Swimming Pools
- Insurance Claims

**HOW TO USE:**
1. Query with the specific service type (e.g., "service areas page content for roofing company" or "driveway installation website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "home_improvement_interiors": """\
**Tool Name:** Home Improvement and Interiors Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for home improvement and interior services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Bathroom Installations
- Doors and Windows
- Doors
- Painting Decorating
- Stairlifts and Home lifts

**HOW TO USE:**
1. Query with the specific service type (e.g., "service areas page content for bathroom installation company" or "doors and windows website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "electrical_security_systems": """\
**Tool Name:** Electrical and Security Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for electrical and security-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Electrical
- Networking Service
- Security Installers
- Fire Protection
- Signage and Shopfitting

**HOW TO USE:**
1. Query with the specific service type (e.g., "service areas page content for electrical contractor" or "security systems website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "health_aesthetics": """\
**Tool Name:** Health and Aesthetics Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for health and aesthetics services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Skin Boosters
- PRP (Platelet-Rich Plasma)
- Aesthetics services
- Beauty treatments

**HOW TO USE:**
1. Query with the specific service type (e.g., "service areas page content for aesthetics clinic" or "skin booster treatment website content")
2. Extract the tone, structure, headings, and content style from the returned examples""",
    },
    "other": {
        "energy_heating_systems": """\
**Tool Name:** Energy and Heating Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for energy and heating-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Air Conditioner
- ASHP (Air Source Heat Pump)
- Boilers
- ECO4
- Insulation
- Solar
- EV Charger
- Wood Burning Stove

**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "construction_property_services": """\
**Tool Name:** Construction and Property Services Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for construction and property-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Building Constructions
- Property Maintenance
- Roofing
- Damp Proofing
- Driveway and Patio
- Canopy and Verandas
- Garden Rooms
- Swimming Pools
- Insurance Claims

**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "home_improvement_interiors": """\
**Tool Name:** Home Improvement and Interiors Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for home improvement and interior services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Bathroom Installations
- Doors and Windows
- Doors
- Painting Decorating
- Stairlifts and Home lifts

**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "electrical_security_systems": """\
**Tool Name:** Electrical and Security Systems Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for electrical and security-related services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Electrical
- Networking Service
- Security Installers
- Fire Protection
- Signage and Shopfitting

**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples""",
        "health_aesthetics": """\
**Tool Name:** Health and Aesthetics Knowledge Base

**Description:**
Use this knowledge base tool to retrieve website content examples and writing guidance for health and aesthetics services.

**WHEN TO USE THIS TOOL:**
Call this tool when the user's industries include ANY of the following:
- Skin Boosters
- PRP (Platelet-Rich Plasma)
- Aesthetics services
- Beauty treatments

**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples""",
    },
}

#: The blogs agent had a single tool, on its own index.
BLOGS_KB_TOOL_DESCRIPTION = """\
**Tool Name:** Blogs Knowledge Base

**Description:**
Use this knowledge base tool to retrieve blogs content examples and writing guidance for blogs.


**HOW TO USE:**
1. Query with the specific service type.
2. Extract the tone, structure, headings, and content style from the returned examples"""
