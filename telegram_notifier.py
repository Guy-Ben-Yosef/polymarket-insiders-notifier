"""
Telegram Notifier Module

Sends trade alerts to multiple Telegram chat IDs via the Bot API.
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"


class TelegramNotifier:
    """Sends formatted trade alerts to Telegram."""

    def __init__(self, bot_token: str, chat_ids: list[str]):
        """
        Initialize the Telegram notifier.

        Args:
            bot_token: Telegram Bot API token from BotFather
            chat_ids: List of chat IDs to send notifications to
        """
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.api_base = f"{TELEGRAM_API_URL}/bot{bot_token}"

    @classmethod
    def from_env(cls) -> "TelegramNotifier | None":
        """
        Create a TelegramNotifier from environment variables.

        Returns:
            TelegramNotifier instance or None if not configured
        """
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_ids_str = os.getenv("TELEGRAM_CHAT_IDS", "").strip()

        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set - Telegram notifications disabled")
            return None

        if not chat_ids_str:
            logger.warning("TELEGRAM_CHAT_IDS not set - Telegram notifications disabled")
            return None

        chat_ids = [cid.strip() for cid in chat_ids_str.split(",") if cid.strip()]

        if not chat_ids:
            logger.warning("No valid chat IDs found - Telegram notifications disabled")
            return None

        logger.info(f"Telegram notifier initialized for {len(chat_ids)} recipient(s)")
        return cls(bot_token, chat_ids)

    def format_trade_message(self, trade: dict[str, Any]) -> str:
        """
        Format a trade into a Telegram-friendly markdown message.

        Args:
            trade: Trade data dictionary from Polymarket API

        Returns:
            Formatted message string with MarkdownV2 formatting
        """
        side = trade.get("side", "UNKNOWN").upper()
        is_buy = side == "BUY"

        # Extract trade details
        market_name = trade.get("title", trade.get("market", trade.get("asset", "Unknown Market")))
        shares = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        usdc_size = float(trade.get("usdcSize", shares * price))
        outcome = trade.get("outcome", "")

        # Get trade timestamp
        trade_ts = trade.get("timestamp", 0)
        trade_time = datetime.fromtimestamp(trade_ts).strftime("%Y-%m-%d %H:%M:%S") if trade_ts else "Unknown"

        # Direction indicator
        direction = "📈 BUY" if is_buy else "📉 SELL"

        # Build message (using Markdown parse mode)
        lines = [
            f"*{direction}*",
            "",
            f"*Market:* {self._escape_markdown(market_name)}",
        ]

        if outcome:
            lines.append(f"*Outcome:* {self._escape_markdown(outcome)}")

        lines.extend([
            f"*Shares:* {shares:,.2f}",
            f"*Price:* ${price:.4f}",
            f"*Total:* ${usdc_size:,.2f} USDC",
            "",
            f"_{trade_time}_",
        ])

        return "\n".join(lines)

    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram Markdown."""
        # Characters that need escaping in Markdown mode
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text

    async def send_trade_alert(self, trade: dict[str, Any], client: httpx.AsyncClient) -> None:
        """
        Send a trade alert to all configured chat IDs.

        Args:
            trade: Trade data dictionary from Polymarket API
            client: httpx AsyncClient for making requests
        """
        message = self.format_trade_message(trade)

        for chat_id in self.chat_ids:
            await self._send_message(chat_id, message, client)

    async def _send_message(self, chat_id: str, text: str, client: httpx.AsyncClient) -> bool:
        """
        Send a message to a specific chat ID.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            client: httpx AsyncClient

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            if not result.get("ok"):
                logger.error(f"Telegram API error for chat {chat_id}: {result.get('description', 'Unknown error')}")
                return False

            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram HTTP error for chat {chat_id}: {e.response.status_code} - {e.response.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Telegram request error for chat {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending to chat {chat_id}: {e}")
            return False
