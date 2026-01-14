"""
Discord Listener for Manual Capture Channel.

Monitors a dedicated Discord channel for missed opportunity submissions.
Uses discord.py to listen for messages with image attachments.

IMPORTANT: This requires the bot to have:
- MESSAGE_CONTENT intent enabled
- Access to the configured channel

Author: Claude Code (Manual Capture Feature)
Date: 2026-01-08
"""

import asyncio
import os
import threading
from typing import Optional

from ..logging_utils import get_logger

log = get_logger("moa.discord_listener")

# Check discord.py availability
try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None


# Global client instance
_client: Optional["discord.Client"] = None
_listener_task: Optional[asyncio.Task] = None
_listener_thread: Optional[threading.Thread] = None
_listener_loop: Optional[asyncio.AbstractEventLoop] = None


def is_feature_enabled() -> bool:
    """Check if manual capture feature is enabled."""
    return os.getenv("FEATURE_MANUAL_CAPTURE", "0") in ("1", "true", "yes")


def get_bot_token() -> str:
    """Get Discord bot token."""
    return os.getenv("DISCORD_BOT_TOKEN", "")


def get_capture_channel_id() -> Optional[int]:
    """Get the channel ID to monitor."""
    channel_id = os.getenv("MANUAL_CAPTURE_CHANNEL_ID", "")
    try:
        return int(channel_id) if channel_id else None
    except ValueError:
        return None


