"""E-mail over plain SMTP (websupport.sk by default: SSL on 465, STARTTLS otherwise).
Failures are raised to the caller, who decides whether they are fatal (they never are
for notifications — those are logged and swallowed)."""
import html
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .. import config, settings

log = logging.getLogger(__name__)


def esc(s) -> str:
    return html.escape(str(s or ""))


def _header(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(s or "")).strip()


def is_configured() -> bool:
    return bool(settings.get("smtp_host") and (settings.get("smtp_from") or settings.get("smtp_user")))


def wrap(body_html: str, buttons: list[tuple[str, str]] | None = None, note: str = "") -> str:
    """One look for every mail: single column, system font, accent button, footer."""
    btns = "".join(
        f"<a href='{esc(url)}' style='display:inline-block;margin:8px 8px 8px 0;padding:11px 18px;border-radius:8px;"
        f"background:#1f5f8b;color:#fff;text-decoration:none;font-weight:700'>{esc(label)}</a>"
        for label, url in (buttons or []))
    host = config.app_url().split("//", 1)[-1]
    foot = f"Táto správa prišla z {esc(host)}." + (f" {esc(note)}" if note else "")
    return (f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:16px;line-height:1.5;"
            f"color:#1b1d22;max-width:560px;margin:0 auto;padding:16px'>{body_html}"
            f"<div style='margin-top:14px'>{btns}</div>"
            f"<p style='margin-top:28px;font-size:13px;color:#6b7280'>{foot}</p></div>")


def send(to: str, subject: str, html_body: str, text_body: str) -> None:
    host = settings.get("smtp_host")
    if not host:
        raise RuntimeError("SMTP server nie je nastavený (Nastavenia → E-mail).")
    if not to:
        raise RuntimeError("Príjemca nemá e-mail.")
    try:
        port = int(settings.get("smtp_port") or "465")
    except ValueError:
        port = 465
    user, password = settings.get("smtp_user"), settings.get("smtp_password")
    sender = settings.get("smtp_from") or user
    msg = EmailMessage()
    msg["Subject"] = _header(subject)
    msg["From"] = formataddr((_header(settings.get("smtp_from_name") or config.APP_NAME), sender))
    msg["To"] = _header(to)
    msg["Date"] = formatdate(localtime=True)
    msg["Auto-Submitted"] = "auto-generated"
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1] if "@" in sender else None)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as s:
            if user:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            if port != 25 or s.has_extn("starttls"):
                s.starttls(context=ctx)
                s.ehlo()
            if user:
                s.login(user, password)
            s.send_message(msg)
    log.info("mail sent to %s: %s", to, subject)
