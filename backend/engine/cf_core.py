"""Build the linear and MLP counterfactual views as JSON."""
import sys
import numpy as np
from contourpy import contour_generator


import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import LOADERS, DATASET_CHOICES, evaluate
from counterfactuals import train_logreg, RashomonEllipsoid, _sigmoid
from lenses import fit_eclipse
from mlp_backend import MLPBackend

N_SCATTER = 600
N_FAN = 40
FIELD_RES = 90
CONTOUR_RES = 400
FAN_RES = 150
MLP_HIDDEN = 16

TARGET_CLASS = 0
MARGIN = 0.10

# Features held fixed during the counterfactual search.
IMMUTABLE = {
    "pima": {"Pregnancies", "Age", "DiabetesPedigreeFunction"},
    "heloc": {"MSinceOldestTradeOpen", "AverageMInFile",
              "ExternalRiskEstimate"},
    "cancer": set(),
}

_MODELS = {}
_LENSES = {}
_VIEWS = {}

DATASETS = DATASET_CHOICES


def _models(dataset_key, eps):
    key = (dataset_key, round(float(eps), 6))
    if key in _MODELS:
        return _MODELS[key]
    data = LOADERS[dataset_key]()

    lin = train_logreg(data.X, data.y)
    lin_ell = RashomonEllipsoid(data.X, lin.theta, eps=eps)
    lin_acc, lin_auc = evaluate(lin, data.X, data.y)

    mlp = MLPBackend(data.X, data.y, eps=eps, hidden=MLP_HIDDEN)
    mlp_acc, mlp_auc = evaluate(mlp, data.X, data.y)

    immutable = IMMUTABLE.get(dataset_key, set()) & set(data.feature_names)
    features = []
    for f in data.feature_meta():
        f = dict(f)
        f["immutable"] = f["name"] in immutable
        features.append(f)

    fixed = np.array([n in immutable for n in data.feature_names], dtype=bool)

    m = dict(data=data, lin=lin, lin_ell=lin_ell, lin_acc=lin_acc,
             lin_auc=lin_auc, mlp=mlp, mlp_acc=mlp_acc, mlp_auc=mlp_auc,
             features=features, immutable=immutable, fixed=fixed,
             median_std=np.median(data.X, axis=0).astype(float))
    _MODELS[key] = m
    return m


def _lens(dataset_key, eps):
    key = (dataset_key, round(float(eps), 6))
    if key not in _LENSES:
        m = _models(dataset_key, eps)
        _LENSES[key] = fit_eclipse(m["data"], m["lin"], m["lin_ell"])
    return _LENSES[key]


