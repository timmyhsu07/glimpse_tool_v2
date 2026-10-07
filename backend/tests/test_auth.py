"""Accounts, sessions, saved values and their protections.

Runs on SQLite by default. Set TEST_DATABASE_URL to run the same tests on Postgres.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "api"))

import auth  # noqa: E402
import db  # noqa: E402
import index  # noqa: E402 

PG = os.environ.get("TEST_DATABASE_URL", "")


def call(method, path, body=None, cookie=None, query="", headers=None):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    raw = json.dumps(body) if body is not None else None
    code, obj, *rest = index.route(method, path, query, raw, h)
    return code, obj, (rest[0] if rest else {})


def session_cookie(extra):
    return extra["Set-Cookie"].split(";")[0]          # "glimpse_session=<token>". 


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for k in ("DATABASE_URL", "POSTGRES_URL", "GLIMPSE_DB", "VERCEL"):
            os.environ.pop(k, None)
        if PG:
            os.environ["DATABASE_URL"] = PG
            with db.connect() as conn, conn.transaction():
                for t in ("saved_values", "sessions", "login_failures", "users"):
                    conn.execute(f"DELETE FROM {t}")
        else:
            os.environ["GLIMPSE_DB"] = os.path.join(self.tmp.name, "test.db")

    def tearDown(self):
        for k in ("DATABASE_URL", "GLIMPSE_DB", "VERCEL"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def register(self, email="ada@example.com", password="correct horse"):
        return call("POST", "/api/register", {"email": email, "password": password})

    def cookie(self, email="ada@example.com"):
        return session_cookie(self.register(email=email)[2])

    def stored(self, sql):
        with db.connect() as conn:
            return conn.all(sql)

    # ---- accounts

    def test_register_signs_you_in(self):
        code, obj, extra = self.register()
        self.assertEqual(code, 201)
        self.assertEqual(obj["user"]["email"], "ada@example.com")
        self.assertIn("HttpOnly", extra["Set-Cookie"])
        self.assertIn("SameSite=Lax", extra["Set-Cookie"])
        _, me, _ = call("GET", "/api/me", cookie=session_cookie(extra))
        self.assertEqual(me["user"], {"email": "ada@example.com"})

    def test_secure_cookie_over_https(self):
        _, _, extra = call("POST", "/api/register",
                           {"email": "s@example.com", "password": "correct horse"},
                           headers={"X-Forwarded-Proto": "https"})
        self.assertIn("; Secure", extra["Set-Cookie"])

    def test_password_and_token_are_never_stored(self):
        _, _, extra = self.register(password="correct horse")
        token = session_cookie(extra).split("=", 1)[1]
        (pw,), = self.stored("SELECT password_hash FROM users")
        self.assertNotIn("correct horse", pw)
        self.assertTrue(pw.startswith("scrypt$"))
        self.assertNotIn(token, [r[0] for r in self.stored("SELECT token_hash FROM sessions")])

    def test_email_is_case_insensitive_and_unique(self):
        self.register(email="Ada@Example.com")
        code, obj, _ = self.register(email="  ada@EXAMPLE.com ")
        self.assertEqual(code, 409)
        self.assertIn("already exists", obj["error"])

    def test_rejects_bad_input(self):
        self.assertEqual(self.register(email="not-an-email")[0], 400)
        self.assertEqual(self.register(password="short")[0], 400)
        self.assertEqual(call("POST", "/api/register", ["not", "an", "object"])[0], 400)

    def test_login_and_logout(self):
        self.register()
        code, _, extra = call("POST", "/api/login",
                              {"email": "ADA@example.com", "password": "correct horse"})
        self.assertEqual(code, 200)
        cookie = session_cookie(extra)
        self.assertEqual(call("GET", "/api/me", cookie=cookie)[1]["user"]["email"],
                         "ada@example.com")
        code, _, out = call("POST", "/api/logout", cookie=cookie)
        self.assertIn("Max-Age=0", out["Set-Cookie"])
        self.assertIsNone(call("GET", "/api/me", cookie=cookie)[1]["user"])

    def test_wrong_password_and_unknown_email_look_the_same(self):
        self.register()
        wrong = call("POST", "/api/login", {"email": "ada@example.com", "password": "nope nope"})
        unknown = call("POST", "/api/login", {"email": "bob@example.com", "password": "nope nope"})
        self.assertEqual(wrong[0], 401)
        self.assertEqual(wrong[:2], unknown[:2])

    def test_forged_cookie_is_ignored(self):
        self.register()
        self.assertIsNone(call("GET", "/api/me", cookie="glimpse_session=made-up")[1]["user"])

    # ---- protections

    def test_repeated_failures_lock_the_email(self):
        self.register()
        for _ in range(auth.FAIL_LIMIT_EMAIL):
            self.assertEqual(call("POST", "/api/login", {"email": "ada@example.com",
                                                         "password": "wrong-guess"})[0], 401)
        code, obj, _ = call("POST", "/api/login",
                            {"email": "ada@example.com", "password": "correct horse"})
        self.assertEqual(code, 429)                    # even the right password waits
        self.assertIn("Too many attempts", obj["error"])

    def test_successful_sign_in_resets_the_count(self):
        self.register()
        for _ in range(auth.FAIL_LIMIT_EMAIL - 1):
            call("POST", "/api/login", {"email": "ada@example.com", "password": "wrong-guess"})
        ok = call("POST", "/api/login", {"email": "ada@example.com", "password": "correct horse"})
        self.assertEqual(ok[0], 200)
        again = call("POST", "/api/login", {"email": "ada@example.com", "password": "wrong-guess"})
        self.assertEqual(again[0], 401)

    def test_cross_site_requests_are_refused(self):
        evil = {"Origin": "https://evil.example", "Host": "glimpse.example"}
        code, obj, _ = call("POST", "/api/register",
                            {"email": "x@example.com", "password": "correct horse"}, headers=evil)
        self.assertEqual(code, 403)
        same = {"Origin": "https://glimpse.example", "Host": "glimpse.example"}
        self.assertEqual(call("POST", "/api/register",
                              {"email": "x@example.com", "password": "correct horse"},
                              headers=same)[0], 201)

    def test_vercel_without_a_database_says_so(self):
        os.environ["VERCEL"] = "1"
        os.environ.pop("DATABASE_URL", None)
        code, obj, _ = call("GET", "/api/me")
        self.assertEqual(code, 503)
        self.assertIn("DATABASE_URL", obj["error"])

    def test_vercel_rewritten_paths_route_correctly(self):
        code, obj = index.route("GET", "/api/glimpse", "__route=health", None)
        self.assertEqual((code, obj["ok"]), (200, True))
        cookie = self.cookie()
        code, me, _ = call("GET", "/api/glimpse", cookie=cookie, query="__route=me")
        self.assertEqual(me["user"]["email"], "ada@example.com")

    # ---- saved values

    def save(self, cookie, values, name="", dataset="pima"):
        return call("POST", "/api/saved",
                    {"dataset": dataset, "name": name, "values": values}, cookie=cookie)

    def listing(self, cookie, dataset="pima"):
        return call("GET", "/api/saved", cookie=cookie, query=f"dataset={dataset}")

    def test_saving_requires_sign_in(self):
        for code, obj, _ in (self.listing(None), self.save(None, {"Glucose": 1}),
                             call("DELETE", "/api/saved", query="id=1")):
            self.assertEqual(code, 401)
            self.assertEqual(obj["error"], "Sign in to save your data.")

    def test_named_saves_of_chosen_values(self):
        cookie = self.cookie()
        self.assertEqual(self.listing(cookie)[1]["saved"], [])
        a = self.save(cookie, {"Glucose": 150, "BMI": 31.5}, name="Before diet")[1]["saved"]
        self.save(cookie, {"Glucose": 120}, name="  After   diet ")
        names = [s["name"] for s in self.listing(cookie)[1]["saved"]]
        self.assertEqual(sorted(names), ["After diet", "Before diet"])
        self.assertEqual(a["values"], {"Glucose": 150.0, "BMI": 31.5})
        # only the chosen values are stored
        (raw,), = self.stored("SELECT data_json FROM saved_values WHERE name = 'After diet'")
        self.assertEqual(json.loads(raw), {"Glucose": 120.0})

    def test_same_name_updates_in_place(self):
        cookie = self.cookie()
        first = self.save(cookie, {"Glucose": 150}, name="Mine")[1]["saved"]
        second = self.save(cookie, {"Glucose": 99}, name="Mine")[1]["saved"]
        self.assertEqual(first["id"], second["id"])
        saved = self.listing(cookie)[1]["saved"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["values"], {"Glucose": 99.0})

    def test_saves_are_per_dataset(self):
        cookie = self.cookie()
        self.save(cookie, {"Glucose": 150}, name="Mine")
        self.assertEqual(self.listing(cookie, dataset="heloc")[1]["saved"], [])

    def test_delete(self):
        cookie = self.cookie()
        sid = self.save(cookie, {"Glucose": 150}, name="Mine")[1]["saved"]["id"]
        self.assertEqual(call("DELETE", "/api/saved", cookie=cookie, query=f"id={sid}")[0], 200)
        self.assertEqual(self.listing(cookie)[1]["saved"], [])
        self.assertEqual(call("DELETE", "/api/saved", cookie=cookie, query=f"id={sid}")[0], 404)

    def test_users_cannot_see_or_delete_each_others_saves(self):
        ada, bob = self.cookie(), self.cookie(email="bob@example.com")
        sid = self.save(ada, {"Glucose": 150}, name="Ada's")[1]["saved"]["id"]
        self.assertEqual(self.listing(bob)[1]["saved"], [])
        self.assertEqual(call("DELETE", "/api/saved", cookie=bob, query=f"id={sid}")[0], 404)
        self.assertEqual(len(self.listing(ada)[1]["saved"]), 1)

    def test_rejects_bad_saved_values(self):
        cookie = self.cookie()
        for values in ({"Glucose": "high"}, {}, {"Glucose": None}, ["Glucose"],
                       {"Glucose": True}, {"Glucose": float("inf")}):
            self.assertEqual(self.save(cookie, values)[0], 400, values)
        self.assertEqual(self.listing(cookie, dataset="nope")[0], 400)

    def test_cap_on_saves_per_dataset(self):
        cookie = self.cookie()
        for i in range(auth.MAX_SAVES):
            self.assertEqual(self.save(cookie, {"Glucose": i}, name=f"s{i}")[0], 200)
        self.assertEqual(self.save(cookie, {"Glucose": 1}, name="one more")[0], 400)
        self.assertEqual(self.save(cookie, {"Glucose": 7}, name="s3")[0], 200)  # update ok

    def test_map_api_is_unchanged(self):
        code, obj = index.route("GET", "/api/health", "", None)
        self.assertEqual((code, obj["ok"]), (200, True))


if __name__ == "__main__":
    unittest.main()
