"""Run GLIMPSE locally: the API plus the frontend, on one port."""
import os
import sys
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
from index import handler  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"GLIMPSE serving on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
