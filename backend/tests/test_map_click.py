import json
import math
import sys
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
warnings.filterwarnings("ignore")

import index  # noqa: E402


def post_scene(body):
    return index.route("POST", "/api/scene", "", json.dumps(body))


class MapClickTests(unittest.TestCase):
    """Clicking an empty spot decodes it into a person through the lens inverse."""

    @classmethod
    def setUpClass(cls):
        code, cls.base = index.route("GET", "/api/scene", "dataset=pima", None)
        assert code == 200

    def centre(self):
        b = self.base["bounds"]
        return [(b["x"][0] + b["x"][1]) / 2, (b["y"][0] + b["y"][1]) / 2]

    def test_click_decodes_to_a_full_person_near_the_click(self):
        point = self.centre()
        code, scene = post_scene({"dataset": "pima", "point": point})
        self.assertEqual(code, 200)
        q = scene["query"]
        self.assertTrue(q["custom"] and q["from_map"])
        names = {f["name"] for f in scene["features"]}
        self.assertEqual(set(scene["decoded"]["values"]), names)
        span = self.base["bounds"]["x"][1] - self.base["bounds"]["x"][0]
        self.assertLess(math.hypot(q["x"] - point[0], q["y"] - point[1]), 0.03 * span)

    def test_person_lands_exactly_where_clicked(self):
        b = self.base["bounds"]
        span = b["x"][1] - b["x"][0]
        for fx, fy in [(0.5, 0.5), (0.1, 0.9), (0.83, 0.27), (0.37, 0.61)]:
            point = [b["x"][0] + fx * span, b["y"][0] + fy * (b["y"][1] - b["y"][0])]
            _, scene = post_scene({"dataset": "pima", "point": point})
            q = scene["query"]
            # a 600-pixel map is ~1/600 of the span per pixel: demand far better
            self.assertLess(math.hypot(q["x"] - point[0], q["y"] - point[1]),
                            span / 600 / 10, (fx, fy))

    def test_far_spot_reports_values_outside_the_data(self):
        b = self.base["bounds"]
        far = [b["x"][1] + 3 * (b["x"][1] - b["x"][0]), b["y"][1]]
        _, scene = post_scene({"dataset": "pima", "point": far})
        self.assertGreater(len(scene["decoded"]["outside"]), 0)

    def test_rejects_bad_points(self):
        for point in ([1], [1, "x"], "1,2", [1, float("nan")], [1, 2, 3], [True, 1]):
            code, _ = post_scene({"dataset": "pima", "point": point})
            self.assertEqual(code, 400, point)


class AroundViewTests(unittest.TestCase):
    """"Around this person": each model's map is a slice through the person that
    holds that model's suggested changes."""

    @classmethod
    def setUpClass(cls):
        code, cls.scene = index.route("GET", "/api/scene", "dataset=pima&view=around", None)
        assert code == 200

    def test_shared_map_is_the_default(self):
        _, scene = index.route("GET", "/api/scene", "dataset=pima", None)
        self.assertEqual(scene["view"], "everyone")
        self.assertNotIn("plane", scene["panels"]["linear"])

    def test_person_in_the_middle_and_changes_shown_whole(self):
        s = self.scene
        self.assertEqual(s["view"], "around")
        self.assertEqual((s["query"]["x"], s["query"]["y"]), (0.0, 0.0))
        for which, p in s["panels"].items():
            self.assertEqual(len(p["xy"]), len(s["points"]))
            self.assertEqual(p["metrics"]["quick_on_map"], 1.0, which)
            self.assertEqual(p["metrics"]["safe_on_map"], 1.0, which)
            for kind in ("standard", "ellice"):      # arrow length = true size of the change
                c = p["cfs"][kind]
                self.assertAlmostEqual(math.hypot(c["x"], c["y"]), c["distance"], places=3)

    def test_clicking_the_quick_change_gives_that_change(self):
        for which in ("linear", "mlp"):
            p = self.scene["panels"][which]
            c = p["cfs"]["standard"]
            code, s2 = post_scene({"dataset": "pima", "view": "around", "point": [c["x"], c["y"]],
                                   "plane": p["plane"]})
            self.assertEqual(code, 200)
            self.assertTrue(s2["query"]["from_map"])
            chance = s2["panels"][which]["metrics"]["p_bad_erm_x0"]
            self.assertLess(chance, 0.5, which)                   # just past the model's line
            if which == "linear":
                self.assertAlmostEqual(chance, 1 / (1 + math.exp(0.1)), places=2)

    def test_rejects_bad_views_and_planes(self):
        self.assertEqual(index.route("GET", "/api/scene", "dataset=pima&view=sideways", None)[0], 400)
        self.assertEqual(post_scene({"dataset": "pima", "view": "sideways", "custom": {}})[0], 400)
        p = self.scene["panels"]["linear"]["plane"]
        o, a = p["origin"], p["axes"]
        for plane in ("x", {"origin": o}, {"origin": o[:-1], "axes": a},
                      {"origin": o, "axes": [a[0]]}, {"origin": [float("nan")] * len(o), "axes": a},
                      {"origin": o[:-1], "axes": [a[0][:-1], a[1][:-1]]}):
            code, _ = post_scene({"dataset": "pima", "view": "around", "point": [0, 0],
                                  "plane": plane})
            self.assertEqual(code, 400, plane)


if __name__ == "__main__":
    unittest.main()