async def send_discord_reply(
    channel_id: int,
    message_id: int,
    content: str,
    react_emoji: str = None,
) -> bool:
    """
    Send a reply to a Discord message.

    Uses webhook or bot API to respond.

    Args:
        channel_id: Discord channel ID
        message_id: Message to reply to
        content: Reply content
        react_emoji: Optional emoji to react with

    Returns:
        True if successful
    """
    try:
        import aiohttp

        bot_token = get_bot_token()
        if not bot_token:
            log.warning("no_bot_token for reply")
            return False

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }

        # React with emoji if specified
        if react_emoji:
            emoji_encoded = react_emoji.encode("utf-8").decode("utf-8")
            react_url = (
                f"https://discord.com/api/v10/channels/{channel_id}"
                f"/messages/{message_id}/reactions/{emoji_encoded}/@me"
            )

            async with aiohttp.ClientSession() as session:
                async with session.put(react_url, headers=headers) as resp:
                    if resp.status not in (200, 204):
                        log.warning("react_failed status=%d", resp.status)

        # Send reply
        reply_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {
            "content": content,
            "message_reference": {
                "message_id": str(message_id),
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(reply_url, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    log.info("reply_sent channel=%d message=%d", channel_id, message_id)
                    return True
                else:
                    log.warning("reply_failed status=%d", resp.status)
                    return False

    except Exception as e:
        log.error("send_reply_failed error=%s", e, exc_info=True)
        return False


# Only define the client class if discord.py is available
if DISCORD_AVAILABLE:
    class ManualCaptureClient(discord.Client):
        """Discord client for monitoring manual capture channel."""

        def __init__(self, capture_channel_id: int, **kwargs):
            # Set up intents
            intents = discord.Intents.default()
            intents.message_content = True  # Required for reading message content
            intents.messages = True

            super().__init__(intents=intents, **kwargs)

            self.capture_channel_id = capture_channel_id
            log.info("capture_client_init channel=%d", capture_channel_id)

        async def on_ready(self):
            """Called when the bot is ready."""
            log.info(
                "capture_client_ready user=%s channel=%d",
                self.user,
                self.capture_channel_id,
            )

        async def on_message(self, message: "discord.Message"):
            """Process incoming messages."""
            # Ignore bot messages
            if message.author.bot:
                return

            # Only process messages in the capture channel
            if message.channel.id != self.capture_channel_id:
                return

            # Must have attachments
            if not message.attachments:
                return

            # Check for image attachments
            image_attachments = [
                a for a in message.attachments if a.content_type and a.content_type.startswith("image/")
            ]

            if not image_attachments:
                return

            log.info(
                "capture_message_received id=%s user=%s images=%d",
                message.id,
                message.author.id,
                len(image_attachments),
            )

            # Process the submission
            try:
                from .manual_capture import format_confirmation_message, process_capture_submission

                # Prepare attachments data
                attachments = [
                    {
                        "url": a.url,
                        "filename": a.filename,
                        "content_type": a.content_type,
                    }
                    for a in image_attachments
                ]

                # Process
                result = await process_capture_submission(
                    message_id=str(message.id),
                    user_id=str(message.author.id),
                    message_text=message.content,
                    attachments=attachments,
                )

                # React and reply
                if result.get("success"):
                    await message.add_reaction("✅")
                else:
                    await message.add_reaction("❌")

                # Send summary reply
                reply_text = format_confirmation_message(result)
                await message.reply(reply_text)

            except Exception as e:
                log.error("message_processing_failed id=%s error=%s", message.id, e, exc_info=True)
                try:
                    await message.add_reaction("❌")
                    await message.reply(f"Error processing capture: {str(e)[:100]}")
                except Exception:
                    pass
else:
    # Placeholder when discord.py is not available
    ManualCaptureClient = None


def _run_listener_in_thread(bot_token: str, channel_id: int):
    """
    Run the Discord listener in a dedicated thread with its own event loop.

    This is necessary because the main runner uses synchronous time.sleep(),
    which would block the asyncio event loop and prevent the Discord client
    from maintaining its websocket connection.
    """
    global _client, _listener_loop

    # Create a new event loop for this thread
    _listener_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_listener_loop)

    try:
        _client = ManualCaptureClient(capture_channel_id=channel_id)
        _listener_loop.run_until_complete(_client.start(bot_token))
    except Exception as e:
        log.error("listener_thread_error error=%s", e, exc_info=True)
    finally:
        if _listener_loop and _listener_loop.is_running():
            _listener_loop.stop()


async def start_listener() -> bool:
    """
    Start the Discord listener in a background thread.

    Uses a dedicated thread with its own event loop to ensure the Discord
    client can maintain its websocket connection even when the main thread
    is blocked by synchronous sleeps.

    Returns:
        True if started successfully
    """
    global _client, _listener_task, _listener_thread

    if not DISCORD_AVAILABLE or ManualCaptureClient is None:
        log.warning("discord_not_available")
        return False

    if not is_feature_enabled():
        log.info("manual_capture_disabled")
        return False

    bot_token = get_bot_token()
    if not bot_token:
        log.warning("no_bot_token for listener")
        return False

    channel_id = get_capture_channel_id()
    if not channel_id:
        log.warning("no_capture_channel_id")
        return False

    # Check if already running
    if _listener_thread is not None and _listener_thread.is_alive():
        log.info("listener_already_running")
        return True

    try:
        # Start the Discord client in a dedicated thread
        _listener_thread = threading.Thread(
            target=_run_listener_in_thread,
            args=(bot_token, channel_id),
            daemon=True,  # Thread will exit when main program exits
            name="discord-capture-listener",
        )
        _listener_thread.start()
        log.info("listener_started channel=%d thread=%s", channel_id, _listener_thread.name)
        return True

    except Exception as e:
        log.error("listener_start_failed error=%s", e, exc_info=True)
        return False


async def stop_listener():
    """Stop the Discord listener."""
    global _client, _listener_task, _listener_thread, _listener_loop

    if _client is not None:
        try:
            # Schedule close on the listener's event loop
            if _listener_loop and _listener_loop.is_running():
                _listener_loop.call_soon_threadsafe(_client.close)
            log.info("listener_stopped")
        except Exception as e:
            log.warning("listener_stop_error error=%s", e)

    if _listener_task is not None:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass

    # Wait for thread to finish (with timeout)
    if _listener_thread is not None and _listener_thread.is_alive():
        _listener_thread.join(timeout=5.0)

    _client = None
    _listener_task = None
    _listener_thread = None
    _listener_loop = None


def is_listener_running() -> bool:
    """Check if listener is currently running."""
    if _listener_thread is not None and _listener_thread.is_alive():
        return True
    return _client is not None and not _client.is_closed()
