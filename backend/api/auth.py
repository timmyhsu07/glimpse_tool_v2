"""Email + password accounts, sessions, and saved values.

No email verification: registering just records the account. Passwords are
kept only as salted scrypt hashes, and sessions and reset links as SHA-256
digests of their tokens, so the database alone cannot be used to sign in.
Repeated failed sign-ins and reset requests are throttled per email and per
network address.

Storage is SQLite locally and Postgres when DATABASE_URL is set; see db.py.
"""
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from http.cookies import SimpleCookie
import re

import db
import mailer

COOKIE = "glimpse_session"
SESSION_DAYS = 30
MIN_PASSWORD = 8
MAX_PASSWORD = 1024
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

FAIL_WINDOW = 15 * 60          # seconds
FAIL_LIMIT_EMAIL = 10          # failed sign-ins per email per window
FAIL_LIMIT_IP = 50             # failed sign-ins per address per window

RESET_MINUTES = 60
RESET_LIMIT_EMAIL = 3          # reset emails per address per hour
RESET_LIMIT_IP = 20            # reset requests per network address per hour

# Shared test accounts shown on the sign-in page: they can sign in and save, but
# nobody can change their password, reset it, or delete them.
def demo_accounts():
    raw = os.environ.get("GLIMPSE_DEMO_ACCOUNTS", "test@ex.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


DEMO_LOCKED = "This is the shared test account, so it can't be changed."

MAX_FIELDS = 500
MAX_SAVES = 50                 # named saves per user per dataset
MAX_NAME = 60
SIGN_IN_TO_SAVE = "Sign in to save your data."


# ---- passwords

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(digest)}"


def verify_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expect = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(expect))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expect)


# Checked against when the email is unknown, so a miss costs the same time as a hit.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# ---- sessions

def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _cookie(token, secure, max_age):
    c = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
    return c + "; Secure" if secure else c


def _start_session(conn, user_id, secure):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
                 "VALUES (?, ?, ?, ?)",
                 (_token_hash(token), user_id, now, now + SESSION_DAYS * 86400))
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
    return {"Set-Cookie": _cookie(token, secure, SESSION_DAYS * 86400)}


def session_token(cookie_header):
    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    morsel = jar.get(COOKIE)
    return morsel.value if morsel else None


