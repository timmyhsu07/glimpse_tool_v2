"""One database API over SQLite (local) and Postgres (deployed).

Set DATABASE_URL (or POSTGRES_URL, as Vercel's Postgres integrations do) to use
Postgres; otherwise accounts live in a SQLite file, ``backend/data/glimpse.db`` by
default or GLIMPSE_DB if set. SQL is written once with ``?`` placeholders.
"""
from contextlib import contextmanager
import os
import sqlite3
import ssl
from urllib.parse import parse_qs, unquote, urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_READY = set()            # databases whose schema exists, per process

# {id} becomes each engine's auto-increment primary key.
_TABLES = [
    """CREATE TABLE IF NOT EXISTS users (
        id            {id},
        email         TEXT   NOT NULL UNIQUE,
        password_hash TEXT   NOT NULL,
        created_at    BIGINT NOT NULL,
        last_login_at BIGINT
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT   PRIMARY KEY,
        user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at BIGINT NOT NULL,
        expires_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS saved_values (
        id         {id},
        user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        dataset    TEXT   NOT NULL,
        name       TEXT   NOT NULL,
        data_json  TEXT   NOT NULL,
        updated_at BIGINT NOT NULL,
        UNIQUE (user_id, dataset, name)
    )""",
    """CREATE TABLE IF NOT EXISTS login_failures (
        key TEXT   NOT NULL,
        at  BIGINT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS login_failures_key ON login_failures (key, at)",
]


def database_url():
    return os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""


def sqlite_path():
    return os.environ.get("GLIMPSE_DB") or os.path.join(_ROOT, "data", "glimpse.db")


def configured():
    """False on Vercel without a database: its filesystem does not persist."""
    return bool(database_url()) or not os.environ.get("VERCEL")


class Database:
    def __init__(self, conn, postgres):
        self.conn = conn
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        return cur

    def one(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise


def _postgres(url):
    import pg8000.dbapi

    u = urlparse(url)
    q = parse_qs(u.query)
    sslmode = q.get("sslmode", [None])[0]
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    use_ssl = sslmode != "disable" and (sslmode is not None or not local)
    return pg8000.dbapi.connect(
        user=unquote(u.username or ""), password=unquote(u.password or ""),
        host=u.hostname, port=u.port or 5432, database=(u.path or "/")[1:],
        ssl_context=ssl.create_default_context() if use_ssl else None,
        timeout=10)


@contextmanager
def connect():
    url = database_url()
    if url:
        db = Database(_postgres(url), postgres=True)
        key, id_col = url, "BIGSERIAL PRIMARY KEY"
    else:
        path = sqlite_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        db = Database(conn, postgres=False)
        key, id_col = path, "INTEGER PRIMARY KEY"
    try:
        if key not in _READY:
            with db.transaction():
                for sql in _TABLES:
                    db.execute(sql.replace("{id}", id_col))
            _READY.add(key)
        yield db
    finally:
        db.conn.close()
