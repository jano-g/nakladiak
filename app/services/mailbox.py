"""The bills mailbox: every 15 minutes read new messages over IMAP and hand PDF / image
attachments to the document pipeline. Idempotent: (UIDVALIDITY, UID, part) is the mail_key,
and the file hash catches the same bill forwarded twice."""
import email
import email.header
import imaplib
import logging
import socket
import ssl

from .. import db, settings, util
from . import documents

log = logging.getLogger(__name__)
MAX_PER_RUN = 20
INTERESTING = ("application/pdf", "image/jpeg", "image/png", "image/webp")


def is_configured() -> bool:
    return bool(settings.get("imap_host") and settings.get("imap_user") and settings.get("imap_password"))


def _decode(value) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _connect() -> imaplib.IMAP4:
    host = settings.get("imap_host")
    try:
        port = int(settings.get("imap_port") or "993")
    except ValueError:
        port = 993
    ctx = ssl.create_default_context()
    if port == 993:
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=40)
    else:
        conn = imaplib.IMAP4(host, port, timeout=40)
        conn.starttls(ctx)
    conn.login(settings.get("imap_user"), settings.get("imap_password"))
    return conn


def test_connection() -> str:
    conn = _connect()
    try:
        status, data = conn.select(settings.get("imap_folder") or "INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Priečinok sa nedá otvoriť.")
        n = int(data[0]) if data and data[0] else 0
        return f"Prihlásenie funguje, v priečinku je {util.plural(n, 'správa', 'správy', 'správ')}."
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def poll() -> dict:
    """Fetch unseen messages, store attachments, mark the message seen. Returns counts."""
    counts = {"messages": 0, "stored": 0, "duplicates": 0, "skipped": 0}
    if not is_configured():
        return counts
    folder = settings.get("imap_folder") or "INBOX"
    conn = _connect()
    try:
        status, data = conn.select(folder)
        if status != "OK":
            raise RuntimeError(f"IMAP priečinok {folder} sa nedá otvoriť.")
        uidvalidity = ""
        st, uv = conn.response("UIDVALIDITY")
        if uv and uv[0]:
            uidvalidity = uv[0].decode() if isinstance(uv[0], bytes) else str(uv[0])
        status, data = conn.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP search zlyhal.")
        uids = data[0].split() if data and data[0] else []
        for uid in uids[:MAX_PER_RUN]:
            uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
            status, msgdata = conn.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not msgdata or not isinstance(msgdata[0], tuple):
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            counts["messages"] += 1
            sender = _decode(msg.get("From"))
            subject = _decode(msg.get("Subject"))
            part_no = 0
            got_any = False
            for part in msg.walk():
                ctype = part.get_content_type()
                filename = _decode(part.get_filename() or "")
                if ctype not in INTERESTING and not (ctype == "application/octet-stream" and filename.lower().endswith(".pdf")):
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                part_no += 1
                key = f"{uidvalidity}:{uid_s}:{part_no}"
                try:
                    doc, created = documents.store(filename or f"priloha-{part_no}", payload, ctype, "mail",
                                                   mail_key=key, mail_from=sender, mail_subject=subject)
                except documents.DocError as exc:
                    log.info("mail %s part %s skipped: %s", uid_s, part_no, exc)
                    counts["skipped"] += 1
                    continue
                got_any = True
                counts["stored" if created else "duplicates"] += 1
            if not got_any:
                counts["skipped"] += 1
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
        db.set_setting("imap_last_ok", db.now_iso())
        db.set_setting("imap_last_error", "")
        return counts
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def poll_safe() -> dict | None:
    try:
        return poll()
    except (imaplib.IMAP4.error, OSError, socket.timeout, ssl.SSLError, RuntimeError) as exc:
        msg = str(exc)[:200]
        log.warning("imap poll failed: %s", msg)
        db.set_setting("imap_last_error", f"{db.now_iso()} {msg}")
        return None
