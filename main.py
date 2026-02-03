"""
Polymarket Wallet Trade Alert System

Monitors a specific Polymarket wallet via REST API polling and displays
real-time trade alerts with colored output.
"""

import asyncio
import logging
import os
import sys
import urllib3
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
POLYMARKET_WALLET = os.getenv("POLYMARKET_WALLET", "").lower()
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds
API_BASE_URL = "https://data-api.polymarket.com"

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


def log_trade(trade: dict[str, Any]) -> None:
    """Log trade details to file."""
    side = trade.get("side", "UNKNOWN").upper()
    market_name = trade.get("title", trade.get("asset", "Unknown"))
    shares = float(trade.get("size", 0))
    price = float(trade.get("price", 0))
    usdc_size = float(trade.get("usdcSize", shares * price))
    
    logger.info(
        f"Trade: {side} | Market: {market_name} | "
        f"Shares: {shares:.2f} | Price: ${price:.4f} | "
        f"Total: ${usdc_size:.2f} USDC"
    )


async def fetch_recent_activity(client: httpx.AsyncClient, limit: int = 20) -> list[dict]:
    """Fetch recent activity for the target wallet."""
    url = f"{API_BASE_URL}/activity"
    params = {
        "user": POLYMARKET_WALLET,
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


async def poll_for_trades() -> None:
    """Poll the REST API for new trades with exponential backoff on errors."""
    seen_hashes: set[str] = set()
    base_delay = POLL_INTERVAL
    max_delay = 60
    current_delay = base_delay
    error_count = 0
    
    # Initialize Telegram notifier
    notifier = TelegramNotifier.from_env()
    if notifier:
        console.print("[green]✓ Telegram notifications enabled[/green]")
    else:
        console.print("[yellow]⚠ Telegram not configured - using terminal output[/yellow]")
    
    # Create HTTP client with SSL verification disabled (for corporate proxies)
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        console.print("[cyan]Fetching initial activity...[/cyan]")
        
        # Get initial trades to populate seen set
        initial_trades = await fetch_recent_activity(client, limit=50)
        for trade in initial_trades:
            tx_hash = trade.get("transactionHash", "")
            if tx_hash:
                seen_hashes.add(tx_hash)
        
        console.print(f"[dim]Loaded {len(seen_hashes)} existing trades[/dim]")
        console.print(
            Panel(
                f"[bold]Monitoring wallet:[/bold]\n[cyan]{POLYMARKET_WALLET}[/cyan]\n\n"
                f"[dim]Polling every {POLL_INTERVAL} seconds[/dim]",
                title="[bold green]Active[/bold green]",
                border_style="green",
            )
        )
        
        while True:
            try:
                # Fetch recent activity
                trades = await fetch_recent_activity(client, limit=20)
                
                # Process new trades (reverse to show oldest first)
                new_trades = []
                for trade in reversed(trades):
                    tx_hash = trade.get("transactionHash", "")
                    if tx_hash and tx_hash not in seen_hashes:
                        # Only process TRADE type activities
                        if trade.get("type") == "TRADE":
                            new_trades.append(trade)
                            seen_hashes.add(tx_hash)
                
                # Send trade alerts
                for trade in new_trades:
                    log_trade(trade)
                    if notifier:
                        await notifier.send_trade_alert(trade, client)
                        console.print(f"[dim]Sent Telegram alert for trade[/dim]")
                    else:
                        # Fallback to terminal if Telegram not configured
                        alert = format_trade_alert(trade)
                        console.print(alert)
                
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
    # Validate configuration
    if not POLYMARKET_WALLET:
        console.print(
            "[red]✗ Error: POLYMARKET_WALLET environment variable not set![/red]"
        )
        console.print(
            "[yellow]Please set the wallet address in .env file or environment[/yellow]"
        )
        sys.exit(1)
    
    # Display startup banner
    console.print(
        Panel(
            "[bold cyan]Polymarket Wallet Trade Alert System[/bold cyan]\n"
            "[dim]Real-time trade monitoring with colored alerts[/dim]",
            border_style="cyan",
        )
    )
    
    console.print(f"[dim]Target wallet: {POLYMARKET_WALLET}[/dim]")
    console.print(f"[dim]Poll interval: {POLL_INTERVAL}s[/dim]")
    console.print(f"[dim]Log file: trades.log[/dim]")
    console.print()
    
    try:
        asyncio.run(poll_for_trades())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        logger.info("Application stopped by user")


if __name__ == "__main__":
    main()