def _user_id(conn, token):
    if not token:
        return None
    row = conn.one("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                   (_token_hash(token), int(time.time())))
    return row[0] if row else None


# ---- accounts; each returns (status, json_body, extra_headers)

def _credentials(data):
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")
    if not isinstance(password, str):
        password = ""
    return email, password


def register(data, secure=False):
    email, password = _credentials(data)
    if len(email) > 254 or not _EMAIL.match(email):
        return 400, {"error": "Enter a valid email address."}, {}
    problem = _new_password_problem(password)
    if problem:
        return 400, {"error": problem}, {}
    pw_hash = hash_password(password)
    with db.connect() as conn, conn.transaction():
        row = conn.one("INSERT INTO users (email, password_hash, created_at) "
                       "VALUES (?, ?, ?) ON CONFLICT (email) DO NOTHING RETURNING id",
                       (email, pw_hash, int(time.time())))
        if row is None:
            return 409, {"error": "An account with that email already exists."}, {}
        headers = _start_session(conn, row[0], secure)
    return 201, {"user": {"email": email}}, headers


def login(data, secure=False, ip=""):
    email, password = _credentials(data)
    keys = (f"email:{email}", f"ip:{ip}")
    now = int(time.time())
    with db.connect() as conn:
        since = now - FAIL_WINDOW
        n_email, n_ip = (conn.one("SELECT COUNT(*) FROM login_failures "
                                  "WHERE key = ? AND at > ?", (k, since))[0] for k in keys)
        if n_email >= FAIL_LIMIT_EMAIL or (ip and n_ip >= FAIL_LIMIT_IP):
            return 429, {"error": "Too many attempts. Wait a few minutes and try again."}, {}
        row = conn.one("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        ok = verify_password(password, row[1] if row else _DUMMY_HASH)
        with conn.transaction():
            if not (row and ok):
                conn.execute("DELETE FROM login_failures WHERE at < ?", (since,))
                for k in keys if ip else keys[:1]:
                    conn.execute("INSERT INTO login_failures (key, at) VALUES (?, ?)", (k, now))
                return 401, {"error": "Incorrect email or password."}, {}
            conn.execute("DELETE FROM login_failures WHERE key = ?", (keys[0],))
            headers = _start_session(conn, row[0], secure)
    return 200, {"user": {"email": email}}, headers


def logout(token, secure=False):
    if token:
        with db.connect() as conn, conn.transaction():
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    return 200, {"user": None}, {"Set-Cookie": _cookie("", secure, 0)}


def current_user(token):
    if not token:
        return None
    with db.connect() as conn:
        row = conn.one("SELECT u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                       "WHERE s.token_hash = ? AND s.expires_at > ?",
                       (_token_hash(token), int(time.time())))
    return {"email": row[0]} if row else None


def _new_password_problem(password):
    if len(password) < MIN_PASSWORD:
        return f"Use a password of at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return "That password is too long."
    return None


def _throttled(conn, keys_limits, window):
    since = int(time.time()) - window
    return any(conn.one("SELECT COUNT(*) FROM login_failures WHERE key = ? AND at > ?",
                        (k, since))[0] >= limit for k, limit in keys_limits)


def _note_attempt(conn, keys, window):
    now = int(time.time())
    conn.execute("DELETE FROM login_failures WHERE at < ?", (now - max(window, FAIL_WINDOW),))
    for k in keys:
        conn.execute("INSERT INTO login_failures (key, at) VALUES (?, ?)", (k, now))


# ---- my account: details, change password, delete account

def account(token):
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": "Sign in to see your account."}, {}
        email, created = conn.one("SELECT email, created_at FROM users WHERE id = ?", (uid,))
        rows = conn.all("SELECT dataset, COUNT(*) FROM saved_values WHERE user_id = ? "
                        "GROUP BY dataset", (uid,))
    return 200, {"user": {"email": email, "created_at": created,
                          "saves": {d: n for d, n in rows}}}, {}


def _check_own_password(conn, uid, password):
    """(ok, error response). Wrong guesses count toward the sign-in throttle."""
    email, stored = conn.one("SELECT email, password_hash FROM users WHERE id = ?", (uid,))
    if email in demo_accounts():
        return False, (403, {"error": DEMO_LOCKED}, {})
    key = f"email:{email}"
    if _throttled(conn, [(key, FAIL_LIMIT_EMAIL)], FAIL_WINDOW):
        return False, (429, {"error": "Too many attempts. Wait a few minutes and try again."}, {})
    if not verify_password(password, stored):
        with conn.transaction():
            _note_attempt(conn, [key], FAIL_WINDOW)
        return False, (401, {"error": "That password isn't right."}, {})
    return True, None


def change_password(token, data):
    current = data.get("current") if isinstance(data.get("current"), str) else ""
    new = data.get("new") if isinstance(data.get("new"), str) else ""
    problem = _new_password_problem(new)
    if problem:
        return 400, {"error": problem}, {}
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": "Sign in to change your password."}, {}
        ok, err = _check_own_password(conn, uid, current)
        if not ok:
            return err
        with conn.transaction():
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (hash_password(new), uid))
            # Sign out everywhere else; this browser stays signed in.
            conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
                         (uid, _token_hash(token)))
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (uid,))
    return 200, {"ok": True}, {}


def delete_account(token, data, secure=False):
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": "Sign in to delete your account."}, {}
        ok, err = _check_own_password(conn, uid, password)
        if not ok:
            return err
        with conn.transaction():
            # Sessions, saves and reset links go with it (ON DELETE CASCADE).
            conn.execute("DELETE FROM saved_values WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    return 200, {"deleted": True}, {"Set-Cookie": _cookie("", secure, 0)}


# ---- forgot password: a one-time link by email

RESET_SENT = "If that email has an account, a reset link is on its way."


def request_reset(data, base_url, ip=""):
    if not mailer.available():
        return 503, {"error": "Password reset by email isn't set up yet."}, {}
    email = str(data.get("email") or "").strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        return 400, {"error": "Enter a valid email address."}, {}
    if email in demo_accounts():
        return 403, {"error": DEMO_LOCKED}, {}
    keys = [(f"reset:{email}", RESET_LIMIT_EMAIL)] + ([(f"reset-ip:{ip}", RESET_LIMIT_IP)] if ip else [])
    with db.connect() as conn:
        if _throttled(conn, keys, 3600):
            return 429, {"error": "Too many reset requests. Try again in an hour."}, {}
        row = conn.one("SELECT id FROM users WHERE email = ?", (email,))
        token = secrets.token_urlsafe(32)
        with conn.transaction():
            _note_attempt(conn, [k for k, _ in keys], 3600)
            if row:
                now = int(time.time())
                conn.execute("DELETE FROM password_resets WHERE user_id = ? OR expires_at < ?",
                             (row[0], now))
                conn.execute("INSERT INTO password_resets (token_hash, user_id, expires_at) "
                             "VALUES (?, ?, ?)",
                             (_token_hash(token), row[0], now + RESET_MINUTES * 60))
    if row:
        try:
            mailer.send_reset(email, f"{base_url}/login.html#reset={token}")
        except Exception:
            return 502, {"error": "Couldn't send the email. Try again in a minute."}, {}
    # Same answer either way, so this can't be used to find out who has an account.
    return 200, {"message": RESET_SENT}, {}


def reset_password(data, secure=False):
    token = data.get("token") if isinstance(data.get("token"), str) else ""
    new = data.get("password") if isinstance(data.get("password"), str) else ""
    problem = _new_password_problem(new)
    if problem:
        return 400, {"error": problem}, {}
    with db.connect() as conn, conn.transaction():
        row = conn.one("SELECT r.user_id, u.email FROM password_resets r "
                       "JOIN users u ON u.id = r.user_id "
                       "WHERE r.token_hash = ? AND r.expires_at > ?",
                       (_token_hash(token), int(time.time())))
        if row is None:
            return 400, {"error": "This reset link has expired or was already used. "
                                  "Ask for a new one."}, {}
        uid, email = row
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), uid))
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM login_failures WHERE key = ?", (f"email:{email}",))
        headers = _start_session(conn, uid, secure)
    return 200, {"user": {"email": email}}, headers


