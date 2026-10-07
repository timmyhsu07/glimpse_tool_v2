"""How we score a 2-D map.

Two families, deliberately kept apart.

READOUT metrics work for EVERY method, invertible or not.  They ask: if all
you had was the picture, how much could you read off it?  They are the only
fair way to put t-SNE and PCA in the same table.

INVERSE metrics only exist for methods with a decoder.  They ask: when the
user clicks a spot on the map and GLIMPSE turns it back into a person, is
that person faithful?  A method scoring NaN here cannot power GLIMPSE's
counterfactual panel at all -- that is a finding, not a missing value.
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.manifold import trustworthiness
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.neighbors import KNeighborsRegressor

from lab import disagreement

TRUST_SAMPLE = 800          # trustworthiness is O(n^2)
KNN_K = 15


def _sub(n, cap, seed=0):
    if n <= cap:
        return np.arange(n)
    return np.sort(np.random.default_rng(seed).choice(n, cap, replace=False))


def _readout(Z, target, k=KNN_K):
    """Spearman between the true value and an out-of-fold kNN read off the map.

    Z is left in each method's own units on purpose: uniform rescaling does
    not change kNN neighbourhoods, and rescaling the axes separately would
    destroy the geometry the user actually sees.
    """
    k = min(k, max(2, len(Z) - 1))
    pred = cross_val_predict(KNeighborsRegressor(n_neighbors=k), Z, target, cv=5)
    return float(spearmanr(target, pred).statistic)


def _sep2d(Z, y):
    """3-fold logistic AUC in the plane: how separable the classes look."""
    from sklearn.metrics import roc_auc_score
    cv = StratifiedKFold(3, shuffle=True, random_state=0)
    p = cross_val_predict(LogisticRegression(max_iter=2000), Z, y, cv=cv,
                          method="predict_proba")[:, 1]
    return float(roc_auc_score(y, p))


def evaluate_projection(proj, X, y, model, ell, seed=0):
    """Score one fitted projection on one evaluation set.

    Returns a flat dict.  NaN means 'this method structurally cannot do this',
    never 'we failed to measure it'.
    """
    X = np.asarray(X, float)
    y = np.asarray(y, int)
    out = {"method": proj.name, **proj.caps.as_dict(),
           "fit_s": round(getattr(proj, "fit_seconds", np.nan), 3)}

    try:
        Z = proj.embed(X)
    except NotImplementedError:
        # t-SNE on a held-out set: no map exists.  Record the refusal.
        out.update({m: np.nan for m in
                    ("trust", "sep2d", "score_read", "rash_read",
                     "recon", "rt", "score_inv", "rash_inv")})
        out["note"] = "no out-of-sample embedding"
        return out

    logit = model.logit(X)
    dis = disagreement(ell, X)

    # ---- readout metrics (every method) ----
    s = _sub(len(X), TRUST_SAMPLE, seed)
    out["trust"] = round(float(trustworthiness(X[s], Z[s], n_neighbors=10)), 4)
    out["sep2d"] = round(_sep2d(Z[s], y[s]), 4)
    out["score_read"] = round(_readout(Z[s], logit[s]), 4)
    out["rash_read"] = round(_readout(Z[s], dis[s]), 4)

    # ---- inverse metrics (decoder only) ----
    Xh = proj.invert(Z)
    if Xh is None:
        out.update({m: np.nan for m in ("recon", "rt", "score_inv", "rash_inv")})
        out["note"] = "no inverse"
        return out

    Z2 = proj.embed(Xh)
    spread = max(float(np.linalg.norm(Z - Z.mean(0), axis=1).mean()), 1e-12)
    out["recon"] = round(float(np.abs(Xh - X).mean()), 4)
    out["rt"] = round(float(np.linalg.norm(Z2 - Z, axis=1).mean() / spread), 4)
    out["score_inv"] = round(float(spearmanr(logit, model.logit(Xh)).statistic), 4)
    out["rash_inv"] = round(float(spearmanr(dis, disagreement(ell, Xh)).statistic), 4)
    out["note"] = ""
    return out


METRIC_HELP = {
    "trust": "trustworthiness, k=10 — are on-screen neighbours real neighbours? (higher better)",
    "sep2d": "3-fold logistic AUC in the plane — are the two classes visibly apart? (higher better)",
    "score_read": "kNN readout of the model's score from the picture (higher better)",
    "rash_read": "kNN readout of model-disagreement from the picture (higher better)",
    "recon": "mean |x - decode(encode(x))| — decoder error (LOWER better)",
    "rt": "round-trip drift of the 2-D point, relative to spread (LOWER better)",
    "score_inv": "Spearman(score, score of the decoded point) (higher better)",
    "rash_inv": "Spearman(disagreement, disagreement of the decoded point) (higher better)",
    "fit_s": "seconds to fit",
}
