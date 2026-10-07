"""Email + password accounts, sessions, and saved values.

No email verification: registering just records the account. Passwords are
kept only as salted scrypt hashes, and sessions as SHA-256 digests of the
cookie token, so the database alone cannot be used to sign in. Repeated failed
sign-ins are throttled per email and per network address.

Storage is SQLite locally and Postgres when DATABASE_URL is set; see db.py.
"""
import base64
import hashlib
import hmac
import json
import math
import secrets
import time
from http.cookies import SimpleCookie
import re

import db

COOKIE = "glimpse_session"
SESSION_DAYS = 30
MIN_PASSWORD = 8
MAX_PASSWORD = 1024
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

FAIL_WINDOW = 15 * 60          # seconds
FAIL_LIMIT_EMAIL = 10          # failed sign-ins per email per window
FAIL_LIMIT_IP = 50             # failed sign-ins per address per window

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
    if len(password) < MIN_PASSWORD:
        return 400, {"error": f"Use a password of at least {MIN_PASSWORD} characters."}, {}
    if len(password) > MAX_PASSWORD:
        return 400, {"error": "That password is too long."}, {}
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
    return {"id": row[0], "name": row[1], "values": json.loads(row[2]),
            "updated_at": row[3]}


def list_saved(token, dataset):
    with db.connect() as conn:
        uid = _user_id(conn, token)
        if uid is None:
            return 401, {"error": SIGN_IN_TO_SAVE}, {}
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
