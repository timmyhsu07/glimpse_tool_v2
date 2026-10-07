import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class VercelConfigTests(unittest.TestCase):
    """One Python function serves the API and the frontend files."""

    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "vercel.json").read_text())

    def test_python_preset_sends_every_request_to_the_function(self):
        # The preset builds one function from pyproject's entrypoint and routes all
        # paths to it; the handler serves the API and frontend/ itself.
        self.assertEqual(self.config["framework"], "python")
        self.assertNotIn("outputDirectory", self.config)

    def test_function_bundles_the_backend_and_frontend(self):
        fn = self.config["functions"]["api/index.py"]
        for part in ("backend/api", "backend/engine", "frontend"):
            self.assertIn(part, fn["includeFiles"])

    def test_pyproject_entrypoint_matches(self):
        self.assertIn('entrypoint = "api.index:handler"',
                      (ROOT / "pyproject.toml").read_text())

    def test_bundled_paths_exist(self):
        for rel in ("api/index.py", "backend/api/index.py", "backend/engine/precomputed",
                    "frontend/index.html", "frontend/login.html"):
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_entry_point_exposes_the_backend_handler(self):
        entry = _load_entry()
        self.assertIs(entry.handler, entry._backend.handler)
        self.assertTrue(hasattr(entry.handler, "do_POST"))

    def test_rewritten_path_routes_like_the_original(self):
        route = _load_entry()._backend.route
        self.assertEqual(route("GET", "/api/index", "__route=health", None)[0], 200)
        self.assertEqual(route("GET", "/api/index", "__route=nope", None)[0], 404)


def _load_entry():
    spec = importlib.util.spec_from_file_location("index", ROOT / "api" / "index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main()
