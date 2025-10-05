from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("discord_upload")


log = get_logger("discord_upload")


def post_embed_with_attachment(
    webhook_url: str,
    embed: Dict[str, Any],
    file_path: Path,
    components: Optional[List[Dict[str, Any]]] = None,
    additional_files: Optional[List[Path]] = None,
) -> bool:
    """Post a single-embed message with attached image file(s) (multipart).

    The embed should reference attachments via:
        embed["image"] = {"url": f"attachment://{file_path.name}"}
        embed["thumbnail"] = {"url": f"attachment://{gauge.name}"}

    If components are provided and bot token is configured, will use bot API.
    Otherwise falls back to webhook (no buttons).

    Parameters
    ----------
    webhook_url : str
        Discord webhook URL
    embed : Dict[str, Any]
        Discord embed object
    file_path : Path
        Primary image file (chart)
    components : Optional[List[Dict[str, Any]]]
        Discord message components (buttons)
    additional_files : Optional[List[Path]]
        Additional image files (e.g., sentiment gauge)

    Returns
    -------
    bool
        True on HTTP 2xx, False otherwise
    """
    # If components requested, try bot API first
    if components:
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv(
            "DISCORD_ALERT_CHANNEL_ID"
        ) or _extract_channel_from_webhook(webhook_url)

        log.debug("components_requested count=%d", len(components))
        log.debug("bot_token_configured value=%s", bool(bot_token))
        log.debug("channel_id value=%s", channel_id)

        if bot_token and channel_id:
            log.debug("using_bot_api_with_buttons")
            success = _post_via_bot_api(
                embed, file_path, components, bot_token, channel_id, additional_files
            )
            log.debug("bot_api_result success=%s", success)
            return success
        else:
            log.debug("bot_api_not_configured_fallback_to_webhook")

    # Fallback to webhook (no components support)
    log.debug("posting_via_webhook_no_buttons")

    # Prepare multiple files if additional_files provided
    files_dict = {}
    open_files = []

    try:
        # Primary file
        f1 = open(file_path, "rb")
        open_files.append(f1)
        files_dict["file"] = (file_path.name, f1, "image/png")

        # Additional files (e.g., gauge)
        if additional_files:
            for idx, add_file in enumerate(additional_files):
                if add_file and add_file.exists():
                    f = open(add_file, "rb")
                    open_files.append(f)
                    files_dict[f"file{idx+1}"] = (add_file.name, f, "image/png")

        data = {"payload_json": json.dumps({"embeds": [embed]})}
        r = requests.post(webhook_url, data=data, files=files_dict, timeout=15)
        log.debug("webhook_response status=%d files=%d", r.status_code, len(files_dict))
        return 200 <= r.status_code < 300

    finally:
        # Close all file handles
        for f in open_files:
            try:
                f.close()
            except Exception:
                pass


def _extract_channel_from_webhook(webhook_url: str) -> Optional[str]:
    """Extract channel ID from webhook URL for bot API fallback.

    Webhook URL format: https://discord.com/api/webhooks/{webhook_id}/{token}
    We can use webhook API to get channel info, but for now return None to require explicit config.
    """
    # Could parse webhook to get channel, but safer to require explicit DISCORD_ALERT_CHANNEL_ID
    return None


def _post_via_bot_api(
    embed: Dict[str, Any],
    file_path: Path,
    components: List[Dict[str, Any]],
    bot_token: str,
    channel_id: str,
    additional_files: Optional[List[Path]] = None,
) -> bool:
    """Post message with attachment and components via Discord Bot API.

    Parameters
    ----------
    embed : dict
        Discord embed object
    file_path : Path
        Path to image file
    components : list
        Discord message components (buttons)
    bot_token : str
        Discord bot token
    channel_id : str
        Discord channel ID

    Returns
    -------
    bool
        True if posted successfully
    """
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    headers = {"Authorization": f"Bot {bot_token}"}

    # Multipart form data with file and JSON payload
    payload = {"embeds": [embed], "components": components}

    data = {"payload_json": json.dumps(payload)}

    try:
        log.debug("posting_to_bot_api url=%s", url)
        log.debug(
            "file_attachment name=%s exists=%s", file_path.name, file_path.exists()
        )
        log.debug("components_count count=%d", len(components))

        # Prepare multiple files
        files_dict = {}
        open_files = []

        try:
            # Primary file
            f1 = open(file_path, "rb")
            open_files.append(f1)
            files_dict["file"] = (file_path.name, f1, "image/png")

            # Additional files (e.g., gauge)
            if additional_files:
                for idx, add_file in enumerate(additional_files):
                    if add_file and add_file.exists():
                        f = open(add_file, "rb")
                        open_files.append(f)
                        files_dict[f"file{idx+1}"] = (add_file.name, f, "image/png")

            r = requests.post(
                url, headers=headers, data=data, files=files_dict, timeout=15
            )
            log.debug(
                "bot_api_response status=%d files=%d", r.status_code, len(files_dict)
            )

            if r.status_code >= 400:
                log.debug("error_response body=%s", r.text[:500])

            return 200 <= r.status_code < 300

        finally:
            # Close all file handles
            for f in open_files:
                try:
                    f.close()
                except Exception:
                    pass

    except Exception as e:
        log.warning("bot_api_exception err=%s", str(e))
        return False