def _setup(dataset_key, eps):
    key = (dataset_key, round(float(eps), 6))
    if key in _VIEWS:
        return _VIEWS[key]

    m = _models(dataset_key, eps)
    lens = _lens(dataset_key, eps)
    data, lin, lin_ell, mlp = m["data"], m["lin"], m["lin_ell"], m["mlp"]

    emb = lens.embed(data.X)
    lo, hi = emb.min(0), emb.max(0)
    pad = 0.08 * (hi - lo)
    lo, hi = lo - pad, hi + pad
    bounds = (lo, hi)

    GXc, GYc, Xc_hi = lens.grid((lo[0], hi[0]), (lo[1], hi[1]), CONTOUR_RES)
    GXf, GYf, Xf_hi = lens.grid((lo[0], hi[0]), (lo[1], hi[1]), FAN_RES)
    H_grid = mlp.embed_h(Xc_hi)
    H_fan = mlp.embed_h(Xf_hi)
    grids = dict(GXc=GXc, GYc=GYc, Xc_hi=Xc_hi, H_grid=H_grid,
                 GXf=GXf, GYf=GYf, Xf_hi=Xf_hi, H_fan=H_fan)

    gx = np.linspace(lo[0], hi[0], FIELD_RES)
    gy = np.linspace(lo[1], hi[1], FIELD_RES)
    GX, GY = np.meshgrid(gx, gy)
    Xfield_hi = lens.invert(np.column_stack([GX.ravel(), GY.ravel()]))
    lin_field = _sigmoid(lin.logit(Xfield_hi)).reshape(FIELD_RES, FIELD_RES)
    mlp_field = mlp.proba(Xfield_hi).reshape(FIELD_RES, FIELD_RES)
    field_axes = dict(x=gx.tolist(), y=gy.tolist())

    if lens.is_linear:
        lin_boundary = [ln for ln in [_theta_line(lens, lin.theta, bounds)]
                        if ln is not None]
        lin_fan = [ln for th in lin_ell.sample_models(N_FAN, random_state=1)
                   if (ln := _theta_line(lens, th, bounds)) is not None]
    else:
        lin_boundary = _contour_lines(GXc, GYc, Xc_hi, lin.theta)
        lin_fan = []
        for th in lin_ell.sample_models(N_FAN, random_state=1):
            lin_fan.extend(_contour_lines(GXf, GYf, Xf_hi, th))

    mlp_boundary = _contour_lines(GXc, GYc, H_grid, mlp.theta)
    mlp_fan = []
    for th in mlp.ell.sample_models(N_FAN, random_state=1):
        mlp_fan.extend(_contour_lines(GXf, GYf, H_fan, th))

    rng = np.random.default_rng(0)
    n = data.n
    scatter_idx = (np.arange(n) if n <= N_SCATTER
                   else rng.choice(n, N_SCATTER, replace=False))

    setup = dict(
        **m, lens=lens, emb=emb, bounds=bounds, eps=float(eps),
        grids=grids, field_axes=field_axes,
        lin_field=lin_field, mlp_field=mlp_field,
        lin_boundary=lin_boundary, lin_fan=lin_fan,
        mlp_boundary=mlp_boundary, mlp_fan=mlp_fan,
        scatter_idx=scatter_idx,
    )
    _VIEWS[key] = setup
    return setup


def _theta_line(lens, theta, bounds):
    """Return the clipped 2D boundary for a linear lens."""
    a, c0 = lens.linear_logit_coeffs(theta)
    return _line_in_box(a, c0, *bounds)


def _line_in_box(w, b, lo, hi):
    """Segment of {w0*x + w1*y + b = 0} inside the box [lo, hi]."""
    a1, a2, c = float(w[0]), float(w[1]), float(b)
    x0, y0, x1, y1 = float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])
    pts = []
    for x in (x0, x1):
        if abs(a2) > 1e-12:
            y = -(c + a1 * x) / a2
            if y0 - 1e-9 <= y <= y1 + 1e-9:
                pts.append((x, y))
    for y in (y0, y1):
        if abs(a1) > 1e-12:
            x = -(c + a2 * y) / a1
            if x0 - 1e-9 <= x <= x1 + 1e-9:
                pts.append((x, y))
    uniq = []
    for p in pts:
        if all(abs(p[0] - q[0]) + abs(p[1] - q[1]) > 1e-6 for q in uniq):
            uniq.append(p)
    if len(uniq) < 2:
        return None
    return {"x": [uniq[0][0], uniq[1][0]], "y": [uniq[0][1], uniq[1][1]]}


