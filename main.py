"""
Polymarket Wallet Trade Alert System

Monitors multiple Polymarket wallets via REST API polling and sends
real-time trade alerts to a dedicated Telegram bot per wallet.
"""

import asyncio
import json
import logging
import os
import sys
import urllib3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from telegram_notifier import TelegramNotifier

# Suppress SSL warnings (for corporate proxies)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Configuration
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds
API_BASE_URL = "https://data-api.polymarket.com"


@dataclass
class WalletMonitor:
    """A single wallet being tracked, paired with its own Telegram bot."""

    label: str
    wallet: str
    notifier: TelegramNotifier | None
    seen_hashes: set[str] = field(default_factory=set)


def load_wallet_monitors() -> list[WalletMonitor]:
    """
    Build the list of wallet monitors from configuration.

    Primary source is WALLETS_CONFIG: a JSON array of objects, each with
    "wallet", "bot_token", "chat_ids" (list), and an optional "label".

    Falls back to the legacy single-wallet vars (POLYMARKET_WALLET /
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS) so existing deploys keep working.
    """
    raw = os.getenv("WALLETS_CONFIG", "").strip()

    if raw:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"WALLETS_CONFIG is not valid JSON: {e}")
            return []
        if not isinstance(entries, list):
            logger.error("WALLETS_CONFIG must be a JSON array of wallet objects")
            return []
    else:
        # Legacy fallback: a single wallet from the old flat env vars.
        wallet = os.getenv("POLYMARKET_WALLET", "").strip()
        if not wallet:
            return []
        entries = [
            {
                "label": wallet[:10],
                "wallet": wallet,
                "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                "chat_ids": os.getenv("TELEGRAM_CHAT_IDS", "").strip(),
            }
        ]

    monitors: list[WalletMonitor] = []
    for i, entry in enumerate(entries):
        wallet = str(entry.get("wallet", "")).strip().lower()
        if not wallet:
            logger.error(f"Wallet entry #{i + 1} is missing a 'wallet' address - skipping")
            continue

        label = str(entry.get("label", "")).strip() or wallet[:10]

        # chat_ids may be a JSON list or a comma-separated string.
        raw_chat_ids = entry.get("chat_ids", [])
        if isinstance(raw_chat_ids, str):
            chat_ids = [c.strip() for c in raw_chat_ids.split(",") if c.strip()]
        else:
            chat_ids = [str(c).strip() for c in raw_chat_ids if str(c).strip()]

        bot_token = str(entry.get("bot_token", "")).strip()

        notifier: TelegramNotifier | None = None
        if bot_token and chat_ids:
            notifier = TelegramNotifier(bot_token, chat_ids, label=label)
        else:
            logger.warning(
                f"Wallet '{label}' has no bot_token/chat_ids - "
                f"trades will only be logged, not sent to Telegram"
            )

        monitors.append(WalletMonitor(label=label, wallet=wallet, notifier=notifier))

    return monitors

