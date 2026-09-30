# crypto-daemon

Autonomous 24/7 crypto earning daemon running on GitHub Actions (free, no sandbox dependency).

## Что делает

- **Wallet monitor** — проверяет XLM/ETH/BTC/SOL каждые 5 минут, мгновенный TG alert при incoming
- **PR tracker** — следит за всеми открытыми PRs (merges, comments, reviews)
- **Bounty scanner** — ищет новые bounty issues в отслеживаемых репозиториях
- **Heartbeat** — каждые 6 часов пишет в TG что живой

## Secrets (GitHub Actions settings → Secrets)

- `GH_TOKEN` — Personal Access Token (repo + workflow scope)
- `TG_TOKEN` — Telegram bot token
- `TG_CHAT` — Telegram chat ID

## TG bot

@makarov_Dmi (chat ID 322108803)
