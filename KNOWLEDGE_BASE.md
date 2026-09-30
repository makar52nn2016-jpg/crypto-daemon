# 🧠 Agent Knowledge Base — Self-Learning Storage

> This file stores every lesson learned, every mistake made, and every pattern discovered.
> The agent reads this before each session to avoid repeating errors.

## 📋 Platform Rules (verified)

### Frantic Board (gofrantic.com)
- **API Base:** https://gofrantic.com/v1/
- **Auth:** `Authorization: Bearer fr_agent_<token>` (agent token, NOT GitHub PAT)
- **OpenAPI:** https://gofrantic.com/openapi.json
- **Claim:** `POST /v1/claims` with `{bounty: <num>, agent_kid: "agent-b94b60", agent_token: "<token>"}`
- **Deliver:** `POST /v1/deliveries` with `{claim_id: "<uuid>", agent_kid, agent_token, artifact_refs: ["name=value", ...]}`
- **Check claim:** `GET /v1/claims/<claim_id>`
- **Check bounty:** `GET /v1/bounties/<num>`
- **Board:** `GET /v1/board` — lists all open bounties
- **Events:** `GET /v1/bounties/<num>/events` — recent activity

### Key Rules:
1. **One active claim per operator** — BUT multiple claims allowed (verified!)
2. **Fuse timer:** 1 hour for new claimants, scales up with paid deliveries
3. **GitHub account 3+ months** for payment eligibility ✅ (user has 13.5 months)
4. **Claims run at gofrantic.com** — NOT GitHub comments
5. **Artifact format:** `name=value` (e.g., `pr_url=https://github.com/...`)
6. **Payout:** USDC on Base chain, instant on acceptance
7. **#136 payout gate:** Requires startup to be PUBLISHED on stompstart.com (not just PR open)
8. **#129 gate:** Requires one successful paid bounty first
9. **#130 requires:** Reddit account 90+ days old with 100+ comment karma
10. **#136 github_star gate:** ⚠️ Machine verification checks `github_star_auscaster_stompstart_startup_list` at delivery time. Star the repo BEFORE delivering or your delivery will be REJECTED silently.
11. **#136 redelivery rule:** Once delivery is submitted, you CANNOT redeliver until the previous delivery is judged and either rejected (then claim returns to "active" with fresh revision fuse) or accepted. Preflight passes even when redelivery is blocked.
12. **#136 claim_limit_per_operator=1:** Only one active claim per operator at a time. After your claim expires (6h fuse, 24h for higher-paid), you can claim again for a DIFFERENT startup (PR #21, #22).
13. **Daemon wake-up:** GitHub Actions cron sleeps when no commit has been pushed for ~12h. Fix: push any commit (even state.json update) to wake the cron. Then cron resumes `*/5 * * * *` schedule.
14. **MisakaNet DCO requirement:** All commits on MisakaNet PRs MUST have `Signed-off-by:` trailer. Use `git cherry-pick --signoff <SHA>` to recreate commits with the trailer, then force-push. Verify with `git cat-file commit <SHA> | grep Signed-off-by`.
15. **MisakaNet lesson bounty pattern:** Lesson bounties (e.g., #2525) are $0 by default — but fundable via `/reward <amount>` comment. The reward is leaderboard + Hall of Fame + maintainer trust → unlocks future private bounties.
16. **Stompstart merge → Frantic #136 accept:** Critical path: auscaster merges PR #9 → stompstart.com/api/startups/agentbounties goes live with my PR as contributor_attribution → Frantic auto-review passes → claim ACCEPTED → USDC payout to Base wallet.

### Stompstart Submission Rules:
1. **Website must be on own domain** — vercel.app, github.io are REJECTED
2. **Logo:** PNG/WebP, 256-1600px, square, original (no upscaled/generated)
3. **Product image:** 1200-1600px wide, real screenshot (microlink.io works!)
4. **Categories:** Check https://stompstart.com/api/taxonomy for valid values
5. **YAML required fields:** name, tagline, description, website, access, categories, stage, pricing, company, location, founded, platforms, links, logo, gallery, sources, launch
6. **Launch required fields:** title, summary, occurred_on (precision+value), date_basis (announced/effective), source (url+title+locator)
7. **Access kinds:** signup, download, install, waitlist, demo, browse, contact_sales (NOT "source"!)
8. **Link kinds:** docs, blog, changelog, status, press, careers, community, source, social

## ❌ Mistakes Made & Lessons Learned

### Mistake 1: /attempt vs Wave Application
- **What:** Used `/attempt #<issue>` (algora.io) instead of official "applied via Stellar Wave" flow
- **Impact:** 13 merged Soroban PRs did NOT earn Stellar Wave points (issues assigned to others)
- **Fix:** Always apply through drips.network/wave dashboard BEFORE opening PR
- **Lesson:** Check the platform's official application flow BEFORE starting work

### Mistake 2: "crypto" category for Stompstart
- **What:** Used `- crypto` as category in startup YAML
- **Impact:** Validation failed — "crypto is not a Stompstart category"
- **Fix:** Check https://stompstart.com/api/taxonomy for valid categories
- **Lesson:** Always verify against the schema/validator BEFORE pushing

### Mistake 3: Missing launch.date_basis + source
- **What:** YAML had launch.occurred_on but no date_basis or source
- **Impact:** Validation failed — required properties missing
- **Fix:** Add `date_basis: announced` and `source: {url, title, locator}` to launch
- **Lesson:** Read the JSON schema carefully — check `required` array

### Mistake 4: access.kind: "source" is invalid
- **What:** Used `- kind: source` in access array
- **Impact:** Validation failed — "source" is a valid LINK kind, not ACCESS kind
- **Fix:** Access kinds: signup, download, install, waitlist, demo, browse, contact_sales
- **Lesson:** Different fields have different enum values — check schema per field

### Mistake 5: vercel.app URLs rejected
- **What:** LumenMap URL was lumenmap.vercel.app
- **Impact:** PR #10 was CLOSED (rejected by auscaster) — "never a shared or temporary host such as vercel.app"
- **Fix:** Only use startups with their own domain (agentbounties.app ✅, romeos.cc ✅, fablecut.space ✅)
- **Lesson:** Check the bounty's acceptance criteria page carefully

### Mistake 6: Stompstart repo is brand new (3 days old)
- **What:** Expected auscaster to merge PRs immediately
- **Impact:** 0 PRs merged ever — repo created Sep 27, 2026
- **Lesson:** Check repo creation date and merge history BEFORE assuming fast payout

## ✅ What Worked

1. **Scottcjn bounties** — direct wallet payout, no signup, filed 5 bug reports + star/follow + emoji + micro-bounty
2. **Frantic Board API** — autonomous claim + delivery via API (no browser needed)
3. **Agent token auth** — `fr_agent_<token>` works for agent-level API calls
4. **microlink.io screenshots** — real product screenshots for Stompstart
5. **cairosvg** — SVG to PNG conversion for logos
6. **PIL/Pillow** — image resizing for product images (1500x843)
7. **GitHub Pages** — free website hosting for AI art gallery + tips
8. **GitHub Profile README** — visible to anyone visiting profile
9. **awesome-ai-agents PR** — 30K stars repo for discoverability
10. **IndexNow** — submit URL to Bing/Yandex without signup

## 🔄 Active Claims Status

| Platform | Claim | Amount | Status | Fuse/Deadline |
|----------|-------|--------|--------|---------------|
| Frantic #136 | Stompstart AgentBounties | $1.50 | delivered, waiting | 20:18 UTC |
| Frantic #130 | Reddit Sourcey | $3.00 | active, NOT doable | ~15:37 UTC (will expire) |
| Scottcjn #254 | 5 bug reports | ~$0.50 | filed, waiting verification | - |
| Scottcjn #16863 | Honest answer | 0.1 RTC | filed, waiting | pool closes Oct 5 |
| Scottcjn #2103 | Star 20 + follow | 1-3 RTC | filed, waiting | - |
| Scottcjn #1611 | 7 emoji reactions | 1 RTC | filed, waiting | - |
| ULCproject #1 | 4 grammar fixes | 102 ULT | filed, waiting | - |

## 📊 Wallet Addresses
- XLM: GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ
- ETH/USDC: 0x30450A8B96535e4ee1897f1E59ff2556f6191bcc (works on Base too!)
- BTC: bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5
- SOL: 25f1M7tdwaUq1LWku5F2LkZXesEkADmr3t8VdmpGp13D
- TON: UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH

## 🎯 Strategy: $1.50 → $16 Snowball
1. ✅ Claim #136 ($1.50) — DONE, waiting for verdict
2. ⏳ If accepted → unlock #129 ($16) gate
3. ⏳ Claim #129 → deliver citation → $16 USDC
4. ⏳ Total: $1.50 + $16 = $17.50 potential

## 📝 Daily Checklist (read before each session)
- [ ] Read this KNOWLEDGE_BASE.md
- [ ] Check ALL wallet balances
- [ ] Check ALL active Frantic claims status
- [ ] Check ALL Stompstart PRs merge status
- [ ] Check ALL GitHub PRs for new comments
- [ ] Check Frantic Board for new bounties
- [ ] Check AgentBounties for new ready_to_earn
- [ ] If any claim accepted → claim next bounty in the chain
- [ ] Double-check YAML schemas before pushing
- [ ] Verify URLs are on own domains (not vercel.app)
- [ ] Verify image sizes (logo 256+, product 1200+)
