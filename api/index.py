"""Vercel entry point. The site and API live in backend/api/index.py."""
import importlib.util
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "backend", "api", "index.py")
# Loaded under its own name: this file is also called "index".
_spec = importlib.util.spec_from_file_location("glimpse_backend", _PATH)
_backend = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backend)

handler = _backend.handler
