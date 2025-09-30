from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
import requests

def post_embed_with_attachment(webhook_url: str, embed: Dict[str, Any], file_path: Path) -> bool:
    """Post a single-embed message with an attached image file (multipart).

    The embed should reference the attachment via:
        embed["image"] = {"url": f"attachment://{file_path.name}"}
    Returns True on HTTP 2xx, False otherwise.
    """
    files = {"file": (file_path.name, open(file_path, "rb"), "image/png")}
    data = {"payload_json": json.dumps({"embeds": [embed]})}
    r = requests.post(webhook_url, data=data, files=files, timeout=15)
    return 200 <= r.status_code < 300
