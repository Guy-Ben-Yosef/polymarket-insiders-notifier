# Polymarket Wallet Trade Alerts

Real-time trade monitoring for multiple Polymarket wallets, each routed to its own Telegram bot.

## Features

- 📈 BUY / 📉 SELL trade alerts
- Track many wallets at once, polled concurrently
- A dedicated Telegram bot (and chat list) per wallet
- Displays market name, outcome, shares, price, and total USDC
- Logs all trades to `trades.log`
- Auto-reconnect with exponential backoff on errors

## Setup

1. Create and activate virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. Set up Telegram bot (see below)

## Telegram Setup

Repeat these steps once per wallet — each wallet gets its own bot:

1. **Create a bot**: Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`
2. **Get your bot token**: BotFather will give you a token like `123456789:ABCdefGhIjKlmNoPqRsTuVwXyZ`
3. **Get chat IDs**:
   - For your personal chat: Message [@userinfobot](https://t.me/userinfobot) to get your ID
   - For groups: Add the bot to the group, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Each recipient must first press **Start** on that wallet's bot, or it can't message them
4. **Configure**: Add an entry for the wallet to `WALLETS_CONFIG` in your `.env` file

## Usage

```bash
python main.py
```

Press `Ctrl+C` to stop.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `WALLETS_CONFIG` | JSON array of wallet→bot mappings (see below) | Required |
| `POLL_INTERVAL` | Seconds between API polls | 5 |

`WALLETS_CONFIG` is a JSON array where each object maps one wallet to one bot:

```json
[
  {
    "label": "Wallet A",
    "wallet": "0xYourFirstWalletHere",
    "bot_token": "111:AAA_bot_token_for_wallet_A",
    "chat_ids": ["123456789"]
  },
  {
    "label": "Wallet B",
    "wallet": "0xYourSecondWalletHere",
    "bot_token": "222:BBB_bot_token_for_wallet_B",
    "chat_ids": ["987654321"]
  }
]
```

- `label` *(optional)* — nickname shown at the top of each alert.
- `wallet` — Polymarket wallet address to monitor.
- `bot_token` — that wallet's own bot token from BotFather.
- `chat_ids` — list of chat IDs that bot notifies (a comma-separated string also works).

> **Note**: Store the whole array on a single line in `.env`. A wallet with no `bot_token`/`chat_ids` still logs trades to the terminal and `trades.log`.
>
> **Legacy**: The old `POLYMARKET_WALLET` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_IDS` vars still work as a single-wallet fallback when `WALLETS_CONFIG` is unset.