# Initialize Rich console
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("trades.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def format_trade_alert(trade: dict[str, Any]) -> Panel:
    """Format a trade into a colored Rich panel for display."""
    side = trade.get("side", "UNKNOWN").upper()
    is_buy = side == "BUY"
    
    # Extract trade details (using activity API field names)
    market_name = trade.get("title", trade.get("market", trade.get("asset", "Unknown Market")))
    shares = float(trade.get("size", 0))
    price = float(trade.get("price", 0))
    usdc_size = float(trade.get("usdcSize", shares * price))
    outcome = trade.get("outcome", "")
    
    # Get trade timestamp
    trade_ts = trade.get("timestamp", 0)
    trade_time = datetime.fromtimestamp(trade_ts).strftime("%Y-%m-%d %H:%M:%S") if trade_ts else "Unknown"
    
    # Create colored text
    color = "green" if is_buy else "red"
    direction_symbol = "📈" if is_buy else "📉"
    
    # Build the alert text
    text = Text()
    text.append(f"{direction_symbol} ", style="bold")
    text.append(f"{side}\n", style=f"bold {color}")
    text.append("Market: ", style="dim")
    text.append(f"{market_name}\n", style="white")
    if outcome:
        text.append("Outcome: ", style="dim")
        text.append(f"{outcome}\n", style="magenta")
    text.append("Shares: ", style="dim")
    text.append(f"{shares:,.2f}\n", style="cyan")
    text.append("Price: ", style="dim")
    text.append(f"${price:.4f}\n", style="yellow")
    text.append("Total: ", style="dim")
    text.append(f"${usdc_size:,.2f} USDC", style=f"bold {color}")
    
    # Create panel with timestamp
    return Panel(
        text,
        title=f"[bold {color}]Trade Alert[/bold {color}]",
        subtitle=f"[dim]{trade_time}[/dim]",
        border_style=color,
    )


def log_trade(trade: dict[str, Any], label: str = "") -> None:
    """Log trade details to file."""
    side = trade.get("side", "UNKNOWN").upper()
    market_name = trade.get("title", trade.get("asset", "Unknown"))
    shares = float(trade.get("size", 0))
    price = float(trade.get("price", 0))
    usdc_size = float(trade.get("usdcSize", shares * price))

    prefix = f"[{label}] " if label else ""
    logger.info(
        f"{prefix}Trade: {side} | Market: {market_name} | "
        f"Shares: {shares:.2f} | Price: ${price:.4f} | "
        f"Total: ${usdc_size:.2f} USDC"
    )


async def fetch_recent_activity(
    client: httpx.AsyncClient, wallet: str, limit: int = 20
) -> list[dict]:
    """Fetch recent activity for the given wallet."""
    url = f"{API_BASE_URL}/activity"
    params = {
        "user": wallet,
        "limit": limit,
    }

    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching activity: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching activity: {e}")
        return []


async def prime_monitor(monitor: WalletMonitor, client: httpx.AsyncClient) -> None:
    """Populate a monitor's seen set so we don't alert on pre-existing trades."""
    initial_trades = await fetch_recent_activity(client, monitor.wallet, limit=50)
    for trade in initial_trades:
        tx_hash = trade.get("transactionHash", "")
        if tx_hash:
            monitor.seen_hashes.add(tx_hash)


async def poll_monitor(monitor: WalletMonitor, client: httpx.AsyncClient) -> None:
    """Check a single wallet for new trades and dispatch alerts."""
    trades = await fetch_recent_activity(client, monitor.wallet, limit=20)

    # Process new trades (reverse to handle oldest first)
    new_trades = []
    for trade in reversed(trades):
        tx_hash = trade.get("transactionHash", "")
        if tx_hash and tx_hash not in monitor.seen_hashes:
            # Only process TRADE type activities
            if trade.get("type") == "TRADE":
                new_trades.append(trade)
                monitor.seen_hashes.add(tx_hash)

    for trade in new_trades:
        log_trade(trade, monitor.label)
        if monitor.notifier:
            await monitor.notifier.send_trade_alert(trade, client)
            console.print(f"[dim]Sent Telegram alert for [{monitor.label}][/dim]")
        else:
            # Fallback to terminal if this wallet has no Telegram bot configured
            console.print(f"[dim][{monitor.label}][/dim]")
            console.print(format_trade_alert(trade))


async def poll_for_trades(monitors: list[WalletMonitor]) -> None:
    """Poll the REST API for new trades with exponential backoff on errors."""
    base_delay = POLL_INTERVAL
    max_delay = 60
    current_delay = base_delay
    error_count = 0

    # Create HTTP client with SSL verification disabled (for corporate proxies)
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        console.print("[cyan]Fetching initial activity...[/cyan]")

        # Populate each monitor's seen set concurrently
        await asyncio.gather(*(prime_monitor(m, client) for m in monitors))

        for m in monitors:
            tele = f"→ bot for {len(m.notifier.chat_ids)} chat(s)" if m.notifier else "→ terminal only"
            console.print(
                f"[dim]Loaded {len(m.seen_hashes)} existing trades for "
                f"[cyan]{m.label}[/cyan] {tele}[/dim]"
            )

        console.print(
            Panel(
                f"[bold]Monitoring {len(monitors)} wallet(s)[/bold]\n"
                + "\n".join(f"[cyan]{m.label}[/cyan]: {m.wallet}" for m in monitors)
                + f"\n\n[dim]Polling every {POLL_INTERVAL} seconds[/dim]",
                title="[bold green]Active[/bold green]",
                border_style="green",
            )
        )

        while True:
            try:
                # Poll every wallet concurrently
                await asyncio.gather(*(poll_monitor(m, client) for m in monitors))

                # Reset error count on success
                error_count = 0
                current_delay = base_delay

            except Exception as e:
                error_count += 1
                logger.error(f"Error polling trades: {e}")
                console.print(f"[red]✗ Error: {e}[/red]")

                # Exponential backoff on repeated errors
                if error_count >= 3:
                    current_delay = min(current_delay * 2, max_delay)
                    console.print(
                        f"[yellow]⚠ Multiple errors. Backing off to {current_delay}s[/yellow]"
                    )

            # Wait before next poll
            await asyncio.sleep(current_delay)


def main() -> None:
    """Main entry point."""
    # Load and validate configuration
    monitors = load_wallet_monitors()
    if not monitors:
        console.print(
            "[red]✗ Error: no wallets configured![/red]"
        )
        console.print(
            "[yellow]Set WALLETS_CONFIG (a JSON array of "
            "{wallet, bot_token, chat_ids} objects) in your .env or environment[/yellow]"
        )
        sys.exit(1)

    # Display startup banner
    console.print(
        Panel(
            "[bold cyan]Polymarket Wallet Trade Alert System[/bold cyan]\n"
            "[dim]Real-time trade monitoring with per-wallet Telegram bots[/dim]",
            border_style="cyan",
        )
    )

    console.print(f"[dim]Tracking {len(monitors)} wallet(s)[/dim]")
    console.print(f"[dim]Poll interval: {POLL_INTERVAL}s[/dim]")
    console.print(f"[dim]Log file: trades.log[/dim]")
    console.print()

    try:
        asyncio.run(poll_for_trades(monitors))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        logger.info("Application stopped by user")


if __name__ == "__main__":
    main()