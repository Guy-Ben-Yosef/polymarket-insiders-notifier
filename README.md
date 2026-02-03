# Polymarket Wallet Trade Alerts

Real-time trade monitoring for a specific Polymarket wallet with Telegram notifications.

## Features

- 📈 BUY trade alerts
- 📉 SELL trade alerts
- Telegram notifications to multiple recipients
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

1. **Create a bot**: Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`
2. **Get your bot token**: BotFather will give you a token like `123456789:ABCdefGhIjKlmNoPqRsTuVwXyZ`
3. **Get chat IDs**: 
   - For your personal chat: Message [@userinfobot](https://t.me/userinfobot) to get your ID
   - For groups: Add the bot to the group, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. **Configure**: Add the token and chat IDs to your `.env` file

## Usage

```bash
python main.py
```

Press `Ctrl+C` to stop.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POLYMARKET_WALLET` | Wallet address to monitor | Required |
| `POLL_INTERVAL` | Seconds between API polls | 5 |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | Optional |
| `TELEGRAM_CHAT_IDS` | Comma-separated chat IDs | Optional |

> **Note**: If Telegram is not configured, alerts will display in the terminal instead.

