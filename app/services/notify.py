"""What we tell the user and when. Best-effort: a failed push or mail is logged into `history`
and never breaks the request/job that triggered it. Every channel the user has on is used."""
import logging
import threading

from .. import config, db
from . import mailer, ntfy

log = logging.getLogger(__name__)


def users_to_notify() -> list[dict]:
    return db.rows(db.q("SELECT * FROM users WHERE active=1"))


def deliver(user: dict, title: str, message: str, click: str = "", tags: list[str] | None = None,
            html_body: str = "", priority: int = 3) -> None:
    def work():
        if user.get("ntfy_topic") and user.get("notify_ntfy", 1):
            try:
                ntfy.push(user["ntfy_topic"], title, message, click=click or config.app_url(), tags=tags, priority=priority)
            except Exception as exc:  # noqa: BLE001
                log.warning("ntfy to %s failed: %s", user["ntfy_topic"], exc)
                db.log_history(None, "ntfy_failed", {"topic": user["ntfy_topic"], "error": str(exc)[:300]})
        if user.get("notify_email") and user.get("email") and mailer.is_configured():
            try:
                body = html_body or f"<p>{mailer.esc(message).replace(chr(10), '<br>')}</p>"
                mailer.send(user["email"], title, mailer.wrap(body, [("Otvoriť", click or config.app_url())]),
                            message + "\n\n" + (click or config.app_url()))
            except Exception as exc:  # noqa: BLE001
                log.warning("mail to %s failed: %s", user["email"], exc)
                db.log_history(None, "mail_failed", {"to": user["email"], "subject": title, "error": str(exc)[:300]})
        db.close()
    threading.Thread(target=work, daemon=True).start()


def broadcast(title: str, message: str, click: str = "", tags: list[str] | None = None, priority: int = 3) -> None:
    for u in users_to_notify():
        deliver(u, title, message, click=click, tags=tags, priority=priority)
