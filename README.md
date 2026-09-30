# 🤖 Crypto Daemon + Cloud Sniper

Autonomous AI agent that hunts crypto bounties 24/7 on GitHub Actions. Free, no server costs.

🌐 **Live website:** https://makar52nn2016-jpg.github.io/crypto-agent/

## What it does

- **Wallet Monitor** — checks XLM/ETH/BTC/SOL/TON/USDT every 5 min, alerts on incoming funds
- **PR Tracker** — tracks 26+ PRs for merges, comments, reviews
- **Bounty Sniper** — discovers new funded bounties every 30 min via GitHub + AgentBounties API
- **Telegram Alerts** — instant notification on action-needed events
- **AI Art Gallery** — generates art, hosts on GitHub Pages
- **Ebook** — 332-page bounty hunting playbook, free download

## Crypto Tips (no signup, direct to wallet)

- TON: `UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH`
- ETH/USDC: `0x30450A8B96535e4ee1897f1E59ff2556f6191bcc`
- XLM: `GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ`
- BTC: `bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5`
- SOL: `25f1M7tdwaUq1LWku5F2LkZXesEkADmr3t8VdmpGp13D`

## Architecture

```
GitHub Actions (cron */5 * * * *)
  ├── daemon.py — wallet + PR monitoring
  └── sniper.py — bounty discovery + auto-claim
```

## Secrets (GitHub Actions)

- `GH_TOKEN` — Personal Access Token
- `TG_TOKEN` — Telegram bot token
- `TG_CHAT` — Telegram chat ID

## License

MIT
