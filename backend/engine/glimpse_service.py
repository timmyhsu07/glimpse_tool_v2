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
        # A saved map of another kind is ignored; the right one is fitted on use.
        if getattr(blob["lens"], "key", "eclipse") == cf_core.MAP_LENS:
            cf_core._LENSES[key] = blob["lens"]


def scene(dataset, eps=EPS, query_id=None, custom=None, constraints=None, view="everyone"):
    _ensure(dataset, eps)
    return cf_core.get_scene(dataset, eps=eps, query_id=query_id, custom=custom,
                             constraints=constraints, view=view)


def people(dataset, customs, eps=EPS):
    _ensure(dataset, eps)
    return cf_core.people(dataset, customs, eps=eps)


def decode(dataset, point, eps=EPS, plane=None):
    _ensure(dataset, eps)
    return cf_core.decode_point(dataset, point, eps=eps, plane=plane)


DATASETS = cf_core.DATASETS
VIEWS = cf_core.VIEWS
VALID = {d["key"] for d in DATASETS}
