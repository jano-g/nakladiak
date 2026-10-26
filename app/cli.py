"""Maintenance commands, run inside the container:
    docker compose exec nakladiak python -m app.cli set-password jano
    docker compose exec nakladiak python -m app.cli users
    docker compose exec nakladiak python -m app.cli zsd [--days 30]
    docker compose exec nakladiak python -m app.cli imap
    docker compose exec nakladiak python -m app.cli process <document_id>
"""
import getpass
import sys

from . import auth, db


def main(argv: list[str]) -> int:
    db.init()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "set-password" and len(argv) > 2:
        user = db.row(db.q1("SELECT * FROM users WHERE username=?", (argv[2].lower(),)))
        if not user:
            print("neznámy používateľ", argv[2]); return 1
        pw = argv[3] if len(argv) > 3 else getpass.getpass("Nové heslo: ")
        if len(pw) < 8:
            print("heslo musí mať aspoň 8 znakov"); return 1
        auth.set_password(user["id"], pw)
        db.log_history(None, "password_reset_cli", {"user": user["username"]})
        print("heslo zmenené, používateľ bol všade odhlásený"); return 0
    if cmd == "users":
        for u in db.q("SELECT id,username,name,email,is_admin,active FROM users"):
            print(u["id"], u["username"], u["name"], u["email"], "admin" if u["is_admin"] else "", "" if u["active"] else "deaktivovaný")
        return 0
    if cmd == "zsd":
        from .connectors import zsd
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 8
        print(zsd.run(days=days)["message"]); return 0
    if cmd == "imap":
        from .services import mailbox
        print(mailbox.poll()); return 0
    if cmd == "process" and len(argv) > 2:
        from .services import documents
        d = documents.process(int(argv[2]))
        print(d["status"], d.get("error") or (d.get("data") or {}).get("summary")); return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
