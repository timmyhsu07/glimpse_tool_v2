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


if __name__ == "__main__":
    unittest.main()
