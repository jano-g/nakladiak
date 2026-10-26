"""Push notifications via ntfy (public ntfy.sh by default). JSON publish so titles with
Slovak diacritics survive (plain headers are latin-1 on the wire)."""
import json
import logging
import urllib.request

from .. import settings

log = logging.getLogger(__name__)


def push(topic: str, title: str, message: str, click: str = "", tags: list[str] | None = None,
         priority: int = 3) -> None:
    if not topic:
        return
    server = (settings.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
    payload = {"topic": topic, "title": title, "message": message, "priority": priority}
    if click:
        payload["click"] = click
    if tags:
        payload["tags"] = tags
    req = urllib.request.Request(server, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "nakladiak/1.0"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    log.info("ntfy pushed to %s: %s", topic, title)
