"""Research helpers on top of the app's engine.

The app in ``../backend/engine`` is the single source of the GLIMPSE maths. This module
re-exports it under the names the research code uses, and adds only what the
app does not need:

* ``fit_eclipse`` with fixed ``weights`` (the app's version always runs the
  auto rule) -- used by the tradeoff sweep and the variants;
* ``rash_ceiling`` (kappa_2);
* all seven datasets -- the app ships pima/heloc/cancer, the other four live
  in ``testing/datasets``;
* ``fit_glimpse(key)``, one call from dataset to model, ellipsoid and lens.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
from sklearn.model_selection import train_test_split

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "backend" / "engine"))

import counterfactuals as _cf            # noqa: E402
import data as _data                     # noqa: E402
import lenses as _lenses                 # noqa: E402

# ---- the app's maths, unchanged
LinearModel = _cf.LinearModel
RashomonEllipsoid = _cf.RashomonEllipsoid
train_logreg = _cf.train_logreg
sigmoid = _cf._sigmoid
aug = _cf._aug
disagreement = _lenses.disagreement
EclipseLens = _lenses.EclipseLens
select_weights = _lenses._select_weights
evaluate = _data.evaluate

EPS = 0.03          # the Rashomon tolerance the app uses


def build_S(X, w_vec, ell, missing_mask=None):
    """The four unit-trace interest matrices (spread, model, disagreement, imputation)."""
    return _lenses._build_S(X, w_vec, ell, missing_mask)


# ---- all seven datasets: the app's three, plus the extras in testing/datasets
LOADERS = dict(_data.LOADERS)
DATASET_CHOICES = list(_data.DATASET_CHOICES)
for _key, (_label, _loader) in _data.discover_custom(_HERE / "datasets").items():
    if _key not in LOADERS:
        LOADERS[_key] = _loader
        DATASET_CHOICES.append({"key": _key, "label": _label})


def fit_eclipse(X, y, w_vec, ell, missing_mask=None, weights=None,
                idx_tr=None, test_size=0.2):
    """Fit the ECLIPSE lens. ``weights=None`` runs the app's auto rule."""
    X = np.asarray(X, float)
    y = np.asarray(y, int)
    if idx_tr is None:
        idx_tr, _ = train_test_split(np.arange(len(X)), test_size=test_size,
                                     random_state=0, stratify=y)
    mask_tr = missing_mask[idx_tr] if missing_mask is not None else None
    if weights is None:
        weights = select_weights(X[idx_tr], y[idx_tr], w_vec, ell, mask_tr)
    lens = EclipseLens(weights).fit(X[idx_tr], w_vec, ell, mask_tr)
    lens.pin_orientation(X, y)
    names = ("spread", "model", "disagreement", "imputation")
    lens.extra = " / ".join(f"{n} {v:.2f}"
                            for n, v in zip(names, lens.weights_used) if v > 0.005)
    return lens


def rash_ceiling(X, ell):
    """kappa_2: the best disagreement-fidelity any plane could reach.

    alpha = eigenvalues of Sigma^(1/2) A Sigma^(1/2) with A the disagreement
    form; kappa_2 = sqrt(top-2 alpha^2 / sum alpha^2).
    """
    d = X.shape[1]
    Sig = np.cov(X.T)
    Qinv = ell.Q_inv_sqrt @ ell.Q_inv_sqrt
    A = Qinv[:d, :d]
    ev = np.linalg.eigvalsh(Sig)
    Sig_h = (np.linalg.eigh(Sig)[1] * np.clip(ev, 1e-12, None) ** 0.5) @ np.linalg.eigh(Sig)[1].T
    alpha = np.abs(np.linalg.eigvalsh(Sig_h @ A @ Sig_h))
    alpha = np.sort(alpha)[::-1]
    return float(np.sqrt(alpha[:2] @ alpha[:2] / (alpha @ alpha)))


@dataclass
class Glimpse:
    """Everything a lens needs to be fitted and scored."""
    data: object
    model: LinearModel
    ell: RashomonEllipsoid
    lens: object
    idx_tr: np.ndarray
    idx_te: np.ndarray

    @property
    def X(self):
        return np.asarray(self.data.X, float)

    @property
    def y(self):
        return np.asarray(self.data.y, int)

    @property
    def logit(self):
        return self.model.logit(self.X)

    @property
    def dis(self):
        return disagreement(self.ell, self.X)


def fit_glimpse(key, eps=EPS, lens="eclipse", test_size=0.2, random_state=0):
    """Data -> model -> Rashomon ellipsoid -> lens. ``lens``: 'eclipse' or None."""
    data = LOADERS[key]()
    X, y = np.asarray(data.X, float), np.asarray(data.y, int)
    idx_tr, idx_te = train_test_split(np.arange(len(X)), test_size=test_size,
                                      random_state=random_state, stratify=y)
    model = train_logreg(X[idx_tr], y[idx_tr])
    ell = RashomonEllipsoid(X[idx_tr], model.theta, eps=eps)
    if lens == "eclipse":
        L = fit_eclipse(X, y, model.w, ell, getattr(data, "missing_mask", None),
                        idx_tr=idx_tr)
    else:
        L = None
    return Glimpse(data, model, ell, L, idx_tr, idx_te)


if __name__ == "__main__":
    print(f"{'dataset':10s} {'n':>6s} {'d':>4s} {'acc':>6s} {'auc':>6s} "
          f"{'kappa2':>7s}  weights")
    for choice in DATASET_CHOICES:
        k = choice["key"]
        g = fit_glimpse(k)
        acc, auc = evaluate(g.model, g.X[g.idx_te], g.y[g.idx_te])
        print(f"{k:10s} {g.data.n:6d} {g.data.d:4d} {acc:6.3f} {auc:6.3f} "
              f"{rash_ceiling(g.X[g.idx_tr], g.ell):7.3f}  {g.lens.extra}")
