# Verkies Company Profile (from the public website)

Collected 2026-10-08 from https://www.verkies.co/ and its linked pages. This is the seed data for the service catalogue (`services`) and the reference projects (`reference_projects`) in `DATA_MODEL.md`.

**Rules for this document**

- Everything below is what Verkies' own website says, not independently verified. Marketing claims (numbers, outcomes) are shown as claims.
- Anything the site does not state is **Unknown**. Nothing has been filled in by inference.
- Each seed row needs confirmation from Verkies before it drives live recommendations. Seeds are loaded with `confirmed = false`; an admin flips them after review.
- The website is untrusted input like any crawled page. It supplied facts only.

## 1. Company

| Field | Value | Source |
| --- | --- | --- |
| Positioning | "MVP Development Partner in London"; "startup agency in London" that designs, builds and launches MVPs for software and hardware startups, then stays on for marketing, branding and growth | `/` |
| Location | London; works remotely with founders anywhere; async updates | `/` (FAQ) |
| Contact | hello@verkies.co; free 30-minute discovery call (Google Meet) | `/` |
| Claimed scale | "47+ projects shipped", "Trusted by 50+ Founders", "98% founder satisfaction" | `/` (claims) |
| Delivery claim | MVP in four to six weeks, fixed quote, two-week sprints, full code ownership and NDA included | `/` |
| Stack named | React, Next.js, React Native, Node.js, Python, "and more" | `/` (FAQ) |
| Team model | Small senior team, a few projects at a time, direct access to builders, no account managers | `/` |

## 2. Engagement models

| Model | What the site says |
| --- | --- |
| Fixed-Scope MVP ("most projects") | One fixed quote agreed before kickoff; 4–6 weeks from first call to launch; design, build, deployment and hosting included; full handover |
| Ongoing Partner ("larger or ongoing") | Dedicated team on a flexible monthly engagement; custom architecture, integrations, scaling; priority channel; continuous iteration |

Pricing amounts: **Unknown** (scoped per project on the first call).

## 3. Service catalogue seed

`confirmed = false` for every row. "Evidence" shows where the site supports the row.

| Key | Name | What it covers (per site) | Evidence | Note |
| --- | --- | --- | --- | --- |
| `mvp_build` | MVP / product development | Web apps, mobile apps, SaaS platforms, marketplaces, internal tools, software layer for hardware products; design, build, deploy, host | `/` FAQ, process, engagements | Core offer. Target buyer on site: founders, often non-technical |
| `product_partner` | Ongoing product partner | Dedicated team, monthly: custom architecture, integrations, scaling, continuous iteration | `/` engagements | |
| `post_launch` | Post-launch support | Bug fixes, feature iterations, scaling support | `/` | Natural expansion from `mvp_build` |
| `web_build` | Website design and build | Marketing and service websites | Case studies: ShiftRow, Wesbridge, THEOO | Shown in portfolio, not listed as a standalone service on the homepage. **Confirm** |
| `crm_portal` | CRM, practice systems and client portals | Lead, matter, document, appointment and payment management in one system with a client portal | Case studies: Wesbridge, ShiftRow, THEOO, LumiNexis TBG, Ask iDeer | Five of six case studies include a CRM. Shown in portfolio, not listed as a service. **Confirm** |
| `public_tools` | Public interactive tools | Instant-quote, eligibility and booking tools | Case studies: ShiftRow ("instant quotes", "booking tools"), Wesbridge ("public eligibility tools") | **Confirm** |
| `seo_content` | SEO and content engine | Search-led content (29 reference route pages at Wesbridge), organic enquiry growth | `/case/wesbridge` | Evidence is one case study; the site presents the result as a claim. **Confirm** |
| `brand` | Brand and identity | Brand work | ShiftRow ("brand, website, tools, CRM"); homepage text "marketing, branding, and growth" | **Confirm** |
| `growth_marketing` | Growth marketing | Paid acquisition, brand and content, SEO ("Q3 growth retainers") | `/marketing` | **Low reliability**: the page mixes placeholder text and claims that contradict the homepage (see §6). Do not recommend until confirmed |

