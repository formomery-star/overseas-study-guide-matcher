from getpass import getpass
from pathlib import Path
import secrets
import os
import base64
import hashlib

target = Path(__file__).resolve().parent / ".env"
if target.exists():
    raise SystemExit("webapp/.env already exists; refusing to overwrite secrets")
first = getpass("Set a unique admin password (20+ characters recommended): ")
second = getpass("Repeat admin password: ")
if first != second or len(first) < 16:
    raise SystemExit("Passwords must match and contain at least 16 characters")
salt = secrets.token_hex(16)
password_hash = hashlib.scrypt(first.encode("utf-8"), salt=salt.encode("utf-8"), n=2**15, r=8, p=1, maxmem=128 * 1024 * 1024).hex()
fernet_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
value = "\n".join([
    "SESSION_SECRET=" + secrets.token_urlsafe(48),
    "DATA_ENCRYPTION_KEY=" + fernet_key,
    # Single quotes keep Compose from interpreting the dollar separators in Werkzeug's scrypt hash.
    "ADMIN_PASSWORD_HASH='scrypt:32768:8:1$" + salt + "$" + password_hash + "'",
    "COOKIE_SECURE=1",
    "FLASK_DEBUG=0",
    "",
])
target.write_text(value, encoding="utf-8")
try:
    os.chmod(target, 0o600)
except OSError:
    pass
print(f"Created {target}. Keep it out of Git, email, chat, and public backups.")
