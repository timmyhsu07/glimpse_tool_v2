"""Fast predictions for entered people, and save renaming / listing."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import index  # noqa: E402
from test_auth import AuthTests, call, session_cookie  # noqa: E402


def people(body):
    code, obj, *_ = index.route("POST", "/api/people", "", json.dumps(body), {})
    return code, obj


class PeopleTests(unittest.TestCase):
    def test_matches_the_scene_verdict(self):
        custom = {"Glucose": 150, "BMI": 31.5}
        code, out = people({"dataset": "pima", "people": [custom, {}]})
        self.assertEqual(code, 200)
        _, scene = index.route("POST", "/api/scene", "",
                               json.dumps({"dataset": "pima", "custom": custom}), {})
        me = out["people"][0]
        for key in ("linear", "mlp"):
            m = scene["panels"][key]["metrics"]
            self.assertAlmostEqual(me[key]["p"], m["p_bad_erm_x0"], places=3)
            self.assertAlmostEqual(me[key]["lo"], m["p_bad_best_x0"], places=3)
            self.assertAlmostEqual(me[key]["hi"], m["p_bad_worst_x0"], places=3)
        json.dumps(out)                                        # plain JSON types only
        self.assertAlmostEqual(me["x"], scene["query"]["x"], places=6)
        self.assertEqual(me["provided"], ["Glucose", "BMI"])
        self.assertEqual(out["people"][1]["provided"], [])          # all typical values
        self.assertEqual(len(out["importance"]), len(out["features"]))

    def test_rejects_bad_input(self):
        self.assertEqual(people({"dataset": "nope", "people": [{}]})[0], 400)
        self.assertEqual(people({"dataset": "pima", "people": []})[0], 400)
        self.assertEqual(people({"dataset": "pima", "people": [{}] * 61})[0], 400)
        self.assertEqual(people({"dataset": "pima", "people": [{"Glucose": "nan"}]})[0], 400)
        self.assertEqual(people({"dataset": "pima", "people": [{"Glucose": True}]})[0], 400)

    def test_scene_has_quick_and_safe_changes(self):
        _, scene = index.route("GET", "/api/scene", "dataset=pima", None, {})
        row = scene["deltas"][0]
        for key in ("linear", "mlp", "linear_quick", "mlp_quick"):
            self.assertIn("cf_real", row[key])


class SaveListTests(AuthTests):
    def test_rename_and_list_every_topic(self):
        ck = session_cookie(self.register()[2])
        ids = [call("POST", "/api/saved", {"dataset": ds, "name": n, "values": {"x": 1}},
                    cookie=ck)[1]["saved"]["id"] for ds, n in (("pima", "a"), ("pima", "b"),
                                                               ("heloc", "a"))]
        code, obj, _ = call("GET", "/api/saved", cookie=ck)
        self.assertEqual(code, 200)
        self.assertEqual(sorted(e["dataset"] for e in obj["saved"]), ["heloc", "pima", "pima"])
        self.assertEqual(call("POST", "/api/saved/rename", {"id": ids[0], "name": "b"},
                              cookie=ck)[0], 409)
        code, obj, _ = call("POST", "/api/saved/rename", {"id": ids[0], "name": "  May  "},
                            cookie=ck)
        self.assertEqual((code, obj["name"]), (200, "May"))
        other = session_cookie(self.register(email="eve@example.com")[2])
        self.assertEqual(call("POST", "/api/saved/rename", {"id": ids[0], "name": "x"},
                              cookie=other)[0], 404)


del AuthTests



class SafeChangeTests(unittest.TestCase):
    """A "safe change" is only offered when every good model is convinced."""

    def test_safe_ok_matches_the_worst_case_margin(self):
        for ds in ("pima", "heloc", "cancer"):
            _, scene = index.route("GET", "/api/scene", f"dataset={ds}", None, {})
            for key in ("linear", "mlp"):
                m = scene["panels"][key]["metrics"]
                self.assertEqual(m["safe_ok"], m["robust_margin_cf"] >= 0.1 - 1e-3, (ds, key))

    def test_suggested_values_stay_within_what_the_data_has_seen(self):
        for ds in ("pima", "heloc", "cancer"):
            _, out = people({"dataset": ds, "people": [{}]})
            feats = {f["name"]: f for f in out["features"]}
            _, scene = index.route("GET", "/api/scene", f"dataset={ds}", None, {})
            for r in scene["deltas"]:
                f = feats[r["name"]]
                lo, hi = min(f["min"], r["x0_real"]), max(f["max"], r["x0_real"])
                for key in ("linear", "mlp", "linear_quick", "mlp_quick"):
                    v = r[key]["cf_real"]
                    self.assertTrue(lo - 1e-3 <= v <= hi + 1e-3, (ds, r["name"], key, v))

    def test_every_model_says_whether_its_changes_work(self):
        _, scene = index.route("GET", "/api/scene", "dataset=cancer", None, {})
        for key in ("linear", "mlp"):
            m = scene["panels"][key]["metrics"]
            self.assertIn("quick_ok", m)
            self.assertTrue(m["quick_ok"])

    def test_credit_has_no_safe_change_with_the_locked_values(self):
        _, scene = index.route("GET", "/api/scene", "dataset=heloc", None, {})
        self.assertFalse(scene["panels"]["linear"]["metrics"]["safe_ok"])
        _, scene = index.route("GET", "/api/scene", "dataset=pima", None, {})
        self.assertTrue(scene["panels"]["linear"]["metrics"]["safe_ok"])


if __name__ == "__main__":
    unittest.main()
