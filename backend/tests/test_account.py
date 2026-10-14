"""My account: details, change password, delete account, forgot password."""
import re
import unittest
from unittest import mock

from test_auth import AuthTests, call, session_cookie

import mailer  # noqa: E402  (test_auth puts api/ on the path)

NEW = "a brand new pass"


class AccountTests(AuthTests):
    def setUp(self):
        super().setUp()
        self.sent = []
        patcher = mock.patch.object(mailer, "send_reset",
                                    lambda email, link: self.sent.append((email, link)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def reset_token(self):
        return re.search(r"#reset=([\w-]+)$", self.sent[-1][1]).group(1)

    # ---- details

    def test_account_shows_email_and_save_counts(self):
        ck = self.cookie()
        call("POST", "/api/saved", {"dataset": "pima", "name": "a", "values": {"Glucose": 1}},
             cookie=ck)
        code, obj, _ = call("GET", "/api/account", cookie=ck)
        self.assertEqual(code, 200)
        self.assertEqual(obj["user"]["email"], "ada@example.com")
        self.assertEqual(obj["user"]["saves"], {"pima": 1})
        self.assertEqual(call("GET", "/api/account")[0], 401)

    # ---- change password

    def test_change_password_needs_the_current_one(self):
        ck = self.cookie()
        code, _, _ = call("POST", "/api/account/password",
                          {"current": "wrong guess!", "new": NEW}, cookie=ck)
        self.assertEqual(code, 401)
        code, _, _ = call("POST", "/api/account/password",
                          {"current": "correct horse", "new": NEW}, cookie=ck)
        self.assertEqual(code, 200)
        self.assertEqual(call("POST", "/api/login", {"email": "ada@example.com",
                                                     "password": NEW})[0], 200)
        self.assertEqual(call("POST", "/api/login", {"email": "ada@example.com",
                                                     "password": "correct horse"})[0], 401)

    def test_change_password_signs_out_other_browsers_only(self):
        here = self.cookie()
        other = session_cookie(call("POST", "/api/login", {"email": "ada@example.com",
                                                           "password": "correct horse"})[2])
        call("POST", "/api/account/password", {"current": "correct horse", "new": NEW},
             cookie=here)
        self.assertIsNotNone(call("GET", "/api/me", cookie=here)[1]["user"])
        self.assertIsNone(call("GET", "/api/me", cookie=other)[1]["user"])

    def test_change_password_rejects_short_ones(self):
        code, obj, _ = call("POST", "/api/account/password",
                            {"current": "correct horse", "new": "short"}, cookie=self.cookie())
        self.assertEqual(code, 400)

    # ---- delete account

    def test_delete_account_removes_everything(self):
        ck = self.cookie()
        call("POST", "/api/saved", {"dataset": "pima", "name": "a", "values": {"Glucose": 1}},
             cookie=ck)
        self.assertEqual(call("POST", "/api/account/delete", {"password": "nope nope"},
                              cookie=ck)[0], 401)
        code, _, extra = call("POST", "/api/account/delete", {"password": "correct horse"},
                              cookie=ck)
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", extra["Set-Cookie"])
        for table in ("users", "sessions", "saved_values"):
            self.assertEqual(self.stored(f"SELECT COUNT(*) FROM {table}")[0][0], 0, table)
        self.assertEqual(self.register()[0], 201)          # the email is free again

    def test_delete_needs_sign_in(self):
        self.assertEqual(call("POST", "/api/account/delete", {"password": "x"})[0], 401)

    # ---- forgot password

    def test_reset_link_sets_a_new_password_once(self):
        self.register()
        code, obj, _ = call("POST", "/api/forgot", {"email": "ADA@example.com"})
        self.assertEqual((code, obj["message"]), (200, auth_msg()))
        self.assertTrue(self.sent[-1][1].startswith("http://localhost/login.html#reset="))
        token = self.reset_token()
        code, obj, extra = call("POST", "/api/reset", {"token": token, "password": NEW})
        self.assertEqual(code, 200)
        self.assertIn("glimpse_session=", extra["Set-Cookie"])
        self.assertEqual(call("POST", "/api/login", {"email": "ada@example.com",
                                                     "password": NEW})[0], 200)
        self.assertEqual(call("POST", "/api/reset", {"token": token, "password": NEW})[0], 400)

    def test_reset_signs_out_old_sessions(self):
        ck = self.cookie()
        call("POST", "/api/forgot", {"email": "ada@example.com"})
        call("POST", "/api/reset", {"token": self.reset_token(), "password": NEW})
        self.assertIsNone(call("GET", "/api/me", cookie=ck)[1]["user"])

    def test_unknown_email_gets_the_same_answer_and_no_mail(self):
        code, obj, _ = call("POST", "/api/forgot", {"email": "nobody@example.com"})
        self.assertEqual((code, obj["message"]), (200, auth_msg()))
        self.assertEqual(self.sent, [])

    def test_reset_tokens_are_stored_hashed_and_expire(self):
        self.register()
        call("POST", "/api/forgot", {"email": "ada@example.com"})
        token = self.reset_token()
        self.assertNotIn(token, str(self.stored("SELECT * FROM password_resets")))
        with mock.patch("auth.time.time", return_value=10 ** 11):
            self.assertEqual(call("POST", "/api/reset", {"token": token, "password": NEW})[0], 400)

    def test_reset_requests_are_throttled(self):
        self.register()
        codes = [call("POST", "/api/forgot", {"email": "ada@example.com"})[0] for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_reset_link_uses_the_configured_url(self):
        self.register()
        with mock.patch.dict("os.environ", {"APP_URL": "https://glimpse.example"}):
            call("POST", "/api/forgot", {"email": "ada@example.com"},
                 headers={"Host": "evil.example"})
        self.assertTrue(self.sent[-1][1].startswith("https://glimpse.example/login.html#reset="))

    def test_reset_unavailable_on_vercel_without_email(self):
        with mock.patch.dict("os.environ", {"VERCEL": "1", "DATABASE_URL": "postgres://x"}):
            with mock.patch("db.configured", return_value=True):
                code, _, _ = call("POST", "/api/forgot", {"email": "ada@example.com"})
        self.assertEqual(code, 503)


def auth_msg():
    import auth
    return auth.RESET_SENT


del AuthTests      # run the inherited tests once, in test_auth.py

if __name__ == "__main__":
    unittest.main()