def _contour_lines(GX, GY, F_grid, theta, level=0.0, max_pts=350):
    """Return contour lines for a model evaluated on a decoded grid."""
    Z = (F_grid @ theta[:-1] + theta[-1]).reshape(GX.shape)
    cg = contour_generator(GX, GY, Z)
    lines = []
    for seg in cg.lines(level):
        step = max(1, len(seg) // max_pts)
        seg = seg[::step]
        lines.append({"x": [float(v) for v in seg[:, 0]],
                      "y": [float(v) for v in seg[:, 1]]})
    return lines


def _dist_to_lines(pt, lines):
    """2D distance from a point to a set of polylines (segment-exact)."""
    best = np.inf
    p = np.asarray(pt, float)
    for ln in lines:
        v = np.column_stack([ln["x"], ln["y"]])
        if len(v) == 1:
            best = min(best, float(np.linalg.norm(v[0] - p)))
            continue
        a, b = v[:-1], v[1:]
        ab = b - a
        t = np.clip(np.einsum("ij,ij->i", p - a, ab) /
                    np.maximum((ab ** 2).sum(1), 1e-18), 0.0, 1.0)
        proj = a + t[:, None] * ab
        best = min(best, float(np.linalg.norm(proj - p, axis=1).min()))
    return best


def _pick_query(setup):
    """Choose a positive example near the fitted boundary."""
    logit = setup["lin"].logit(setup["data"].X)
    cand = np.where((logit > 0.3) & (logit < 2.2))[0]
    if len(cand) == 0:
        return int(np.argmax(logit))
    return int(cand[np.argmin(np.abs(logit[cand] - 1.0))])


def _custom_x0(setup, custom):
    """Standardize entered values and fill blanks with dataset medians."""
    data = setup["data"]
    sc = data.scaler
    x0 = setup["median_std"].copy()
    provided = np.zeros(data.d, dtype=bool)
    for j, name in enumerate(data.feature_names):
        v = custom.get(name)
        if v is None or v == "":
            continue
        x0[j] = (float(v) - float(sc.mean_[j])) / float(sc.scale_[j])
        provided[j] = True
    return x0, provided


def decode_point(dataset_key, point, eps=0.03):
    """The person the map places at a 2-D position, in real units.

    ECLIPSE is linear with orthonormal axes, so this is its exact inverse and the
    person lands where the click was. Values keep six significant digits (well
    under a pixel, even for small-scale features), so whole-number features can
    come back fractional. Also returns the features that fall outside the
    observed data.
    """
    setup = _setup(dataset_key, float(np.clip(eps, 0.005, 0.2)))
    data = setup["data"]
    x_std = setup["lens"].invert(np.asarray(point, float).reshape(1, 2))[0]
    real = data.to_real(x_std)
    values, outside = {}, []
    for f, v in zip(setup["features"], real):
        v = float(f"{v:.6g}")
        values[f["name"]] = v
        if not f["min"] <= v <= f["max"]:
            outside.append(f["label"])
    return values, outside


def _percentile(col, v):
    return float(np.mean(col <= v) * 100.0)


def _panel(setup, which, x0):
    """Build one model panel for a query."""
    lens, bounds = setup["lens"], setup["bounds"]
    g = setup["grids"]
    fixed = setup["fixed"]

    if which == "linear":
        model, ell = setup["lin"], setup["lin_ell"]
        cf_std = ell.standard_cf(x0, TARGET_CLASS, margin=MARGIN, fixed=fixed)
        cf_rob = ell.robust_cf(x0, TARGET_CLASS, margin=MARGIN, fixed=fixed)
        theta_w = ell.worst_model(cf_rob, TARGET_CLASS)
        if lens.is_linear:
            worst_lines = [ln for ln in [_theta_line(lens, theta_w, bounds)]
                           if ln is not None]
        else:
            worst_lines = _contour_lines(g["GXc"], g["GYc"], g["Xc_hi"], theta_w)
        logit_x0 = float(model.logit(x0)[0])
        logit_cf = float(model.logit(cf_rob)[0])
        rob_x0 = float(ell.robust_logit(x0, TARGET_CLASS)[0])
        rob_cf = float(ell.robust_logit(cf_rob, TARGET_CLASS)[0])
    else:
        mlp = setup["mlp"]
        cf_std = mlp.standard_cf(x0, TARGET_CLASS, margin=MARGIN, fixed=fixed)
        cf_rob = mlp.robust_cf(x0, TARGET_CLASS, margin=MARGIN, fixed=fixed)
        theta_w = mlp.worst_model(cf_rob, TARGET_CLASS)
        worst_lines = _contour_lines(g["GXc"], g["GYc"], g["H_grid"], theta_w)
        logit_x0 = float(mlp.logit(x0[None, :])[0])
        logit_cf = float(mlp.logit(cf_rob[None, :])[0])
        rob_x0 = float(mlp.robust_logit(x0[None, :], TARGET_CLASS)[0])
        rob_cf = float(mlp.robust_logit(cf_rob[None, :], TARGET_CLASS)[0])

    std_2d = lens.embed(cf_std)[0]
    rob_2d = lens.embed(cf_rob)[0]

    boundary = setup[f"{'lin' if which == 'linear' else 'mlp'}_boundary"]
    d_erm = _dist_to_lines(rob_2d, boundary)
    d_worst = _dist_to_lines(rob_2d, worst_lines) if worst_lines else None

    pen = max(-(logit_x0 + rob_x0), 0.0)
    metrics = {
        "pred_bad": bool(_sigmoid(logit_x0) >= 0.5),
        "p_bad_erm_x0": _sigmoid(logit_x0),
        "p_bad_best_x0": _sigmoid(logit_x0 - pen),
        "p_bad_worst_x0": _sigmoid(logit_x0 + pen),
        "p_bad_erm_cf": _sigmoid(logit_cf),
        "p_bad_worst_cf": _sigmoid(-rob_cf),
        "robust_margin_x0": rob_x0,
        "robust_margin_cf": rob_cf,
        "cost_std": float(np.linalg.norm(cf_std - x0)),
        "cost_rob": float(np.linalg.norm(cf_rob - x0)),
        "already_robust": bool(rob_x0 >= 0),
        "d2_cf_to_erm": d_erm,
        "d2_cf_to_worst": d_worst,
        "worst_closer": bool(d_worst is not None and d_worst <= d_erm + 1e-9),
    }
    metrics = {k: (round(float(v), 4)
                   if isinstance(v, (float, np.floating, np.ndarray)) else v)
               for k, v in metrics.items()}

    return {
        "kind": which,
        "acc": setup[f"{'lin' if which == 'linear' else 'mlp'}_acc"],
        "auc": setup[f"{'lin' if which == 'linear' else 'mlp'}_auc"],
        "field": {"z": setup[f"{'lin' if which == 'linear' else 'mlp'}_field"].tolist(),
                  **setup["field_axes"]},
        "boundary": boundary,
        "fan": setup[f"{'lin' if which == 'linear' else 'mlp'}_fan"],
        "worst": worst_lines,
        "cfs": {"standard": {"x": float(std_2d[0]), "y": float(std_2d[1]),
                             "distance": round(float(np.linalg.norm(cf_std - x0)), 3)},
                "ellice":   {"x": float(rob_2d[0]), "y": float(rob_2d[1]),
                             "distance": round(float(np.linalg.norm(cf_rob - x0)), 3)}},
        "metrics": metrics,
        "_cf_rob_full": cf_rob,
        "_cf_std_full": cf_std,
    }


def _feature_deltas(setup, x0, panels):
    """Return per-feature changes for each robust counterfactual."""
    data = setup["data"]
    sc = data.scaler
    meta = {f["name"]: f for f in data.feature_meta()}
    out = []
    for j, name in enumerate(data.feature_names):
        fm = meta[name]
        x0r = float(sc.mean_[j] + sc.scale_[j] * x0[j])
        row = {
            "name": name,
            "label": fm["label"], "unit": fm["unit"], "desc": fm["desc"],
            "integer": fm["integer"],
            "group": fm.get("group", ""),
            "group_label": fm.get("group_label", ""),
            "value_label": fm.get("value_label", ""),
            "immutable": name in setup["immutable"],
            "missing": False,
            "x0_real": x0r,
            "pct_x0": _percentile(data.X[:, j], x0[j]),
        }
        for key, panel in panels.items():
            cf = panel["_cf_rob_full"]
            d_std = float(cf[j] - x0[j])
            row[key] = {
                "delta_std": round(d_std, 4),
                "delta_real": round(d_std * float(sc.scale_[j]), 4),
                "cf_real": round(float(sc.mean_[j] + sc.scale_[j] * cf[j]), 4),
                "pct_cf": round(_percentile(data.X[:, j], float(cf[j])), 1),
            }
        out.append(row)
    return out


def get_scene(dataset_key, eps=0.03, query_id=None, custom=None):
    """Return the JSON scene for a dataset row or entered values."""
    eps = float(np.clip(eps, 0.005, 0.2))
    setup = _setup(dataset_key, eps)
    data, emb, lens = setup["data"], setup["emb"], setup["lens"]

    if custom is not None:
        x0, provided = _custom_x0(setup, custom)
        x0_2d = lens.embed(x0)[0]
        pred = int(_sigmoid(float(setup["lin"].logit(x0)[0])) > 0.5)
        query = {"id": None, "custom": True,
                 "x": float(x0_2d[0]), "y": float(x0_2d[1]), "outcome": pred}
    else:
        if query_id is None or not (0 <= int(query_id) < data.n):
            query_id = _pick_query(setup)
        query_id = int(query_id)
        x0 = data.X[query_id].astype(float)
        x0_2d = emb[query_id]
        query = {"id": query_id, "custom": False,
                 "x": float(x0_2d[0]), "y": float(x0_2d[1]),
                 "outcome": int(data.y[query_id])}

    panels = {"linear": _panel(setup, "linear", x0),
              "mlp": _panel(setup, "mlp", x0)}

    deltas = _feature_deltas(setup, x0, panels)
    for j, row in enumerate(deltas):
        row["missing"] = (bool(not provided[j]) if custom is not None
                          else bool(data.missing_mask[query["id"], j]))
    for p in panels.values():
        del p["_cf_rob_full"], p["_cf_std_full"]

    idx = setup["scatter_idx"]
    pts_payload = [{"id": int(i), "x": float(emb[i, 0]), "y": float(emb[i, 1]),
                    "outcome": int(data.y[i])}
                   for i in idx]

    lo, hi = setup["bounds"]
    return {
        "dataset": data.name,
        "class_names": list(data.class_names),
        "eps": eps,
        "lens": {"key": lens.key, "label": lens.label,
                 "is_linear": bool(lens.is_linear),
                 "extra": lens.extra, "blurb": lens.blurb,
                 "quality": lens.quality},
        "bounds": {"x": [float(lo[0]), float(hi[0])],
                   "y": [float(lo[1]), float(hi[1])]},
        "points": pts_payload,
        "query": query,
        "panels": panels,
        "deltas": deltas,
        "features": setup["features"],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="smoke-test scenes offline")
    ap.add_argument("--datasets", nargs="*",
                    default=[d["key"] for d in DATASETS])
    args = ap.parse_args()

    for dkey in args.datasets:
        s = get_scene(dkey, eps=0.03)
        q = s["lens"]["quality"]
        print(f"{s['dataset']:14s} {s['lens']['extra']}")
        print(f"    lens quality: recon={q['recon']:.3f} "
              f"trust={q['trust']:.3f} rt={q['rt']:.3f}")
        for name, p in s["panels"].items():
            m = p["metrics"]
            print(f"    {name:6s} acc={p['acc']:.3f} auc={p['auc']:.3f}  "
                  f"cost std={m['cost_std']:.3f} rob={m['cost_rob']:.3f}  "
                  f"margin(cf)={m['robust_margin_cf']:+.3f}  "
                  f"worst_closer={m['worst_closer']}")
        feats = s["features"]
        custom = {feats[0]["name"]: feats[0]["max"]}
        sc = get_scene(dkey, eps=0.03, custom=custom)
        mc = sc["panels"]["linear"]["metrics"]
        print(f"    custom person: P(bad)={mc['p_bad_erm_x0']:.2f} "
              f"cost rob={mc['cost_rob']:.3f} "
              f"imputed={sum(r['missing'] for r in sc['deltas'])}/{len(feats)}")