# ---- saved values: named, per user and dataset, signed-in users only

def _clean_values(values):
    """{feature: number or None}, or None if the shape is wrong."""
    if not isinstance(values, dict) or not 0 < len(values) <= MAX_FIELDS:
        return None
    clean = {}
    for k, v in values.items():
        if not isinstance(k, str) or not 0 < len(k) <= 100:
            return None
        if v is None or v == "":
            clean[k] = None
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            clean[k] = float(v)
        else:
            return None
    return clean


def _entry(row):
    e = {"id": row[0], "name": row[1], "values": json.loads(row[2]), "updated_at": row[3]}
    if len(row) > 4:
        e["dataset"] = row[4]
    return e


def list_saved(token, dataset):
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": SIGN_IN_TO_SAVE}, {}
        if dataset is None:
            rows = conn.all("SELECT id, name, data_json, updated_at, dataset FROM saved_values "
                            "WHERE user_id = ? ORDER BY updated_at DESC, id DESC", (uid,))
        else:
            rows = conn.all("SELECT id, name, data_json, updated_at FROM saved_values "
                            "WHERE user_id = ? AND dataset = ? ORDER BY updated_at DESC, id DESC",
                            (uid, dataset))
    return 200, {"saved": [_entry(r) for r in rows]}, {}


def save_values(token, dataset, name, values):
    clean = _clean_values(values)
    if clean is None:
        return 400, {"error": "Nothing valid to save: values must be numbers or blank."}, {}
    if all(v is None for v in clean.values()):
        return 400, {"error": "Choose at least one value to save."}, {}
    name = " ".join(str(name or "").split())[:MAX_NAME] or "My saved values"
    now = int(time.time())
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": SIGN_IN_TO_SAVE}, {}
        with conn.transaction():
            exists = conn.one("SELECT 1 FROM saved_values WHERE user_id = ? AND dataset = ? "
                              "AND name = ?", (uid, dataset, name))
            count = conn.one("SELECT COUNT(*) FROM saved_values WHERE user_id = ? "
                             "AND dataset = ?", (uid, dataset))[0]
            if not exists and count >= MAX_SAVES:
                return 400, {"error": f"You can keep up to {MAX_SAVES} saves per dataset. "
                                      "Delete one first."}, {}
            row = conn.one(
                "INSERT INTO saved_values (user_id, dataset, name, data_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (user_id, dataset, name) DO UPDATE SET "
                "data_json = excluded.data_json, updated_at = excluded.updated_at "
                "RETURNING id, name, data_json, updated_at",
                (uid, dataset, name, json.dumps(clean), now))
    return 200, {"saved": _entry(row)}, {}


def rename_saved(token, entry_id, name):
    if not isinstance(entry_id, int) or isinstance(entry_id, bool):
        return 400, {"error": "'id' must be a number"}, {}
    name = " ".join(str(name or "").split())[:MAX_NAME]
    if not name:
        return 400, {"error": "Give the save a name."}, {}
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": SIGN_IN_TO_SAVE}, {}
        with conn.transaction():
            row = conn.one("SELECT dataset FROM saved_values WHERE id = ? AND user_id = ?",
                           (entry_id, uid))
            if row is None:
                return 404, {"error": "That save no longer exists."}, {}
            clash = conn.one("SELECT 1 FROM saved_values WHERE user_id = ? AND dataset = ? "
                             "AND name = ? AND id <> ?", (uid, row[0], name, entry_id))
            if clash:
                return 409, {"error": "You already have a save with that name."}, {}
            conn.execute("UPDATE saved_values SET name = ? WHERE id = ?", (name, entry_id))
    return 200, {"id": entry_id, "name": name}, {}


def delete_saved(token, entry_id):
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": SIGN_IN_TO_SAVE}, {}
        with conn.transaction():
            cur = conn.execute("DELETE FROM saved_values WHERE id = ? AND user_id = ?",
                               (entry_id, uid))
    if cur.rowcount == 0:
        return 404, {"error": "That save no longer exists."}, {}
    return 200, {"deleted": entry_id}, {}
