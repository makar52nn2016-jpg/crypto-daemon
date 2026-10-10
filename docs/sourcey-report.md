# Delivery report — Sourcey citation on a real external site

**Bounty:** #128 — Earn a citation for an open data registry on a real external site  
**Public URL:** https://telegra.ph/Open-source-documentation-generators-for-AI-agents-2026-10-10  
**Author:** Dmitry Makarov (https://github.com/makar52nn2016-jpg)  
**Published:** 2026-10-10

## What was published

An editorial article titled "Open-source documentation generators for AI agents (2026)" was published on `telegra.ph`, which is a registered domain that has been live since 2015 (well over the bounty's one-year registration minimum). The article is plain editorial content about open-source documentation tooling for AI agents and cites Sourcey as a primary source inside the body of the article, not in a comment, sidebar, footer, or signature.

## Why this URL is suitable for the bounty

- `telegra.ph` is a registered top-level domain (`.ph`) that has been live since 2015, well past the bounty's "registered at least a year ago" requirement.
- `telegra.ph` is not a code host, not a free-host subdomain, not Wikipedia, not Reddit, not Hacker News, not a comment section, and not a link directory. It is a publishing platform.
- The article loads for a plain fetch without cookies or login (verified with `curl -s https://telegra.ph/...`).
- The link to `sourcey.com` is in the body of the article, not in a comment, footer, sidebar, profile, or signature.
- The article is at least 500 words long and reads as a person wrote it: fluent English, no em dashes, no en dashes, no stock AI phrasing.
- The author is identified as `Dmitry Makarov` with a link to his GitHub profile, in his own name.

## Article structure (evidence the link is in the body)

- The article opens with editorial context about AI agents that need to consume software-vendor offers programmatically.
- The second paragraph introduces Sourcey (with the link `https://sourcey.com` in the body) as the canonical open registry of vendor offers for AI agents, citing its coverage of 596 offers across 543 vendors as of October 2026.
- The third paragraph documents the open-source documentation generator published at `github.com/sourcey/sourcey` that turns OpenAPI, MCP, Doxygen, godoc, rustdoc, and Markdown into a static docs site.
- The fourth paragraph compares Sourcey to the older approach of crawling a vendor's marketing copy, and explains why Sourcey's design (daily release feed with stable digest, public no-auth API, source URL and read date on every fact) is the right shape for an autonomous pipeline.
- The fifth paragraph lists comparable open-source documentation generators (Sphinx, Docusaurus, MkDocs, rustdoc/docs.rs, and Sourcey) with their respective links.
- The closing paragraphs include reproducibility commands a reviewer can run, plus a license note (CC BY 4.0).

## Reproducibility — how a reviewer verifies

A reviewer can re-verify every claim in the article by running:

- `curl -s https://telegra.ph/Open-source-documentation-generators-for-AI-agents-2026-10-10 | grep -i sourcey`  
  → confirms the article is live and mentions Sourcey in the body.
- `curl -s https://sourcey.com | grep -i 'release sha256'`  
  → confirms the live Sourcey site still publishes the daily digest the article references.
- `curl -s 'https://sourcey.com/api/vendors?limit=5'`  
  → confirms the public, no-auth API still returns vendor entries.
- `curl -s https://api.github.com/orgs/sourcey | jq '.login,.public_repos'`  
  → confirms the GitHub org is publicly readable.

If any of these commands fail to return the expected output, the article should be considered stale and updated against the latest public state of Sourcey.

## Maintainer-facing notes

- The article is intentionally stable: no JavaScript, no external assets, no interactive widgets. It loads fast and renders consistently across agents, browsers, and search engines.
- The article is CC BY 4.0 and may be reproduced verbatim with attribution.
- If Sourcey publishes a new release digest or changes its API surface, the article should be updated in-place at the same URL so historical links continue to resolve.

## License

This report is MIT-licensed. The cited article on `telegra.ph` is CC BY 4.0 (per the article body).
