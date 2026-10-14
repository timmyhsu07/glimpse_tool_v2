"""HTTP handler for the GLIMPSE site and API."""
import os
import sys
import json
import math

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "engine"))
sys.path.insert(0, _HERE)
_FRONTEND = os.path.join(_HERE, "..", "..", "frontend")

from http.server import BaseHTTPRequestHandler  # noqa: E402
from urllib.parse import urlparse, parse_qs  # noqa: E402

import auth  # noqa: E402
import db  # noqa: E402

# Static files available when this handler runs from a normal web server.
_HTML, _JS = "text/html; charset=utf-8", "application/javascript; charset=utf-8"
_STATIC = {
    "/": ("index.html", _HTML),
    "/index.html": ("index.html", _HTML),
    "/app": ("app.html", _HTML),
    "/app.html": ("app.html", _HTML),
    "/login": ("login.html", _HTML),
    "/login.html": ("login.html", _HTML),
    "/account": ("account.html", _HTML),
    "/account.html": ("account.html", _HTML),
    "/common.js": ("common.js", _JS),
    "/home.js": ("home.js", _JS),
    "/app.js": ("app.js", _JS),
    "/auth.js": ("auth.js", _JS),
    "/account.js": ("account.js", _JS),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
_AUTH = ("/me", "/register", "/login", "/logout", "/saved", "/account",
         "/account/password", "/account/delete", "/forgot", "/reset")

_gs = None
_BUILD = "rewrite-root-3"


def _service():
    """Load the model engine when an API request needs it."""
    global _gs
    if _gs is None:
        import glimpse_service as gs
        _gs = gs
    return _gs


def _is_auth(p):
    return "/api/" in p + "/" and p.endswith(_AUTH)


def _json_object(body):
    try:
        data = json.loads(body or "{}")
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _saved_route(method, q, body, token):
    """Named saved values. GET ?dataset=, POST {dataset, name, values}, DELETE ?id=."""
    if method == "DELETE":
        try:
            return auth.delete_saved(token, int(q.get("id", [""])[0]))
        except ValueError:
            return 400, {"error": "'id' must be a number"}, {}
    if method == "POST":
        data = _json_object(body)
        if data is None:
            return 400, {"error": "invalid JSON body"}, {}
        ds = data.get("dataset")
    elif method == "GET":
        ds = q.get("dataset", [None])[0]
    else:
        return 405, {"error": "method not allowed"}, {}
    if ds not in _service().VALID:
        return 400, {"error": f"unknown dataset '{ds}'"}, {}
    if method == "GET":
        return auth.list_saved(token, ds)
    return auth.save_values(token, ds, data.get("name"), data.get("values"))


def _same_origin(headers):
    """Refuse state changes started by another site (the browser sends Origin)."""
    origin = headers.get("Origin")
    if not origin:
        return True
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
    return urlparse(origin).netloc == host


def _base_url(headers):
    """Where reset links point. A configured URL wins over request headers."""
    fixed = os.environ.get("APP_URL") or os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
    if fixed:
        return fixed.rstrip("/") if "://" in fixed else "https://" + fixed.rstrip("/")
    proto = headers.get("X-Forwarded-Proto") or "http"
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or "localhost"
    return f"{proto}://{host}"


def _client_ip(headers):
    fwd = headers.get("X-Forwarded-For", "")
    return (headers.get("X-Real-IP") or fwd.split(",")[0]).strip()


def _auth_route(method, p, q, body, headers):
    """Account endpoints. Returns (status, json, extra_headers)."""
    if not db.configured():
        return 503, {"error": "Accounts are not set up on this server: "
                              "set DATABASE_URL to a Postgres database."}, {}
    if method in ("POST", "DELETE") and not _same_origin(headers):
        return 403, {"error": "Cross-site request refused."}, {}
    token = auth.session_token(headers.get("Cookie"))
    secure = headers.get("X-Forwarded-Proto", "") == "https"
    if p.endswith("/saved"):
        return _saved_route(method, q, body, token)
    if method == "GET" and p.endswith("/me"):
        return 200, {"user": auth.current_user(token)}, {}
    if method == "GET" and p.endswith("/account"):
        return auth.account(token)
    if method != "POST":
        return 405, {"error": "method not allowed"}, {}
    if p.endswith("/logout"):
        return auth.logout(token, secure)
    data = _json_object(body)
    if data is None:
        return 400, {"error": "invalid JSON body"}, {}
    if p.endswith("/register"):
        return auth.register(data, secure)
    if p.endswith("/account/password"):
        return auth.change_password(token, data)
    if p.endswith("/account/delete"):
        return auth.delete_account(token, data, secure)
    if p.endswith("/forgot"):
        return auth.request_reset(data, _base_url(headers), _client_ip(headers))
    if p.endswith("/reset"):
        return auth.reset_password(data, secure)
    if p.endswith("/login"):
        return auth.login(data, secure, _client_ip(headers))
    return 404, {"error": "not found"}, {}


def _map_point(value):
    """A clicked map position [x, y], or None if it is not one."""
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and abs(v) < 1e6 for v in value):
        return None
    return [float(v) for v in value]


