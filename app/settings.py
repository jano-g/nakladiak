"""App settings editable in Nastavenia. `.env` is the base, a non-empty DB value wins.
Secrets are never rendered back to the browser."""
import os

from . import db

# key -> (env var, default)
OVERRIDABLE: dict[str, tuple[str, str]] = {
    "anthropic_api_key": ("ANTHROPIC_API_KEY", ""),
    "claude_model": ("CLAUDE_MODEL", "claude-sonnet-5-5"),
    "imap_host": ("IMAP_HOST", ""),
    "imap_port": ("IMAP_PORT", "993"),
    "imap_user": ("IMAP_USER", ""),
    "imap_password": ("IMAP_PASSWORD", ""),
    "imap_folder": ("IMAP_FOLDER", "INBOX"),
    "imap_enabled": ("IMAP_ENABLED", "1"),
    "zsd_user": ("ZSD_USER", ""),
    "zsd_password": ("ZSD_PASSWORD", ""),
    "zsd_business_partner_id": ("ZSD_BUSINESS_PARTNER_ID", ""),
    "twocaptcha_api_key": ("TWOCAPTCHA_API_KEY", ""),
    "zsd_enabled": ("ZSD_ENABLED", "1"),
    "zsd_time": ("ZSD_TIME", "14:35"),
    "smtp_host": ("SMTP_HOST", ""),
    "smtp_port": ("SMTP_PORT", "465"),
    "smtp_user": ("SMTP_USER", ""),
    "smtp_password": ("SMTP_PASSWORD", ""),
    "smtp_from": ("SMTP_FROM", ""),
    "smtp_from_name": ("SMTP_FROM_NAME", "Nakladiak"),
    "ntfy_server": ("NTFY_SERVER", "https://ntfy.sh"),
    "alert_ntfy_topic": ("ALERT_NTFY_TOPIC", ""),
    "statement_reminder_days": ("STATEMENT_REMINDER_DAYS", "30"),
}
SECRET_KEYS = {"anthropic_api_key", "imap_password", "zsd_password", "twocaptcha_api_key", "smtp_password"}


def get(key: str) -> str:
    env_var, default = OVERRIDABLE.get(key, ("", ""))
    v = db.get_setting(key, "")
    if v:
        return v
    if env_var:
        return os.environ.get(env_var, "") or default
    return default


def set_(key: str, value: str) -> None:
    db.set_setting(key, value)


def source(key: str) -> str:
    """Where the effective value comes from: 'db', 'env' or 'default'."""
    if db.get_setting(key, ""):
        return "db"
    env_var, _ = OVERRIDABLE.get(key, ("", ""))
    if env_var and os.environ.get(env_var, ""):
        return "env"
    return "default"


def public_view() -> dict:
    """All settings for the UI; secrets replaced by a boolean 'is set' marker."""
    out = {}
    for key in OVERRIDABLE:
        val = get(key)
        if key in SECRET_KEYS:
            out[key] = {"set": bool(val), "source": source(key)}
        else:
            out[key] = {"value": val, "source": source(key)}
    return out