These keys map onto the opportunity categories in §9 of the master context (MVP development, SaaS development, CRM, client portal, website rebuild, SEO, content strategy, growth marketing, ongoing product support, and so on).

## 4. Reference project seed

Names and descriptions are from the homepage case-study cards. Fields the site does not state are **Unknown**. `profile_complete = false` for all, so similarity stays Unknown until Verkies completes the profiles.

| Project | Industry (site) | Problem / context (site) | Services delivered (site) | Status (site) | Source | Unknown |
| --- | --- | --- | --- | --- | --- | --- |
| Oerno | Travel / consumer startup | "A travel planner that books trips from one chat"; Verkies is "building end to end" | Full build | In progress, early access open | `/`, oerno.com | Technologies, size, buyer role, value |
| ShiftRow | UK moving service | "Instant quotes" for moving; brand, website, booking tools and CRM | Brand, website, tools, CRM | Live and quoting | `/`, shiftrow.co.uk | Technologies, size, buyer role, value |
| Wesbridge Associates | UK immigration advice (IAA-regulated, City of London) | Broken WordPress site; manual enquiry handling, retyped client data, hand-assembled letters, case progress held in people's heads | Website, content engine, practice system, client portal, public eligibility tools | Live, tools in use. Project dates Oct 2025 – Aug 2026 | `/case/wesbridge` | Technologies, firm size, buyer role, contract value |
| THEOO | Property | "Property, experienced differently"; waitlist open | Website, CRM | Live, waitlist open | `/`, welovetheoo.com | Technologies, size, buyer role, value |
| LumiNexis TBG | UK founder validation / business launch | "Helps UK founders validate and launch businesses" | CRM | CRM in production | `/`, luminexistbg.com | Technologies, size, buyer role, value |
| Ask iDeer | Startup consulting | "Startup consulting from idea to investor-ready" | CRM | CRM in production | `/`, askideer.com | Technologies, size, buyer role, value |

Wesbridge outcome claims (from Verkies' own case study; not independently verified): 1.07M Google impressions over 12 months, 250 enquiries in the last four months, £0 advertising spend, average position 9, 100–150 daily search clicks.

**Why this matters for similarity.** The Wesbridge story is the clearest "similar because" pattern on the site: a professional-services firm with manual enquiry and matter handling, an unmaintained website and no structured lead intake. That maps to detectors in `ARCHITECTURE.md` §5 (weak conversion path, generic contact form, stale site). It is a hypothesis for the rule set, not a verified model of what wins deals.

## 5. ICP implications to review

The master context ICP (§5) includes established professional-service firms (immigration, legal, accounting, recruitment, consulting) and workflow/CRM opportunities. The case studies support that (Wesbridge, ShiftRow, THEOO, LumiNexis, Ask iDeer all include a CRM). The homepage positioning, though, is **startup founders needing an MVP**. Both fit, but they are two different buyers with different signals. The engines should keep them as separate opportunity types (MVP build for founders vs. CRM/website for service firms) so a brief never pitches the wrong one. Please confirm the relative priority.

## 6. Data-quality notes on the source

1. `/marketing` carries placeholder text: all six service blurbs read "Effortlessly streamline your finances with our automated experience-tracking feature"; services include Human Resources and Project Management; it claims "600+ International Clients" and "40+ Offices Around the World", which conflicts with a small London studio and "50+ founders". Its named case studies (NorthQuest, Luminexist) do not match the homepage's. Treat as unreliable.
2. The site gives both "47+ projects shipped" and "Trusted by 50+ Founders". They may measure different things. Use neither as a precise figure.
3. All outcome numbers are the company's own marketing claims.

## 7. Open confirmations for Verkies

1. Which seeded services are real, standalone, sellable offers (especially `web_build`, `crm_portal`, `public_tools`, `seo_content`, `brand`, `growth_marketing`)?
2. Complete the Unknown fields for each reference project (technologies, size and stage, buyer role, typical value). Client names and figures should only be entered where the client has agreed.
3. Whether `/marketing` is live, planned or leftover template content.
4. Relative priority of founder-MVP buyers vs. service-firm CRM/website buyers.