def route(method, path, query, body, headers=None):
    """Return an HTTP status and JSON response for an API request.

    Account endpoints also return a third item, extra response headers.
    """
    q = parse_qs(query or "")
    # Vercel rewrites /api/<route> to this function as ?__route=<route>.
    if "__route" in q:
        path = "/api/" + q.pop("__route")[0]
    p = path.rstrip("/")

    if method == "GET" and p.endswith("/health"):
        return 200, {"ok": True, "build": _BUILD}

    if _is_auth(p):
        return _auth_route(method, p, q, body, headers or {})

    gs = _service()

    if method == "GET" and p.endswith("/datasets"):
        return 200, {"datasets": gs.DATASETS}

    if method == "GET" and p.endswith("/scene"):
        ds = q.get("dataset", ["pima"])[0]
        if ds not in gs.VALID:
            return 400, {"error": f"unknown dataset '{ds}'"}
        try:
            return 200, gs.scene(ds, query_id=q.get("query", [None])[0])
        except Exception as exc:
            return 500, {"error": str(exc)}

    if method == "POST" and p.endswith("/scene"):
        try:
            data = json.loads(body or "{}")
        except Exception:
            return 400, {"error": "invalid JSON body"}
        ds = data.get("dataset", "pima")
        if ds not in gs.VALID:
            return 400, {"error": f"unknown dataset '{ds}'"}
        if "point" in data:                       # an empty spot clicked on the map
            point = _map_point(data["point"])
            if point is None:
                return 400, {"error": "'point' must be [x, y] map coordinates"}
            try:
                values, outside = gs.decode(ds, point)
                scene = gs.scene(ds, custom=values)
            except Exception as exc:
                return 500, {"error": str(exc)}
            scene["query"]["from_map"] = True
            scene["decoded"] = {"values": values, "outside": outside}
            return 200, scene
        custom = data.get("custom")
        if not isinstance(custom, dict):
            return 400, {"error": "'custom' must be a {feature: value} object"}
        clean = {}
        for k, v in custom.items():
            if v is None or v == "":
                clean[k] = None
            else:
                try:
                    clean[k] = float(v)
                except (TypeError, ValueError):
                    return 400, {"error": f"'{k}' is not a number: {v!r}"}
        try:
            return 200, gs.scene(ds, custom=clean)
        except Exception as exc:
            return 500, {"error": str(exc)}

    return 404, {"error": "not found"}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _reply_json(self, code, obj, extra=None):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj).encode("utf-8"), extra)

    def _reply(self, result):
        code, obj, *rest = result
        extra = dict(rest[0]) if rest else {}
        if rest:                                   # account data is never cached
            extra["Cache-Control"] = "no-store"
        self._reply_json(code, obj, extra)

    def _serve_static(self, path):
        fname, ctype = _STATIC[path]
        try:
            with open(os.path.join(_FRONTEND, fname), "rb") as fh:
                self._send(200, ctype, fh.read())
        except OSError:
            self._reply_json(404, {"error": "not found"})

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/")
        if u.path in _STATIC:
            self._serve_static(u.path)
            return
        if (p.endswith(("/datasets", "/scene", "/health")) or _is_auth(p)
                or "__route=" in u.query):
            self._reply(route("GET", u.path, u.query, None, self.headers))
            return
        self._serve_static("/")

    def do_DELETE(self):
        u = urlparse(self.path)
        self._reply(route("DELETE", u.path, u.query, None, self.headers))

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode("utf-8") if n else ""
        u = urlparse(self.path)
        self._reply(route("POST", u.path, u.query, body, self.headers))
