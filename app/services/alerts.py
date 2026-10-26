"""App errors → ntfy (same topic as the niko1 infra alerts). Rate-limited: one message per key
per hour, 20 a day in total; never recursive (a failed alert only goes to the log)."""
import logging
import threading
import time

from .. import config, settings
from . import ntfy

log = logging.getLogger(__name__)
_lock = threading.Lock()
_last: dict[str, float] = {}
_day = ["", 0]  # [date, count]
DAILY_LIMIT = 20


def alert(key: str, title: str, message: str) -> None:
    topic = settings.get("alert_ntfy_topic")
    if not topic:
        return
    with _lock:
        now = time.time()
        today = time.strftime("%Y-%m-%d")
        if _day[0] != today:
            _day[0], _day[1] = today, 0
        if now - _last.get(key, 0) < 3600:
            return
        if _day[1] >= DAILY_LIMIT:
            if _day[1] == DAILY_LIMIT:
                _day[1] += 1
                title, message = "limit upozornení", "Ďalšie chyby dnes už len v logoch (docker logs nakladiak)."
            else:
                return
        else:
            _day[1] += 1
        _last[key] = now

    def work():
        try:
            ntfy.push(topic, f"{config.APP_NAME}: {title}", message[:900], tags=["warning"], priority=4)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert delivery failed: %s", exc)
    threading.Thread(target=work, daemon=True).start()
