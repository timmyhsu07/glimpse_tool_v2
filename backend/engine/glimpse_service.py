"""Load precomputed models for the serverless API."""
import os
import sys
import pickle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cf_core  # noqa: E402

EPS = 0.03
_PRE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precomputed")


def _ensure(dataset, eps):
    """Load a dataset's precomputed model and lens when available."""
    key = (dataset, round(float(eps), 6))
    if key in cf_core._MODELS:
        return
    path = os.path.join(_PRE, f"{dataset}_{round(float(eps), 6)}.pkl")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            blob = pickle.load(f)
        cf_core._MODELS[key] = blob["m"]
        cf_core._LENSES[key] = blob["lens"]


def scene(dataset, eps=EPS, query_id=None, custom=None):
    _ensure(dataset, eps)
    return cf_core.get_scene(dataset, eps=eps, query_id=query_id, custom=custom)


def decode(dataset, point, eps=EPS):
    _ensure(dataset, eps)
    return cf_core.decode_point(dataset, point, eps=eps)


DATASETS = cf_core.DATASETS
VALID = {d["key"] for d in DATASETS}
